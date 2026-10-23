"""Real Chromium and broker checks for the added public canonical tree export.

Only an owned generic fixture is used. REPLICA_PUBLIC_SNAPSHOT_RUNTIME may select
an explicitly versioned generic runtime; no model or target website is invoked.
"""
from copy import deepcopy
from contextlib import nullcontext
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import inspect
import json
import os
from pathlib import Path
import subprocess
import tempfile
import threading
import unittest

from harness.replica import runner, transport, trees
from harness.replica.runtime import public_snapshot
from harness.replica.runtime.observation import redact

SECRET = 'GENERIC_SECRET_DO_NOT_EXPORT_7391'
STORAGE = 'GENERIC_STORAGE_DO_NOT_EXPORT_8642'
SOURCE = 'GENERIC_SOURCE_DO_NOT_EXPORT_5938'
ACTIVE = 'GENERIC_ACTIVE_DO_NOT_EXPORT_6204'
HTML = '''<!doctype html><html><head><title>Public tree fixture</title>
<script>const GENERIC_SOURCE_DO_NOT_EXPORT_5938 = true;</script>
</head><body><h1 data-note="javascript: literal business attribute">Public tree fixture</h1>
<p>javascript: literal business text</p><label for="query">Query</label>
<input id="query" value="initial"><label><input id="checked" type="checkbox">Enabled</label>
<input id="password" type="password" value="GENERIC_SECRET_DO_NOT_EXPORT_7391">
<button id="active" onclick="window.GENERIC_ACTIVE_DO_NOT_EXPORT_6204=true">Action</button>
<a id="unsafe" href="javascript:window.GENERIC_ACTIVE_DO_NOT_EXPORT_6204=true">Unsafe</a>
<div id="host"></div><iframe id="frame" src="/frame"></iframe>
<script>
localStorage.setItem('generic-private', 'GENERIC_STORAGE_DO_NOT_EXPORT_8642');
const root=document.querySelector('#host').attachShadow({mode:'open'});
root.innerHTML='<script>GENERIC_SHADOW_SOURCE_REMOVED<\\/script><label>Shadow<input id="shadow" value="shadow value"></label>';
</script></body></html>'''
FRAME = '<!doctype html><title>Frame</title><script>const GENERIC_FRAME_SOURCE_REMOVED=1;</script><button id="frame-button">Frame action</button>'


class Fixture:
    def __enter__(self):
        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                data = (FRAME if self.path == '/frame' else HTML).encode()
                self.send_response(200)
                self.send_header('Content-Type', 'text/html; charset=utf-8')
                self.send_header('Content-Length', str(len(data)))
                self.end_headers()
                self.wfile.write(data)
            def log_message(self, *args):
                pass
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.origin = 'http://127.0.0.1:' + str(self.server.server_port)
        return self

    def __exit__(self, *args):
        self.server.shutdown()
        self.server.server_close()


def nodes(snapshot):
    indexed = {}
    def walk(node, path):
        if node is None:
            return
        indexed[path] = node
        for index, child in enumerate(node.get('children', [])):
            walk(child, path + '/children/' + str(index))
        for key in ('shadowRoot', 'templateContent'):
            if key in node:
                walk(node[key], path + '/' + key)
    for frame in snapshot['frames']:
        walk(frame['document'], frame['key'] + '/document')
    return indexed


class PublicSnapshotTests(unittest.TestCase):
    def test_projection_source_and_registration_digest_cannot_drift(self):
        self.assertEqual(inspect.getsource(public_snapshot._public_projection), inspect.getsource(runner._public_projection))
        self.assertEqual(public_snapshot.PROJECTION_POLICY, runner.PROJECTION_POLICY)
        expected = hashlib.sha256((inspect.getsource(runner._public_projection) +
                                   json.dumps(runner.PROJECTION_POLICY, sort_keys=True)).encode()).hexdigest()
        self.assertEqual(public_snapshot.projection_metadata()['sha256'], expected)

    def test_real_capture_preserves_live_state_and_remaps_ax_and_frame_references(self):
        from playwright.sync_api import sync_playwright
        with Fixture() as fixture, sync_playwright() as playwright:
            browser = playwright.chromium.launch(executable_path='/usr/bin/chromium', headless=True, args=['--no-sandbox'])
            try:
                page = browser.new_page()
                page.goto(fixture.origin)
                page.locator('#query').fill('edited query')
                page.locator('#checked').check()
                page.locator('#query').focus()
                page.locator('#query').evaluate('(e) => e.setSelectionRange(2, 7, "backward")')
                canonical = trees.capture(page)['canonical']
                original = deepcopy(canonical)
                self.assertIn(ACTIVE, json.dumps(canonical), 'fixture must exercise the executable AX URL channel')
                self.assertIn(SOURCE, json.dumps(canonical), 'private raw source stays available to the comparator')
                exported = public_snapshot.export_snapshot(canonical)
                tree = exported['tree']
                self.assertEqual(canonical, original, 'export must not mutate private raw/canonical capture')
                self.assertEqual(tree, public_snapshot.public_execution_projection(
                    runner._public_projection(redact(canonical, secrets=[SECRET]))))
                text = json.dumps(exported)
                self.assertIn('javascript: literal business attribute', text)
                self.assertIn('javascript: literal business text', text)
                for canary in (SECRET, STORAGE, SOURCE, ACTIVE, 'GENERIC_SHADOW_SOURCE_REMOVED', 'GENERIC_FRAME_SOURCE_REMOVED'):
                    self.assertFalse(canary in text, 'public tree leaked ' + canary)
                indexed = nodes(tree)
                paths = {node.get('attributes', {}).get('id'): path for path, node in indexed.items()}
                query = indexed[paths['query']]
                self.assertEqual(query['attributes']['value'], 'initial')
                self.assertEqual(query['live']['value'], 'edited query')
                self.assertEqual((query['live']['selectionStart'], query['live']['selectionEnd'], query['live']['selectionDirection']), (2, 7, 'backward'))
                self.assertTrue(query['live']['focused'])
                self.assertTrue(indexed[paths['checked']]['live']['checked'])
                self.assertNotIn('onclick', indexed[paths['active']]['attributes'])
                self.assertNotIn('href', indexed[paths['unsafe']]['attributes'])
                self.assertEqual(indexed[paths['password']]['live']['value'], '[REDACTED]')
                self.assertTrue(any('/shadowRoot/' in path for path in indexed))
                for frame in tree['frames']:
                    focus = frame['key'] + '/' + frame['activeElementPath']
                    self.assertIn(focus, indexed)
                    if frame['owner']:
                        self.assertIn(frame['owner'], indexed)
                ax_query = [node for frame in tree['frames'] for node in frame['ax']
                            if node.get('backendDOMNodeId') == paths['query']]
                self.assertEqual(len(ax_query), 1)
                self.assertEqual(ax_query[0]['value']['value'], 'edited query')
                self.assertEqual(tree['unsupported'], [])
                malformed = deepcopy(canonical)
                malformed['frames'][0]['private_storage'] = {'canary': STORAGE}
                with self.assertRaises(ValueError):
                    public_snapshot.export_snapshot(malformed)
                with self.assertRaises(ValueError):
                    public_snapshot.export_snapshot({'raw': canonical, 'frames': []})
            finally:
                browser.close()

    def test_frozen_broker_exports_same_capture_without_source_secret_or_storage(self):
        scratch = Path('work/replica-pilot/public-snapshot-tests')
        scratch.mkdir(parents=True, exist_ok=True)
        saved = os.environ.get('REPLICA_PUBLIC_SNAPSHOT_EVIDENCE_ROOT')
        if saved:
            Path(saved).mkdir(parents=True, exist_ok=False)
        directory = nullcontext(saved) if saved else tempfile.TemporaryDirectory(dir=scratch)
        with directory as temporary, Fixture() as fixture:
            root = Path(temporary).resolve()
            selector = root / 'unused-selector.json'
            selector.touch()
            config = {'run_dir':str(root / 'run'), 'origin':fixture.origin,
                      'prompt':'Unused generic public observation test; no model call',
                      'auth_source':str(selector), 'action_limit':10, 'script_call_limit':2, 'time_limit_seconds':120}
            if os.environ.get('REPLICA_PUBLIC_SNAPSHOT_RUNTIME'):
                config['runtime_source'] = os.environ['REPLICA_PUBLIC_SNAPSHOT_RUNTIME']
            plan = transport.prepare_session(config)
            workspace = Path(plan['workspace'])
            (workspace / 'flow.py').write_text('''def run(h):
    h.expect({"disposition":"unknown"})
    h.page.goto(h.origin)
    h.expect({"disposition":"unknown"})
    h.page.locator("#query").fill("changed runtime value")
    return h.observe("export-public-tree")
''')
            request = Path(plan['private']) / 'request.json'
            request.write_text(json.dumps({'script_path':'flow.py'}))
            with transport.OriginGateway(plan):
                process = subprocess.run([transport.PYTHON, str(Path(plan['runtime']) / 'browser_broker.py'),
                                          '--config', plan['broker_config'], '--execute-file', str(request)],
                                         capture_output=True, text=True, timeout=110)
            self.assertEqual(process.returncode, 0, process.stderr)
            outcome = json.loads(process.stdout)
            (root / 'broker-process.json').write_text(json.dumps({
                'returncode':process.returncode, 'stdout':outcome, 'stderr':process.stderr}, indent=2))
            result = outcome['result']
            self.assertEqual(result['status'], 'completed', result)
            self.assertTrue(outcome['process_tree_clean'])
            self.assertEqual(result['actions'], 2)
            observation = result['return_value']
            self.assertIn('public_tree', observation)
            evidence = workspace / outcome['evidence_directory']
            exported = json.loads((evidence / observation['public_tree']).read_text())
            self.assertEqual(observation['public_tree_projection_sha256'], public_snapshot.projection_metadata()['sha256'])
            self.assertEqual(observation['security_projection'], public_snapshot.security_projection_metadata())
            call = evidence.name
            canonical_path = Path(plan['private']) / 'broker' / 'jobs' / call / 'private-trees' / Path(observation['dom']).stem / 'canonical.json'
            if not canonical_path.exists():
                candidates = list((Path(plan['private']) / 'broker').rglob(Path(observation['dom']).stem + '/canonical.json'))
                self.assertEqual(len(candidates), 1)
                canonical_path = candidates[0]
            private = json.loads(canonical_path.read_text())
            self.assertEqual(exported['tree'], public_snapshot.public_execution_projection(runner._public_projection(private)))
            for path in evidence.iterdir():
                if path.suffix in {'.json', '.jsonl', '.html'}:
                    text = path.read_text()
                    for canary in (SECRET, STORAGE, SOURCE, ACTIVE, 'GENERIC_SHADOW_SOURCE_REMOVED', 'GENERIC_FRAME_SOURCE_REMOVED'):
                        self.assertFalse(canary in text, str(path) + ' leaked ' + canary)
            (root / 'validation.json').write_text(json.dumps({
                'passed':True, 'no_model_calls':True, 'owned_generic_fixture_only':True,
                'actual_browser_actions':result['actions'], 'public_evidence_directory':str(evidence),
                'runtime_source':plan['runtime_source'], 'runtime_file_hashes':plan['runtime_file_hashes'],
                'public_projection':public_snapshot.projection_metadata(),
                'additional_security_projection':public_snapshot.security_projection_metadata(),
                'checks':['private capture unchanged', 'same capture public projection parity',
                          'AX execution URL removed', 'script body removed', 'secret value removed',
                          'Storage absent', 'public files copied by real sandbox Broker', 'process tree clean']}, indent=2)+'\n')


if __name__ == '__main__':
    unittest.main()
