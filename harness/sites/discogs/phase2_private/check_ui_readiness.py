"""Private independent UI environment acceptance. Never a learner score."""
import importlib.util
import json
import os
from pathlib import Path
import time
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[4]
spec=importlib.util.spec_from_file_location('private_eval',Path(__file__).with_name('evaluator.py'))
e=importlib.util.module_from_spec(spec);spec.loader.exec_module(e)
BASE=os.environ.get('BM_PRIVATE_BASE_URL','http://127.0.0.1:12042')
def main():
    out=e.RUNTIME/('private/'+os.environ.get('BM_PRIVATE_UI_RUN','ui-readiness-001'));out.mkdir(parents=True,exist_ok=False)
    results=[];start=time.monotonic()
    with sync_playwright() as pw:
        browser=pw.chromium.launch(executable_path=r'C:\Users\29935\AppData\Local\Google\Chrome\Application\chrome.exe',headless=True)
        for case in e.cases():
            if os.environ.get('BM_PRIVATE_UI_CASES') and case['id'] not in os.environ['BM_PRIVATE_UI_CASES'].split(','): continue
            folder=out/case['id'];folder.mkdir()
            stamp=time.monotonic(); reset=e.reset(case);before=e.observe()
            context=browser.new_context(viewport={'width':1440,'height':1000});context.set_default_timeout(15000);context.set_default_navigation_timeout(30000)
            context.tracing.start(screenshots=True,snapshots=True,sources=False)
            page=context.new_page();events=e.attach_ui(page);error=None;login=False;control=False;page_errors=[]
            page.on('pageerror',lambda error:page_errors.append(str(error)))
            def act(locator):
                locator.wait_for(state='visible');locator.scroll_into_view_if_needed();locator.click()
            try:
                page.goto(BASE+'/login',wait_until='domcontentloaded')
                # Public page supplies the ordinary fixture credentials; no secret read.
                act(page.get_by_role('button',name='Sign in',exact=True))
                page.wait_for_url(BASE+'/',wait_until='domcontentloaded');login=True
                page.goto(BASE+case['entry'],wait_until='domcontentloaded')
                if case['kind'].startswith('membership_'):
                    name='Add to Collection' if case['table']=='collection_items' else 'Add to Wantlist'
                    locator=page.get_by_role('button',name=name,exact=True);locator.wait_for(state='visible');control=True
                    path='/api/me/'+('collection' if case['table']=='collection_items' else 'wantlist')+'/'+str(case['release_id'])
                    with page.expect_response(lambda r: r.request.method=='POST' and r.url.endswith(path),timeout=15000):act(locator)
                elif case['kind']=='cart_increment':
                    locator=page.locator('a[href="/cart?add='+str(case['listing_id'])+'"]');locator.wait_for(state='visible');control=True
                    with page.expect_response(lambda r:r.request.method=='POST' and r.url.endswith('/api/cart/items'),timeout=15000):act(locator)
                    page.wait_for_url(BASE+'/cart',wait_until='domcontentloaded')
                elif case['kind']=='cart_remove':
                    with e.connect(ROOT/case['initial_db']) as db:
                        seller=db.execute('select u.username from marketplace_listings m join users u on u.id=m.seller_user_id where m.id=?',(case['listing_id'],)).fetchone()[0]
                    title=page.get_by_role('link',name=case['title'],exact=True)
                    locator=title.locator('xpath=../..').filter(has_text='Seller: '+seller).get_by_role('button',name='Remove',exact=True);locator.wait_for(state='visible');control=True
                    with page.expect_response(lambda r:r.request.method=='DELETE' and '/api/cart/items/' in r.url,timeout=15000):act(locator)
                else:
                    search=page.get_by_placeholder('Search releases...');search.wait_for(state='visible');search.fill(case['title'])
                    with page.expect_response(lambda r:r.request.method=='GET' and '/api/backend/search?' in r.url,timeout=15000) as search_response:
                        act(page.get_by_role('main').get_by_role('button',name='Search',exact=True))
                    if search_response.value.status>=400: raise RuntimeError('UI prerequisite request rejected: '+str(search_response.value.status))
                    selection=page.get_by_role('button').filter(has_text='#'+str(case['release_id']));selection.wait_for(state='visible');act(selection)
                    inputs=page.locator('section').first.locator('input')
                    # Source-verified private reference positions; never learner input.
                    inputs.nth(4).fill(str(case['quantity']))
                    locator=page.get_by_role('button',name='Create Listing',exact=True);locator.wait_for(state='visible');control=True
                    with page.expect_response(lambda r:r.request.method=='POST' and r.url.endswith('/api/me/listings'),timeout=15000):act(locator)
                page.wait_for_timeout(700)
            except Exception as exc:error=type(exc).__name__+': '+str(exc)
            after=e.observe();shot=folder/'after.png';page.screenshot(path=str(shot),full_page=True)
            (folder/'after.html').write_text(page.content(),encoding='utf8')
            # Auth UI DOM carries only public fixture defaults; no cookie/token archive.
            (folder/'before.private.json').write_text(json.dumps(before,ensure_ascii=False,indent=2),encoding='utf8')
            (folder/'after.private.json').write_text(json.dumps(after,ensure_ascii=False,indent=2),encoding='utf8')
            evaluation=e.evaluate(case,before,after,{'events':events,'screenshot_path':str(shot),'ui_error':error})
            result={'id':case['id'],'kind':'environment_acceptance_not_learner','login_ok':login,'control_reachable':control,'elapsed_seconds':time.monotonic()-stamp,'url':page.url,'events':events,'page_errors':page_errors,'error':error,'evaluation':evaluation,'reset':reset,'classification':'expected_business_result_verified' if evaluation['outcome']=='passed' else 'control_reachable_business_blocked' if control and any(x['status']>=400 for x in events) else 'ui_prerequisite_environment_blocked' if not control and any(x['status']>=400 for x in events) else 'unable_to_confirm'}
            (folder/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8')
            context.tracing.stop(path=folder/'trace.zip');context.close();results.append(result)
            print(json.dumps({'id':case['id'],'classification':result['classification'],'elapsed_seconds':result['elapsed_seconds']}),flush=True)
        browser.close()
    counts={name:sum(x['classification']==name for x in results) for name in sorted({r['classification'] for r in results})}
    report={'run_id':'phase2-discogs-20261021-01','kind':'independent_environment_acceptance_not_learner','denominator':30,'executed':len(results),'classification_counts':counts,'status':'environment_limits_evidenced' if counts.get('control_reachable_business_blocked',0) or counts.get('ui_prerequisite_environment_blocked',0) else 'ready' if counts.get('expected_business_result_verified',0)==30 else 'not_ready','elapsed_seconds':time.monotonic()-start,'model_tokens':None,'model_cost':None,'inventory_sha256':e.digest(e.INVENTORY),'results':results}
    (out/'report.private.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps({k:v for k,v in report.items() if k!='results'}),flush=True)
if __name__=='__main__':main()
