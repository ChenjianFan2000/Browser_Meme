"""Mock only. Never invokes credential helper or network."""
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import threading
import time
import unittest
from urllib.parse import urlsplit,parse_qs
import requests

P=Path(__file__).with_name('github_release.py')
spec=importlib.util.spec_from_file_location('release_under_test',P);r=importlib.util.module_from_spec(spec);spec.loader.exec_module(r)
class Response:
    def __init__(self,status=200,value=None,content=b''):self.status_code=status;self.value=value;self.content=content;self.headers={}
    def json(self):return self.value
    def close(self):pass
    def iter_content(self,n):yield self.content
class Fake:
    def __init__(self,commit):
        self.commit=commit;self.login=r.ACCOUNT;self.repository=r.REPOSITORY;self.visibility='public';self.release=None;self.items=[];self.payloads={};self.posts=0;self.fail_after_upload=False;self.active=0;self.peak=0;self.lock=threading.Lock();self.calls=[];self.digest_missing=False
    def __call__(self,method,url,**kwargs):
        path=urlsplit(url).path;self.calls.append((method,path));base='/repos/'+r.REPOSITORY
        if path=='/user':return Response(value={'login':self.login})
        if path==base:return Response(value={'full_name':self.repository,'visibility':self.visibility,'private':self.visibility!='public','permissions':{'push':True,'admin':True}})
        if '/commits/' in path:return Response(value={'sha':self.commit}) if path.endswith(self.commit) or self.release else Response(404,{})
        if method=='GET' and path==base+'/releases':return Response(value=[self.release] if self.release else [])
        if method=='POST' and path==base+'/releases':
            self.posts+=1;self.release={'id':7,'tag_name':kwargs['json']['tag_name'],'target_commitish':kwargs['json']['target_commitish'],'draft':True,'html_url':'https://github.com/'+r.REPOSITORY+'/releases/tag/test'};return Response(201,dict(self.release))
        if method=='GET' and path==base+'/releases/7':return Response(value=dict(self.release))
        if method=='PATCH' and path==base+'/releases/7':self.release['draft']=False;return Response(value=dict(self.release))
        if method=='GET' and path==base+'/releases/7/assets':return Response(value=[dict(x) for x in self.items])
        if method=='POST' and 'uploads.github.com' in url:
            assert hasattr(kwargs['data'],'read'), 'upload must stream file object'
            with self.lock:self.active+=1;self.peak=max(self.peak,self.active)
            content=kwargs['data'].read();time.sleep(.005)
            with self.lock:
                name=parse_qs(urlsplit(url).query)['name'][0];item={'id':len(self.items)+10,'name':name,'state':'uploaded','size':len(content),'digest':None if self.digest_missing else 'sha256:'+hashlib.sha256(content).hexdigest()};self.items.append(item);self.payloads[item['id']]=content;self.active-=1
            if self.fail_after_upload:self.fail_after_upload=False;raise requests.ConnectionError('mock response lost')
            return Response(201,dict(item))
        if '/releases/assets/' in path:
            id=int(path.rsplit('/',1)[1])
            if method=='DELETE':self.items=[x for x in self.items if x['id']!=id];return Response(204)
            return Response(content=self.payloads[id])
        raise AssertionError(('unexpected mock endpoint',method,path))
class Tests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.base=Path(self.temp.name);self.commit='a'*40;(self.base/'body.md').write_text('Synthetic release')
        assets=[]
        for i in range(8):
            f=self.base/('part-'+str(i)+'.bin');f.write_bytes(('synthetic'+str(i)).encode());assets.append({'path':f.name,'name':f.name,'size':f.stat().st_size,'sha256':r.digest(f)})
        self.plan={'repository':r.REPOSITORY,'tag':'phase2-test','target_commit':self.commit,'body_path':'body.md','body_sha256':r.digest(self.base/'body.md'),'assets':assets,'approved_export_manifest':{'path':'synthetic','sha256':'b'*64}}
        self.planpath=self.base/'plan.json';self.writeplan();self.fake=Fake(self.commit);self.registration=self.base/'reg.json';self.manager=r.ReleaseManager(r.APIClient('SYNTHETIC_TOKEN_NOT_REAL',self.fake),self.planpath,self.registration)
    def tearDown(self):self.temp.cleanup()
    def writeplan(self):self.planpath.write_text(json.dumps(self.plan))
    def test_complete_four_concurrent_upload_resume_verify_publish(self):
        self.manager.prepare();uploaded=self.manager.upload();self.assertEqual(len(uploaded['assets']),8);self.assertLessEqual(self.fake.peak,4)
        before=len([c for c in self.fake.calls if c[0]=='POST']);self.manager.upload();self.assertEqual(before,len([c for c in self.fake.calls if c[0]=='POST']))
        self.assertFalse(self.manager.publish()['draft']);self.assertFalse(self.manager.verify()['draft'])
        with self.assertRaises(r.ReleaseError):self.manager.upload()
    def test_plan_and_account_repo_guards(self):
        self.fake.login='somebody_else'
        with self.assertRaises(r.ReleaseError):self.manager.prepare()
        self.fake.login=r.ACCOUNT;self.fake.visibility='private'
        with self.assertRaises(r.ReleaseError):self.manager.prepare()
        self.fake.visibility='public';self.plan['repository']='other/repo';self.writeplan()
        with self.assertRaises(r.ReleaseError):r.load_plan(self.planpath)
    def test_local_tamper_and_plan_binding(self):
        self.manager.prepare();(self.base/'part-0.bin').write_bytes(b'changed')
        with self.assertRaises(r.ReleaseError):self.manager.upload()
        self.plan['tag']='another';self.writeplan();other=r.ReleaseManager(self.manager.client,self.planpath,self.registration)
        with self.assertRaises(r.ReleaseError):other.bound()
    def test_remote_digest_conflict_never_deleted(self):
        self.manager.prepare();self.manager.upload();self.fake.items[0]['digest']='sha256:'+'0'*64
        with self.assertRaises(r.ReleaseError):self.manager.upload()
        self.assertFalse(any(c[0]=='DELETE' for c in self.fake.calls))
    def test_missing_digest_download_stream_verified(self):
        self.manager.prepare();self.fake.digest_missing=True;result=self.manager.upload();self.assertTrue(all(a['verification']=='streamed_download_sha256' for a in result['assets']))
    def test_lost_post_response_reconciles_no_duplicate(self):
        self.manager.prepare();self.fake.fail_after_upload=True;self.manager.upload();self.assertEqual(len(self.fake.items),8)
        self.assertEqual(len([c for c in self.fake.calls if c[0]=='POST' and c[1].endswith('/assets')]),8)
    def test_unknown_asset_and_unowned_partial_fail(self):
        self.manager.prepare();self.fake.items=[{'id':99,'name':'foreign','state':'starter','size':0}]
        with self.assertRaises(r.ReleaseError):self.manager.upload(True)
        self.fake.items[0]['name']=self.plan['assets'][0]['name']
        with self.assertRaises(r.ReleaseError):self.manager.upload(True)
        self.assertFalse(any(c[0]=='DELETE' for c in self.fake.calls))
    def test_owned_partial_requires_explicit_recovery(self):
        self.manager.prepare();self.fake.items=[{'id':99,'name':self.plan['assets'][0]['name'],'state':'starter','size':0}]
        r.journal(self.registration,{'event':'owned_asset_response','asset_id':99,'asset_name':self.plan['assets'][0]['name']})
        with self.assertRaises(r.ReleaseError):self.manager.upload()
        self.manager.upload(True);self.assertTrue(any(c[0]=='DELETE' for c in self.fake.calls));self.assertEqual(len(self.fake.items),8)
    def test_prepare_exclusive_and_existing_tag_conflict(self):
        self.manager.prepare()
        with self.assertRaises(r.ReleaseError):self.manager.prepare()
        another=r.ReleaseManager(self.manager.client,self.planpath,self.base/'another.json')
        with self.assertRaises(r.ReleaseError):another.prepare()
    def test_body_hash_required_and_body_tamper(self):
        saved=self.plan.pop('body_sha256');self.writeplan()
        with self.assertRaises(r.ReleaseError):r.load_plan(self.planpath)
        self.plan['body_sha256']=saved;self.writeplan()
        (self.base/'body.md').write_text('unregistered body')
        with self.assertRaises(r.ReleaseError):self.manager.prepare()
        self.assertEqual(self.fake.posts,0)
    def test_body_tamper_after_prepare_blocks_publish(self):
        self.manager.prepare();self.manager.upload();(self.base/'body.md').write_text('changed after prepare')
        with self.assertRaises(r.ReleaseError):self.manager.publish()
        self.assertTrue(self.fake.release['draft'])
    def test_safe_errors_and_get_only_retry(self):
        calls=[]
        def bad(method,url,**kw):calls.append(method);raise requests.ConnectionError('DO_NOT_ECHO_SECRET')
        client=r.APIClient('SECRET',bad)
        for method,count in [('GET',3),('POST',1)]:
            calls.clear()
            with self.assertRaises(r.ReleaseError) as caught:client.request(method,'/user')
            self.assertEqual(len(calls),count);self.assertNotIn('SECRET',json.dumps(caught.exception.safe));self.assertNotIn('SECRET',str(caught.exception))
if __name__=='__main__':unittest.main()
