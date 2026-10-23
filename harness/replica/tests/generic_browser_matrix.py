"""Real native-browser conformance matrix on an owned, generic HTTP fixture.

Run: python -m harness.replica.tests.generic_browser_matrix --run-dir work/replica-pilot/generic-matrix-001
No target website, learner artifact, authentication content or model is read.
A safe_for_learning verdict requires every case to pass against one runtime hash.
"""
from __future__ import annotations
import argparse
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import subprocess
import threading
import time
from urllib.parse import urlsplit

from harness.replica import transport

HTML = '''<!doctype html><title>Generic matrix</title><body>
<h1>Generic fixture</h1><output id="persisted"></output><output id="counter">0</output>
<label>Query<input id="query"></label><label>Mode<select id="mode"><option value="a">A</option><option value="b">B</option></select></label>
<label><input type="checkbox" id="enabled">Enabled</label>
<input id="password" type="password" value="GENERIC_PASSWORD_CANARY">
<button id="persist" onclick="localStorage.setItem('memo',document.querySelector('#query').value);document.cookie='generic=yes;path=/';show()">Persist</button>
<button id="increment" onclick="document.querySelector('#counter').textContent=Number(document.querySelector('#counter').textContent)+1">Increment</button>
<button id="add" onclick="const li=document.createElement('li');li.textContent=document.querySelector('#query').value;document.querySelector('#list').append(li)">Add</button>
<button class="duplicate">Duplicate one</button><button class="duplicate">Duplicate two</button>
<button id="hidden" style="display:none">Hidden</button><button id="disabled" disabled>Disabled</button>
<ul id="list"><li>Initial</li></ul><a href="/two" id="next">Next</a><a href="/" id="home">Home</a>
<script>const CLIENT_SOURCE_CANARY=17;function show(){document.querySelector('#persisted').textContent=(localStorage.getItem('memo')||'empty')+'|'+(document.cookie.includes('generic=yes')?'cookie-ok':'no-cookie')}show()</script>
</body>'''
PREDICT = 'h.expect({"disposition":"unknown"}, "Generic conformance action")\n'


def script(body, *, navigate=True):
    lines = ['def run(h):']
    if navigate:
        lines += [' '+PREDICT.strip(), ' h.page.goto(h.origin)']
    lines += [' '+line if line else '' for line in body.splitlines()]
    return '\n'.join(lines)+'\n'


def action(expression):
    return PREDICT + expression + '\n'


class Matrix:
    def __init__(self, root, origin):
        self.root, self.origin = root, origin
        self.records=[]
        self.start=time.monotonic()
        self.selector=root/'dummy-auth-selector.json'
        self.selector.touch()  # existence-only selector; no authentication used

    def plan(self, name):
        return transport.prepare_session({'run_dir':str(self.root/name),'origin':self.origin,
            'prompt':'Unused generic zero-model conformance audit','auth_source':str(self.selector),
            'action_limit':80,'script_call_limit':10,'time_limit_seconds':240})

    def call(self, plan, name, source):
        workspace=Path(plan['workspace']);private=Path(plan['private'])
        path=workspace/(name+'.py');path.write_text(source)
        request=private/(name+'-request.json');request.write_text(json.dumps({'script_path':path.name}))
        started=time.monotonic()
        result=subprocess.run([transport.PYTHON,str(Path(plan['runtime'])/'browser_broker.py'),
            '--config',plan['broker_config'],'--execute-file',str(request)],capture_output=True,text=True,timeout=160)
        record={'name':name,'exit_code':result.returncode,'stdout':result.stdout,'stderr':result.stderr,
                'elapsed_seconds':time.monotonic()-started,'source_sha256':hashlib.sha256(source.encode()).hexdigest()}
        try:record['outcome']=json.loads(result.stdout)
        except ValueError:record['outcome']=None
        (private/(name+'-process.json')).write_text(json.dumps(record,indent=2))
        return record

    def report(self,name,plan,calls,checks):
        passed=all(checks.values())
        record={'case':name,'passed':passed,'checks':checks,'calls':calls,
                'runtime_hashes':plan['runtime_hashes'],'run_dir':plan['run_dir']}
        self.records.append(record)
        (self.root/'matrix-progress.json').write_text(json.dumps({'cases':self.records},indent=2))
        print(json.dumps({'case':name,'passed':passed,'checks':checks}),flush=True)

    @staticmethod
    def outcome(call):
        return (call.get('outcome') or {}).get('result') or {}

    def ordinary(self,name,expression):
        plan=self.plan('ordinary-'+name)
        with transport.OriginGateway(plan):
            first=self.call(plan,'ordinary-failure',script(expression))
            second=self.call(plan,'recovery',script('return h.page.locator("#counter").inner_text()'))
        result=self.outcome(first);recovery=self.outcome(second)
        self.report('ordinary-'+name,plan,[first,second],{
            'failed_action_stopped':result.get('status')=='error',
            'not_policy_boundary':result.get('failure_category')!='boundary',
            'no_latched_stop':not (first.get('outcome') or {}).get('budget',{}).get('stop_reason'),
            'next_call_recovers':recovery.get('status')=='completed',
            'unperformed_effect':recovery.get('return_value')=='0',
            'process_trees_clean':all((c.get('outcome') or {}).get('process_tree_clean') is True for c in [first,second])})

    def safety(self,name,expression):
        plan=self.plan('safety-'+name)
        # Deliberately catch denial: runtime must still preserve closure.
        body='try:\n '+expression.replace('\n','\n ')+'\nexcept Exception:\n pass\nreturn "caught by learner"'
        with transport.OriginGateway(plan):
            first=self.call(plan,'denial',script(body))
            second=self.call(plan,'must-refuse',script('return h.page.title()'))
        result=self.outcome(first)
        self.report('safety-'+name,plan,[first,second],{
            'policy_boundary':result.get('failure_category')=='boundary',
            'latch_recorded':bool((first.get('outcome') or {}).get('budget',{}).get('stop_reason')),
            'restart_refuses':second['exit_code']!=0 and 'execution stopped' in second['stderr'],
            'first_tree_clean':(first.get('outcome') or {}).get('process_tree_clean') is True})

    def storage(self):
        plan=self.plan('storage-calls')
        body=action('h.page.locator("#query").fill("saved")')+action('h.page.locator("#persist").click()')+action('h.page.get_by_role("link",name="Next",exact=True).click()')+'return h.page.url'
        second='start=h.page.url\n'+action('h.page.goto(h.origin+"/two")')+'return {"initial_url":start,"state":h.page.locator("#persisted").inner_text(),"url":h.page.url}'
        with transport.OriginGateway(plan):
            first=self.call(plan,'store-and-cross-page',script(body))
            following=self.call(plan,'new-page-storage',script(second,navigate=False))
        data=self.outcome(following).get('return_value') or {}
        self.report('two-call-storage-and-page-semantics',plan,[first,following],{
            'first_cross_page':str(self.outcome(first).get('return_value','')).endswith('/two'),
            'second_starts_about_blank':data.get('initial_url')=='about:blank',
            'cookie_and_localstorage_survive':data.get('state')=='saved|cookie-ok',
            'explicit_navigation_succeeds':str(data.get('url','')).endswith('/two'),
            'both_completed':all(self.outcome(c).get('status')=='completed' for c in [first,following])})

    def flow(self):
        plan=self.plan('continuous-flow')
        body=''
        for expression in ['h.page.locator("#query").fill("Dynamic row")','h.page.locator("#mode").select_option("b")',
                'h.page.locator("#enabled").check()','h.page.locator("#add").click()']:
            body+=action(expression)
        body+='h.confirm(h.page.get_by_role("listitem").filter(has_text="Dynamic row"))\n'
        body+='state={"query":h.page.locator("#query").input_value(),"mode":h.page.locator("#mode").input_value(),"checked":h.page.locator("#enabled").is_checked(),"rows":h.page.get_by_role("listitem").all_text_contents()}\n'
        body+=action('h.page.get_by_role("link",name="Next",exact=True).click()')
        body+='h.page.wait_for_url(h.origin+"/two",timeout=1000)\n'
        body+=action('h.page.go_back()')+'state["back_url"]=h.page.url\n'
        body+=action('h.page.go_forward()')+'state["forward_url"]=h.page.url\n'
        body+=action('h.page.reload()')+'state["reload_url"]=h.page.url\nreturn state'
        with transport.OriginGateway(plan):result=self.call(plan,'continuous',script(body))
        data=self.outcome(result).get('return_value') or {}
        self.report('continuous-native-flow',plan,[result],{
            'completed':self.outcome(result).get('status')=='completed',
            'query_fill':data.get('query')=='Dynamic row','select_option':data.get('mode')=='b',
            'check':data.get('checked') is True,'dynamic_list_locator':data.get('rows')==['Initial','Dynamic row'],
            'back':str(data.get('back_url','')).endswith('/'),
            'forward':str(data.get('forward_url','')).endswith('/two'),
            'reload':str(data.get('reload_url','')).endswith('/two'),
            'tree_clean':(result.get('outcome') or {}).get('process_tree_clean') is True})

    def readpoint(self):
        plan=self.plan('readpoint-stop')
        body='try:\n h.read_point("Interpret generic observation")\nexcept Exception:\n pass\n'+action('h.page.locator("#increment").click()')+'return "suffix incorrectly ran"'
        with transport.OriginGateway(plan):
            first=self.call(plan,'pause-and-catch',script(body))
            second=self.call(plan,'resume',script('return h.page.locator("#counter").inner_text()'))
            third=self.call(plan,'direct-reading-return',script('return {"status":"needs_reading","reason":"Generic direct reading request"}',navigate=False))
            fourth=self.call(plan,'resume-direct-reading',script('return h.page.url',navigate=False))
        result=self.outcome(first)
        self.report('readpoint-stops-suffix-and-resumes',plan,[first,second,third,fourth],{
            'needs_reading':result.get('status')=='needs_reading','suffix_action_not_executed':result.get('actions')==1,
            'no_safety_latch':not (first.get('outcome') or {}).get('budget',{}).get('stop_reason'),
            'next_call_recovers':self.outcome(second).get('status')=='completed',
            'counter_unchanged':self.outcome(second).get('return_value')=='0',
            'direct_return_needs_reading':self.outcome(third).get('status')=='needs_reading',
            'direct_reading_resumes':self.outcome(fourth).get('status')=='completed'})

    def run(self,groups):
        if 'storage' in groups:self.storage()
        if 'flow' in groups:self.flow()
        if 'ordinary' in groups:
            for name,expression in [('zero','h.confirm(h.page.locator("#absent"))'),('multiple','h.confirm(h.page.locator(".duplicate"))'),
                ('hidden','h.confirm(h.page.locator("#hidden"))'),('disabled','h.confirm(h.page.locator("#disabled"))'),
                ('timeout','h.page.locator("#absent").wait_for(state="visible",timeout=120)')]:self.ordinary(name,expression)
        if 'safety' in groups:
            for name,expression in [('client-source','h.page.locator("script").inner_html()'),('secret-value','h.page.locator("#password").input_value()'),
                ('cross-origin',action('h.page.goto("http://127.0.0.1:9/forbidden")').strip()),('missing-prediction','h.page.locator("#increment").click()')]:self.safety(name,expression)
        if 'readpoint' in groups:self.readpoint()
        current={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in transport.RUNTIME.glob('*.py')}
        current['trees.py']=hashlib.sha256((transport.RUNTIME.parent/'trees.py').read_bytes()).hexdigest()
        same=all(row['runtime_hashes']==current for row in self.records)
        safe=all(row['passed'] for row in self.records) and same and set(groups)=={'storage','flow','ordinary','safety','readpoint'}
        report={'safe_for_learning':safe,'all_selected_cases_passed':all(row['passed'] for row in self.records),
            'all_cases_use_current_runtime':same,'current_runtime_hashes':current,'groups':groups,
            'no_model_calls':True,'no_target_website_or_learner_artifacts_read':True,'elapsed_seconds':time.monotonic()-self.start,
            'supported_scope':'Generic public runtime APIs tested here; no exhaustive Playwright claim; browser page is fresh each call, storage persists.',
            'cases':self.records}
        (self.root/'matrix-report.json').write_text(json.dumps(report,indent=2))
        print(json.dumps({k:v for k,v in report.items() if k!='cases'}),flush=True)
        return report


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-dir',required=True,help='New directory for immutable generic browser evidence')
    parser.add_argument('--groups',default='storage,flow,ordinary,safety,readpoint',help='Comma-separated groups; full safe verdict requires all five')
    args=parser.parse_args();root=Path(args.run_dir).resolve();root.mkdir(parents=True,exist_ok=False)
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            body=HTML.encode();self.send_response(200);self.send_header('Content-Type','text/html');self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
        def log_message(self,*args):pass
    with ThreadingHTTPServer(('127.0.0.1',0),Handler) as server:
        threading.Thread(target=server.serve_forever,daemon=True).start()
        try:report=Matrix(root,f'http://127.0.0.1:{server.server_port}').run(args.groups.split(','))
        finally:server.shutdown()
    raise SystemExit(0 if report['all_selected_cases_passed'] else 1)

if __name__=='__main__':main()
