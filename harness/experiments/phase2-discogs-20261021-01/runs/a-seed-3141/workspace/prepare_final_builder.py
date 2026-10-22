from pathlib import Path
import json
s=Path('build_package_v2.py').read_text()
s=s.replace("if e.get('kind')=='observation' and e.get('url'):","if e.get('kind')=='observation' and str(e.get('url','')).startswith('http://127.0.0.1:12042'):")
s=s.replace("   if path not in seen:","   if path:")
s=s.replace("No source_refs.","Original browser evidence is retained.")
s=s.replace("'classification':'learner_note'","'classification':('locator' if 'locator:' in e.get('text','') else 'business_rule' if 'business_rule:' in e.get('text','') else 'implementation' if 'implementation:' in e.get('text','') else 'learner_note')")
Path('build_package_v3.py').write_text(s)
p=Path('artifact_data.json');d=json.loads(p.read_text())
for r in d['rules']:
 if r[0]=='R10': r[4]=['Later E19/E20 observations resolved multi-result and no-match behavior; see R19']
 if r[0]=='R14': r[4]=['Later E23 tested multi-unit selective removal; see R24']
p.write_text(json.dumps(d,indent=2)+'\n')
p=Path('revisions/r002/behavior_model.py');s=p.read_text().replace('url=o.get("url","")','url=o.get("url","")\n    if not isinstance(url,str): url=""').replace('text=o.get("visible_text",o.get("text","")) or ""','text=o.get("visible_text",o.get("text","")) or ""\n    if not isinstance(text,str): text=""').replace('One new active listing appears in My Listings; repeating creation can make another distinct listing','One new active listing appears in My Listings')
p.write_text(s)
Path('experiments/behavior_model_v4.py').write_text(s)
