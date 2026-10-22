"""No task execution/DB access: original function code and pure hook equivalence."""
import inspect
import json
import marshal
import os
from management import PRIVATE, ROOT, PARENT, WORKERS, evaluator, load_file, sha

def code_hashes(module):
    import hashlib
    return {name:hashlib.sha256(marshal.dumps(value.__code__)).hexdigest() for name,value in vars(module).items()
            if inspect.isfunction(value) and value.__module__==module.__name__}

def main():
    results=[]
    for key,worker in WORKERS.items():
        original_env=os.environ.get('BM_DISCOGS_PHASE2_RUNTIME')
        os.environ['BM_DISCOGS_PHASE2_RUNTIME']=str(worker['runtime'] if key in 'abc' else PARENT)
        original=load_file('scale_equivalence_original_'+key,PRIVATE/'evaluator.py')
        if original_env is None:os.environ.pop('BM_DISCOGS_PHASE2_RUNTIME',None)
        else:os.environ['BM_DISCOGS_PHASE2_RUNTIME']=original_env
        expanded=evaluator(worker['runtime'])
        assert code_hashes(original)==code_hashes(expanded)
        assert [original.public_case(c) for c in original.cases()]==[expanded.public_case(c) for c in expanded.cases()]
        arguments=dict(method='GET',url='http://127.0.0.1:12042/api/generic-management-probe',status=404,
                       request_body=None,response_body=None,content_type='application/json')
        assert original.ingest_http(**arguments)==expanded.ingest_http(**arguments)
        assert expanded.RUNTIME==worker['runtime'].resolve() and expanded.DB==worker['runtime'].resolve()/'data/discogs.db'
        results.append({'worker_id':key,'all_original_function_code_hashes_equal':True,'public_inventory_identical':True,
                        'pure_ingest_output_equal':True,'runtime_db_binding_correct':True,'business_db_accessed':False})
    output=ROOT/'harness/experiments/phase2-discogs-20261021-01/private/scale-management-equivalence-v001.json'
    with output.open('x',encoding='utf-8') as f:json.dump({'kind':'management_import_hook_equivalence_not_task_test',
        'signature':'ingest_http(method,url,status,request_body=None,response_body=None,content_type=None)',
        'frozen_evaluator_sha256':sha(PRIVATE/'evaluator.py'),'frozen_driver_sha256':sha(PRIVATE/'driver.py'),
        'results':results,'original_abc_state_read_or_reset':False},f,indent=2)
    print(json.dumps({'status':'passed','workers':len(results),'output':str(output),'sha256':sha(output)}))

if __name__=='__main__':main()
