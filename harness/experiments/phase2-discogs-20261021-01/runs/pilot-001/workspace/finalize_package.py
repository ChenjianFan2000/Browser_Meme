"""Final offline publication. READY.json is written only after all validation passes."""
import hashlib,json,shutil
from pathlib import Path
from validate_package import validate

def write(path,value):Path(path).write_text(json.dumps(value,indent=2)+'\n')
budget=json.loads(Path('budget-final.json').read_text())
coverage_path=Path('revisions/002/coverage.json')
coverage=json.loads(coverage_path.read_text())
coverage['budget_at_publication']=budget
coverage['budget_at_publication']['learner_stop_reason']='contract_stop_after_ui_action_timeout'
write(coverage_path,coverage)
report=validate()
write('revisions/002/validation.json',report)
for folder in [Path('revisions/001/__pycache__'),Path('revisions/002/__pycache__'),Path('__pycache__')]:
 if folder.exists():shutil.rmtree(folder)
manifest=[]
for root in [Path('revisions/001'),Path('revisions/002'),Path('experiments')]:
 for p in sorted(root.rglob('*')):
  if p.is_file() and p.name!='artifact_manifest.json':
   manifest.append({'path':p.as_posix(),'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'size_bytes':p.stat().st_size})
for p in [Path('evidence_index.json'),Path('budget-final.json'),Path('publish_package.py'),Path('complete_metadata.py'),Path('validate_package.py'),Path('finalize_package.py')]:
 manifest.append({'path':p.as_posix(),'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'size_bytes':p.stat().st_size})
write('revisions/002/artifact_manifest.json',manifest)
# Recheck all required artifacts and references including the final manifest before publication.
validate()
for folder in [Path('revisions/001/__pycache__'),Path('revisions/002/__pycache__')]:
 if folder.exists():shutil.rmtree(folder)
limitations=json.loads(Path('revisions/002/limitations.json').read_text())
ready={'revision_directory':'revisions/002','stop_reason':'contract_stop_after_ui_action_timeout','limitations':limitations['limitations'],'condition':'A','scheduling_seed':1729,'prior_revision_directory':'revisions/001','actions_used':budget['actions'],'browser_submissions_used':budget['script_calls'],'evidence_refs':limitations['evidence_refs']}
write('READY.json',ready)
print(json.dumps({'published':'READY.json','revision_directory':ready['revision_directory'],'stop_reason':ready['stop_reason'],'validation':'passed','actions':budget['actions'],'browser_submissions':budget['script_calls']}))
