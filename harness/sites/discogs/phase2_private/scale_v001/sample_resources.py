"""Management resource samples, no browser/DB/site data read."""
import json
import subprocess
import time
from pathlib import Path
import psutil
from management import ROOT

def main():
    folder=ROOT/'.runtime/phase2-scale-management-v001';folder.mkdir(exist_ok=True)
    stop=folder/'stop-resource-sampler-001'
    with (folder/'resource-samples-001.jsonl').open('x',encoding='utf-8') as output:
        while not stop.exists():
            ui=[];chrome=0
            for process in psutil.process_iter(['pid','name','cmdline','memory_info']):
                try:
                    command=process.info['cmdline'] or []
                    if any('scale_v001' in word and ('ui_acceptance.py' in word or 'cli_ui_acceptance.py' in word) for word in command):ui.append(process.pid)
                    if 'chrome' in (process.info['name'] or '').lower():chrome+=1
                except (psutil.NoSuchProcess,psutil.AccessDenied):pass
            row={'at_ns':time.time_ns(),'host_available_bytes':psutil.virtual_memory().available,
                 'host_cpu_percent':psutil.cpu_percent(),'active_scale_ui_processes':ui,
                 'active_scale_ui_count':len(ui),'all_host_chrome_process_count':chrome,'host_process_count':len(psutil.pids())}
            try:
                result=subprocess.run(['wsl','-d','BrowserMeme-Ubuntu','--','cat','/proc/meminfo','/proc/loadavg'],
                    capture_output=True,text=True,timeout=12,creationflags=subprocess.CREATE_NO_WINDOW)
                row['wsl_memavailable_bytes']=next(int(line.split()[1])*1024 for line in result.stdout.splitlines() if line.startswith('MemAvailable:'))
                row['wsl_loadavg']=result.stdout.splitlines()[-1]
            except Exception as error:row['wsl_sample_unknown']=type(error).__name__
            output.write(json.dumps(row)+'\n');output.flush()
            time.sleep(2)

if __name__=='__main__':main()
