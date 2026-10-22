import json, hashlib, sys
from pathlib import Path
from datetime import datetime, timezone
out=Path('revisions/r002')
def ref(p):return {'path':p.as_posix(),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}
required=['revision.json','rulebook.md','rules.json','objects.json','coverage.json','scripts.py','behavior_model.py','exploration.jsonl']
for f in required:assert (out/f).is_file()
validation=json.loads((out/'validation.json').read_text());assert validation['status']=='passed'
assert validation['action_predictions']==300 and validation['action_readbacks']==300
assert not Path('READY.json').exists()
# Recheck every original export immediately before sealing.
for item in json.loads((out/'evidence_manifest.json').read_text()):
 assert ref(Path(item['path']))==item
manifest={'revision_directory':out.as_posix(),'parent_revision_directory':'revisions/r001','artifacts':[ref(p) for p in sorted(out.iterdir()) if p.is_file() and p.name!='artifact_manifest.json'],'evidence_inventory':'revisions/r002/evidence_manifest.json','validation':'revisions/r002/validation.json'}
(out/'artifact_manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
timestamp=sys.argv[1]
end=datetime.strptime(timestamp,'%Y-%m-%d %H:%M:%S UTC').replace(tzinfo=timezone.utc)
first_clock=datetime(2026,10,21,5,33,4,tzinfo=timezone.utc)
# Initial authoritative status was read near the first clock; +30s is conservative.
upper=(end-first_clock).total_seconds()+30
assert upper<7200
ready={'revision_directory':'revisions/r002','stop_reason':'ui_action_limit_reached','limitations':[
'Coverage is bounded to the supplied account and observed conditions; other behavior remains hypothesis or unknown.',
'300 actual UI actions,36 executed scripts;39 total submissions including3 pre-execution rejections. No browser work continued after the action limit.',
'Raw runtime classifications are retained as unconfirmed; learner conclusions use observed readback and sanitized responses and are not independent scoring.',
'Checkout affected-record totals remain unknown. Missing removal/reactivation controls do not establish absent backend behavior.',
'Visually identical own listings can be ambiguous; reusable helpers stop before such writes. Exact sign_in/sign_out/checkout wrappers were not all executed.',
'Final pure-model guards passed offline checks; no private tasks or independent evaluation feedback were used.'
], 'condition':'A','scheduling_seed':3141,'learner_label':'gpt-6.1-sol as requested at launch','published_at_utc':timestamp,'conservative_inclusive_elapsed_seconds_at_sealing':upper,'artifact_manifest':ref(out/'artifact_manifest.json'),'validation':'revisions/r002/validation.json'}
# Publication is the final filesystem mutation in this script.
Path('READY.json').write_text(json.dumps(ready,indent=2)+'\n')
print('Published READY.json -> revisions/r002; original evidence and parent revision retained.')
