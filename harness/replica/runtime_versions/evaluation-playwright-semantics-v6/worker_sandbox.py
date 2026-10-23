"""Trusted browser worker namespace with a single fixed-origin Unix capability."""
from pathlib import Path

PYTHON_ROOT = '/opt/codex/runtimes/codex-primary-runtime/dependencies/python'
NODE_ROOT = '/opt/codex/runtimes/codex-primary-runtime/dependencies/node'


def command(runtime, job_path, socket_path, *, state_dir=None, step_barrier_dir=None):
    runtime, job_path = Path(runtime).resolve(), Path(job_path).resolve()
    args = ['bwrap', '--unshare-all', '--new-session', '--die-with-parent', '--clearenv']
    for path in ('/bin', '/sbin', '/usr', '/lib', '/lib64', PYTHON_ROOT, NODE_ROOT):
        args += ['--ro-bind', path, path]
    args += ['--ro-bind', str(runtime), str(runtime), '--bind', str(job_path.parent), str(job_path.parent)]
    # A read-only bind of the Unix socket permits connect but exposes no parent
    # private files. Network namespace has neither host TCP nor abstract sockets.
    args += ['--ro-bind', str(socket_path), str(socket_path)]
    for directory in (state_dir, step_barrier_dir):
        if directory and Path(directory).resolve() != job_path.parent:
            value = str(Path(directory).resolve())
            args += ['--bind', value, value]
    args += ['--proc', '/proc', '--dev', '/dev', '--tmpfs', '/tmp',
             '--setenv', 'HOME', '/tmp', '--setenv', 'TMPDIR', '/tmp',
             '--setenv', 'LANG', 'C.UTF-8', '--setenv', 'PATH', NODE_ROOT + '/bin:/usr/bin:/bin',
             '--setenv', 'PLAYWRIGHT_NODEJS_PATH', NODE_ROOT + '/bin/node',
             '--chdir', str(job_path.parent), '--', PYTHON_ROOT + '/bin/python',
             str(runtime / 'browser_runtime.py'), '--job', str(job_path)]
    return args
