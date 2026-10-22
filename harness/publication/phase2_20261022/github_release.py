"""Restricted GitHub release publisher. No credentials enter files/logs/argv."""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import threading
import time
from urllib.parse import quote
import requests

REPOSITORY = 'ChenjianFan2000/Browser_Meme'
ACCOUNT = 'ChenjianFan2000'
API = 'https://api.github.com'
LOCK = threading.Lock()

class ReleaseError(Exception):
    def __init__(self, kind, endpoint='local', status=None):
        self.safe = {'error_type':kind,'endpoint':endpoint}
        if status is not None:self.safe['status']=status
        super().__init__(kind)

def digest(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda:f.read(1024*1024),b''):h.update(block)
    return h.hexdigest()

def read(path):return json.loads(Path(path).read_text(encoding='utf-8-sig'))

def credential():
    env=os.environ.copy();env.update(GIT_TERMINAL_PROMPT='0',GCM_INTERACTIVE='never')
    try:
        result=subprocess.run(['git','credential','fill'],input='protocol=https\nhost=github.com\nusername='+ACCOUNT+'\n\n',text=True,capture_output=True,env=env,timeout=30,check=False)
    except Exception:raise ReleaseError('credential_helper_failed') from None
    if result.returncode:raise ReleaseError('credential_helper_failed')
    fields=dict(line.split('=',1) for line in result.stdout.splitlines() if '=' in line)
    if fields.get('username','').lower()!=ACCOUNT.lower() or not fields.get('password'):raise ReleaseError('credential_identity_missing')
    return fields['password']

class APIClient:
    def __init__(self, token, transport=None):self.token=token;self.transport=transport or requests.request
    def request(self, method, endpoint, *, allowed=(200,), data=None, stream=False, headers=None):
        url=endpoint if endpoint.startswith('https://') else API+endpoint
        if not (url.startswith(API+'/') or url.startswith('https://uploads.github.com/repos/'+REPOSITORY+'/releases/')):raise ReleaseError('untrusted_api_endpoint')
        safe_endpoint=endpoint.split('?',1)[0].replace(API,'').replace('https://uploads.github.com','')
        kwargs={'headers':{'Authorization':'Bearer '+self.token,'Accept':'application/vnd.github+json','X-GitHub-Api-Version':'2022-11-28',**(headers or {})},'timeout':(15,180),'allow_redirects':False,'stream':stream}
        if data is not None:
            if isinstance(data,dict):kwargs['json']=data
            else:kwargs['data']=data
        attempts=3 if method=='GET' else 1
        for attempt in range(attempts):
            try:response=self.transport(method,url,**kwargs)
            except requests.RequestException:
                if attempt+1<attempts:continue
                raise ReleaseError('transport_failure',safe_endpoint) from None
            if method=='GET' and response.status_code in {429,500,502,503,504} and attempt+1<attempts:
                response.close();continue
            if response.status_code not in allowed:
                status=response.status_code;response.close();raise ReleaseError('http_failure',safe_endpoint,status)
            return response
    def json(self,method,endpoint,**kwargs):
        response=self.request(method,endpoint,**kwargs)
        try:return response.json()
        except Exception:raise ReleaseError('invalid_json_response',endpoint.split('?',1)[0]) from None
        finally:response.close()

def load_plan(path):
    path=Path(path).resolve();plan=read(path)
    if plan.get('repository')!=REPOSITORY:raise ReleaseError('repository_guard')
    if plan.get('expected_visibility','public')!='public':raise ReleaseError('visibility_guard')
    if not re.fullmatch(r'[0-9a-fA-F]{40}',str(plan.get('target_commit',''))):raise ReleaseError('exact_commit_required')
    if not isinstance(plan.get('tag'),str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]{0,127}',plan['tag']):raise ReleaseError('invalid_tag')
    if not re.fullmatch(r'[0-9a-f]{64}',str(plan.get('body_sha256',''))):raise ReleaseError('body_sha256_required')
    names=set()
    for item in plan.get('assets',[]):
        if (not isinstance(item.get('name'),str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]{0,200}',item['name']) or item['name'] in names):raise ReleaseError('invalid_or_duplicate_asset_name')
        names.add(item['name'])
        if type(item.get('size')) is not int or not 0<=item['size']<2**31 or not re.fullmatch(r'[0-9a-f]{64}',str(item.get('sha256',''))):raise ReleaseError('invalid_asset_size_or_hash')
        item['resolved_path']=str((path.parent/item['path']).resolve())
    if not names:raise ReleaseError('empty_asset_plan')
    plan['resolved_body_path']=str((path.parent/plan['body_path']).resolve());return plan,digest(path)

def check_local(plan):
    body=Path(plan['resolved_body_path'])
    if not body.is_file() or digest(body)!=plan['body_sha256']:raise ReleaseError('local_body_hash_mismatch')
    for asset in plan['assets']:
        path=Path(asset['resolved_path'])
        if not path.is_file() or path.stat().st_size!=asset['size'] or digest(path)!=asset['sha256']:raise ReleaseError('local_asset_hash_or_size_mismatch')

def journal(path,event):
    allowed={'event','asset_name','asset_id','state','sha256','size','error_type','endpoint','status','release_id'}
    row={k:v for k,v in event.items() if k in allowed};row['time_ns']=time.time_ns()
    with LOCK:
        with Path(str(path)+'.journal.jsonl').open('a',encoding='utf-8') as f:f.write(json.dumps(row,ensure_ascii=True)+'\n');f.flush();os.fsync(f.fileno())

def journal_rows(path):
    file=Path(str(path)+'.journal.jsonl')
    return [json.loads(line) for line in file.read_text().splitlines() if line.strip()] if file.exists() else []

class ReleaseManager:
    def __init__(self,client,plan_path,registration):
        self.client=client;self.plan,self.plan_sha=load_plan(plan_path);self.registration=Path(registration).resolve();self.base='/repos/'+REPOSITORY
    def guards(self):
        user=self.client.json('GET','/user')
        if user.get('login')!=ACCOUNT:raise ReleaseError('authenticated_account_guard')
        repo=self.client.json('GET',self.base)
        if repo.get('full_name')!=REPOSITORY or repo.get('visibility')!='public' or repo.get('private') is not False:raise ReleaseError('repository_visibility_guard')
        if repo.get('permissions',{}).get('push') is not True or repo.get('permissions',{}).get('admin') is not True:raise ReleaseError('repository_push_permission_required')
        commit=self.client.json('GET',self.base+'/commits/'+self.plan['target_commit'])
        if commit.get('sha')!=self.plan['target_commit']:raise ReleaseError('target_commit_guard')
        endpoint=self.base+'/commits/'+quote(self.plan['tag'],safe='')
        response=self.client.request('GET',endpoint,allowed=(200,404))
        try:
            if response.status_code==200 and response.json().get('sha')!=self.plan['target_commit']:raise ReleaseError('existing_tag_commit_conflict')
        finally:response.close()
    def releases(self):
        result=[];page=1
        while True:
            rows=self.client.json('GET',self.base+'/releases?per_page=100&page='+str(page));result.extend(rows)
            if len(rows)<100:return result
            page+=1
    def bound(self, *, require_draft=True):
        reg=read(self.registration)
        if (reg.get('kind')!='created_release_registration' or reg.get('repository')!=REPOSITORY or reg.get('plan_sha256')!=self.plan_sha or reg.get('tag')!=self.plan['tag'] or reg.get('target_commit')!=self.plan['target_commit']):raise ReleaseError('registration_binding_guard')
        value=self.client.json('GET',self.base+'/releases/'+str(reg['release_id']))
        if (value.get('id')!=reg['release_id'] or value.get('tag_name')!=self.plan['tag'] or value.get('target_commitish')!=self.plan['target_commit'] or (require_draft and value.get('draft') is not True)):raise ReleaseError('release_identity_or_draft_guard')
        return reg,value
    def prepare(self):
        if self.registration.exists():raise ReleaseError('exclusive_registration_required')
        self.guards();check_local(self.plan)
        if any(r.get('tag_name')==self.plan['tag'] for r in self.releases()):raise ReleaseError('existing_release_for_tag')
        self.registration.parent.mkdir(parents=True,exist_ok=True)
        body_path=Path(self.plan['resolved_body_path'])
        body_bytes=body_path.read_bytes()
        if hashlib.sha256(body_bytes).hexdigest()!=self.plan['body_sha256']:raise ReleaseError('local_body_hash_mismatch')
        body=body_bytes.decode('utf-8')
        try:value=self.client.json('POST',self.base+'/releases',allowed=(201,),data={'tag_name':self.plan['tag'],'target_commitish':self.plan['target_commit'],'name':self.plan['tag'],'body':body,'draft':True,'prerelease':False})
        except ReleaseError:
            # Never retry creation: a lost POST response may already have created a draft.
            journal(self.registration,{'event':'prepare_ambiguous_manual_reconciliation_required'})
            raise
        if value.get('draft') is not True or type(value.get('id')) is not int or value.get('tag_name')!=self.plan['tag'] or value.get('target_commitish')!=self.plan['target_commit']:raise ReleaseError('created_release_response_guard')
        reg={'kind':'created_release_registration','repository':REPOSITORY,'release_id':value['id'],'tag':self.plan['tag'],'target_commit':self.plan['target_commit'],'html_url':value.get('html_url'),'plan_sha256':self.plan_sha,'created_at_ns':time.time_ns()}
        self.registration.parent.mkdir(parents=True,exist_ok=True)
        with self.registration.open('x',encoding='utf-8') as f:json.dump(reg,f,indent=2);f.write('\n')
        journal(self.registration,{'event':'draft_created','release_id':value['id']});return reg
    def assets(self,release_id):
        result=[];page=1
        while True:
            rows=self.client.json('GET',self.base+'/releases/'+str(release_id)+'/assets?per_page=100&page='+str(page));result.extend(rows)
            if len(rows)<100:return result
            page+=1
    def verify_asset(self,value,planned):
        if value.get('name')!=planned['name'] or value.get('size')!=planned['size'] or value.get('state')!='uploaded':raise ReleaseError('remote_asset_state_or_size_conflict')
        remote=value.get('digest')
        if remote is not None:
            if remote!='sha256:'+planned['sha256']:raise ReleaseError('remote_asset_digest_conflict')
            method='github_sha256_digest'
        else:
            # GitHub API binary downloads may redirect to signed blob URLs. Never forward auth there.
            endpoint=self.base+'/releases/assets/'+str(value['id'])
            response=self.client.request('GET',endpoint,allowed=(200,302),stream=True,headers={'Accept':'application/octet-stream'})
            if response.status_code==302:
                location=response.headers.get('Location','');response.close()
                from urllib.parse import urlsplit
                target=urlsplit(location)
                if target.scheme!='https' or target.hostname not in {'release-assets.githubusercontent.com','objects.githubusercontent.com'}:raise ReleaseError('asset_download_redirect_guard')
                try:response=requests.get(location,stream=True,timeout=(15,180),allow_redirects=False)
                except requests.RequestException:raise ReleaseError('asset_download_transport_failure',endpoint) from None
                if response.status_code!=200:
                    status=response.status_code;response.close();raise ReleaseError('asset_download_http_failure',endpoint,status)
            h=hashlib.sha256();size=0
            try:
                for block in response.iter_content(1024*1024):h.update(block);size+=len(block)
            except requests.RequestException:raise ReleaseError('asset_download_transport_failure',endpoint) from None
            finally:response.close()
            if size!=planned['size'] or h.hexdigest()!=planned['sha256']:raise ReleaseError('downloaded_asset_hash_conflict')
            method='streamed_download_sha256'
        return {'name':planned['name'],'asset_id':value['id'],'size':planned['size'],'sha256':planned['sha256'],'state':'uploaded','verification':method}
    def upload(self,recover_owned_failed=False):
        self.guards();reg,release=self.bound();check_local(self.plan)
        existing=self.assets(reg['release_id']);mapping={}
        for item in existing:
            if item['name'] in mapping:raise ReleaseError('duplicate_remote_asset_names')
            mapping[item['name']]=item
        planned_names={x['name'] for x in self.plan['assets']}
        if any(x not in planned_names for x in mapping):raise ReleaseError('unknown_remote_asset_present')
        owned={r['asset_id'] for r in journal_rows(self.registration) if r.get('event')=='owned_asset_response' and type(r.get('asset_id')) is int}
        def one(asset):
            prior=mapping.get(asset['name'])
            if prior:
                if prior.get('state')=='uploaded':return self.verify_asset(prior,asset)
                if not recover_owned_failed or prior.get('id') not in owned or prior.get('state') not in {'starter','failed'}:raise ReleaseError('unowned_or_unapproved_partial_asset')
                self.client.request('DELETE',self.base+'/releases/assets/'+str(prior['id']),allowed=(204,)).close()
            journal(self.registration,{'event':'upload_attempt','asset_name':asset['name'],'sha256':asset['sha256'],'size':asset['size']})
            endpoint='https://uploads.github.com/repos/'+REPOSITORY+'/releases/'+str(reg['release_id'])+'/assets?name='+quote(asset['name'],safe='')
            try:
                with Path(asset['resolved_path']).open('rb') as f:value=self.client.json('POST',endpoint,allowed=(201,),data=f,headers={'Content-Type':'application/octet-stream','Content-Length':str(asset['size'])})
                journal(self.registration,{'event':'owned_asset_response','asset_name':asset['name'],'asset_id':value.get('id'),'state':value.get('state')})
                result=self.verify_asset(value,asset)
                journal(self.registration,{'event':'asset_verified','asset_name':asset['name'],'asset_id':value['id'],'state':'uploaded','sha256':asset['sha256'],'size':asset['size']});return result
            except ReleaseError as error:
                journal(self.registration,{'event':'upload_failed','asset_name':asset['name'],**error.safe})
                # POST is never retried. A matching complete object is safe to verify;
                # an ambiguous partial object is not assigned ownership or deleted.
                found=[r for r in self.assets(reg['release_id']) if r.get('name')==asset['name']]
                if len(found)==1 and found[0].get('state')=='uploaded':return self.verify_asset(found[0],asset)
                raise
        results=[];failures=[]
        with ThreadPoolExecutor(max_workers=4) as pool:
            futures={pool.submit(one,a):a for a in self.plan['assets']}
            for future in as_completed(futures):
                try:results.append(future.result())
                except ReleaseError as error:failures.append(error.safe)
                except Exception:failures.append({'error_type':'unexpected_upload_failure','endpoint':'upload'})
        if failures:raise ReleaseError('upload_batch_incomplete')
        return {'release_id':reg['release_id'],'assets':sorted(results,key=lambda r:r['name'])}
    def verify(self,require_draft=False):
        self.guards();reg,release=self.bound(require_draft=require_draft);check_local(self.plan);values=self.assets(reg['release_id'])
        if len(values)!=len(self.plan['assets']) or {a['name'] for a in values}!={a['name'] for a in self.plan['assets']}:raise ReleaseError('remote_asset_inventory_conflict')
        mapping={a['name']:a for a in values}
        return {'release_id':reg['release_id'],'tag':reg['tag'],'target_commit':reg['target_commit'],'draft':release['draft'],'html_url':release.get('html_url'),'assets':[self.verify_asset(mapping[a['name']],a) for a in self.plan['assets']]}
    def publish(self):
        value=self.verify(require_draft=True)
        result=self.client.json('PATCH',self.base+'/releases/'+str(value['release_id']),data={'draft':False})
        if result.get('draft') is not False or result.get('tag_name')!=self.plan['tag'] or result.get('target_commitish')!=self.plan['target_commit']:raise ReleaseError('published_release_response_guard')
        verified=self.verify();journal(self.registration,{'event':'release_published','release_id':value['release_id']});return verified

def main():
    p=argparse.ArgumentParser();p.add_argument('--plan',required=True);p.add_argument('--registration',required=True);p.add_argument('command',choices=['prepare','upload','verify','publish']);p.add_argument('--recover-owned-failed',action='store_true');args=p.parse_args()
    try:
        # Reject invalid local plans before touching credential helper.
        load_plan(args.plan);manager=ReleaseManager(APIClient(credential()),args.plan,args.registration)
        result=manager.upload(args.recover_owned_failed) if args.command=='upload' else getattr(manager,args.command)()
        print(json.dumps({'status':'ok','command':args.command,'result':result},ensure_ascii=True))
    except ReleaseError as error:print(json.dumps({'status':'error',**error.safe}));raise SystemExit(1)
    except Exception:print(json.dumps({'status':'error','error_type':'unexpected_failure','endpoint':'local'}));raise SystemExit(1)

if __name__=='__main__':main()
