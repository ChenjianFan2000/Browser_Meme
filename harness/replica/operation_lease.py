"""Coordinator operation lease: serialize calls and exclude maintenance.

Lock descriptors stay open in the trusted subreaper until owned descendants
are cleaned. A persistent receipt claim closes the crash window if supervisors
are killed: an absent/invalid cleanup receipt blocks later work.
"""
from __future__ import annotations

import argparse
import ctypes
import fcntl
import importlib.util
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
import uuid


class LeaseBusy(RuntimeError):
    pass


class BudgetExhausted(RuntimeError):
    pass


def boot_id():
    return Path('/proc/sys/kernel/random/boot_id').read_text().strip()


def atomic_json(path, value):
    temporary = path.with_name(path.name + '.' + uuid.uuid4().hex + '.tmp')
    with temporary.open('x') as stream:
        json.dump(value, stream)
        stream.flush()
        os.fsync(stream.fileno())
    temporary.replace(path)


def receipt_valid(claim):
    try:
        path = Path(claim['receipt'])
        if path.is_symlink() or not isinstance(claim.get('supervisor_pid'), int):
            return False
        value = json.loads(path.read_text())
        return (value.get('status') == 'cleaned' and value.get('owned_processes_remaining') == 0
                and value.get('nonce') == claim['nonce']
                and value.get('supervisor_pid') == claim['supervisor_pid'])
    except (OSError, KeyError, TypeError, ValueError):
        return False


def lock(descriptor, deadline, interrupted=lambda: False):
    while True:
        if interrupted():
            raise InterruptedError('lease interrupted before dispatch')
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return
        except BlockingIOError:
            if time.monotonic() >= deadline:
                raise LeaseBusy('operation lease busy; no command dispatched')
            time.sleep(min(.02, max(0, deadline-time.monotonic())))


def run(directory, command, *, kind, guard, wait_seconds=0, timeout_seconds=300,
        expected_parent=None, stop_paths=(), deadline_ns=None, budget_boot_id=None):
    if kind not in ('browser-call', 'maintenance') or not command:
        raise ValueError('operation kind and nonempty command required')
    if not 0 <= wait_seconds < float('inf') or not 0 < timeout_seconds < float('inf'):
        raise ValueError('finite nonnegative wait and finite positive timeout required')
    if deadline_ns is not None and (not isinstance(deadline_ns, int) or deadline_ns <= 0 or not budget_boot_id):
        raise ValueError('monotonic deadline requires positive integer nanoseconds and boot identity')
    directory = Path(directory).resolve(strict=True)
    stopped = False
    def stop(signum, frame):
        nonlocal stopped
        stopped = True
    old_handlers = {sig: signal.signal(sig, stop) for sig in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP)}
    parent = os.getppid() if expected_parent is None else expected_parent
    libc = ctypes.CDLL(None, use_errno=True)
    if libc.prctl(1, signal.SIGTERM, 0, 0, 0) != 0:
        raise OSError(ctypes.get_errno(), 'lease parent-death setup failed')
    if os.getppid() != parent:
        stopped = True
    claim_path = directory/'active.json'
    admission = os.open(directory/'admission.lock', os.O_RDWR | os.O_CREAT | os.O_CLOEXEC, 0o600)
    active = os.open(directory/'operation.lock', os.O_RDWR | os.O_CREAT | os.O_CLOEXEC, 0o600)
    claim = None
    child = None
    started = time.monotonic()
    deadline = started + wait_seconds
    def budget_expired():
        return deadline_ns is not None and (budget_boot_id != boot_id() or time.monotonic_ns() >= deadline_ns)
    if deadline_ns is not None:
        deadline = min(deadline, deadline_ns / 1e9)
    def event(state, **extra):
        with (directory/'journal.jsonl').open('a') as stream:
            stream.write(json.dumps({'state': state, 'kind': kind, 'pid': os.getpid(),
                'time_ns': time.time_ns(), 'time_monotonic': time.monotonic(), **extra})+'\n')
            stream.flush()
    try:
        if budget_expired():
            raise BudgetExhausted('construction total wall deadline exhausted; no command dispatched')
        try:
            lock(admission, deadline, lambda: stopped)
        except LeaseBusy:
            if budget_expired():
                raise BudgetExhausted('construction total wall deadline exhausted while waiting')
            raise
        event('admission_acquired')
        # Maintenance retains admission while waiting and executing. Browser
        # calls release it once active, allowing maintenance to reserve next.
        try:
            lock(active, deadline, lambda: stopped)
        except LeaseBusy:
            if budget_expired():
                raise BudgetExhausted('construction total wall deadline exhausted while waiting')
            raise
        if stopped:
            raise InterruptedError('lease interrupted before dispatch')
        if any(Path(path).exists() for path in stop_paths):
            raise InterruptedError('STOP marker present; no command dispatched')
        if budget_expired():
            raise BudgetExhausted('construction total wall deadline exhausted; no command dispatched')
        if claim_path.exists():
            previous = json.loads(claim_path.read_text())
            if not receipt_valid(previous):
                raise LeaseBusy('previous operation cleanup unconfirmed; no command dispatched')
            event('previous_cleanup_confirmed', previous=previous)
            claim_path.unlink()
        if kind == 'browser-call':
            os.close(admission)
            admission = None
        nonce = uuid.uuid4().hex
        claim = {'kind': kind, 'nonce': nonce, 'receipt': str(directory/(nonce+'.cleanup.json')),
                 'supervisor_pid': None, 'lease_pid': os.getpid(), 'started_at_ns': time.time_ns(),
                 'command': list(command), 'timeout_seconds': timeout_seconds}
        operation_deadline_ns = time.monotonic_ns()+int(timeout_seconds*1e9)
        if deadline_ns is not None:
            operation_deadline_ns = min(operation_deadline_ns, deadline_ns)
        claim['operation_deadline_ns'] = operation_deadline_ns
        claim['run_deadline_ns'] = deadline_ns
        # Claim exists before any child can run. A crash during Popen/update
        # leaves a conservative, non-reusable claim rather than a safety gap.
        atomic_json(claim_path, claim)
        descriptors = (active,) if admission is None else (active, admission)
        child = subprocess.Popen([sys.executable, str(Path(__file__).resolve()), '--guardian',
            '--guard', str(guard), '--receipt', claim['receipt'], '--nonce', nonce,
            '--expected-parent', str(os.getpid()), '--operation-deadline-ns', str(operation_deadline_ns),
            '--', *command],
            pass_fds=descriptors, start_new_session=True)
        claim['supervisor_pid'] = child.pid
        atomic_json(claim_path, claim)
        event('dispatched', claim=claim)
        stopping_since = None
        while child.poll() is None:
            if stopped or time.monotonic_ns() >= operation_deadline_ns:
                if stopping_since is None:
                    stopping_since = time.monotonic()
                    child.send_signal(signal.SIGTERM)
                    event('stopping', reason='interrupted' if stopped else 'run_deadline' if budget_expired() else 'timeout')
                elif time.monotonic()-stopping_since > 20:
                    child.kill()
            time.sleep(.02)
        clean = receipt_valid(claim)
        event('finished', exit_code=child.returncode, process_tree_clean=clean)
        if clean:
            claim_path.unlink()
        if not clean:
            return 74
        return 130 if stopped else 124 if stopping_since is not None else child.returncode
    finally:
        # No LOCK_UN: duplicated descriptors in a surviving guard must retain
        # ownership after this process exits. close only this process's copies.
        os.close(active)
        if admission is not None:
            os.close(admission)
        for sig, handler in old_handlers.items():
            signal.signal(sig, handler)


def guardian(args, command):
    """Hold inherited lock FDs through cleanup, including parent-death races.

    The expected parent is supplied before spawn. Capturing getppid only after
    interpreter startup would miss a parent that died before this process ran.
    Reuse the frozen trusted guard's descendant-kill/reap implementation.
    """
    stopped = False
    def stop(signum, frame):
        nonlocal stopped
        stopped = True
    for sig in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
        signal.signal(sig, stop)
    libc = ctypes.CDLL(None, use_errno=True)
    if libc.prctl(36, 1, 0, 0, 0) != 0 or libc.prctl(1, signal.SIGTERM, 0, 0, 0) != 0:
        raise OSError(ctypes.get_errno(), 'lease guardian setup failed')
    if os.getppid() != args.expected_parent:
        stopped = True
    spec = importlib.util.spec_from_file_location('lease_trusted_process_guard', args.guard)
    guard = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(guard)
    child = None
    timed_out = time.monotonic_ns() >= args.operation_deadline_ns
    try:
        if not stopped and not timed_out:
            child = subprocess.Popen(command)
        while child is not None and child.poll() is None and not stopped:
            if time.monotonic_ns() >= args.operation_deadline_ns:
                timed_out = True
                break
            time.sleep(.02)
        code = child.returncode if child is not None and child.returncode is not None else 143
    finally:
        guard.terminate_owned()
    with Path(args.receipt).open('x') as stream:
        json.dump({'status': 'cleaned', 'owned_processes_remaining': 0, 'nonce': args.nonce,
                   'supervisor_pid': os.getpid(), 'child_exit_code': code,
                   'termination_reason': 'timeout' if timed_out else 'interrupted' if stopped else 'command_exit',
                   'cleaned_at_ns': time.time_ns()}, stream)
        stream.flush()
        os.fsync(stream.fileno())
    return 124 if timed_out else code


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--guardian', action='store_true')
    parser.add_argument('--directory')
    parser.add_argument('--kind', choices=('browser-call', 'maintenance'))
    parser.add_argument('--guard', required=True)
    parser.add_argument('--receipt')
    parser.add_argument('--nonce')
    parser.add_argument('--wait-seconds', type=float, default=0)
    parser.add_argument('--timeout-seconds', type=float, default=300)
    parser.add_argument('--expected-parent', type=int)
    parser.add_argument('--stop-path', action='append', default=[])
    parser.add_argument('--deadline-ns', type=int)
    parser.add_argument('--budget-boot-id')
    parser.add_argument('--operation-deadline-ns', type=int)
    parser.add_argument('command', nargs=argparse.REMAINDER)
    args = parser.parse_args()
    command = args.command[1:] if args.command[:1] == ['--'] else args.command
    if args.guardian:
        return guardian(args, command)
    if not args.directory or not args.kind:
        parser.error('--directory and --kind required')
    try:
        return run(args.directory, command, kind=args.kind, guard=args.guard,
            wait_seconds=args.wait_seconds, timeout_seconds=args.timeout_seconds,
            expected_parent=args.expected_parent, stop_paths=args.stop_path,
            deadline_ns=args.deadline_ns, budget_boot_id=args.budget_boot_id)
    except BudgetExhausted as error:
        print(str(error), file=sys.stderr)
        return 124
    except LeaseBusy as error:
        print(str(error), file=sys.stderr)
        return 75
    except InterruptedError as error:
        print(str(error), file=sys.stderr)
        return 130


if __name__ == '__main__':
    raise SystemExit(main())
