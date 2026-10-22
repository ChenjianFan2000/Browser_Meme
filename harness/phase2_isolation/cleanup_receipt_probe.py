"""Generic Linux private cleanup-receipt probe; fake CLI never invokes a model."""
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
ROOT = Path('/opt/browser-meme/tmp/phase2-isolation-audit/cleanup-receipt-031')
sys.path.insert(0, str(ROOT))
import launch_solar
from process_guard import receipt_valid, snapshot
fake = ROOT / 'fake-codex'
fake.write_text('#!/usr/bin/python3\nimport subprocess,time,pathlib\nx=subprocess.Popen(["/bin/sleep","90"],start_new_session=True)\npathlib.Path(' + repr(str(ROOT / 'owned-pid')) + ').write_text(str(x.pid))\ntime.sleep(90)\n')
fake.chmod(0o700)
launch_solar.CODEX = str(fake)
home = ROOT / 'home'; home.mkdir(); (home / 'auth.json').write_text('{}')
(ROOT / 'prompt').write_text('generic no model')
launch_solar.launch(dict(private=str(ROOT/'private'),codex_home=str(home),broker_config=None,workspace=str(ROOT),runtime=str(ROOT),prompt_path=str(ROOT/'prompt'),time_limit_seconds=.5))
launch = json.loads((ROOT/'private/launch-result.json').read_text())
receipt = ROOT/'private'/launch['cleanup_receipt']
assert launch['timeout'] and launch['process_tree_clean']
assert receipt_valid(receipt, nonce=launch['cleanup_nonce'], supervisor_pid=launch['supervisor_pid'])
assert not receipt_valid(receipt, nonce='wrong', supervisor_pid=launch['supervisor_pid'])
assert not receipt_valid(receipt, nonce=launch['cleanup_nonce'], supervisor_pid=-1)
assert not receipt_valid(ROOT/'absent',nonce='generic',supervisor_pid=1)
missing = ROOT/'killed-receipt.json'
child = subprocess.Popen([sys.executable,str(ROOT/'process_guard.py'),'--receipt',str(missing),'--nonce','killed','--','/bin/sleep','90'])
owned={}
for _ in range(100):
 rows=snapshot();owned={pid:row for pid,row in rows.items() if row[0]==child.pid}
 if owned:break
 time.sleep(.02)
assert owned
child.kill();child.wait()
assert not receipt_valid(missing,nonce='killed',supervisor_pid=child.pid)
for pid,row in owned.items():
 current=snapshot().get(pid)
 if current and current[1]==row[1]:
  try:os.kill(pid,signal.SIGKILL)
  except ProcessLookupError:pass
result={'status':'passed','checks':{'timeout_has_valid_private_receipt':True,'wrong_nonce_denied':True,'wrong_pid_denied':True,'missing_receipt_denied':True,'killed_guard_has_no_cleanup_receipt':True},'launch_result':launch}
(ROOT/'result.json').write_text(json.dumps(result,indent=2))
print(json.dumps(result))
