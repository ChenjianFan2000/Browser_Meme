'use strict';
const fs=require('node:fs'),http=require('node:http'),https=require('node:https'),net=require('node:net'),tls=require('node:tls');
const own=Number(process.env.BM_ALLOWED_BACKEND_PORT),foreign=process.env.BM_FOREIGN_BACKEND_PORTS.split(',').map(Number);
const fixture=JSON.parse(fs.readFileSync(process.env.BM_FIXTURE_FILE,'utf8').replace(/^\uFEFF/,''));
const results=[];
function httpCall(port,path='/healthz',method='GET',body=null,token=null){return new Promise((resolve,reject)=>{
 const headers={};if(body){headers['Content-Type']='application/json';headers['Content-Length']=Buffer.byteLength(body);}if(token)headers.Authorization='Bearer '+token;
 const request=http.request({host:'localhost',port,path,method,headers},response=>{let data='';response.on('data',chunk=>data+=chunk);response.on('end',()=>resolve({status:response.statusCode,body:data}));});request.on('error',reject);request.setTimeout(5000,()=>request.destroy(new Error('timeout')));if(body)request.write(body);request.end();});}
function rawCall(port,options={}){return new Promise((resolve,reject)=>{const socket=net.createConnection({host:'localhost',port,...options});let data='';socket.setTimeout(5000,()=>socket.destroy(new Error('timeout')));socket.on('connect',()=>socket.write('GET /healthz HTTP/1.1\r\nHost: localhost\r\nConnection: close\r\n\r\n'));socket.on('data',chunk=>data+=chunk);socket.on('end',()=>resolve(data));socket.on('error',reject);});}
function denied(error){return error?.code==='EACCES'||error?.cause?.code==='EACCES';}
async function expectDenied(name,call){try{await call();results.push({name,passed:false,reason:'unexpected_connection'});}catch(error){results.push({name,passed:denied(error),code:error.code||error.cause?.code||'unknown'});}}
(async()=>{
 results.push({name:'http_fixed_loopback_maps_own',passed:(await httpCall(12138)).status===200});
 results.push({name:'net_fixed_loopback_maps_own',passed:(await rawCall(12138)).includes('200 OK')});
 results.push({name:'undici_fetch_fixed_maps_own',passed:(await fetch('http://localhost:12138/healthz')).status===200});
 results.push({name:'lookup_cannot_escape_loopback',passed:(await rawCall(own,{lookup:(_,__,callback)=>callback(null,'203.0.113.1',4)})).includes('200 OK')});
 const login=await httpCall(own,'/auth/login','POST',JSON.stringify({username_or_email:fixture.account.username,password:fixture.account.password}));
 const token=JSON.parse(login.body).access_token;if(!token)throw new Error('Public fixture authentication failed');
 const ownWrite=await httpCall(own,'/me/collection/1','POST',null,token);
 results.push({name:'own_business_write',passed:ownWrite.status===200});
 for(const port of foreign){
  await expectDenied('http_foreign_write_'+port,()=>httpCall(port,'/me/collection/1','POST',null,token));
  await expectDenied('net_foreign_'+port,()=>rawCall(port));
  await expectDenied('undici_foreign_write_'+port,()=>fetch('http://127.0.0.1:'+port+'/me/collection/1',{method:'POST',headers:{Authorization:'Bearer '+token}}));
  await expectDenied('tls_foreign_'+port,()=>new Promise((resolve,reject)=>{const socket=tls.connect({host:'localhost',port,rejectUnauthorized:false});socket.on('error',reject);socket.on('secureConnect',resolve);}));
 }
 await expectDenied('original_frontend_denied',()=>httpCall(12042));
 await expectDenied('external_destination_denied',()=>rawCall(443,{host:'203.0.113.1'}));
 const record={kind:'management_transport_probe_not_learner',own_backend_port:own,checks:results,passed:results.filter(r=>r.passed).length,total:results.length};
 fs.writeFileSync(process.env.BM_PROBE_OUTPUT,JSON.stringify(record,null,2),{flag:'wx'});console.log(JSON.stringify({passed:record.passed,total:record.total}));
 if(record.passed!==record.total)process.exitCode=1;
})().catch(error=>{console.error(error.name+': '+error.message);process.exitCode=1;});
