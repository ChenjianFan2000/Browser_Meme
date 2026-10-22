"""Offline packaging of curated prose claims and original exported UI evidence."""
import glob, hashlib, json, pathlib, shutil, sys

ROOT = pathlib.Path('.')

def ref(path):
    p = pathlib.Path(path)
    return {'path':p.as_posix(), 'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}

def evidence(calls):
    out=[]
    for n in calls:
        d=pathlib.Path(glob.glob('evidence/call-%03d-*'%n)[0])
        r=json.loads((d/'result.json').read_text())
        for p in [d/'actions.jsonl', d/'network.json', d/r['last_observation']['dom']]:
            out.append(ref(p))
    return out

def build(revision, maximum, parent=None):
    directory=ROOT/('revisions/'+revision)
    directory.mkdir(parents=True,exist_ok=False)
    facts=json.loads(pathlib.Path('knowledge.json').read_text())
    rules=[]
    for f in facts['rules']:
        if max(f['calls'],default=0)>maximum:continue
        r={k:v for k,v in f.items() if k!='calls'}
        r['evidence_refs']=evidence(f['calls'])
        rules.append(r)
    def write(name,obj):
        (directory/name).write_text(json.dumps(obj,indent=2,ensure_ascii=False)+'\n')
    write('rules.json',rules)
    allrefs=evidence(list(range(1,maximum+1)))
    previous={r['id']:r for r in json.loads((ROOT/'revisions'/parent/'rules.json').read_text())} if parent else {}
    changed=[r['id'] for r in rules if previous.get(r['id'])!=r]
    write('revision.json',{'revision':revision,'parent_revision':parent,'condition':'B','learner':'gpt-6.1-sol','scheduling_seed':3141,'changed_rules':changed, 'changed_scripts':['scripts.py']+sorted(str(x) for x in pathlib.Path('experiments').glob('*.py') if int(x.name[:2])>21), 'failure_category':['locator','business_rule','implementation'], 'evidence_refs':allrefs,'rationale':'Browser-only bounded observations. Predictions preceding actions remain in the original record, including refuted predictions. Failed scripts and parent revision retained. No executable behavior predictor. Scheduling seed does not specify model sampling.'})
    lines=['# Bounded browser knowledge — '+revision,'','Condition B: prose knowledge and native execution scripts only. Account, data and time are those of this learning run. No universal backend claims. Action predictions are hypotheses recorded before observation, not independent truth.','']
    for r in rules:
        lines += ['## '+r['id']+' ('+r['status']+')',r['statement'],'','Preconditions: '+ '; '.join(r['preconditions']), '', 'Evidence: '+', '.join('['+x['path']+'](../../'+x['path']+') sha256 `'+x['sha256']+'`' for x in r['evidence_refs']), '']
    lines += ['## Remaining uncertainty','See coverage.json for distinguishing experiments. Missing or disabled controls establish only a UI boundary; they do not establish absent backend behavior. Do not retry a non-idempotent write without confirming its outcome. Reload after membership writes to separate optimistic counters from persistent counts.','']
    (directory/'rulebook.md').write_text('\n'.join(lines))
    write('coverage.json',{'scope':'Observed origin http://127.0.0.1:12042 only; supplied account; current run state', 'explored':[{'area':x['area'],'findings':x['findings'],'evidence_refs':evidence(x['calls'])} for x in facts['coverage'] if max(x['calls'])<=maximum], 'unexplored':facts['unexplored'], 'current_competing_hypotheses':[{'statement':s,'evidence_refs':allrefs} for s in facts['hypotheses']], 'proposed_distinguishing_experiments':facts['proposed'], 'success_rejection_boundary_evidence':{'success':evidence([6,9,10,16,17]+([27,33,35,37,39] if maximum>=39 else [])),'rejection':evidence([21]+([24,25,28,31,32,34] if maximum>=34 else [])) if maximum>=21 else [],'boundary':evidence([12,13,15,17]+([29,30,36,38,40] if maximum>=40 else []))},'limits':{'script_calls_observed':maximum,'runtime_action_count':sum(json.loads(pathlib.Path(glob.glob('evidence/call-%03d-*'%i)[0]+'/result.json').read_text()).get('actions',0) for i in range(1,maximum+1)),'unknown_affected_counts':'No hidden state counts inferred; checkout touched multiple visible objects and its total record count remains unknown.','no_task_scoring':'No private tasks supplied; per-action predictions are not task-boundary scores.'}})
    pages={}
    for n in range(1,maximum+1):
        d=pathlib.Path(glob.glob('evidence/call-%03d-*'%n)[0])
        for line in (d/'actions.jsonl').read_text().splitlines():
            a=json.loads(line)
            if a.get('kind')!='observation' or not a.get('url','').startswith('http://127.0.0.1:12042'):continue
            url=a['url']
            pages[url]={'url':url,'visible_summary':a.get('visible_text','').split('DISCOGS')[0][:6000],'evidence_refs':[ref(d/a['dom'])], 'uncertainty':'Rendered observations only; no claim about all routes, records or permissions'}
    write('objects.json',{'pages':list(pages.values()),'identities':[dict({k:v for k,v in o.items() if k!='calls'},evidence_refs=evidence(o['calls'])) for o in facts['objects'] if max(o['calls'])<=maximum], 'relationships':[{'statement':'Release detail links to its marketplace; own collection/wantlist contain release cards; marketplace listing links to cart; seller page lists own listing status.','evidence_refs':evidence([6,7,9,16,17])}], 'actions':'See scripts.py and per-action exploration.jsonl; scripts require current DOM confirmation and externally supplied predictions.'})
    log=[]
    for n in range(1,maximum+1):
        d=pathlib.Path(glob.glob('evidence/call-%03d-*'%n)[0]); result=json.loads((d/'result.json').read_text())
        events=[json.loads(x) for x in (d/'actions.jsonl').read_text().splitlines()]
        meta=facts['experiments'].get(str(n),{})
        action_predictions=[x for x in events if x.get('kind')=='action_before']
        assessments=[]
        for i,event in enumerate(events):
            if event.get('kind')!='action_before':continue
            j=i+1
            while j<len(events) and events[j].get('kind')!='action_before':j+=1
            segment=events[i+1:j]
            after=[x for x in segment if x.get('kind')=='action_after']
            obs=[x for x in segment if x.get('kind')=='observation' and x.get('label')=='after-'+str(event['action'])]
            o=obs[0] if obs else None
            mutations=[x for x in segment if x.get('kind')=='observation' for x in x.get('network',[]) if x.get('method') not in ['GET',None]]
            error=after[0].get('error') if after else 'Missing action_after'
            if error: category='locator'
            elif any(x.get('status',0)>=400 for x in mutations):category='business_rule'
            elif mutations:category='accepted_response_observed'
            elif o and 'server-side exception' in o.get('visible_text',''):category='implementation'
            elif event['method'] in ['goto','hover','fill','select_option']:category='rendered_readback'
            else:category='ui_readback_only'
            assessments.append({'action':event['action'],'classification':category,'prediction':event['prediction'],'prediction_scope':'per-action, no whole-task score','readback':ref(d/o['dom']) if o else None,'ui_caused_mutation_responses':mutations,'error':error,'interpretation':'Use experiment interpretation and bounded rules for semantic conclusions; raw runtime classification is retained unchanged in original evidence. UI-only readback does not establish persistent business effects.'})
        log.append({'experiment':n,'why_selected':meta.get('why','Inspect an independently observed UI branch'), 'alternatives_considered':meta.get('alternatives',['More breadth','A repeat or boundary on the current object']), 'whole_task_prediction':None,'prediction':action_predictions,'action_assessments':assessments, 'actual_evidence':[{'label':x['label'],'url':x['url'],'visible_text':x.get('visible_text','').split('DISCOGS')[0], 'evidence_ref':ref(d/x['dom'])} for x in events if x.get('kind')=='observation' and (x.get('label','').startswith('after-') or x.get('label')=='final')], 'classification':meta.get('classification','observed_success_or_read_only') if result['status']=='completed' else meta.get('classification','locator'), 'error':result.get('error'), 'interpretation':meta.get('outcome','See original per-action readbacks; broader behavior remains unknown.'), 'resulting_revision':'r001' if n<=21 else revision, 'evidence_refs':[ref(d/'actions.jsonl'),ref(d/'network.json'),ref(d/'result.json')]})
    (directory/'exploration.jsonl').write_text(''.join(json.dumps(x,ensure_ascii=False)+'\n' for x in log))
    shutil.copyfile('reusable_scripts.py',directory/'scripts.py')
    print(directory)

if __name__=='__main__':build(sys.argv[1],int(sys.argv[2]),sys.argv[3] if len(sys.argv)>3 else None)
