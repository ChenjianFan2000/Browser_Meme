"""Registered management-only worker identities, never learner input."""
from pathlib import Path
ROOT=Path(__file__).resolve().parents[4]
PARENT=ROOT/'.runtime/phase2-routing-v002'
WORKERS={name:{'id':name,'runtime':ROOT/('.runtime/phase2-eval-worker-'+name),'frontend_port':front,'backend_port':back} for name,front,back in [('a',13042,13138),('b',14042,14138),('c',15042,15138)]}
def identify(path):
    resolved=Path(path).resolve()
    return next((worker for worker in WORKERS.values() if worker['runtime'].resolve()==resolved),None)
