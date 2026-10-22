"""Generic Linux Codex namespace parent-death probe, no model or website."""
import ctypes,json,os,pathlib,signal,subprocess,sys,time
ROOT=pathlib.Path('/opt/browser-meme/tmp/phase2-isolation-audit/lifecycle-tree-021')
ROOT.mkdir(parents=True,exist_ok=True)
sys.path.insert(0,str(ROOT))
from permissions import CODEX,overrides
worker=ROOT/'worker.py'
worker.write_text("import os,time,pathlib,subprocess\np=pathlib.Path('heartbeat')\nsubprocess.Popen(['/bin/sleep','90'])\nwhile True:\n p.write_text(str(time.time()))\n time.sleep(.1)\n")
libc=ctypes.CDLL(None,use_errno=True)
def parent_death():
 parent=os.getpid()
 def setup():
  if libc.prctl(1,signal.SIGKILL,0,0,0)!=0: os._exit(125)
  if os.getppid()!=parent: os.kill(os.getpid(),signal.SIGKILL)
 return setup
def descendants(pid):
 rows={}
 for entry in pathlib.Path('/proc').iterdir():
  if not entry.name.isdigit(): continue
  try:
   raw=(entry/'stat').read_text(); tail=raw[raw.rfind(')')+2:].split(); rows[int(entry.name)]=(int(tail[1]),tail[19],tail[0])
  except (OSError,ValueError): pass
 found={pid}
 while True:
  nxt=found|{k for k,v in rows.items() if v[0] in found}
  if nxt==found: break
  found=nxt
 return {k:rows[k] for k in found if k in rows}
results=[]
for guarded in (False,True):
 heartbeat=ROOT/'heartbeat';heartbeat.unlink(missing_ok=True)
 r,w=os.pipe(); parent=os.fork()
 if parent==0:
  os.close(r)
  args=[CODEX,'sandbox','-P','p2','-C',str(ROOT)]+overrides()+['/usr/bin/python3',str(worker)]
  child=subprocess.Popen(args,start_new_session=True,preexec_fn=parent_death() if guarded else None,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
  os.write(w,str(child.pid).encode());os.close(w)
  time.sleep(90);os._exit(0)
 os.close(w);child=int(os.read(r,32));os.close(r)
 for _ in range(100):
  if heartbeat.exists():break
  time.sleep(.1)
 assert heartbeat.exists(),'namespace worker failed to start'
 owned=descendants(child)
 os.kill(parent,signal.SIGKILL);os.waitpid(parent,0)
 time.sleep(1)
 alive=[]
 for pid,(_,start,_) in owned.items():
  try:
   raw=pathlib.Path(f'/proc/{pid}/stat').read_text();tail=raw[raw.rfind(')')+2:].split()
   if tail[19]==start and tail[0]!='Z':alive.append(pid)
  except OSError:pass
 results.append({'guarded':guarded,'owned_count':len(owned),'alive_after_parent_death':len(alive)})
 for pid in alive:
  try:os.kill(pid,signal.SIGKILL)
  except ProcessLookupError:pass
assert results[0]['alive_after_parent_death']>0,results
assert results[1]['alive_after_parent_death']==0,results
(ROOT/'result.json').write_text(json.dumps({'status':'passed','results':results},indent=2))
print(json.dumps({'status':'passed','results':results}))
