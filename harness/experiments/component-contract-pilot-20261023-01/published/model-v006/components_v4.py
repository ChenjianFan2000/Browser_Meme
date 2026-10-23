"""Native locator/extraction utilities; no task flows and no pre-recorded objects."""
def expectation(contract_ref,branch='ready',parameters=None,unknown_slots=None,disposition='accepted'):
    if contract_ref in ['jobs.search','jobs.collection'] and branch=='ready' and unknown_slots is None:unknown_slots=['rows.*.title','rows.*.company','rows.*.location_mode','rows.*.save_label']
    return {'disposition':disposition,'contract_ref':contract_ref,'branch':branch,'parameters':parameters or {},'unknown_slots':unknown_slots or []}
def job_rows(page):
    return page.locator('button.w-full').filter(has=page.locator('div.truncate'))
def public_jobs(page):
    rows=job_rows(page)
    data=[]
    for i in range(rows.count()):
        fields=rows.nth(i).locator('div.truncate').all_text_contents()
        if len(fields)!=3:
            return []
        data.append({'title':fields[0],'company':fields[1],'location_mode':fields[2]})
    return data

def job_row(page,identity):
    return job_rows(page).filter(has=page.get_by_text(identity['title'],exact=True)).filter(has=page.get_by_text(identity['company'],exact=True)).filter(has=page.get_by_text(identity['location_mode'],exact=True))
def detail(page):
    return page.locator('div.p-5').filter(has=page.get_by_text('About the job',exact=True))
def post_card(page,body):
    return page.locator('.linkedin-card').filter(has=page.get_by_text(body,exact=True))
def deterministic_job(data):
    ordered=sorted(data,key=lambda r:(r['title'],r['company'],r['location_mode']))
    if not ordered:return None
    target=ordered[0]
    if sum(1 for r in data if r==target)!=1:return None
    return target
def detail_parameters(identity,save_label):
    fields=identity['location_mode'].split(' • ')
    if len(fields)!=2:return None
    return {'title':identity['title'],'company':identity['company'],'location':fields[0],'mode_text':'• '+fields[1],'save_label':save_label}
def business_prediction(contract_ref,branch='ready',parameters=None,unknown_slots=None,changed=None,affected=None,business_state=None,disposition='accepted'):
    p=expectation(contract_ref,branch,parameters,unknown_slots,disposition)
    p['effects']={'persistent_state_changed':changed,'affected_record_count':affected}
    if business_state is not None:p['expected_business_state']=business_state
    return p

import json
OPERATIONS={
 'navigate':{'business_change':False,'records':0,'guard':'known route; protected routes require authentication'},
 'auth_success':{'business_change':False,'records':0,'guard':'login form and public valid account'},
 'auth_reject':{'business_change':False,'records':0,'guard':'login form and format-valid wrong password'},
 'search':{'business_change':False,'records':0,'guard':'authenticated jobs'},
 'select_job':{'business_change':False,'records':0,'guard':'unique bound public job identity'},
 'save':{'business_change':True,'records':1,'guard':'selected job and known current save state'},
 'apply':{'business_change':True,'records':1,'guard':'selected job and not already applied'},
 'open_composer':{'business_change':False,'records':0,'guard':'authenticated feed'},
 'fill_post':{'business_change':False,'records':0,'guard':'composer open'},
 'create_post':{'business_change':True,'records':1,'guard':'composer open and nonempty trimmed body'},
 'like':{'business_change':True,'records':1,'guard':'unique bound post and known liked/count'},
 'open_comments':{'business_change':False,'records':0,'guard':'unique bound post'},
 'fill_comment':{'business_change':False,'records':0,'guard':'comment form open'},
 'comment':{'business_change':True,'records':1,'guard':'comment form open and nonempty body'},
 'form_edit':{'business_change':False,'records':0,'guard':'current component; unauthenticated edits restricted to login'},
 'reload':{'business_change':False,'records':0,'guard':'known current component'}
}
def initial_state():
 return {'entities':{},'reconciliation':[],'absent_posts':[],'route':'/login','authenticated':False,'query':'','location':'','selected_job':None,'rows':None,'jobs':{},'posts':{},'composer':False,'body':'','comments_for':None,'comment_body':'','delta':{'created_posts':0,'created_comments':0,'reactions_added':0,'reactions_removed':0,'saved_jobs_added':0,'saved_jobs_removed':0,'applications_added':0,'applications_removed':0}}
def clone(value):return json.loads(json.dumps(value))
def identity_key(identity):return json.dumps([identity['title'],identity['company'],identity['location_mode']])
def bind_job(state,identity,saved,applied,applicants):
 consistency=registry_consistency(state)
 if not consistency['ok']:return consistency
 if not valid_identity(identity) or not isinstance(saved,bool) or applied is not None and not isinstance(applied,bool) or applicants is not None and (not isinstance(applicants,int) or isinstance(applicants,bool) or applicants<0):return guard_failure('ill-typed public job observation')
 s=clone(state);key=identity_key(identity)
 if key not in s['jobs']:
  s['jobs'][key]={'identity':identity,'saved':saved,'baseline_saved':saved,'applied':applied,'baseline_applied':applied,'applicants':applicants}
 else:
  j=s['jobs'][key]
  for field,value in [('saved',saved),('applied',applied),('applicants',applicants)]:
   if value is not None:
    if j[field] is not None and j[field]!=value:return guard_failure('observed job state contradicts predicted '+field)
    j[field]=value
  if j['baseline_applied'] is None:j['baseline_applied']=applied
 return checked_state(s)
def bind_post(state,body,liked,reactions,comments,unique):
 if not isinstance(body,str) or not isinstance(liked,bool) or not isinstance(reactions,int) or isinstance(reactions,bool) or reactions<0 or not isinstance(comments,int) or isinstance(comments,bool) or comments<0 or unique is not True:return guard_failure('ill-typed or ambiguous post observation')
 if sum(1 for entity in state.get('entities',{}).values()if entity['known'].get('body')==body)>1:return guard_failure('ambiguous same-body entities cannot bind through body key')
 consistency=registry_consistency(state)
 if not consistency['ok']:return consistency
 observed={'liked':liked,'reactions':reactions,'comments':comments}
 handles=entity_handles_for_body(state,body)
 if len(handles)==1:
  conflicts=shared_post_conflicts(state['entities'][handles[0]]['known'],observed)
  if conflicts:return registry_conflict('bind_post disagrees with registered entity',body,conflicts)
 s=clone(state)
 s['absent_posts']=[item for item in s['absent_posts']if item!=body]
 if body not in s['posts']:
  s['posts'][body]=dict(observed,baseline_liked=liked,fresh=False)
  s.setdefault('reconciliation',[]).append({'kind':'initial_binding','body':body,'observed':observed})
 else:
  prior=s['posts'][body]
  if any(prior[key]!=observed[key] for key in observed):
   return {'ok':False,'readpoint':'post observation contradicts stored state','reconciliation':{'kind':'contradiction','body':body,'prior':clone(prior),'observed':observed,'state_changed':False}}
  s.setdefault('reconciliation',[]).append({'kind':'consistent','body':body,'observed':observed})
 if len(handles)==1:
  s['entities'][handles[0]]['known'].update(observed)
  s['entities'][handles[0]]['provenance'].append('consistent bind_post observation')
 return checked_state(s)
def guard_failure(reason):return {'ok':False,'readpoint':reason}
def component_for(state):
 if state['route']=='/login':return expectation('auth.login')
 if state['route']=='/feed':return expectation('feed.ready')
 if state['route']=='/jobs':return expectation('jobs.search',parameters={'query':state['query'],'location':state['location']})
 return None

def plan(state,action,parameters=None):
 consistency=registry_consistency(state)
 if not consistency['ok']:return consistency
 p=parameters or {};s=clone(state)
 required={'navigate':['path'],'search':['query','location'],'select_job':['identity'],'fill_post':['body'],'like':['body'],'open_comments':['body'],'fill_comment':['body','text'],'comment':['body']}
 if not isinstance(p,dict) or any(k not in p for k in required.get(action,[])):return guard_failure('missing action parameter')
 if any(k in p and not isinstance(p[k],str) for k in ['path','query','location','body','text']):return guard_failure('ill-typed action parameter')
 if 'identity' in p and not valid_identity(p['identity']):return guard_failure('ill-typed identity')
 if action not in OPERATIONS:return guard_failure('unmodeled action semantics')
 if action in ['like','open_comments','fill_comment','comment'] and sum(1 for entity in s.get('entities',{}).values() if entity['known'].get('body')==p.get('body'))>1:return guard_failure('duplicate-content entity registry requires richer action contract; body-keyed write unsupported')
 if not s['authenticated']:
  if action=='form_edit':
   component=p.get('component') or component_for(s)
   if s['route']!='/login' or not isinstance(component,dict) or component.get('contract_ref')!='auth.login' or component.get('branch') not in ['ready','rejected']:return guard_failure('unauthenticated form edit requires current login component')
  elif action not in ['navigate','auth_success','auth_reject']:return guard_failure('authentication required')
 changed=OPERATIONS[action]['business_change'];records=OPERATIONS[action]['records'];claim=None
 if action=='navigate':
  route=p['path']
  if route not in ['/login','/feed','/jobs']:return guard_failure('route outside model')
  if route in ['/feed','/jobs'] and not s['authenticated']:return guard_failure('authentication required for protected route; redirect branch unsupported')
  s['route']=route
  if route=='/jobs':s['query']=p.get('query','bioinformatician jobs');s['location']=p.get('location','United States')
  claim=component_for(s)
 elif action=='auth_success':
  if s['route']!='/login':return guard_failure('login form not current')
  s['authenticated']=True;s['route']='/feed';claim=expectation('feed.ready')
 elif action=='auth_reject':
  if s['route']!='/login':return guard_failure('login form not current')
  claim=expectation('auth.login',branch='rejected',disposition='rejected')
 elif action=='search':
  if s['route']!='/jobs':return guard_failure('jobs route required')
  s['query']=p['query'];s['location']=p['location'];s['selected_job']=None;s['rows']=None
  claim=expectation('jobs.search',parameters={'query':s['query'],'location':s['location']})
 elif action=='select_job':
  key=identity_key(p['identity'])
  if s['route']!='/jobs' or s['rows'] is None or sum(1 for r in s['rows'] if r==p['identity'])!=1 or key not in s['jobs']:return guard_failure('unique publicly bound job required')
  s['selected_job']=key;j=s['jobs'][key];claim=expectation('jobs.detail',parameters=detail_parameters(j['identity'],'Saved' if j['saved'] else 'Save'))
 elif action in ['save','apply']:
  key=s['selected_job']
  if s['route']!='/jobs' or key is None or key not in s['jobs']:return guard_failure('explicit selected bound job required')
  j=s['jobs'][key]
  if action=='save':
   old=j['saved'];j['saved']=not old
   add='saved_jobs_removed' if j['baseline_saved'] else 'saved_jobs_added'
   s['delta'][add]+=1 if j['saved']!=j['baseline_saved'] else -1
   claim=expectation('jobs.detail',parameters=detail_parameters(j['identity'],'Saved' if j['saved'] else 'Save'))
  else:
   if j['applied'] is None or j['applicants'] is None:return guard_failure('application state/applicants unknown_external; read selected public detail')
   if j['applied']:return guard_failure('already Applied is disabled; no repeat write')
   j['applied']=True;j['applicants']+=1;s['delta']['applications_added']+=1
   d=detail_parameters(j['identity'],'Saved' if j['saved'] else 'Save');d['applicants_text']=str(j['applicants']);claim=expectation('jobs.applied',parameters=d)
 elif action in ['open_composer','fill_post','create_post']:
  if s['route']!='/feed':return guard_failure('feed required')
  if action=='open_composer':s['composer']=True;s['body']=''
  elif not s['composer']:return guard_failure('composer not open')
  if action=='fill_post':s['body']=p['body']
  if action=='create_post':
   body=s['body'].strip()
   if not body:
    changed=False;records=0;claim=expectation('post.composer',branch='open',parameters={'body':s['body']},disposition='rejected')
   else:
    if body in s['posts'] or entity_handles_for_body(s,body) or body not in s['absent_posts']:return guard_failure('fresh body absence must be checked on public UI before submit')
    s['absent_posts']=[item for item in s['absent_posts']if item!=body]
    s['posts'][body]={'liked':False,'baseline_liked':False,'reactions':0,'comments':0,'fresh':True};s['delta']['created_posts']+=1;s['composer']=False;claim=expectation('post.body',branch='present',parameters={'body':body})
  else:claim=expectation('post.composer',branch='open',parameters={'body':s['body']})
 elif action in ['like','open_comments','fill_comment','comment']:
  body=p['body']
  if s['route']!='/feed' or body not in s['posts']:return guard_failure('bound unique post required')
  post=s['posts'][body]
  if action=='like':
   if any(s['delta'][key] is None for key in ['reactions_added','reactions_removed']):return guard_failure('external reaction delta baseline unknown; establish fresh baseline before write')
   post['liked']=not post['liked'];post['reactions']+=1 if post['liked'] else -1
   domain='reactions_removed' if post['baseline_liked'] else 'reactions_added';s['delta'][domain]+=1 if post['liked']!=post['baseline_liked'] else -1
   claim=expectation('post.reaction',parameters={'body':body,'like_label':'Liked' if post['liked'] else 'Like','reactions_text':str(post['reactions'])})
  elif action=='open_comments':s['comments_for']=body;s['comment_body']='';claim=expectation('post.comments',parameters={'body':body,'input':''})
  elif s['comments_for']!=body:return guard_failure('comment form not open for target')
  elif action=='fill_comment':s['comment_body']=p['text'];claim=expectation('post.comments',parameters={'body':body,'input':s['comment_body']})
  else:
   if not s['comment_body'].strip():return guard_failure('empty comment branch not verified')
   if s['delta']['created_comments'] is None:return guard_failure('external comment delta baseline unknown; establish fresh baseline before write')
   text=s['comment_body'].strip();post['comments']+=1;s['delta']['created_comments']+=1;s['comment_body']='';claim=expectation('post.comment_created',parameters={'body':body,'comment':text})
 elif action=='form_edit':claim=p.get('component') or component_for(s)
 elif action=='reload':claim=p.get('component') or component_for(s)
 if action in ['like','comment'] and p.get('body') in s['posts']:
  body=p['body'];handles=[key for key,entity in s.get('entities',{}).items()if entity['known'].get('body')==body]
  if len(handles)==1:
   for key in ['liked','reactions','comments']:s['entities'][handles[0]]['known'][key]=s['posts'][body][key]
 if claim is None or claim.get('parameters') is None:return guard_failure('cannot generate target component')
 claim['effects']={'persistent_state_changed':changed,'affected_record_count':None if action in ['like','comment'] else records}
 expected={'route.path':s['route'],'session.authenticated':s['authenticated']}
 for domain,count in s['delta'].items():
  if isinstance(count,int) and not isinstance(count,bool):expected['persistent_delta.'+domain+'.count']=count
 claim['expected_business_state']=expected
 consistency=registry_consistency(s)
 if not consistency['ok']:return consistency
 return {'ok':True,'prediction':claim,'state':s,'action':action,'guard':OPERATIONS[action]['guard']}

def valid_identity(identity):
 return isinstance(identity,dict) and all(k in identity and isinstance(identity[k],str) for k in ['title','company','location_mode'])
def bind_rows(state,rows):
 consistency=registry_consistency(state)
 if not consistency['ok']:return consistency
 if not isinstance(rows,list) or not all(valid_identity(r) for r in rows):return guard_failure('ill-typed external rows')
 s=clone(state);s['rows']=clone(rows);return checked_state(s)

def bind_post_absence(state,body,matching_cards):
 consistency=registry_consistency(state)
 if not consistency['ok']:return consistency
 if not isinstance(body,str) or matching_cards!=0 or isinstance(matching_cards,bool):return guard_failure('post body not publicly absent')
 if body in state['posts'] or entity_handles_for_body(state,body):return guard_failure('current-view absence cannot erase a known object or establish a fresh body')
 s=clone(state)
 if body not in s['absent_posts']:s['absent_posts'].append(body)
 return checked_state(s)
def collection_prediction():
 return expectation('jobs.collection',branch='ready')
def current_post_observation(page,body):
 card=post_card(page,body)
 if card.count()!=1:return None
 liked=card.get_by_role('button',name='👍 Liked',exact=True).count()==1
 count=card.locator('span.ml-1').inner_text()
 comments=card.get_by_role('button').filter(has_text='comments').inner_text().split(' ')[0]
 if not count.isdigit() or not comments.isdigit():return None
 return {'liked':liked,'reactions':int(count),'comments':int(comments)}
def symbolic_value(value,parameters):
 if isinstance(value,dict):
  if '$param' in value:
   return clone(parameters[value['$param']]) if value['$param'] in parameters else {'$unknown':{'parameter':value['$param'],'status':'unknown_external'}}
  if '$slot' in value:return {'$unknown':{'slot':value['$slot'],'status':'unknown_external'}}
  return {key:symbolic_value(item,parameters) for key,item in value.items()}
 if isinstance(value,list):return [symbolic_value(item,parameters) for item in value]
 return value
def symbolic_component(contract,branch,parameters):
 if branch not in contract['branches']:return guard_failure('unknown contract branch')
 return {'schema':'symbolic-component-tree/v2','tree':symbolic_value(contract['branches'][branch].get('tree',{}),parameters),'parameters':clone(parameters),'claim':'symbolic component, not full page rendering'}

def normalize_job_row_binding(binding):
 if not isinstance(binding,dict) or not all(k in binding for k in ['title','company','location_mode','save_label']):return guard_failure('missing job slot binding')
 if not isinstance(binding['title'],str) or not isinstance(binding['company'],str) or binding['save_label'] not in ['Save','Saved']:return guard_failure('ill-typed job field binding')
 parts=binding['location_mode']
 if not isinstance(parts,list) or len(parts)!=3 or not all(isinstance(x,str)for x in parts) or parts[1]!=' • ':return guard_failure('unrecognized location slot leaves')
 return {'ok':True,'identity':{'title':binding['title'],'company':binding['company'],'location_mode':''.join(parts)},'saved':binding['save_label']=='Saved','raw_slots':clone(binding)}
def normalize_visible_job(identity,saved):
 if not valid_identity(identity) or not isinstance(saved,bool):return guard_failure('ill-typed visible job')
 parts=identity['location_mode'].split(' • ')
 if len(parts)!=2:return guard_failure('ambiguous visible location delimiter')
 return normalize_job_row_binding({'title':identity['title'],'company':identity['company'],'location_mode':[parts[0],' • ',parts[1]],'save_label':'Saved' if saved else 'Save'})
def entity_signature(observation):
 return {key:observation[key]for key in ['body','author','liked','reactions','comments']if key in observation}
def register_entity(state,handle,observation,provenance):
 if not isinstance(handle,str) or not isinstance(observation,dict) or not isinstance(provenance,str) or not valid_entity_observation(observation):return guard_failure('ill-typed entity registration')
 consistency=registry_consistency(state)
 if not consistency['ok']:return consistency
 if handle in state['entities']:return guard_failure('entity handle already registered; reconcile explicitly')
 body=observation['body'];handles=entity_handles_for_body(state,body);known=entity_signature(observation)
 if not handles and body in state['posts']:
  conflicts=shared_post_conflicts(state['posts'][body],known)
  if conflicts:return registry_conflict('registered entity disagrees with existing post',body,conflicts)
  for key in ['liked','reactions','comments']:
   if key not in known:known[key]=state['posts'][body][key]
 s=clone(state)
 s['absent_posts']=[item for item in s['absent_posts']if item!=body]
 s['entities'][handle]={'known':known,'provenance':[provenance],'identity_status':'local causal handle; not DOM position or server ID'}
 if handles and body in s['posts']:
  previous=s['posts'].pop(body)
  s.setdefault('reconciliation',[]).append({'kind':'body_alias_invalidated','body':body,'prior_body_alias':previous,'reason':'multiple causal entities share displayed content','provenance':provenance})
 return checked_state(s)
def match_entity_candidates(state,observation):
 consistency=registry_consistency(state)
 if not consistency['ok']:return consistency
 if not valid_entity_observation(observation):return guard_failure('ill-typed entity observation')
 known=entity_signature(observation);candidates=[]
 for handle,entity in state['entities'].items():
  signature=entity['known']
  if all(key not in signature or signature[key]==value for key,value in known.items()):candidates.append(handle)
 return {'ok':True,'candidates':candidates,'identity_status':'unique' if len(candidates)==1 else 'ambiguous' if candidates else 'unmatched','locatable_by_current_signature':len(candidates)==1,'action_allowed':len(candidates)==1 and sum(1 for entity in state['entities'].values()if entity['known'].get('body')==observation['body'])==1,'observed_signature':known}
def reconcile_entity(state,handle,observation,provenance,mode='verify'):
 if handle not in state.get('entities',{}) or not valid_entity_observation(observation) or not isinstance(provenance,str) or mode not in ['verify','external_update']:return guard_failure('unknown entity or invalid observation provenance')
 consistency=registry_consistency(state)
 if not consistency['ok']:return consistency
 prior=clone(state['entities'][handle]['known']);observed=entity_signature(observation)
 body=prior['body']
 if len(entity_handles_for_body(state,body))==1 and body in state['posts']:
  for key in ['liked','reactions','comments']:
   if key not in prior:prior[key]=state['posts'][body][key]
 differences={key:{'prior':prior[key],'observed':value}for key,value in observed.items()if key in prior and prior[key]!=value}
 if differences and mode!='external_update':return {'ok':False,'readpoint':'entity contradiction','reconciliation':{'kind':'contradiction','differences':differences,'provenance':provenance,'prior_unchanged':True}}
 if observed['body']!=prior.get('body'):return guard_failure('content changed; no stable public identity proof for reconciliation')
 s=clone(state);s['entities'][handle]['known'].update(observed);s['entities'][handle]['provenance'].append(provenance)
 if differences:
  body=observed['body']
  if sum(1 for entity in s['entities'].values()if entity['known'].get('body')==body)==1 and body in s['posts']:
   for key in ['liked','reactions','comments']:
    if key in observed:s['posts'][body][key]=observed[key]
  if any(key in differences for key in ['liked','reactions']):s['delta']['reactions_added']=None;s['delta']['reactions_removed']=None
  if 'comments' in differences:s['delta']['created_comments']=None
 consistency=registry_consistency(s)
 if not consistency['ok']:return consistency
 return {'ok':True,'state':s,'reconciliation':{'kind':'external_update' if differences else 'consistent','differences':differences,'provenance':provenance,'prediction_credit':False}}

def valid_entity_observation(observation):
 if not isinstance(observation,dict) or not isinstance(observation.get('body'),str) or any(key not in ['body','author','liked','reactions','comments']for key in observation):return False
 for key in ['body','author']:
  if key in observation and not isinstance(observation[key],str):return False
 if 'liked' in observation and not isinstance(observation['liked'],bool):return False
 for key in ['reactions','comments']:
  if key in observation and (not isinstance(observation[key],int) or isinstance(observation[key],bool) or observation[key]<0):return False
 return True
def bind_contract_rows(state,rows_each):
 consistency=registry_consistency(state)
 if not consistency['ok']:return consistency
 if not isinstance(rows_each,list):return guard_failure('ill-typed each bindings')
 rows=[];raw=[]
 for item in rows_each:
  if not isinstance(item,dict) or not isinstance(item.get('parent_id'),str):return guard_failure('missing capture-local provenance')
  normalized=normalize_job_row_binding(item.get('bindings'))
  if not normalized['ok']:return normalized
  rows.append(normalized['identity']);raw.append({'capture_parent':item['parent_id'],'normalization':normalized})
 s=bind_rows(state,rows)
 if 'ok' in s and not s['ok']:return s
 s['row_binding_provenance']=raw;return checked_state(s)
def knowledge_labels(state):
 unknown=[]
 if state.get('rows') is None:unknown.append('result collection values/cardinality')
 for key,job in state.get('jobs',{}).items():
  if job['applied'] is None or job['applicants'] is None:unknown.append('job application metadata '+key)
 for domain,value in state['delta'].items():
  if value is None:unknown.append('reset-relative delta '+domain)
 return {'known':{'route':state['route'],'authenticated':state['authenticated'],'registered_entity_handles':list(state.get('entities',{}))},'unknown_external':unknown,'unknown_semantics':['same-body business write contract','unseen validation and unsupported controls'],'identity_policy':'multiple compatible public signatures remain ambiguous'}

def entity_handles_for_body(state,body):
 return [handle for handle,entity in state.get('entities',{}).items()if entity['known'].get('body')==body]
def shared_post_conflicts(prior,observed):
 return {key:{'prior':prior[key],'observed':observed[key]}for key in ['liked','reactions','comments']if key in prior and key in observed and prior[key]!=observed[key]}
def registry_conflict(reason,body,differences):
 return {'ok':False,'readpoint':reason,'reconciliation':{'kind':'contradiction','body':body,'differences':differences,'prior_unchanged':True,'state_changed':False}}
def registry_consistency(state):
 if not isinstance(state.get('absent_posts'),list) or not all(isinstance(body,str)for body in state['absent_posts']):return guard_failure('ill-typed absence preconditions')
 for body in state['absent_posts']:
  if body in state.get('posts',{}) or entity_handles_for_body(state,body):return registry_conflict('fresh-body absence precondition conflicts with known object',body,{})
 for handle,entity in state.get('entities',{}).items():
  if not isinstance(entity,dict) or not valid_entity_observation(entity.get('known')):return guard_failure('ill-typed registered entity state')
 for body,post in state.get('posts',{}).items():
  if not isinstance(post,dict) or any(key not in post for key in ['liked','reactions','comments']) or not valid_entity_observation(dict({'body':body},**{key:post[key]for key in ['liked','reactions','comments']})):return guard_failure('ill-typed body post state')
  handles=entity_handles_for_body(state,body)
  if len(handles)>1:return registry_conflict('ambiguous body alias must not remain actionable',body,{'handles':handles})
  if len(handles)==1:
   conflicts=shared_post_conflicts(post,state['entities'][handles[0]]['known'])
   if conflicts:return registry_conflict('post and entity registries disagree',body,conflicts)
 return {'ok':True}

def checked_state(candidate):
 consistency=registry_consistency(candidate)
 if not consistency['ok']:return consistency
 return candidate
