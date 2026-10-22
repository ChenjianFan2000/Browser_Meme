"use strict";
// Deployment-only interposition for the trusted frozen Node site process.
// Intentionally not an OS sandbox against arbitrary native code.
const net = require('node:net');
const fs = require('node:fs');
const {syncBuiltinESMExports} = require('node:module');
const own = Number(process.env.BM_ALLOWED_BACKEND_PORT);
const fixed = 12138;
const log = process.env.BM_CONNECTION_LOG;
if (!Number.isInteger(own) || ![13138,14138,15138,16138,17138,18138,19138,20138,21138,22138,23138,24138].includes(own) || !log) throw new Error('Unregistered worker transport');
const connect = net.Socket.prototype.connect;
const loopback = new Set(['localhost','127.0.0.1','::1','[::1]']);
function audit(row) { fs.appendFileSync(log, JSON.stringify({at_ns:process.hrtime.bigint().toString(),pid:process.pid,...row})+'\n'); }
function boundedConnect(...args) {
  const normalized=Array.isArray(args[0]) ? args[0] : net._normalizeArgs(args);
  const options=normalized[0];
  const callback=normalized[1];
  const host=String(options.host || 'localhost').toLowerCase();
  const port=Number(options.port);
  if (options.path || !loopback.has(host) || ![own,fixed].includes(port)) {
    audit({decision:'denied',requested_host:host,requested_port:Number.isFinite(port)?port:null,pipe:!!options.path});
    const error=new Error('Worker outbound connection denied');error.code='EACCES';
    // Socket APIs expect asynchronous connection errors (http/undici included).
    process.nextTick(()=>this.destroy(error));
    return this;
  }
  const target={...options,host:'127.0.0.1',port:own};
  delete target.lookup; // Never allow caller resolution to escape loopback.
  audit({decision:'allowed',requested_host:host,requested_port:port,target_host:'127.0.0.1',target_port:own,mapped:port===fixed});
  return callback ? connect.call(this,target,callback) : connect.call(this,target);
}
Object.defineProperty(net.Socket.prototype,'connect',{value:boundedConnect,writable:false,configurable:false});
syncBuiltinESMExports();
process.env.BM_WORKER_TRANSPORT_ACTIVE='v002';
audit({decision:'preload_active',own_backend_port:own,fixed_backend_port:fixed,node:process.version});
