"""Read-only environment discovery, with an explicit optional transport smoke."""
import html
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
from urllib.parse import urlparse

from .artifacts import freeze, verify_frozen, write_json
from .contract import load_inputs, read_json, repository_root, require, validate

DEFAULT_CDP = 'http://127.0.0.1:9337'


def local_http(url):
    parsed = urlparse(url)
    require(parsed.scheme in ('http', 'https') and parsed.hostname in ('localhost', '127.0.0.1', '::1'),
            'preflight permits loopback HTTP only')
    require(not parsed.username and not parsed.password, 'credentials forbidden in probe URL')


class LocalRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        local_http(newurl)
        return super().redirect_request(request, fp, code, msg, headers, newurl)


def probe_http(url, expect_json=False):
    try:
        local_http(url)
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), LocalRedirect())
        with opener.open(url, timeout=3) as response:
            result = {'reachable': True, 'available': 200 <= response.status < 400, 'http_status': response.status}
            if expect_json:
                data = json.loads(response.read(1024 * 1024).decode('utf-8'))
                endpoint = data.get('webSocketDebuggerUrl', '')
                parsed = urlparse(endpoint)
                result['available'] = parsed.scheme in ('ws', 'wss') and parsed.hostname in ('localhost', '127.0.0.1', '::1')
                result['browser_version'] = data.get('Browser')
                result['websocket_endpoint_local'] = result['available']
            return result
    except urllib.error.HTTPError as exc:
        return {'reachable': True, 'available': False, 'http_status': exc.code, 'error': str(exc)}
    except Exception as exc:
        return {'reachable': False, 'available': False, 'error': str(exc)}


def discover_browser():
    candidates = [os.environ.get('HARNESS_CHROME'), *[shutil.which(name) for name in ('google-chrome', 'chromium', 'chrome')]]
    if os.name == 'nt':
        for base in (os.environ.get('LOCALAPPDATA'), os.environ.get('ProgramFiles'), os.environ.get('ProgramFiles(x86)'),
                     r'C:\Users\29935\AppData\Local'):
            if base:
                candidates.append(str(Path(base) / 'Google/Chrome/Application/chrome.exe'))
    return next((str(Path(path).resolve()) for path in candidates if path and Path(path).is_file()), None)


def run_smoke(out, cdp_url):
    command = [sys.executable, '-m', 'harness.browser_smoke', '--out', str(out)]
    if cdp_url:
        command.extend(['--cdp', cdp_url])
    try:
        process = subprocess.run(command, capture_output=True, text=True, timeout=180, shell=False,
                                 creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
        value = read_json(out / 'result.json') if (out / 'result.json').is_file() else {}
        return {'status': 'passed' if process.returncode == 0 and value.get('status') == 'passed' else 'blocked_or_failed',
                'returncode': process.returncode, 'result': str(out / 'result.json') if (out / 'result.json').is_file() else None,
                'error': value.get('error')}
    except Exception as exc:
        return {'status': 'blocked_or_failed', 'error': str(exc)}


def execute(site_path, bundle_path, out, cdp_url=DEFAULT_CDP, launch_browser=False, smoke=False,
            repo_root=None, http_probe=None, browser_discovery=None, dependency_probe=None, smoke_probe=None):
    root = Path(repo_root or repository_root()).resolve()
    out = Path(out).resolve()
    # Refuse collisions before doing even read-only probes.
    out.mkdir(parents=True, exist_ok=False)
    result = {'kind': 'environment_preflight', 'measurement_status': 'not_started',
              'measurement_note': '未开始目标网站测量；启动前环境检查不是模型成绩。',
              'model_repair_allowed': False, 'case_success_rate': None, 'step_match_rate': None,
              'ready_for_measurement': False, 'status': 'blocked', 'checks': {},
              'browser_smoke': {'status': 'unverified', 'reason': 'No real browser smoke requested or completed.'},
              'business_reset_performed': False, 'business_tasks_executed': False, 'model_called': False}
    http_probe = http_probe or probe_http
    browser_discovery = browser_discovery or discover_browser
    dependency_probe = dependency_probe or (lambda: importlib.util.find_spec('websocket') is not None)
    smoke_probe = smoke_probe or run_smoke
    try:
        site, bundle, cases = load_inputs(site_path, bundle_path, root)
        counts = validate(site, bundle, cases)
        result.update(site_id=site['site_id'], revision=bundle['revision'], fixed_denominators=counts)
        result['checks']['structure'] = {'passed': True, **counts}
        freeze(Path(site_path), Path(bundle_path), site, cases, out, root)
        result['checks']['site_http'] = http_probe(site['base_url'])
        result['checks']['browser_dependency'] = {'websocket_client_found': bool(dependency_probe()),
                                                  'runtime_use': 'unverified until real smoke succeeds'}
        if launch_browser:
            executable = browser_discovery()
            result['checks']['browser_selection'] = {'mode': 'launch', 'executable': executable,
                                                     'executable_found': bool(executable), 'launch_verified': False}
            browser_discovered = bool(executable)
            selected_cdp = None
        else:
            local_http(cdp_url)
            endpoint = http_probe(cdp_url.rstrip('/') + '/json/version', expect_json=True)
            result['checks']['browser_selection'] = {'mode': 'cdp', 'url': cdp_url, 'endpoint': endpoint,
                                                     'transport_verified': False}
            browser_discovered = endpoint.get('available', False)
            selected_cdp = cdp_url
        discoveries_ok = (result['checks']['site_http'].get('available', False) and browser_discovered and
                          result['checks']['browser_dependency']['websocket_client_found'])
        if smoke and discoveries_ok:
            result['browser_smoke'] = smoke_probe(out / 'browser-smoke', selected_cdp)
        elif smoke:
            result['browser_smoke']['reason'] = 'Prerequisite discovery blocked; real smoke was not attempted.'
        smoke_passed = result['browser_smoke']['status'] == 'passed'
        result['integrity_errors'] = verify_frozen(out, root, site)
        result['ready_for_measurement'] = bool(discoveries_ok and smoke_passed and not result['integrity_errors'])
        result['status'] = 'passed' if result['ready_for_measurement'] else ('unverified' if discoveries_ok and not smoke else 'blocked')
        if launch_browser:
            result['checks']['browser_selection']['launch_verified'] = smoke_passed
        else:
            result['checks']['browser_selection']['transport_verified'] = smoke_passed
    except Exception as exc:
        result['error'] = str(exc)
        result['status'] = 'blocked'
    write_json(out / 'preflight.json', result)
    report = ('<!doctype html><meta charset="utf-8"><title>Harness preflight</title>'
              '<style>body{font:16px system-ui;max-width:1000px;margin:40px auto}pre{white-space:pre-wrap}</style>'
              '<h1>启动前环境检查</h1><p><strong>未开始目标网站测量</strong></p>'
              '<p>未执行业务重置或任务，未调用模型。找到 Chrome 或 CDP 端点不代表浏览器能力已经验证。'
              '真实 browser-smoke 未通过时，能力标记为未验证。没有模型成功率成绩。</p>'
              '<p><a href="preflight.json">完整检查记录</a></p><pre>' +
              html.escape(json.dumps(result, ensure_ascii=False, indent=2)) + '</pre>')
    (out / 'report.html').write_text(report, encoding='utf-8')
    return result
