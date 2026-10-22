"""Read compact management status without printing website scripts or credentials."""
import argparse
from .management import wsl_python, LINUX_ROOT


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("run_id")
    args = parser.parse_args()
    source = """from pathlib import Path
import json,time
base=Path(BASE)
out={'run_id':RUN}
file=base/'private/browser/broker.jsonl'
if file.exists():
 rows=[]
 for line in file.read_text(encoding="utf-8").splitlines():
  try: rows.append(json.loads(line))
  except ValueError: pass
 out['browser_calls']=sum(r.get('event')=='result' for r in rows)
 out['ui_actions']=sum(r.get('actions',0) for r in rows if r.get('event')=='result')
 out['last_browser_event']=rows[-1] if rows else None
 out['browser_errors']=[]
 for result_path in sorted((base/'private/browser').glob('call-*/evidence/result.json')):
  result=json.loads(result_path.read_text(encoding="utf-8"))
  if result.get('error'): out['browser_errors'].append({'call':result_path.parent.parent.name,'error':result['error'][:700]})
file=base/'private/solar/events.jsonl'
if file.exists():
 rows=[]
 for line in file.read_text(encoding="utf-8").splitlines():
  try: rows.append(json.loads(line))
  except ValueError: pass
 out['cli_event_count']=len(rows)
 out['last_cli_event_type']=rows[-1].get('type') if rows else None
 out['seconds_since_cli_event']=round(time.time()-file.stat().st_mtime)
 out['cli_errors']=[r for r in rows if r.get('type') in ['error','turn.failed']]
 out['usage']=[r['usage'] for r in rows if 'usage' in r]
 out['last_item_types']=[r.get('item',{}).get('type') for r in rows[-8:]]
ready=base/'workspace/READY.json'
out['ready']=json.loads(ready.read_text(encoding="utf-8")) if ready.exists() else None
print(json.dumps(out))
""".replace("BASE", repr(LINUX_ROOT + "/" + args.run_id)).replace("RUN", repr(args.run_id))
    result = wsl_python(source)
    print(result.stdout.decode())
    if result.returncode:
        print(result.stderr.decode())


if __name__ == "__main__":
    main()
