"""Persistent local replica service management; never starts models or resets sites.

Start creates a new private management directory with immutable bundle manifest
and process identity receipt. Health checks bytes and the actual registered
listener. Stop signals only that registered process through a Linux pidfd.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
from urllib.request import ProxyHandler, build_opener

ROOT = Path(__file__).resolve().parents[2]


def _json(path, value, *, new=False):
    path = Path(path)
    if new:
        with path.open('x', encoding='utf-8') as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
            stream.write('\n')
    else:
        temporary = path.with_name(path.name + '.tmp-' + str(os.getpid()))
        with temporary.open('x', encoding='utf-8') as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
            stream.write('\n')
        temporary.replace(path)


def _manifest(directory):
    files, invalid = {}, []
    for path in sorted(Path(directory).rglob('*')):
        relative = str(path.relative_to(directory))
        if path.is_symlink():
            invalid.append(relative + ':symlink')
        elif path.is_file():
            digest = hashlib.sha256()
            with path.open('rb') as stream:
                for block in iter(lambda: stream.read(1024 * 1024), b''):
                    digest.update(block)
            files[relative] = digest.hexdigest()
        elif not path.is_dir():
            invalid.append(relative + ':nonregular')
    return files, invalid


def _process(pid):
    try:
        root = Path('/proc') / str(int(pid))
        raw = (root / 'stat').read_text()
        fields = raw[raw.rfind(')') + 2:].split()
        command = [part.decode('utf-8', errors='surrogateescape')
                   for part in (root / 'cmdline').read_bytes().split(b'\0') if part]
        return {'pid': int(pid), 'starttime': fields[19], 'state': fields[0],
                'command': command, 'cwd': os.readlink(root / 'cwd')}
    except (OSError, ValueError, IndexError):
        return None


def _identity(receipt):
    current = _process(receipt['pid'])
    matches = bool(current and current['starttime'] == receipt['starttime']
                   and current['command'] == receipt['command'] and current['cwd'] == receipt['cwd'])
    return current, matches


def _owns_listener(pid, port):
    """Verify endpoint socket inode belongs to this process, not a port bystander."""
    try:
        sockets = set()
        for fd in (Path('/proc') / str(pid) / 'fd').iterdir():
            try:
                target = os.readlink(fd)
                if target.startswith('socket:['):
                    sockets.add(target[8:-1])
            except OSError:
                continue
        table = (Path('/proc') / str(pid) / 'net/tcp').read_text().splitlines()[1:]
        return any(row[3] == '0A' and row[1] == '0100007F:' + format(int(port), '04X') and row[9] in sockets
                   for row in (line.split() for line in table))
    except (OSError, ValueError, IndexError):
        return False


def health(out):
    """Check registered identity, all bundle files, added files and local HTTP health."""
    out = Path(out).resolve()
    receipt = json.loads((out / 'process-receipt.json').read_text())
    registered = json.loads((out / 'bundle-manifest.json').read_text())
    directory = Path(receipt['directory'])
    try:
        actual, invalid = _manifest(directory)
        changed = sorted(name for name in set(actual) | set(registered['files'])
                         if actual.get(name) != registered['files'].get(name))
        if not directory.is_dir():
            invalid.append(':bundle_directory_missing')
    except OSError as error:
        actual, changed, invalid = {}, [], [type(error).__name__]
    current, matches = _identity(receipt)
    alive = bool(matches and current['state'] not in {'Z', 'X'})
    owns = alive and _owns_listener(receipt['pid'], receipt['port'])
    endpoint = {'ready': False, 'status_code': None, 'error': None}
    if owns:
        try:
            opener = build_opener(ProxyHandler({}))
            with opener.open(receipt['origin'] + '/__replica_health__', timeout=2) as response:
                value = json.loads(response.read(8192))
                endpoint = {'ready': response.status == 200 and value == {'status':'ready', 'kind':'static_browser_app'},
                            'status_code': response.status, 'error': None}
        except Exception as error:
            endpoint['error'] = type(error).__name__
    result = {'healthy': bool(alive and owns and endpoint['ready'] and not changed and not invalid),
              'pid': receipt['pid'], 'identity_matches': matches, 'alive': alive, 'owns_listener': owns,
              'origin': receipt['origin'], 'bundle_unchanged': not changed and not invalid,
              'changed_files': changed, 'invalid_files': invalid, 'http': endpoint,
              'checked_at_ns': time.time_ns()}
    _json(out / 'health.json', result)
    return result


def _signal_registered(receipt, signum):
    if not hasattr(os, 'pidfd_open') or not hasattr(signal, 'pidfd_send_signal'):
        raise RuntimeError('Linux pidfd support required for identity-safe stop')
    try:
        descriptor = os.pidfd_open(receipt['pid'])
    except ProcessLookupError:
        return False
    try:
        current, matches = _identity(receipt)
        if not matches or current['state'] in {'Z', 'X'}:
            return False
        signal.pidfd_send_signal(descriptor, signum)
        return True
    finally:
        os.close(descriptor)


def stop(out, *, timeout=5):
    """Stop only the registered PID when starttime, argv and cwd still match.

    A mismatched live PID is never signaled, including if a PID has been reused.
    """
    out = Path(out).resolve()
    receipt = json.loads((out / 'process-receipt.json').read_text())
    current, matches = _identity(receipt)
    result = {'stopped': False, 'signaled': False, 'pid': receipt['pid'], 'identity_matches': matches,
              'reason': None, 'checked_at_ns': time.time_ns()}
    if current is None or current['state'] in {'Z', 'X'}:
        result.update(stopped=True, reason='already_exited')
    elif not matches:
        result['reason'] = 'identity_mismatch_refused'
    else:
        result['signaled'] = _signal_registered(receipt, signal.SIGTERM)
        deadline = time.monotonic() + float(timeout)
        while time.monotonic() < deadline:
            current, matches = _identity(receipt)
            if current is None or current['state'] in {'Z', 'X'} or not matches:
                break
            time.sleep(.05)
        if current and matches and current['state'] not in {'Z', 'X'}:
            _signal_registered(receipt, signal.SIGKILL)
            deadline = time.monotonic() + 2
            while time.monotonic() < deadline:
                current, matches = _identity(receipt)
                if current is None or current['state'] in {'Z', 'X'} or not matches:
                    break
                time.sleep(.05)
        # The old registered process has exited if this PID now belongs to a
        # different process. That replacement has not been signaled.
        result.update(stopped=current is None or current['state'] in {'Z', 'X'} or not matches,
                      reason='registered_process_exited' if current is None or current['state'] in {'Z', 'X'} or not matches else 'termination_unconfirmed')
    _json(out / 'stop.json', result)
    return result


def start(directory, port, out, *, entry='index.html', startup_timeout=10):
    """Launch a detached static server and return after verified local readiness."""
    directory, out = Path(directory).resolve(strict=True), Path(out).resolve()
    if not directory.is_dir():
        raise ValueError('bundle must be a directory')
    if out == directory or directory in out.parents:
        raise ValueError('management output must be outside served bundle')
    relative = Path(entry)
    if relative.is_absolute() or '..' in relative.parts or not (directory / relative).is_file():
        raise ValueError('entry must be an existing bundle-relative file')
    port = int(port)
    if not 1 <= port <= 65535:
        raise ValueError('port must be between 1 and 65535')
    files, invalid = _manifest(directory)
    if invalid:
        raise ValueError('bundle has unsupported files: ' + ', '.join(invalid))
    out.mkdir(parents=True, mode=0o700, exist_ok=False)
    command = [sys.executable, '-m', 'harness.replica.server', '--directory', str(directory),
               '--port', str(port), '--entry', entry]
    _json(out / 'bundle-manifest.json', {'directory':str(directory), 'files':files, 'entry':entry,
                                       'recorded_at_ns':time.time_ns()}, new=True)
    with (out / 'stdout.log').open('xb') as stdout, (out / 'stderr.log').open('xb') as stderr:
        child = subprocess.Popen(command, cwd=ROOT, stdin=subprocess.DEVNULL,
                                 stdout=stdout, stderr=stderr, start_new_session=True, close_fds=True)
    # /proc/PID/cmdline can briefly be empty while exec installs the new image.
    # Wait for this directly owned child, without registering an incomplete argv.
    identity_deadline = time.monotonic() + min(2, float(startup_timeout))
    identity = None
    while time.monotonic() < identity_deadline:
        observed = _process(child.pid)
        if observed and observed['command'] == command and observed['cwd'] == str(ROOT):
            identity = observed
            break
        if child.poll() is not None:
            break
        time.sleep(.01)
    if identity is None:
        # The unreaped Popen child is ours; this is not a PID read from a stale
        # receipt. Reap it here so failed registration cannot orphan a service.
        if child.poll() is None:
            child.terminate()
            try:
                child.wait(timeout=2)
            except subprocess.TimeoutExpired:
                child.kill()
                child.wait(timeout=2)
        raise RuntimeError('new server process identity could not be registered')
    receipt = {**identity, 'directory':str(directory), 'port':port, 'origin':f'http://127.0.0.1:{port}',
               'entry':entry, 'recorded_at_ns':time.time_ns(), 'start_new_session':True,
               'stdin':'DEVNULL', 'stdout':str(out/'stdout.log'), 'stderr':str(out/'stderr.log')}
    _json(out / 'process-receipt.json', receipt, new=True)
    deadline = time.monotonic() + float(startup_timeout)
    while time.monotonic() < deadline:
        result = health(out)
        if result['healthy']:
            return {'started':True, 'out':str(out), 'receipt':str(out/'process-receipt.json'), **result}
        if child.poll() is not None:
            break
        time.sleep(.1)
    cleanup = stop(out)
    raise RuntimeError('replica server did not become healthy; inspect fixed logs; cleanup=' + str(cleanup['reason']))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='mode', required=True)
    command = commands.add_parser('start', help='Start detached static server; --out must be a new directory')
    command.add_argument('--directory', required=True)
    command.add_argument('--port', required=True, type=int)
    command.add_argument('--out', required=True)
    command.add_argument('--entry', default='index.html')
    for name in ('health', 'stop'):
        command = commands.add_parser(name, help='Check or stop only the process registered in --out')
        command.add_argument('--out', required=True)
    args = parser.parse_args()
    result = start(args.directory, args.port, args.out, entry=args.entry) if args.mode == 'start' else health(args.out) if args.mode == 'health' else stop(args.out)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    okay = result.get('started') if args.mode == 'start' else result.get('healthy') if args.mode == 'health' else result.get('stopped')
    raise SystemExit(0 if okay else 1)


if __name__ == '__main__':
    main()
