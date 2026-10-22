"""Management-only deployment; delegates unchanged, hash-checked original build."""
import importlib.util
import os
from pathlib import Path
ROOT = Path(__file__).resolve().parents[4]
RUNTIME = ROOT / '.runtime/phase2-discogs-20261021-01'
os.environ['BM_DISCOGS_RUNTIME'] = str(RUNTIME)
os.environ['BM_DISCOGS_REFERENCE_RUNTIME'] = str(ROOT / '.runtime/phase1-discogs-pw-20261020-1633')
spec = importlib.util.spec_from_file_location('phase2_original_deploy', ROOT / 'harness/sites/discogs/loop_deploy.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
if __name__ == '__main__':
    module.main()
