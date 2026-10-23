"""Private enum-only acquisition telemetry; never an input to stability decisions."""
from collections import Counter
import json
import math
from pathlib import Path
import re
import time
from urllib.parse import urlsplit

SCHEMA = 'acquisition-diagnostics/v1'
KINDS = frozenset({'closed_shadow_root','unresolved_frame_dom','unresolved_frame_id','capture_error',
    'unsupported_frame_origin','missing_or_multiple_body','accessible_name_exceeds_900',
    'frame_topology_changed_after_acquisition','dom_ax_capture_unsupported','semantic_capture_error'})
ERROR_TYPES = frozenset({'Error','TimeoutError','TargetClosedError','RuntimeError','ValueError',
    'KeyError','TypeError','AttributeError','NotImplementedError','AssertionError','OSError'})
RESOURCES = frozenset({'document','stylesheet','image','media','font','script','texttrack','xhr',
    'fetch','eventsource','websocket','manifest','other'})
METHODS = frozenset({'GET','HEAD','POST','PUT','PATCH','DELETE','OPTIONS','CONNECT','TRACE'})


def error_category(value):
    # Classify transiently; no original exception string or class is persisted.
    try:text = str(value).lower()
    except Exception:return 'other'
    for token, category in (('frame has been detached','frame_detached'),('frame was detached','frame_detached'),
        ('execution context was destroyed','execution_context_destroyed'),('target closed','target_closed'),
        ('target page, context or browser has been closed','target_closed'),('timeout','timeout'),
        ('err_aborted','aborted'),('err_connection','connection_failure'),('err_name_not_resolved','dns_failure')):
        if token in text:return category
    return 'other'


def exception_summary(error):
    name = type(error).__name__
    return {'error_type':name if name in ERROR_TYPES else 'other','error_category':error_category(error)}


def unsupported_summary(items):
    if not isinstance(items,list):return [{'kind':'invalid_unsupported_structure'}]
    result=[]
    for item in items[:128]:
        if not isinstance(item,dict):result.append({'kind':'unknown'});continue
        kind=item.get('kind');record={'kind':kind if isinstance(kind,str) and kind in KINDS else 'unknown'}
        frame=item.get('frame')
        if isinstance(frame,str) and re.fullmatch(r'f[0-9]{1,8}',frame):record['frame']=frame
        count=item.get('count')
        if isinstance(count,int) and not isinstance(count,bool) and 0<=count<=1000000:record['count']=count
        if 'error_type' in item:record['error_type']=item['error_type'] if isinstance(item['error_type'],str) and item['error_type'] in ERROR_TYPES else 'other'
        if 'error' in item:record['error_category']=error_category(item['error'])
        if isinstance(item.get('detail'),dict):record['detail']=unsupported_summary([item['detail']])[0]
        result.append(record)
    if len(items)>128:result.append({'kind':'additional_records_omitted','count':len(items)-128})
    return result


def capture_summary(snapshot=None,canonical=None):
    result={}
    if isinstance(snapshot,dict):
        semantic=snapshot.get('semantics',{})
        semantic=semantic if isinstance(semantic,dict) else {}
        timing=semantic.get('timing',{})
        timing=timing if isinstance(timing,dict) else {}
        for key in ('full_dom_ax_seconds','long_name_guard_seconds','elapsed_seconds'):
            value=timing.get(key)
            if isinstance(value,(int,float)) and not isinstance(value,bool) and math.isfinite(value) and value>=0:
                result[{'elapsed_seconds':'semantic_capture_seconds'}.get(key,key)]=value
        raw=snapshot.get('raw',{})
        raw=raw if isinstance(raw,dict) else {}
        result['raw_unsupported']=unsupported_summary(raw.get('unsupported',[]))
        result['semantics_unsupported']=unsupported_summary(semantic.get('unsupported',[]))
    if isinstance(canonical,dict):result['canonical_unsupported']=unsupported_summary(canonical.get('unsupported',[]))
    return result


class NetworkDiagnostics:
    """Mirrors request lifecycle without changing the runtime's pending dictionary."""
    def __init__(self,origin,path,clock=time.monotonic):
        self.origin=origin;self.clock=clock;self.started=clock();self.serial=0;self.events=0
        self.active={};self.counts=Counter();self.write_errors=0;self.write_seconds=0.0
        self.body_reads_active=0;self.maximum_body_read_seconds=0.0
        self.stream=None
        try:self.stream=Path(path).open('x',encoding='utf-8')
        except OSError:self.write_errors+=1

    def _metadata(self,request):
        self.serial+=1;result={'request':self.serial}
        try:resource=request.resource_type
        except Exception:resource='other'
        result['resource_type']=resource if isinstance(resource,str) and resource in RESOURCES else 'other'
        try:
            parsed=urlsplit(request.url);registered=urlsplit(self.origin)
            result['origin_class']='same_origin' if (parsed.scheme,parsed.netloc)==(registered.scheme,registered.netloc) else 'other_origin' if parsed.scheme in {'http','https'} else 'non_http'
        except Exception:result['origin_class']='unknown'
        try:method=request.method
        except Exception:method='other'
        result['method']=method if isinstance(method,str) and method in METHODS else 'other'
        try:result['navigation']=bool(request.is_navigation_request())
        except Exception:result['navigation']=False
        try:result['redirect_parent_present']=request.redirected_from is not None
        except Exception:result['redirect_parent_present']=False
        return result

    def _emit(self,event,metadata=None,**fields):
        self.events+=1;self.counts[event]+=1
        record={'schema':SCHEMA,'sequence':self.events,'elapsed_seconds':self.clock()-self.started,
                'event':event,**(metadata or {}),**fields}
        begun=time.monotonic()
        if self.stream is not None and not self.stream.closed:
            try:self.stream.write(json.dumps(record,allow_nan=False,separators=(',',':'))+'\n');self.stream.flush()
            except (OSError,ValueError):self.write_errors+=1
        self.write_seconds+=time.monotonic()-begun

    def start(self,request):
        key=id(request)
        if key in self.active:self._emit('duplicate_start',self.active[key]);return
        value={**self._metadata(request),'started':self.clock()};self.active[key]=value
        self._emit('request_started',{k:v for k,v in value.items() if k!='started'})

    def finish(self,request,failed=False):
        value=self.active.pop(id(request),None)
        if value is None:self._emit('unmatched_request_failed' if failed else 'unmatched_request_finished');return
        fields={}
        if failed:
            try:fields['failure_category']=error_category(request.failure)
            except Exception:fields['failure_category']='other'
        self._emit('request_failed' if failed else 'request_finished',{k:v for k,v in value.items() if k!='started'},
                   lifetime_seconds=max(0,self.clock()-value['started']),**fields)

    def response_begin(self,request):
        value=self.active.get(id(request))
        metadata={k:v for k,v in value.items() if k!='started'} if value else self._metadata(request)
        self._emit('response_callback_begin',metadata,matched_pending=value is not None)
        return metadata,self.clock()

    def body_begin(self,token):
        self.body_reads_active+=1;self._emit('response_body_begin',token[0]);return self.clock()

    def body_end(self,token,begun,error=None):
        elapsed=max(0,self.clock()-begun);self.body_reads_active=max(0,self.body_reads_active-1)
        self.maximum_body_read_seconds=max(self.maximum_body_read_seconds,elapsed)
        self._emit('response_body_end',token[0],duration_seconds=elapsed,
                   outcome='error' if error else 'completed',**(exception_summary(error) if error else {}))

    def response_end(self,token):
        self._emit('response_callback_end',token[0],duration_seconds=max(0,self.clock()-token[1]))

    def snapshot(self,actual_pending_count):
        now=self.clock();pending=sorted(self.active.values(),key=lambda x:x['request'])
        return {'schema':SCHEMA,'event_file':'acquisition-network.jsonl','private_control_plane_only':True,
            'pending_request_count':actual_pending_count,'diagnostic_active_count':len(pending),
            'pending':[{**{k:v for k,v in value.items() if k!='started'},'age_seconds':max(0,now-value['started'])} for value in pending[:128]],
            'pending_omitted':max(0,len(pending)-128),'lifecycle_counts':dict(self.counts),
            'body_reads_active':self.body_reads_active,'maximum_body_read_seconds':self.maximum_body_read_seconds,
            'telemetry_write_seconds':self.write_seconds,'telemetry_write_errors':self.write_errors,
            'privacy':'fixed enums, ordinal request IDs, counts and timings only; no URL, host, path, headers, body or original error text'}

    def close(self):
        if self.stream is not None:
            try:self.stream.close()
            except OSError:self.write_errors+=1
