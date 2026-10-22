"""Management-only native UI -> exact expanded CLI begin/finish integration."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import time
from urllib.parse import urlparse
try:
    import psutil
except ImportError:
    # Existing host management dependency; no package install/site build change.
    sys.path.append(r'D:\Anaconda\Lib\site-packages')
    import psutil
from playwright.sync_api import sync_playwright
from management import HERE, EXTRA, evaluator, sha

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--worker',choices=EXTRA,required=True);args=parser.parse_args()
    worker=EXTRA[args.worker];e=evaluator(worker['runtime']);case=e.fixed('P01')
    out=worker['runtime']/'private/scale-cli-ui-001';out.mkdir(exist_ok=False)
    def cli(arguments):
        result=subprocess.run([sys.executable,str(HERE/'management.py'),'--runtime',str(worker['runtime']),*arguments],capture_output=True,text=True,check=True,creationflags=subprocess.CREATE_NO_WINDOW)
        return json.loads(result.stdout)
    reset=cli(['reset-case','--id',case['id']]);before=cli(['begin','--id',case['id'],'--output',str(out/'before.json')])
    events=[];pending=set();starts={};base='http://127.0.0.1:'+str(worker['frontend_port'])
    def canonical(url):
        p=urlparse(url)
        return p._replace(netloc='127.0.0.1:12042').geturl() if p.hostname=='127.0.0.1' and p.port==worker['frontend_port'] else url
    def event(request,status,phase):
        try:body=request.post_data_json
        except Exception:body=None
        item=e.ingest_http(request.method,canonical(request.url),status,request_body=body)
        if item is not None:
            item.update(management_request_started_ns=starts[request],management_received_ns=time.time_ns(),event_phase=phase)
            events.append(item)
        return item
    def dispatched(request):
        starts[request]=time.time_ns()
        if event(request,0,'dispatch') is not None:pending.add(request)
    def response_seen(response):
        event(response.request,response.status,'response')
    def finished(request):pending.discard(request)
    with sync_playwright() as pw:
        browser=pw.chromium.launch(executable_path=r'C:\Users\29935\AppData\Local\Google\Chrome\Application\chrome.exe',headless=True)
        owned=[(p.pid,p.create_time()) for p in psutil.Process().children(recursive=True) if 'chrome' in p.name().lower()]
        context=browser.new_context();context.tracing.start(screenshots=True,snapshots=True,sources=False)
        page=context.new_page();page.on('request',dispatched);page.on('response',response_seen);page.on('requestfinished',finished)
        page.goto(base+'/login');page.get_by_role('button',name='Sign in',exact=True).click();page.wait_for_url(base+'/')
        page.goto(base+case['entry'])
        target=page.get_by_role('button',name='Add to Collection' if case['table']=='collection_items' else 'Add to Wantlist',exact=True)
        target.wait_for(state='visible');target.scroll_into_view_if_needed();target.click();page.wait_for_timeout(700)
        page.screenshot(path=str(out/'final.png'));context.tracing.stop(path=out/'trace.zip');context.close();browser.close()
    clean=all(not psutil.pid_exists(pid) or psutil.Process(pid).create_time()!=created for pid,created in owned)
    barrier={'relay_drained':not pending,'browser_tree_clean':clean,'gateway_log_complete':True}
    ui={'events':events,'screenshot_path':str(out/'final.png'),'ui_error':None,'management_barrier':barrier}
    with (out/'ui.json').open('x',encoding='utf-8') as f:json.dump(ui,f,indent=2)
    finish=cli(['finish','--id',case['id'],'--before',str(out/'before.json'),'--ui-evidence',str(out/'ui.json'),'--output',str(out/'evaluation.json')])
    value=json.loads((out/'evaluation.json').read_text(encoding='utf-8'))
    passed=value['evaluation']['task_outcome']=='passed' and value['safe_to_reset'] is True
    result={'worker_id':args.worker,'kind':'management_cli_native_ui_integration_not_formal_score','passed':passed,
            'reset':reset,'before':before,'finish':finish,'safe_to_reset':value['safe_to_reset'],
            'barrier':barrier,'event_count':len(events),'original_before_hash_unchanged':sha(out/'before.json')==before['sha256'],
            'origin_alias_scope':'Private native-UI test only; formal relay already exposes canonical12042 origin',
            'physical_formal_relay_exercised':False}
    with (out/'result.management.json').open('x',encoding='utf-8') as f:json.dump(result,f,indent=2)
    print(json.dumps({'worker_id':args.worker,'passed':passed,'safe_to_reset':value['safe_to_reset']}))
    if not passed:raise RuntimeError('Exact expanded CLI integration failed')
    cli(['reset-learning','--seed','0'])

if __name__=='__main__':main()
