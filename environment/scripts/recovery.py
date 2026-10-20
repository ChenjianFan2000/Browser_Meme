"""Bounded download retries, live progress, and verified atomic publication."""
import argparse
import errno
import hashlib
import json
import os
from pathlib import Path
import selectors
import signal
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
STORAGE_ERRORS = {errno.EIO, errno.ENODEV, errno.ENXIO, errno.EROFS, errno.ENOSPC, errno.ESTALE}


class StorageError(RuntimeError):
    pass


def digest(path):
    value = hashlib.sha256()
    updated = time.monotonic()
    total = 0
    with Path(path).open('rb') as stream:
        while data := stream.read(1024 * 1024):
            value.update(data)
            total += len(data)
            if time.monotonic() - updated >= 15:
                announce(f'Checking {Path(path).name}: {total} bytes')
                updated = time.monotonic()
    return value.hexdigest()


def atomic_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    pending = path.with_name(path.name + '.pending')
    with pending.open('w', encoding='utf-8') as stream:
        json.dump(value, stream, indent=2)
        stream.write('\n')
        stream.flush()
        os.fsync(stream.fileno())
    pending.replace(path)


def state(label, status, **details):
    atomic_json(os.environ.get('BM_DOWNLOAD_STATE', ROOT / '.runtime/logs/download-state.json'),
                dict(stage=label, status=status, time=time.strftime('%Y-%m-%dT%H:%M:%S%z'), **details))


def announce(message):
    print(f'[{time.strftime("%H:%M:%S")}] {message}', flush=True)


def quarantine(path):
    path = Path(path)
    moved = path.with_name(f'{path.name}.rejected-{time.time_ns()}')
    path.replace(moved)
    announce(f'Kept rejected data for inspection: {moved.name}')


def snapshot(paths):
    size = modified = 0
    for path in map(Path, paths):
        if path.is_dir():
            entries = path.rglob('*')
        else:
            entries = [path]
        for entry in entries:
            try:
                if entry.is_file():
                    info = entry.stat()
                    size += info.st_size
                    modified = max(modified, info.st_mtime_ns)
            except FileNotFoundError:
                pass  # A downloader can rename a completed temporary file.
    return size, modified


def stop_child(process):
    if process.poll() is None:
        os.killpg(process.pid, signal.SIGTERM)
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait(timeout=5)


def run(command, label, *, attempts=1, timeout=7200, idle_timeout=300, watch=(), env=None):
    """Heartbeat is informational; only child output/file growth resets the idle timer."""
    for attempt in range(1, attempts + 1):
        announce(f'{label}: attempt {attempt}/{attempts}')
        state(label, 'running', attempt=attempt, attempts=attempts)
        previous = snapshot(watch)
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                   bufsize=0, start_new_session=True, env=env)
        selector = selectors.DefaultSelector()
        selector.register(process.stdout, selectors.EVENT_READ)
        started = progress = heartbeat = time.monotonic()
        last_snapshot = started
        timed_out = False
        try:
            while selector.get_map():
                for key, _ in selector.select(timeout=1):
                    data = os.read(key.fd, 65536)
                    if not data:
                        selector.unregister(key.fileobj)
                        continue
                    sys.stdout.write(data.decode('utf-8', errors='replace').replace('\r', '\n'))
                    sys.stdout.flush()
                    progress = time.monotonic()
                now = time.monotonic()
                if now - last_snapshot >= 5:
                    current = snapshot(watch)
                    if current != previous:
                        previous, progress = current, now
                    last_snapshot = now
                if now - heartbeat >= 15:
                    # Force a real G-drive lookup, including on processes stalled in kernel I/O.
                    (ROOT / 'AGENTS.md').stat()
                    announce(f'{label}: running {int(now-started)}s; '
                             f'no progress {int(now-progress)}s; watched {previous[0]} bytes')
                    state(label, 'running', attempt=attempt, elapsed_seconds=int(now-started),
                          idle_seconds=int(now-progress), watched_bytes=previous[0])
                    heartbeat = now
                if now - started >= timeout or now - progress >= idle_timeout:
                    announce(f'{label}: timeout; stopping this attempt and retaining partial files')
                    timed_out = True
                    stop_child(process)
                    break
            code = process.wait(timeout=5)
        finally:
            stop_child(process)
            selector.close()
            process.stdout.close()
        if code == 0 and not timed_out:
            state(label, 'complete', attempt=attempt)
            return 0
        code = 124 if timed_out else code
        if code == 75:
            return code  # Let the Windows supervisor recover the storage/WSL layer.
        state(label, 'retrying' if attempt < attempts else 'failed', exit_code=code, attempt=attempt)
        if attempt < attempts:
            delay = min(float(os.environ.get('BM_RETRY_DELAY', '5')) * 2**(attempt-1), 60)
            announce(f'{label}: exit {code}; retry in {delay:g}s')
            time.sleep(delay)
    return code


def fetch(target, urls, expected, *, attempts=None):
    target = Path(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    attempts = attempts or int(os.environ.get('BM_DOWNLOAD_ATTEMPTS', '6'))
    if target.exists():
        if digest(target) == expected:
            announce(f'Cached and verified: {target.name}')
            return
        quarantine(target)
    partial = target.with_name(target.name + '.part')
    for attempt in range(attempts):
        # Covers a crash after the last byte, but before checksum/rename.
        if partial.exists() and digest(partial) == expected:
            partial.replace(target)
            announce(f'Completed partial verified: {target.name}')
            return
        url = urls[attempt % len(urls)]
        offset = partial.stat().st_size if partial.exists() else 0
        announce(f'{target.name}: resume at {offset} bytes; source {url}')
        limit = int(os.environ.get('BM_FILE_ATTEMPT_TIMEOUT', '900'))
        headers = partial.with_name(partial.name + '.headers')
        code = run(['curl', '--fail', '--location', '--silent', '--show-error',
                    '--connect-timeout', '10', '--max-time', str(limit),
                    '--speed-limit', '1024', '--speed-time', '60', '--continue-at', '-',
                    '--dump-header', str(headers), '--output', str(partial), url], target.name,
                   timeout=limit+10, idle_timeout=90, watch=[partial])
        if code in (23, 75):
            raise StorageError(f'Cannot write {partial}; check drive connection/free space.')
        if partial.exists() and digest(partial) == expected:
            partial.replace(target)
            state(target.name, 'complete', sha256=expected)
            return
        range_rejected = headers.exists() and any(
            line.startswith('HTTP/') and line.split()[1:2] == ['416']
            for line in headers.read_text(errors='replace').splitlines())
        if partial.exists() and (code in (0, 33, 36) or range_rejected):
            # Range unsupported, changed object, or a bad completed body.
            # Retain the bytes separately; the next attempt starts clean.
            quarantine(partial)
        if attempt + 1 < attempts:
            delay = min(float(os.environ.get('BM_RETRY_DELAY', '5')) * 2**attempt, 60)
            announce(f'{target.name}: not verified; next source/attempt in {delay:g}s')
            time.sleep(delay)
    raise RuntimeError(f'{target.name}: exhausted {attempts} attempts; rerun to resume.')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--label', required=True)
    parser.add_argument('--attempts', type=int, default=3)
    parser.add_argument('--timeout', type=int, default=7200)
    parser.add_argument('--idle-timeout', type=int, default=300)
    parser.add_argument('--watch', action='append', default=[])
    parser.add_argument('command', nargs=argparse.REMAINDER)
    args = parser.parse_args()
    command = args.command[1:] if args.command[:1] == ['--'] else args.command
    if not command:
        parser.error('A command is required after --')
    return run(command, args.label, attempts=args.attempts, timeout=args.timeout,
               idle_timeout=args.idle_timeout, watch=args.watch)


def install_signal_handlers():
    def cancelled(signum, frame):
        raise KeyboardInterrupt
    signal.signal(signal.SIGTERM, cancelled)


if __name__ == '__main__':
    install_signal_handlers()
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        announce('Cancelled; verified downloads and partial files retained.')
        raise SystemExit(130)
    except (OSError, StorageError) as error:
        announce(str(error))
        raise SystemExit(75 if isinstance(error, StorageError) or error.errno in STORAGE_ERRORS else 1)
