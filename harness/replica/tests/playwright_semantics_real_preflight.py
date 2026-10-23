"""One owned Chromium session; generic collector controls, no target websites.

Run directly with --output PATH. Paired controller/worker validation is separate.
"""
from copy import deepcopy
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import argparse
import hashlib
import json
from pathlib import Path
import sys
import threading
import time

ROOT = Path(__file__).resolve().parents[3]
RUNTIME = ROOT / 'harness/replica/runtime_versions/evaluation-playwright-semantics-v6'
sys.path[:0] = [str(RUNTIME), str(ROOT)]
import playwright_semantics as semantics
import trees
from harness.replica.runner import _public_projection
from playwright.sync_api import Locator, sync_playwright

PASSWORD = 'GENERIC_PASSWORD_CANARY_7391'
TOKEN = 'GENERIC_TOKEN_CANARY_8162'
HTML = '''<!doctype html><html><head><title>Owned semantics control</title>
<link rel="stylesheet" href="/app.css"></head><body>
<h1>Owned semantics control</h1><button id="primary">Run</button>
<input id="message" aria-label="Message" value="hello">
<input id="choice" type="checkbox" aria-label="Choice">
<input id="password" type="password" value="GENERIC_PASSWORD_CANARY_7391">
<input id="token" name="token" aria-label="Token" value="GENERIC_TOKEN_CANARY_8162">
<ul id="list"><li>Alpha</li><li>Beta</li></ul>
<button id="conditional"><span class="conditional">Conditional label</span></button>
<a href="/next">Next</a><p>javascript: literal business text</p>
<a href="javascript:window.GENERIC_EXECUTION_CANARY_4972=true">Execution link</a>
<div id="wrapper"><button>Nested action</button></div>
<iframe id="frame" src="/frame"></iframe></body></html>'''
FRAME = '<!doctype html><html><head><title>Frame</title></head><body><button>Frame action</button></body></html>'


class Fixture:
    def __enter__(self):
        self.hide = False
        fixture = self
        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                if self.path == '/app.css':
                    payload = '.conditional {display:' + ('none' if fixture.hide else 'inline') + ';}'
                    mime = 'text/css'
                else:
                    payload = FRAME if self.path == '/frame' else HTML
                    mime = 'text/html; charset=utf-8'
                data = payload.encode()
                self.send_response(200)
                self.send_header('Content-Type', mime)
                self.send_header('Content-Length', str(len(data)))
                self.send_header('Cache-Control', 'no-store')
                self.end_headers()
                self.wfile.write(data)
            def log_message(self, *args):
                pass
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.origin = 'http://127.0.0.1:' + str(self.server.server_port)
        return self

    def __exit__(self, *args):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)


def main(output):
    output.mkdir(parents=True, exist_ok=False)
    checks, timings = [], []
    result = {'scope': 'owned generic collector only; controller/worker pair separate',
              'runtime': RUNTIME.name, 'checks': checks, 'timings': timings,
              'browser_closed': False, 'passed': False}
    def check(name, condition, **detail):
        checks.append({'name': name, 'passed': bool(condition), **detail})
        if not condition:
            raise AssertionError(name)
    def capture(page, origin):
        value = semantics.capture_checkpoint(page, origin=origin, aria_snapshot=Locator.aria_snapshot)
        timings.append(deepcopy(value['semantics']['timing']))
        return value
    def public_dom(value, roots):
        result = _public_projection(trees.canonicalize(value['raw'], roots))
        for frame in result['frames']:
            frame.pop('ax', None)
        return result
    started = time.monotonic()
    try:
        with Fixture() as source, Fixture() as replica, sync_playwright() as playwright:
            browser = playwright.chromium.launch(executable_path='/usr/bin/chromium', headless=True,
                                                  args=['--no-sandbox'])
            try:
                context = browser.new_context()
                left, right = context.new_page(), context.new_page()
                roots = {source.origin: '@site', replica.origin: '@site'}
                left.goto(source.origin)
                right.close()
                right = context.new_page()
                right.goto(replica.origin, wait_until='networkidle')
                baseline = capture(left, source.origin)
                same = capture(right, replica.origin)
                expected = semantics.canonical_semantics(baseline['semantics'], roots)
                check('same_app_complete_frame_semantics_equal', expected == semantics.canonical_semantics(same['semantics'], roots),
                      frame_count=len(expected['frames']))
                check('same_app_public_dom_equal', public_dom(baseline, roots) == public_dom(same, roots))
                check('complete_same_origin_frame_topology', len(expected['frames']) == 2 and expected['frames'][1]['parent'] == 'f0' and bool(expected['frames'][1]['owner']))
                # Collector must not change DOM/live focus/selection; compare independently
                # before/after default snapshot acquisition on the already settled page.
                before = trees.capture(right)
                read = semantics.capture_semantics(right, before['raw'], origin=replica.origin,
                                                    aria_snapshot=Locator.aria_snapshot)
                after = trees.capture(right)
                check('default_snapshot_has_no_dom_live_state_side_effect', public_dom(before, roots) == public_dom(after, roots))
                raw_text = json.dumps(read)
                check('token_canary_is_exercised_in_raw_native_snapshot', TOKEN in raw_text)
                projected = json.dumps(semantics.canonical_semantics(read, roots))
                check('explicit_execution_url_canary_exercised_and_projected', 'GENERIC_EXECUTION_CANARY_4972' in raw_text and 'GENERIC_EXECUTION_CANARY_4972' not in projected and 'javascript: literal business text' in projected)
                clean = semantics.sanitize_record(read, {PASSWORD, TOKEN})
                check('password_token_absent_after_persistence_sanitizer', PASSWORD not in json.dumps(clean) and TOKEN not in json.dumps(clean),
                      password_in_raw_snapshot=PASSWORD in raw_text)
                # Simulate the public runtime wrapper changing its secret set. Trusted
                # capture receives the saved native method and stays byte-identical.
                original_snapshot = Locator.aria_snapshot
                try:
                    Locator.aria_snapshot = lambda owner, **kwargs: original_snapshot(owner, **kwargs).replace(TOKEN, '[REDACTED]')
                    bypassed = semantics.capture_semantics(right, before['raw'], origin=replica.origin,
                                                           aria_snapshot=original_snapshot)
                    check('trusted_capture_bypasses_public_secret_wrapper', semantics.canonical_semantics(read) == semantics.canonical_semantics(bypassed))
                finally:
                    Locator.aria_snapshot = original_snapshot
                mutations = {
                    'role': "document.querySelector('#primary').setAttribute('role','link')",
                    'name': "document.querySelector('#primary').textContent='Other run'",
                    'disabled': "document.querySelector('#primary').disabled=true",
                    'checked': "document.querySelector('#choice').checked=true",
                    'order': "const l=document.querySelector('#list'); l.append(l.firstElementChild)",
                    'visibility': "document.querySelector('#primary').style.display='none'",
                    'live_value': "document.querySelector('#message').value='edited'",
                }
                for name, mutation in mutations.items():
                    right.close()
                    right = context.new_page()
                    right.goto(replica.origin, wait_until='networkidle')
                    right.evaluate(mutation)
                    changed = capture(right, replica.origin)
                    actual = semantics.canonical_semantics(changed['semantics'], roots)
                    check('semantic_negative_' + name, actual['status'] == 'confirmed' and actual != expected, status=actual['status'], unsupported=actual['unsupported'], equal=actual == expected)
                right.close()
                right = context.new_page()
                right.goto(replica.origin, wait_until='networkidle')
                right.evaluate("const old=document.querySelector('#wrapper'); const fresh=document.createElement('div'); fresh.id=old.id; fresh.append(...old.childNodes); old.replaceWith(fresh)")
                reconstructed = capture(right, replica.origin)
                check('native_equivalent_wrapper_preserves_semantics', semantics.canonical_semantics(reconstructed['semantics'], roots) == expected,
                      native_ax_equal=trees.canonicalize(baseline['raw'], roots) == trees.canonicalize(reconstructed['raw'], roots))
                replica.hide = True
                right.close()
                right = context.new_page()
                right.goto(replica.origin, wait_until='networkidle')
                hidden = capture(right, replica.origin)
                check('external_css_negative_same_full_public_dom', public_dom(baseline, roots) == public_dom(hidden, roots))
                check('external_css_negative_semantics_independently_different', semantics.canonical_semantics(hidden['semantics'], roots) != expected)
                replica.hide = False
                for length in (900, 901):
                    right.close()
                    right = context.new_page()
                    right.goto(replica.origin, wait_until='networkidle')
                    right.locator('#primary').evaluate('(element, n) => element.setAttribute("aria-label", "L".repeat(n))', length)
                    value = capture(right, replica.origin)['semantics']
                    check('name_length_' + str(length), value['status'] == ('confirmed' if length == 900 else 'unconfirmed'),
                          unsupported=value['unsupported'], timing=value['timing'])
                right.close()
                right = context.new_page()
                right.goto(replica.origin, wait_until='networkidle')
                right.locator('#primary').evaluate('(element) => element.setAttribute("aria-label", "😀".repeat(451))')
                astral = capture(right, replica.origin)['semantics']
                check('name_utf16_units_902_rejected', astral['status'] == 'unconfirmed')
                right.close()
                right = context.new_page()
                right.goto(replica.origin, wait_until='networkidle')
                right.locator('#frame').evaluate('(element, url) => element.src=url', source.origin + '/frame')
                right.wait_for_load_state('networkidle')
                cross = capture(right, replica.origin)['semantics']
                check('cross_origin_frame_fail_closed', cross['status'] == 'unconfirmed' and any(item['kind'] == 'unsupported_frame_origin' for item in cross['unsupported']))
                right.close()
                right = context.new_page()
                right.goto(replica.origin, wait_until='networkidle')
                right.evaluate('document.body.remove()')
                try:
                    missing = capture(right, replica.origin)['semantics']
                    check('missing_body_fail_closed', missing['status'] == 'unconfirmed')
                except Exception as error:
                    check('missing_body_fail_closed', True, acquisition_error_type=type(error).__name__)
                # Representative size measures the role/name guard's scaling; never
                # substitutes a larger timeout or target-specific cache.
                right.close()
                right = context.new_page()
                right.goto(replica.origin, wait_until='networkidle')
                right.evaluate('for(let i=0;i<600;i++){const b=document.createElement("button");b.textContent="Control "+i;document.body.append(b)}')
                large = capture(right, replica.origin)['semantics']
                check('representative_600_controls_capture_confirmed', large['status'] == 'confirmed', timing=large['timing'])
                result['passed'] = True
            finally:
                browser.close()
                result['browser_closed'] = True
    finally:
        result['elapsed_seconds'] = time.monotonic() - started
        result['policy_sha256'] = hashlib.sha256(json.dumps(semantics.POLICY, sort_keys=True).encode()).hexdigest()
        (output / 'results.json').write_text(json.dumps(result, indent=2, ensure_ascii=False))
    print(json.dumps({'passed': result['passed'], 'checks': len(checks), 'elapsed_seconds': result['elapsed_seconds'], 'browser_closed': result['browser_closed']}))


def remaining_controls(output):
    """Only controls not reached in collector-003; never rerun passed groups."""
    output.mkdir(parents=True, exist_ok=False)
    result = {'scope': 'only missing-body and representative-size controls',
              'checks': [], 'passed': False, 'browser_closed': False}
    started = time.monotonic()
    try:
        with Fixture() as fixture, sync_playwright() as playwright:
            browser = playwright.chromium.launch(executable_path='/usr/bin/chromium', headless=True,
                                                  args=['--no-sandbox'])
            try:
                page = browser.new_page()
                page.goto(fixture.origin, wait_until='networkidle')
                page.evaluate('for(let i=0;i<600;i++){const b=document.createElement("button");b.textContent="Control "+i;document.body.append(b)}')
                large = semantics.capture_checkpoint(page, origin=fixture.origin, aria_snapshot=Locator.aria_snapshot)
                result['checks'].append({'name': 'representative_600_controls_capture_confirmed',
                                         'passed': large['semantics']['status'] == 'confirmed',
                                         'timing': large['semantics']['timing']})
                assert result['checks'][-1]['passed']
                page.evaluate('document.body.remove()')
                # Test the explicit semantics body guard using the root metadata.
                root_raw = {'frames': [large['raw']['frames'][0]], 'unsupported': []}
                missing = semantics.capture_semantics(page, root_raw, origin=fixture.origin,
                                                       aria_snapshot=Locator.aria_snapshot)
                result['checks'].append({'name': 'missing_body_semantics_fail_closed',
                                         'passed': missing['status'] == 'unconfirmed' and bool(missing['unsupported']),
                                         'unsupported': missing['unsupported']})
                assert result['checks'][-1]['passed']
                try:
                    full = semantics.capture_checkpoint(page, origin=fixture.origin, aria_snapshot=Locator.aria_snapshot)
                    rejected = full['semantics']['status'] == 'unconfirmed'
                    reason = 'unconfirmed'
                except Exception as error:
                    rejected, reason = True, type(error).__name__
                result['checks'].append({'name': 'missing_body_full_acquisition_fail_closed',
                                         'passed': rejected, 'reason': reason})
                assert rejected
                result['passed'] = True
            finally:
                browser.close()
                result['browser_closed'] = True
    finally:
        result['elapsed_seconds'] = time.monotonic() - started
        (output / 'results.json').write_text(json.dumps(result, indent=2, ensure_ascii=False))
    print(json.dumps(result))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--remaining-only', action='store_true')
    args = parser.parse_args()
    (remaining_controls if args.remaining_only else main)(args.output)
