"""Private fixed-command service handoff; never a learner/broker tool.

The daemon acquires the existing construction maintenance locks itself. Start
it outside the old maintenance guardian. RPC is token-authenticated, same-UID,
and cannot supply commands: only the immutable prepared command can execute.
"""
from __future__ import annotations
import argparse
import ctypes
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import secrets
import signal
import socket
import struct
import subprocess
import sys
import time

try:
    from . import operation_lease as lease
except ImportError:
    import operation_lease as lease


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def identity(pid):
    try:
        raw = Path(f'/proc/{int(pid)}/stat').read_text()
        fields = raw[raw.rfind(')')+2:].split()
        return {'pid': int(pid), 'starttime': fields[19], 'state': fields[0]}
    except (OSError, ValueError, IndexError):
        return None


def live(value):
    current = identity(value['pid']) if value else None
    return bool(current and current['starttime'] == value['starttime'] and current['state'] != 'Z')


def load_guard(path):
    spec = importlib.util.spec_from_file_location('persistent_trusted_guard', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def family(guard, root):
    rows = guard.snapshot()
    owned = {root}
    while True:
        expanded = owned | {pid for pid, row in rows.items() if row[0] in owned}
        if expanded == owned:
            return {pid: rows[pid] for pid in owned if pid in rows}
        owned = expanded


def listener_owned(guard, pid, port):
    inodes = set()
    for line in Path('/proc/net/tcp').read_text().splitlines()[1:]:
        fields = line.split()
        address, encoded_port = fields[1].split(':')
        if fields[3] == '0A' and int(encoded_port, 16) == port and address == '0100007F':
            inodes.add(fields[9])
    for child in family(guard, pid):
        try:
            for fd in Path(f'/proc/{child}/fd').iterdir():
                try:
                    target = os.readlink(fd)
                    if target.startswith('socket:[') and target[8:-1] in inodes:
                        return True
                except OSError:
                    pass
        except OSError:
            pass
    return False


def guardian(directory, nonce, expected_parent, descriptors):
    directory = Path(directory)
    config = json.loads((directory/'config.json').read_text())
    transaction = directory/nonce
    stopped = False
    def stop(signum, frame):
        nonlocal stopped
        stopped = True
    for sig in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
        signal.signal(sig, stop)
    libc = ctypes.CDLL(None, use_errno=True)
    if libc.prctl(36, 1, 0, 0, 0) or libc.prctl(1, signal.SIGTERM, 0, 0, 0):
        raise OSError('service guardian prctl failed')
    if os.getppid() != expected_parent:
        stopped = True
    guard = load_guard(config['guard'])
    service = None
    committed = False
    error = None
    launcher = None
    try:
        deadline = time.monotonic()+config['startup_seconds']
        if stopped:
            raise InterruptedError('parent disappeared before launch')
        with (transaction/'launcher.stdout').open('xb') as stdout, (transaction/'launcher.stderr').open('xb') as stderr:
            launcher = subprocess.Popen(config['command'], stdin=subprocess.DEVNULL, stdout=stdout, stderr=stderr)
            while launcher.poll() is None:
                if stopped or time.monotonic() >= deadline:
                    raise InterruptedError('startup interrupted or timed out')
                time.sleep(.02)
        if launcher.returncode:
            raise RuntimeError('fixed launcher failed: '+str(launcher.returncode))
        while not stopped and time.monotonic() < deadline:
            try:
                pid = int(Path(config['pid_file']).read_text().strip())
                candidate = identity(pid)
                if candidate and pid in family(guard, os.getpid()) and live(candidate) and listener_owned(guard, pid, config['listener_port']):
                    service = candidate
                    break
            except (OSError, ValueError):
                pass
            time.sleep(.02)
        if service is None:
            raise RuntimeError('PID/starttime/descendant/listener ownership not confirmed')
        # Keep only the explicitly registered service subtree. Existing external
        # services never enter this guardian's descendant set and are untouched.
        cleanup_deadline = time.monotonic()+5
        while True:
            rows = family(guard, os.getpid())
            allowed = set(family(guard, service['pid'])) | {os.getpid()}
            extras = {pid: row for pid, row in rows.items() if pid not in allowed and row[2] != 'Z'}
            if not extras:
                break
            for pid, row in extras.items():
                current = guard.snapshot().get(pid)
                if current and current[1] == row[1]:
                    try:
                        os.kill(pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
            if time.monotonic() >= cleanup_deadline:
                raise RuntimeError('unregistered descendants did not clean')
            time.sleep(.02)
        receipt = {'schema': 'persistent-service-owner/v1', 'status': 'prepared', 'nonce': nonce,
            'service': service, 'guardian': identity(os.getpid()), 'boot_id': lease.boot_id(),
            'config_sha256': sha(directory/'config.json'), 'listener_port': config['listener_port'],
            'ownership': 'explicit service PID and its descendants only', 'created_at_ns': time.time_ns()}
        lease.atomic_json(transaction/'owner.json', receipt)
        while not (transaction/'commit').exists():
            if stopped or time.monotonic() >= deadline or not live(service):
                raise InterruptedError('handoff not committed')
            time.sleep(.02)
        # This durable commit is an explicit ownership transfer, not a claim
        # that the live service was cleaned. A stale operation claim remains
        # fail-closed unless the daemon confirms this exact owner receipt.
        if stopped or not live(service):
            raise InterruptedError('handoff interrupted before durable commit')
        receipt['status'] = 'handed_off'
        receipt['committed_at_ns'] = time.time_ns()
        lease.atomic_json(transaction/'owner.json', receipt)
        committed = True
        libc.prctl(1, 0, 0, 0, 0)
        for fd in descriptors:
            os.close(fd)
        while not stopped and live(service):
            time.sleep(.05)
    except BaseException as failure:
        error = type(failure).__name__+': '+str(failure)
    finally:
        guard.terminate_owned()
        lease.atomic_json(transaction/'cleanup.json', {'status': 'cleaned', 'owned_processes_remaining': 0,
            'supervisor_pid': os.getpid(), 'nonce': nonce, 'service': service,
            'committed': committed, 'error': error, 'cleaned_at_ns': time.time_ns()})


def prepared_config(directory):
    directory = Path(directory).resolve()
    registration = json.loads((directory/'registration.json').read_text())
    for name, expected in registration['files'].items():
        if sha(directory/name) != expected:
            raise ValueError('prepared service manager bytes changed: '+name)
    return directory, json.loads((directory/'config.json').read_text())


def client_alive(connection):
    try:
        return connection.recv(1, socket.MSG_PEEK | socket.MSG_DONTWAIT) != b''
    except BlockingIOError:
        return True


def owned_receipt(directory):
    pointer = directory/'current.json'
    if not pointer.exists():
        return None
    return json.loads((directory/json.loads(pointer.read_text())['nonce']/'owner.json').read_text())


def operation(directory, config, request, connection):
    locks = Path(config['lease_directory'])
    admission = os.open(locks/'admission.lock', os.O_CREAT | os.O_RDWR, 0o600)
    active = os.open(locks/'operation.lock', os.O_CREAT | os.O_RDWR, 0o600)
    child = None
    claim = None
    claim_path = locks/'active.json'
    try:
        wait_seconds = float(request.get('wait_seconds', 0))
        if not 0 <= wait_seconds <= 3600:
            raise ValueError('finite wait_seconds in [0,3600] required')
        deadline = time.monotonic()+wait_seconds
        lease.lock(admission, deadline, lambda: not client_alive(connection))
        lease.lock(active, deadline, lambda: not client_alive(connection))
        if claim_path.exists():
            old = json.loads(claim_path.read_text())
            transferred = owned_receipt(directory)
            confirmed_handoff = (transferred and transferred['status'] == 'handed_off'
                and transferred['nonce'] == old.get('nonce')
                and transferred['guardian']['pid'] == old.get('supervisor_pid')
                and transferred['boot_id'] == lease.boot_id()
                and transferred['config_sha256'] == sha(directory/'config.json')
                and live(transferred['guardian']) and live(transferred['service']))
            if not lease.receipt_valid(old) and not confirmed_handoff:
                raise lease.LeaseBusy('legacy/current operation cleanup unconfirmed')
            claim_path.unlink()
        current = owned_receipt(directory)
        if request['operation'] == 'stop':
            if current:
                cleanup = directory/current['nonce']/'cleanup.json'
                if live(current['guardian']):
                    os.kill(current['guardian']['pid'], signal.SIGTERM)
                elif not cleanup.exists():
                    raise RuntimeError('registered guardian lost without cleanup receipt; stop unconfirmed')
                stop_deadline = time.monotonic()+20
                while not cleanup.exists() and time.monotonic() < stop_deadline:
                    time.sleep(.02)
                cleanup_claim = {'receipt': str(cleanup), 'nonce': current['nonce'],
                                 'supervisor_pid': current['guardian']['pid']}
                if not lease.receipt_valid(cleanup_claim) or live(current['service']):
                    raise RuntimeError('registered service cleanup unconfirmed')
            return {'status': 'stopped', 'owner': current}
        if current and live(current['service']):
            if live(current['guardian']):
                return {'status': 'already_handed_off', 'owner': current}
            raise RuntimeError('service live but registered guardian lost; independent cleanup required')
        nonce = secrets.token_hex(16)
        transaction = directory/nonce
        transaction.mkdir(mode=0o700)
        claim = {'kind': 'maintenance', 'nonce': nonce, 'receipt': str(transaction/'cleanup.json'),
                 'supervisor_pid': None, 'lease_pid': os.getpid(), 'explicit_service_handoff': str(directory)}
        lease.atomic_json(claim_path, claim)
        child = subprocess.Popen([sys.executable, str(directory/'manager.py'), 'guardian', '--directory', str(directory),
            '--nonce', nonce, '--expected-parent', str(os.getpid()), '--fd', str(admission), '--fd', str(active)],
            pass_fds=(admission, active), start_new_session=True, stdin=subprocess.DEVNULL)
        claim['supervisor_pid'] = child.pid
        lease.atomic_json(claim_path, claim)
        owner_path = transaction/'owner.json'
        while child.poll() is None and not owner_path.exists():
            if not client_alive(connection):
                raise InterruptedError('client interrupted before handoff')
            time.sleep(.02)
        if not owner_path.exists() or not client_alive(connection):
            raise RuntimeError('service ownership preparation failed/interrupted')
        lease.atomic_json(directory/'current.json', {'nonce': nonce})
        (transaction/'commit').touch()
        while child.poll() is None:
            owner = json.loads(owner_path.read_text())
            if owner['status'] == 'handed_off':
                claim_path.unlink()
                return {'status': 'handed_off', 'owner': owner}
            time.sleep(.02)
        raise RuntimeError('guardian exited before handoff')
    except BaseException:
        if child is not None and child.poll() is None:
            child.send_signal(signal.SIGTERM)
            child.wait(timeout=20)
        if claim and lease.receipt_valid(claim):
            claim_path.unlink(missing_ok=True)
        raise
    finally:
        os.close(active)
        os.close(admission)


def serve(directory):
    directory, config = prepared_config(directory)
    path = directory/'control.sock'
    if path.exists():
        raise RuntimeError('control socket already exists; verify owner before removal')
    token = (directory/'token').read_text().strip()
    with socket.socket(socket.AF_UNIX) as server:
        server.bind(str(path)); os.chmod(path, 0o600); server.listen(4)
        lease.atomic_json(directory/'daemon.json', {'daemon': identity(os.getpid()), 'boot_id': lease.boot_id(),
            'config_sha256': sha(directory/'config.json')})
        while True:
            connection, _ = server.accept()
            with connection:
                try:
                    _, uid, _ = struct.unpack('3i', connection.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12))
                    connection.settimeout(5)
                    data = b''
                    while b'\n' not in data and len(data) < 65536:
                        part = connection.recv(4096)
                        if not part: raise ValueError('incomplete request')
                        data += part
                    request = json.loads(data.split(b'\n', 1)[0])
                    if uid != os.getuid() or not secrets.compare_digest(str(request.pop('token', '')), token):
                        raise PermissionError('management authentication rejected')
                    if set(request)-{'operation', 'wait_seconds'} or request.get('operation') not in ('start', 'stop', 'status'):
                        raise ValueError('only prepared service lifecycle operations permitted')
                    prepared_config(directory)
                    connection.setblocking(True)
                    if request['operation'] == 'status':
                        owner = owned_receipt(directory)
                        result = {'status': 'owner_status', 'owner': owner,
                                  'service_alive': bool(owner and live(owner['service'])),
                                  'guardian_alive': bool(owner and live(owner['guardian']))}
                    else:
                        result = operation(directory, config, request, connection)
                    connection.sendall(json.dumps(result).encode()+b'\n')
                except BaseException as error:
                    try: connection.sendall(json.dumps({'status': 'error', 'error': type(error).__name__+': '+str(error)}).encode()+b'\n')
                    except OSError: pass


def rpc(directory, operation_name, wait_seconds=0, token=None):
    directory = Path(directory).resolve()
    token = (directory/'token').read_text().strip() if token is None else token
    with socket.socket(socket.AF_UNIX) as connection:
        connection.connect(str(directory/'control.sock'))
        connection.sendall(json.dumps({'token': token, 'operation': operation_name, 'wait_seconds': wait_seconds}).encode()+b'\n')
        response = b''
        while b'\n' not in response:
            value = connection.recv(65536)
            if not value: raise RuntimeError('manager disconnected; inspect durable owner receipt')
            response += value
    return json.loads(response.split(b'\n', 1)[0])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('operation', choices=('prepare', 'serve', 'start-daemon', 'start', 'stop', 'status', 'guardian'))
    parser.add_argument('--directory', required=True)
    parser.add_argument('--lease-directory')
    parser.add_argument('--guard')
    parser.add_argument('--pid-file')
    parser.add_argument('--listener-port', type=int)
    parser.add_argument('--startup-seconds', type=float, default=30)
    parser.add_argument('--wait-seconds', type=float, default=0)
    parser.add_argument('--nonce')
    parser.add_argument('--expected-parent', type=int)
    parser.add_argument('--fd', type=int, action='append', default=[])
    args, command = parser.parse_known_args()
    args.command = command
    directory = Path(args.directory).resolve()
    if args.operation == 'prepare':
        command = args.command[1:] if args.command[:1] == ['--'] else args.command
        if not command or not args.pid_file or not args.guard or not args.lease_directory or not args.listener_port:
            parser.error('prepare needs fixed command, PID file, guard, lease directory and listener port')
        if not 1 <= args.listener_port <= 65535 or not 0 < args.startup_seconds <= 3600:
            parser.error('valid listener port and finite startup budget required')
        directory.mkdir(parents=True, mode=0o700, exist_ok=False)
        (directory/'process_guard.py').write_bytes(Path(args.guard).read_bytes())
        config = {'command': command, 'pid_file': str(Path(args.pid_file).resolve()), 'listener_port': args.listener_port,
            'guard': str(directory/'process_guard.py'), 'original_guard_source': str(Path(args.guard).resolve()),
            'lease_directory': str(Path(args.lease_directory).resolve()),
            'startup_seconds': args.startup_seconds}
        lease.atomic_json(directory/'config.json', config)
        (directory/'manager.py').write_bytes(Path(__file__).read_bytes())
        (directory/'operation_lease.py').write_bytes(Path(lease.__file__).read_bytes())
        token_fd = os.open(directory/'token', os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(token_fd, 'w') as stream: stream.write(secrets.token_hex(32))
        lease.atomic_json(directory/'registration.json', {'files': {name: sha(directory/name) for name in ('config.json','manager.py','operation_lease.py','process_guard.py')}})
        print(json.dumps({'status': 'prepared', 'directory': str(directory), 'command_sha256': hashlib.sha256(json.dumps(command).encode()).hexdigest()}))
    elif args.operation == 'guardian':
        guardian(directory, args.nonce, args.expected_parent, args.fd)
    elif args.operation == 'serve':
        serve(directory)
    elif args.operation == 'start-daemon':
        prepared_config(directory)
        with (directory/'daemon.stdout').open('ab') as stdout, (directory/'daemon.stderr').open('ab') as stderr:
            child = subprocess.Popen([sys.executable, str(directory/'manager.py'), 'serve', '--directory', str(directory)],
                start_new_session=True, stdin=subprocess.DEVNULL, stdout=stdout, stderr=stderr)
        deadline = time.monotonic()+10
        while child.poll() is None and not (directory/'daemon.json').exists() and time.monotonic()<deadline: time.sleep(.02)
        if not (directory/'daemon.json').exists(): raise RuntimeError('daemon startup failed; inspect fixed logs')
        print((directory/'daemon.json').read_text())
    else:
        result = rpc(directory, args.operation, args.wait_seconds)
        print(json.dumps(result))
        return 1 if result['status'] == 'error' else 0


if __name__ == '__main__':
    raise SystemExit(main())
