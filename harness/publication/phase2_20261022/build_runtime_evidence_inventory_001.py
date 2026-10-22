"""Select phase2 deployment evidence; no database opens, upload or original mutation."""
from pathlib import Path
from datetime import datetime, timezone
import hashlib,json,os,re
ROOT=Path(__file__).resolve().parents[3]
EXP=ROOT/'harness/experiments/phase2-discogs-20261021-01'
OUT=Path(__file__).resolve().parent/'runtime-evidence-inventory-001.json'
ROOT_NAMES=['phase2-discogs-20261021-01','phase2-routing-v001','phase2-routing-v002']+['phase2-eval-worker-'+c for c in 'abcdefghijkl']+['phase2-scale-management-v001']
FORBIDDEN={'data','source','node_modules','.next','venv','venv-lockcheck','npm-cache','wheelhouse','transport-cache','codex-home','state','memories','__pycache__','.git'}
EXTENSIONS={'.json','.jsonl','.log','.txt','.sha256','.patch','.png','.html','.zip','.py','.js','.cjs','.md','.csv'}
def digest(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for block in iter(lambda:f.read(1024*1024),b''):h.update(block)
 return h.hexdigest()
def classify(p):
 n=p.name.lower();parts=p.parts
 if p.suffix=='.zip':return 'browser_trace_archive_requires_secret_scan'
 if p.suffix=='.png':return 'ui_screenshot_requires_visual_scan'
 if p.suffix=='.html':return 'ui_dom_snapshot_requires_secret_scan'
 if p.suffix in {'.py','.js','.cjs','.patch'}:return 'historical_management_adapter_or_patch_snapshot'
 if 'log' in n or p.suffix=='.jsonl':return 'service_or_management_event_log_requires_secret_scan'
 if 'manifest' in n or 'hash' in n or 'baseline.sha256'==n:return 'version_build_dependency_or_state_hash_inventory'
 if 'readiness' in n or 'admission' in n:return 'readiness_and_admission_result'
 return 'private_management_result_or_evidence'
def reason(p):
 parts=set(p.relative_to(ROOT).parts)
 if p.name.lower() in {'auth.json','.env','research.env'}:return 'real_auth_or_environment_store_never_export'
 if p.suffix.lower() in {'.db','.sqlite','.sqlite3','.wal','.shm'} or any(x in p.name.lower() for x in ['.db-wal','.db-shm']):return 'database_or_database_sidecar_excluded'
 if 'frozen-evaluation' in parts:return 'formal_case_truth_already_archived_in_experiment_private_truth_archive'
 if parts & FORBIDDEN:return 'runtime_data_source_dependencies_cache_or_personal_state_excluded'
 if p.suffix.lower() not in EXTENSIONS:return 'non_result_or_process_control_marker_excluded'
 return None
refs={};read_sources=[]
def collect(value,origin):
 if isinstance(value,dict):
  for key,item in value.items():collect(key,origin);collect(item,origin)
 elif isinstance(value,list):
  for item in value:collect(item,origin)
 elif isinstance(value,str):
  n=value.replace(chr(92),'/')
  if '.runtime/' not in n:return
  relative='.runtime/'+n.split('.runtime/',1)[1]
  # Only single path-shaped strings, never parse arbitrary shell/code strings.
  if any(c in relative for c in ['\n','\r','*','{','}','<','>','|']):return
  refs.setdefault(relative,set()).add(origin)
for folder in [EXP,EXP/'private',EXP/'private/scale-deployment-v001',EXP/'isolation',EXP/'reviews',EXP/'reports']:
 for p in sorted(folder.glob('*.json')):
  try:v=json.loads(p.read_text(encoding='utf-8-sig'))
  except (OSError,ValueError):continue
  origin=p.relative_to(ROOT).as_posix();read_sources.append({'path':origin,'sha256':digest(p)});collect(v,origin)
selected={};excluded=[];pruned=[]
for name in ROOT_NAMES:
 base=ROOT/'.runtime'/name
 if not base.is_dir():continue
 for folder,dirs,files in os.walk(base):
  parent=Path(folder)
  for d in list(dirs):
   candidate=parent/d
   if d in FORBIDDEN or d in {'frozen-evaluation','initial_states'}:
    dirs.remove(d);pruned.append({'path':candidate.relative_to(ROOT).as_posix(),'reason':'formal_truth_already_archived' if d=='frozen-evaluation' else 'database_initial_state_or_source_dependencies_cache_excluded'})
  for name2 in sorted(files):
   path=parent/name2;relative=path.relative_to(ROOT).as_posix();why=reason(path)
   if why:excluded.append({'path':relative,'reason':why});continue
   first=path.stat();h=digest(path);last=path.stat()
   if first.st_size!=last.st_size or first.st_mtime_ns!=last.st_mtime_ns:raise ValueError('Changing evidence during inventory: '+relative)
   selected[relative]={'source_path':str(path),'source_repo_relative_path':relative,'archive_path':'runtime-evidence/'+relative.removeprefix('.runtime/'),'restore_path':relative,'sha256':h,'bytes':last.st_size,'evidence_type':classify(path),'selection_reason':'bounded phase2 deployment root management/result evidence; failed readiness rounds retained','associated_references':[],'secret_scan_status':'pending_unique_export_scanner','verbatim_publication_approved':False}
# Include only explicitly referred parent phase1 inventories/logs, never its large source/dependency trees.
for relative,origins in list(refs.items()):
 path=ROOT/relative
 if relative.startswith('.runtime/phase1-discogs-pw-20261020-1633/') and path.is_file() and not reason(path):
  selected[relative]={'source_path':str(path),'source_repo_relative_path':relative,'archive_path':'runtime-evidence/'+relative.removeprefix('.runtime/'),'restore_path':relative,'sha256':digest(path),'bytes':path.stat().st_size,'evidence_type':classify(path),'selection_reason':'explicit parent-source phase2 provenance reference only','associated_references':[],'secret_scan_status':'pending_unique_export_scanner','verbatim_publication_approved':False}
# Close references in selected result JSON, avoiding binary/trace contents and excluded subtrees.
for relative,item in list(selected.items()):
 path=ROOT/relative
 if path.suffix=='.json':
  try:collect(json.loads(path.read_text(encoding='utf-8-sig')),relative)
  except (ValueError,OSError):pass
reference_dispositions=[]
for relative,origins in sorted(refs.items()):
 path=ROOT/relative
 if relative in selected:
  selected[relative]['associated_references']=sorted(origins);status='included';why='selected result file'
 elif 'frozen-evaluation' in Path(relative).parts:status='already_archived';why='formal180 originals are in EXP/private/truth-archive/formal-180-001; original absolute source path preserved there'
 elif path.is_dir():
  status='directory_reference_partially_covered';why='only selected result files exported; runtime directory is not a reproducible full installation'
 elif not path.exists():status='not_present_or_nonliteral_reference';why='preserve historical reference but do not fabricate missing evidence'
 else:status='excluded';why=reason(path) or 'outside bounded phase2 result roots; separate owner needed'
 reference_dispositions.append({'source_reference':relative,'referenced_by':sorted(origins),'disposition':status,'reason':why})
rows=sorted(selected.values(),key=lambda r:r['source_repo_relative_path'])
formal=json.loads((EXP/'formal-inputs-001.json').read_text())['files']
required=[{'path':k,'expected_sha256':v,'included':k in selected,'actual_sha256':selected.get(k,{}).get('sha256')} for k,v in formal.items() if k.startswith('.runtime/')]
if len(required)!=3 or any(not r['included'] or r['actual_sha256']!=r['expected_sha256'] for r in required):raise ValueError('Required original3 readiness bindings not closed')
value={'schema_version':1,'kind':'phase2_external_runtime_evidence_inventory','status':'inventory_frozen_requires_secret_scan_and_export','recorded_at_utc':datetime.now(timezone.utc).isoformat(),'scope':'bounded deployment roots only; not recursive .runtime or original4roots credential rescan','builder_sha256':digest(Path(__file__)),'entries':rows,'file_count':len(rows),'total_bytes':sum(r['bytes'] for r in rows),'explicit_runtime_roots':ROOT_NAMES,'management_reference_sources':read_sources,'reference_dispositions':reference_dispositions,'excluded_files':excluded,'pruned_directories':pruned,'original_formal_input_runtime_bindings':required,'formal_truth_archive':{'path':'harness/experiments/phase2-discogs-20261021-01/private/truth-archive/formal-180-001/archive-index.json','sha256':digest(EXP/'private/truth-archive/formal-180-001/archive-index.json'),'duplicated':False},'publication_policy':{'upload_performed':False,'originals_modified':False,'verbatim_approved':False,'separate_scanner_required':True,'sanitized_export_source_to_export_hash_mapping_required':True,'no_database_opened':True,'no_real_auth_storage_opened':True},'limitations':['This inventory restores evidentiary result files, not installed site/database/cache/source trees.','Original absolute paths remain in unchanged evidence; source_repo_relative_path/archive_path/restore_path map them for a portable export.','Service logs can grow after inventory; unique export must reject changed source hashes and freeze its own snapshot rather than silently refresh this inventory.','Reference source selection covers top-level experiment management reports and transitive selected runtime JSON; learner/evaluation artifacts already live in EXP and are not rescanned here.','No credential absence claim: ZIP/network/HTML/screenshots/logs require unique export scanner and redaction review before public upload.']}
with OUT.open('x',encoding='utf-8') as f:json.dump(value,f,ensure_ascii=False,indent=2);f.write('\n')
print(json.dumps({'path':str(OUT),'sha256':digest(OUT),'files':len(rows),'bytes':value['total_bytes'],'reference_dispositions':len(reference_dispositions)}))
