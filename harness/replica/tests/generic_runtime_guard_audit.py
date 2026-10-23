"""Independent runtime fault injection; generic fixture, zero model calls.

Run from repository root with --out NEW_DIRECTORY. This records observations,
including failures, rather than treating supervisor receipts as sole evidence.
"""
from __future__ import annotations

import argparse
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import threading
import time

from harness.replica import monitor, runner, transport


def write(path, value):
    Path(path).write_text(json.dumps(value, indent=2) + "\n")


def processes():
    rows = {}
    for path in Path('/proc').glob('[0-9]*/stat'):
        try:
            value = path.read_text()
            fields = value[value.rfind(')') + 2:].split()
            pid = int(path.parent.name)
            rows[pid] = {'pid': pid, 'ppid': int(fields[1]), 'starttime': fields[19],
                         'state': fields[0], 'comm': value[value.find('(')+1:value.rfind(')')]}
        except (OSError, ValueError, IndexError):
            pass
    return rows


def descendants(pid):
    rows = processes()
    owned = {pid}
    while True:
        expanded = owned | {key for key, row in rows.items() if row['ppid'] in owned}
        if expanded == owned:
            break
        owned = expanded
    return {key: rows[key] for key in owned if key in rows}


def remaining(tracked):
    now = processes()
    return [row for key, row in tracked.items() if key in now and
            now[key]['starttime'] == row['starttime'] and now[key]['state'] != 'Z']


def kill_tracked(tracked):
    for row in remaining(tracked):
        try:
            os.kill(row['pid'], signal.SIGKILL)
        except ProcessLookupError:
            pass


def monitor_cases(root):
    spam = monitor.supervise([sys.executable, '-u', '-c',
        "import time\nwhile True:\n print('alive',flush=True)\n time.sleep(.01)"],
        root / 'monitor-spam', timeout=10, idle_timeout=3, interval=.03,
        min_memory_bytes=0, min_disk_bytes=0)
    # This short-lived launcher creates a detached child that survives its exit.
    pidfile = root / 'orphan-pid.json'
    source = ("import subprocess,sys,json,pathlib; "
              "p=subprocess.Popen([sys.executable,'-c','import time;time.sleep(30)'],start_new_session=True); "
              f"pathlib.Path({str(pidfile)!r}).write_text(json.dumps({{'pid':p.pid}}))")
    orphan = monitor.supervise([sys.executable, '-c', source], root / 'monitor-orphan',
        timeout=10, idle_timeout=5, interval=.03, min_memory_bytes=0, min_disk_bytes=0)
    if not pidfile.exists():
        return {'spam': {'result': spam}, 'orphan': {'result': orphan, 'injection_not_reached': True}}
    pid = json.loads(pidfile.read_text())['pid']
    observed = processes().get(pid)
    tracked = {pid: observed} if observed else {}
    leaked = remaining(tracked)
    kill_tracked(tracked)
    return {'spam': {'result': spam, 'stdout_bytes': (root/'monitor-spam/stdout.log').stat().st_size,
                     'stopped_for_no_progress': spam['reason'] == 'no_evidence_progress'},
            'orphan': {'result': orphan, 'live_descendants_after_return': leaked,
                       'audit_cleanup_sent': bool(leaked)}}


def controller(config):
    data = json.loads(Path(config).read_text())
    source, replica = data['plans']
    runner.run_pair(source, replica, data['script'], data['out'], policy=data['policy'],
                    runtime_source=data.get('runtime_source'))


def pair_case(root, name, ports, runtime_source=None):
    case = root / name
    case.mkdir()
    script = case / 'flow.py'
    script.write_text('def run(h):\n try:\n  h.page.locator("#never").wait_for(state="visible",timeout=30000)\n except Exception:\n  pass\n h.expect({"disposition":"unknown"}, "Suffix must stop after browser disconnect")\n h.page.locator("#suffix").click()\n')
    plans = []
    for port in ports:
        plans.append({'origin': f'http://127.0.0.1:{port}', 'upstream_host': '127.0.0.1',
                      'upstream_port': port, 'socket': str(transport.make_socket_path()), 'public_fixture': {}})
    policy = {'mode': 'raw_strict', 'wall_seconds': 20, 'progress_seconds': 2,
              'barrier_wait_seconds': 4, 'min_memory_bytes': 0, 'min_disk_bytes': 0,
              'stability': {'enabled': False}}
    if name == 'wall-time':
        policy.update(wall_seconds=2, progress_seconds=15)
    elif name in ('stop', 'browser-disconnect', 'controller-termination'):
        policy.update(wall_seconds=90, progress_seconds=75, barrier_wait_seconds=55)
    config = case / 'config.json'
    write(config, {'plans': plans, 'script': str(script), 'out': str(case/'pair'), 'policy': policy,
                   'runtime_source': str(runtime_source) if runtime_source else None})
    with (case/'controller.stdout').open('w') as stdout, (case/'controller.stderr').open('w') as stderr:
        child = subprocess.Popen([sys.executable, '-m', 'harness.replica.tests.generic_runtime_guard_audit', '--controller', str(config)],
                                 stdout=stdout, stderr=stderr, start_new_session=True)
        tracked = {}
        injection = None
        deadline = time.monotonic() + 115
        try:
            while child.poll() is None and time.monotonic() < deadline:
                tracked.update(descendants(child.pid))
                # Wait until state0 was compared, so the fault hits a live browser.
                ready = (case/'pair/comparisons/state0/step-result.json').exists()
                if ready and injection is None:
                    if name == 'stop':
                        (case/'pair/STOP').touch()
                        injection = {'signal': 'STOP', 'time_monotonic': time.monotonic()}
                    elif name == 'browser-disconnect':
                        candidates = [row for row in tracked.values() if row['comm'] == 'chromium']
                        if candidates:
                            target = min(candidates, key=lambda row: row['pid'])
                            os.kill(target['pid'], signal.SIGKILL)
                            injection = {'signal': 'SIGKILL browser', 'target': target, 'time_monotonic': time.monotonic()}
                    elif name == 'controller-termination':
                        child.send_signal(signal.SIGTERM)
                        injection = {'signal': 'SIGTERM controller', 'time_monotonic': time.monotonic()}
                time.sleep(.02)
            child.wait(timeout=2)
            # The trusted subreaper has its own bounded cleanup after parent death.
            settle_deadline = time.monotonic() + 18
            while remaining(tracked) and time.monotonic() < settle_deadline:
                time.sleep(.05)
            live = remaining(tracked)
            result_path = case/'pair/result.json'
            result = json.loads(result_path.read_text()) if result_path.exists() else None
            records = []
            for lane in ('source', 'replica'):
                path = case/'pair'/lane/'job/evidence/actions.jsonl'
                records.append({'lane': lane, 'action_before_count': sum(json.loads(line).get('kind') == 'action_before'
                    for line in path.read_text().splitlines()) if path.exists() else 0})
            row = {'case': name, 'controller_exit_code': child.returncode, 'injection': injection,
                   'result': result, 'tracked_processes': list(tracked.values()),
                   'live_tracked_processes_after_exit': live, 'actions': records,
                   'result_missing': result is None, 'audit_cleanup_sent': bool(live)}
            write(case/'audit.json', row)
            return row
        finally:
            kill_tracked(tracked)
            if child.poll() is None:
                child.kill()
                child.wait(timeout=3)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--out')
    parser.add_argument('--controller')
    parser.add_argument('--cases', default='no-checkpoint-progress,wall-time,stop,browser-disconnect,controller-termination')
    parser.add_argument('--runtime-source', help='Coordinator-owned generic runtime/version; frozen by run_pair')
    args = parser.parse_args()
    if args.controller:
        controller(args.controller)
        return
    root = Path(args.out).resolve()
    root.mkdir(parents=True, exist_ok=False)
    runtime_source = transport.resolve_runtime_source(args.runtime_source)
    hashes = {str(path): hashlib.sha256(path.read_bytes()).hexdigest() for path in
              [Path(monitor.__file__), Path(runner.__file__), Path(transport.__file__), *runtime_source.glob('*.py')]}
    report = {'scope': 'generic fault injection only; no model/target/learner/oracle',
              'runtime_source': str(runtime_source),
              'source_hashes_before': hashes, 'monitor': monitor_cases(root), 'pairs': []}
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            body = b'<title>Guard audit fixture</title><main>Ready</main><button id="suffix">Suffix</button>'
            self.send_response(200)
            self.send_header('Content-Type', 'text/html')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        def log_message(self, *args):
            pass
    servers = [ThreadingHTTPServer(('127.0.0.1', 0), Handler) for _ in range(2)]
    try:
        for server in servers:
            threading.Thread(target=server.serve_forever, daemon=True).start()
        for name in args.cases.split(','):
            row = pair_case(root, name, [server.server_port for server in servers], runtime_source)
            report['pairs'].append(row)
            print(json.dumps({'case': name, 'reason': (row['result'] or {}).get('reason'),
                'live_processes': len(row['live_tracked_processes_after_exit']), 'injection': row['injection']}), flush=True)
            write(root/'audit-report.json', report)
    finally:
        for server in servers:
            server.shutdown()
            server.server_close()
    report['source_hashes_after'] = {path: hashlib.sha256(Path(path).read_bytes()).hexdigest() for path in hashes}
    report['source_changed_during_audit'] = report['source_hashes_after'] != hashes
    write(root/'audit-report.json', report)


if __name__ == '__main__':
    main()
