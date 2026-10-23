"""Actual TCP process handoff/interruption, never a browser or target site."""
import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import sys
import tempfile
import time
import unittest

from harness.replica import operation_lease, persistent_service as manager

MODULE = Path(manager.__file__).resolve()
GUARD = MODULE.parent/'runtime/process_guard.py'


def wait_for(predicate, seconds=10):
    deadline = time.monotonic()+seconds
    while time.monotonic()<deadline:
        if predicate(): return
        time.sleep(.02)
    raise AssertionError('missing real subprocess evidence')


class PersistentServiceTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.locks = self.root/'locks'; self.locks.mkdir()
        self.daemons = []
        self.clients = []

    def tearDown(self):
        for directory, daemon in self.daemons:
            if daemon.poll() is None:
                try: manager.rpc(directory, 'stop', 2)
                except Exception: pass
                daemon.kill(); daemon.wait(timeout=5)
        for child in self.clients:
            if child.poll() is None: child.kill()
            child.communicate(timeout=5)
        self.temp.cleanup()

    def setup_manager(self, name, pending=False):
        directory = self.root/name
        pidfile = self.root/(name+'.pid')
        roguefile = self.root/(name+'-rogue.pid')
        with socket.socket() as selector:
            selector.bind(('127.0.0.1', 0)); port = selector.getsockname()[1]
        server = ('import os,pathlib,socket,time; s=socket.socket(); '
            f's.bind(("127.0.0.1",{port}));s.listen();pathlib.Path({str(pidfile)!r}).write_text(str(os.getpid())); '
            'time.sleep(60)')
        launcher = self.root/(name+'-launch.py')
        launcher.write_text('import subprocess,sys,pathlib,time\n'
            f'p=subprocess.Popen([sys.executable,"-c",{server!r}],start_new_session=True)\n'
            'rogue=subprocess.Popen([sys.executable,"-c","import time;time.sleep(60)"],start_new_session=True)\n'
            f'pathlib.Path({str(roguefile)!r}).write_text(str(rogue.pid))\n'+('time.sleep(60)\n' if pending else ''))
        prepared = subprocess.run([sys.executable, '-m', 'harness.replica.persistent_service', 'prepare',
            '--directory', str(directory), '--lease-directory', str(self.locks), '--guard', str(GUARD),
            '--pid-file', str(pidfile), '--listener-port', str(port), '--startup-seconds', '15', '--',
            sys.executable, str(launcher)], capture_output=True, text=True, timeout=5)
        self.assertEqual(prepared.returncode, 0, prepared.stderr)
        daemon = subprocess.Popen([sys.executable, str(directory/'manager.py'), 'serve', '--directory', str(directory)],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
        self.daemons.append((directory, daemon))
        wait_for(lambda: (directory/'daemon.json').exists())
        return directory, daemon, pidfile, roguefile

    def maintenance(self, assertion):
        command = [sys.executable, '-m', 'harness.replica.operation_lease', '--directory', str(self.locks),
            '--kind', 'maintenance', '--guard', str(GUARD), '--wait-seconds', '10', '--timeout-seconds', '5',
            '--', sys.executable, '-c', assertion]
        result = subprocess.run(command, capture_output=True, text=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_explicit_service_survives_maintenance_unregistered_child_dies(self):
        directory, _, pidfile, roguefile = self.setup_manager('persistent')
        denied = manager.rpc(directory, 'start', token='wrong-token')
        self.assertEqual(denied['status'], 'error')
        self.assertFalse(pidfile.exists())
        result = manager.rpc(directory, 'start', 1)
        self.assertEqual(result['status'], 'handed_off', result)
        owner = result['owner']; rogue = manager.identity(int(roguefile.read_text()))
        self.assertTrue(manager.live(owner['service']))
        self.assertFalse(rogue and manager.live(rogue))
        self.maintenance('pass')
        self.assertTrue(manager.live(owner['service']))
        stopped = manager.rpc(directory, 'stop', 1)
        self.assertEqual(stopped['status'], 'stopped', stopped)
        self.assertFalse(manager.live(owner['service']))
        print(json.dumps({'probe': 'persistent_handoff', 'owner': owner,
            'alive_after_later_maintenance': True, 'unregistered_child_alive': False,
            'cleanup': json.loads((directory/owner['nonce']/'cleanup.json').read_text())}), flush=True)

    def test_client_and_daemon_sigkill_before_commit_cleanup_under_lease(self):
        for killed in ('client', 'daemon'):
            with self.subTest(killed=killed):
                directory, daemon, pidfile, roguefile = self.setup_manager(killed, pending=True)
                client = subprocess.Popen([sys.executable, str(directory/'manager.py'), 'start', '--directory', str(directory)],
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True)
                self.clients.append(client)
                wait_for(pidfile.exists)
                service = manager.identity(int(pidfile.read_text())); rogue = manager.identity(int(roguefile.read_text()))
                self.assertTrue(manager.live(service))
                claim = json.loads((self.locks/'active.json').read_text())
                os.kill(client.pid if killed == 'client' else daemon.pid, signal.SIGKILL)
                # This runs only after inherited locks and verified cleanup have
                # settled. The assertion inspects kernel process identity live.
                assertion = ('from harness.replica.persistent_service import live; '
                    f'assert not live({service!r}); assert not live({rogue!r})')
                self.maintenance(assertion)
                cleanup = json.loads(Path(claim['receipt']).read_text())
                self.assertEqual(cleanup['owned_processes_remaining'], 0)
                self.assertFalse(cleanup['committed'])
                print(json.dumps({'probe': 'precommit_sigkill', 'killed': killed,
                    'service_alive_before_signal': True, 'service_alive_at_maintenance': manager.live(service),
                    'cleanup': cleanup}), flush=True)

    def test_lost_guardian_cannot_falsely_report_service_stopped(self):
        directory, _, _, _ = self.setup_manager('lost-guardian')
        result = manager.rpc(directory, 'start', 1)
        owner = result['owner']
        try:
            os.kill(owner['guardian']['pid'], signal.SIGKILL)
            wait_for(lambda: not manager.live(owner['guardian']))
            self.assertTrue(manager.live(owner['service']))
            refused = manager.rpc(directory, 'stop', 1)
            self.assertEqual(refused['status'], 'error')
            self.assertIn('cleanup receipt', refused['error'])
            print(json.dumps({'probe': 'lost_guardian_fail_closed',
                'registered_service_still_alive': manager.live(owner['service']), 'stop_result': refused}), flush=True)
        finally:
            # The test owns this exact recorded process identity. This is an
            # explicit fixture cleanup, never a forged successful owner receipt.
            if manager.live(owner['service']): os.kill(owner['service']['pid'], signal.SIGKILL)
            wait_for(lambda: not manager.live(owner['service']))


if __name__ == '__main__': unittest.main()
