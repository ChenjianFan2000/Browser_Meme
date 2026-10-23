"""One generic CLI lifecycle integration, including stale-PID signal refusal."""
import argparse
import json
from pathlib import Path
import signal
import socket
import subprocess
import sys
import tempfile
import unittest


def cli(*args):
    result = subprocess.run([sys.executable, '-m', 'harness.replica.service', *map(str,args)],
                            capture_output=True, text=True, timeout=20)
    return {'returncode':result.returncode, 'stdout':result.stdout, 'stderr':result.stderr,
            'result':json.loads(result.stdout) if result.stdout.strip().startswith('{') else None}


def start_fixture(root):
    root.mkdir(parents=True, exist_ok=False)
    bundle = root / 'generic-bundle'
    bundle.mkdir()
    (bundle / 'index.html').write_text('<!doctype html><title>Managed generic fixture</title><main>Ready</main>')
    (bundle / 'app.js').write_text('window.genericFixture=true;')
    with socket.socket() as listener:
        listener.bind(('127.0.0.1',0))
        port = listener.getsockname()[1]
    result = cli('start', '--directory', bundle, '--port', port, '--out', root / 'service')
    (root / 'start-cli.json').write_text(json.dumps(result, indent=2))
    if result['returncode']:
        raise AssertionError(result)


def check_started(root):
    """May run in a different exec channel from the start CLI to check persistence."""
    root = Path(root).resolve()
    service = root / 'service'
    records = {'start':json.loads((root / 'start-cli.json').read_text())}
    bystander = subprocess.Popen([sys.executable,'-c','import time;time.sleep(90)'], stdin=subprocess.DEVNULL,
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
    try:
        records['independent_process_health'] = cli('health', '--out', service)
        assert records['independent_process_health']['result']['healthy']
        receipt = json.loads((service / 'process-receipt.json').read_text())
        # Stale receipt: current PID but a different kernel starttime. No signal.
        for label, changes in [('stale-starttime', {'starttime':str(int(receipt['starttime'])+1)}),
                                ('wrong-command', {'command':receipt['command']+['NOT-THE-REGISTERED-COMMAND']}),
                                ('bystander-pid', {'pid':bystander.pid})]:
            alternate = root / label
            alternate.mkdir()
            (alternate / 'process-receipt.json').write_text(json.dumps({**receipt,**changes}))
            result = cli('stop','--out',alternate)
            records[label] = result
            assert result['returncode'] == 1
            assert result['result']['reason'] == 'identity_mismatch_refused'
            assert result['result']['signaled'] is False
            assert bystander.poll() is None
            assert cli('health','--out',service)['result']['healthy']
        bundle = root / 'generic-bundle'
        (bundle / 'app.js').write_text('window.genericFixture=false;')
        (bundle / 'added.json').write_text('{}')
        records['tamper'] = cli('health','--out',service)
        result = records['tamper']['result']
        assert records['tamper']['returncode'] == 1
        assert result['alive'] and result['owns_listener'] and result['http']['ready']
        assert not result['bundle_unchanged']
        assert result['changed_files'] == ['added.json','app.js']
        records['stop'] = cli('stop','--out',service)
        assert records['stop']['result']['stopped'] and records['stop']['result']['signaled']
        records['repeated_stop'] = cli('stop','--out',service)
        assert records['repeated_stop']['result']['stopped']
        assert not records['repeated_stop']['result']['signaled']
        records['after_stop'] = cli('health','--out',service)
        assert not records['after_stop']['result']['alive']
        records['passed'] = True
        records['no_model_calls'] = True
        records['fixture_only'] = True
        (root / 'validation.json').write_text(json.dumps(records,indent=2)+'\n')
        return records
    finally:
        bystander.terminate()
        bystander.wait(timeout=5)
        cli('stop','--out',service)


class ServiceTest(unittest.TestCase):
    def test_detached_cli_health_manifest_and_identity_safe_stop(self):
        scratch=Path('work/replica-pilot/service-tests')
        scratch.mkdir(parents=True,exist_ok=True)
        with tempfile.TemporaryDirectory(dir=scratch) as temporary:
            root=Path(temporary)/'probe'
            start_fixture(root)
            self.assertTrue(check_started(root)['passed'])


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check-started',help='Check own generic fixture previously started in a separate exec channel')
    args,rest=parser.parse_known_args()
    if args.check_started:
        record=check_started(args.check_started)
        print(json.dumps({'passed':record['passed'],'validation':str(Path(args.check_started)/'validation.json')}))
    else:
        unittest.main(argv=[sys.argv[0],*rest])
