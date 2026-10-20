"""Static parse audit plus dependency and original PatchWorld import smoke audit."""
from pathlib import Path
import ast, importlib.util, json, platform, sys

ROOT = Path(__file__).resolve().parents[2]
sys.dont_write_bytecode = True
manifest = json.loads((ROOT / 'SOURCE_MANIFEST.json').read_text(encoding='utf-8'))
out = {'python': sys.version, 'platform': platform.platform(), 'repositories': [], 'dependencies': {}, 'patchworld_smoke': {}}
for repo in manifest['repositories']:
    result = {'repo': repo['repo'], 'python_files': 0, 'parse_errors': []}
    for entry in repo['files']:
        if entry['status'] != 'downloaded_verified' or not entry['path'].endswith('.py'):
            continue
        path = ROOT / repo.get('local_root', 'external/' + repo['repo']) / entry['path']
        result['python_files'] += 1
        try:
            ast.parse(path.read_text(encoding='utf-8-sig'), filename=str(path))
        except Exception as exc:
            result['parse_errors'].append({'path': entry['path'], 'error': str(exc)})
    out['repositories'].append(result)
for name in ['numpy','torch','openai','anthropic','dill','gitinfo','mloggers','autopep8','gymnasium','hydra','omegaconf','openai_hf_interface','jsonlines','json_repair','tqdm','PIL','playwright','pydantic','loguru','tiktoken','transformers','func_timeout','pygame','ale_py']:
    try:
        spec = importlib.util.find_spec(name)
        out['dependencies'][name] = {'available': spec is not None, 'origin': spec.origin if spec else None}
    except Exception as exc:
        out['dependencies'][name] = {'available': False, 'error': str(exc)}
try:
    sys.path.insert(0, str(ROOT / 'external' / 'PatchWorld'))
    from patchworld.worldmodel_base import GraphState, BaseWorldModel
    from patchworld.worldmodel_data import Transition, Trajectory
    from patchworld.worldmodel_validator import validate_model, load_model_from_code
    import inspect
    transition = Transition('obs','act','next',0.0,False)
    trajectory = Trajectory([transition],'issue','smoke',0,0,'train',False,0.0)
    assert trajectory.num_steps == 1 and trajectory.task_description == 'obs'
    out['patchworld_smoke'] = {'status': 'passed', 'GraphState': str(inspect.signature(GraphState)), 'validate_model': str(inspect.signature(validate_model)), 'tested': 'Original package imports and Transition/Trajectory dataclass behavior only; no LLM, environment server, or generated model execution.'}
except Exception as exc:
    out['patchworld_smoke'] = {'status':'failed', 'error':repr(exc)}
(ROOT / 'artifacts/source_downloads/audit_results.json').write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps({'python_files':sum(x['python_files'] for x in out['repositories']), 'parse_errors':[{'repo':x['repo'],**e} for x in out['repositories'] for e in x['parse_errors']], 'patchworld_smoke':out['patchworld_smoke'], 'missing_dependencies':[k for k,v in out['dependencies'].items() if not v['available']]},ensure_ascii=False))
