"""Synthetic metadata only: nonexistent content sources prove no payload reads."""
import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
P=Path(__file__).with_name('merge_export_manifests_v001.py');spec=importlib.util.spec_from_file_location('merge_test',P);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
class MergeTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.base=Path(self.temp.name);self.out=self.base/'out'
        def invrow(name):return {'source_path':'original/'+name,'archive_path':'result/'+name,'restore_path':'restore/'+name,'expected_original_sha256':name[0]*64}
        def entry(name):return {'source_path':'export/'+name,'original_source_path':'original/'+name,'archive_path':'result/'+name,'restore_path':'restore/'+name,'original_sha256':name[0]*64,'export_sha256':'e'*64,'original_size':13,'export_size':7,'treatment':'redacted','redaction_counts':{'cookie':1},'archive_exclusions':[],'extra_original_metadata':{'preserve':['nested',42]}}
        self.a,self.b,self.c,self.d=[invrow(n) for n in ['a.zip','b.zip','c.zip','d.zip']];self.ea,self.eb,self.ed=[entry(n) for n in ['a.zip','b.zip','d.zip']]
        self.globalx={'source_path':'excluded/auth.json','reason':'excluded_without_opening','content_read_or_hashed':False}
        self.candidatex={'source_path':self.c['source_path'],'archive_path':self.c['archive_path'],'reason':'known_auth','content_read_or_hashed':False}
        self.parentinv={'schema_version':1,'entries':[self.a,self.b,self.c],'excluded_roots':[self.globalx],'source_root':'SYNTHETIC_ROOT'}
        self.parent={'schema_version':1,'status':'export_blocked','source_root':'SYNTHETIC_ROOT','entries':[self.ea],'exclusions':[self.globalx,self.candidatex],'failures':[{'source_path':self.b['source_path'],'error_type':'ValueError','reason':'synthetic_zip_parse'}],'scheduler_error':None}
        self.retryinv={'schema_version':1,'source_root':'SYNTHETIC_ROOT','entries':[self.b],'excluded_roots':[self.globalx]}
        self.retry={'schema_version':1,'status':m.PENDING,'source_root':'SYNTHETIC_ROOT','entries':[self.eb],'exclusions':[self.globalx],'failures':[]}
        self.supinv={'schema_version':1,'source_root':'SYNTHETIC_ROOT','entries':[self.d]}
        self.sup={'schema_version':1,'status':m.PENDING,'source_root':'SYNTHETIC_ROOT','entries':[self.ed],'exclusions':[],'failures':[]}
    def tearDown(self):self.temp.cleanup()
    def pin(self,name,value):
        p=self.base/name;p.write_text(json.dumps(value),encoding='utf-8');return [str(p),m.sha(p)]
    def runmerge(self,include_retry=True,include_sup=True):
        pi=self.pin('pi.json',self.parentinv);self.parent['inventory_sha256']=pi[1];pm=self.pin('pm.json',self.parent)
        ri=self.pin('ri.json',self.retryinv);self.retry['inventory_sha256']=ri[1];rm=self.pin('rm.json',self.retry)
        si=self.pin('si.json',self.supinv);self.sup['inventory_sha256']=si[1];sm=self.pin('sm.json',self.sup)
        return m.merge(pi,pm,[ri+rm] if include_retry else [],[si+sm] if include_sup else [],self.out)
    def test_exact_dictionary_union_lineage_and_no_payload_reads(self):
        result=self.runmerge();self.assertFalse(result['approved_written']);self.assertEqual(result['coverage']['shards'],8)
        final=json.loads((self.out/'export-manifest.pending.json').read_text());inv=json.loads((self.out/'inventory.merged.json').read_text());shards=[json.loads(x.read_text()) for x in sorted(self.out.glob('audit-shard-*.json'))]
        self.assertEqual(final['entries'][0],self.ea);self.assertEqual(final['exclusions'],self.parent['exclusions']);self.assertEqual(len(inv['entries']),4)
        self.assertEqual({m.canon(x) for s in shards for x in s['entries']},{m.canon(x) for x in final['entries']})
        m.check_union(final,shards,inv,m.sha(self.out/'inventory.merged.json'));self.assertTrue(all(r.get('expected_original_sha256') for r in inv['entries']))
    def test_union_rejects_modified_full_dictionary(self):
        self.runmerge();final=json.loads((self.out/'export-manifest.pending.json').read_text());inv=json.loads((self.out/'inventory.merged.json').read_text());shards=[json.loads(x.read_text()) for x in sorted(self.out.glob('audit-shard-*.json'))]
        shards[0]['entries'][0]['extra_original_metadata']['preserve'][1]=99
        with self.assertRaisesRegex(ValueError,'shard_union_differs'):m.check_union(final,shards,inv,m.sha(self.out/'inventory.merged.json'))
    def test_missing_retry_blocks_before_output(self):
        with self.assertRaisesRegex(ValueError,'unrepaired'):self.runmerge(False)
        self.assertFalse(self.out.exists())
    def test_retry_cannot_replace_success(self):
        self.retryinv['entries']=[self.a];self.retry['entries']=[self.ea]
        with self.assertRaisesRegex(ValueError,'exact_unique_parent_failure'):self.runmerge()
    def test_retry_remaining_failure_blocks(self):
        self.retry['failures']=[{'source_path':self.b['source_path']}]
        with self.assertRaisesRegex(ValueError,'complete_bound_pending'):self.runmerge()
    def test_supplement_source_and_archive_collision(self):
        self.supinv['entries'][0]['source_path']=self.a['source_path'];self.sup['entries'][0]['original_source_path']=self.a['source_path']
        with self.assertRaisesRegex(ValueError,'overlap'):self.runmerge()
    def test_no_silent_new_exclusions(self):
        self.retry['exclusions'].append({'source_path':'new/exclusion','content_read_or_hashed':False})
        with self.assertRaisesRegex(ValueError,'new_exclusion'):self.runmerge()
    def test_parent_hash_cannot_change_in_retry(self):
        self.retry['entries'][0]['original_sha256']='f'*64
        with self.assertRaisesRegex(ValueError,'original_hash_inventory'):self.runmerge()
    def test_duplicate_parent_failure_and_partition_gap(self):
        self.parent['failures']*=2
        with self.assertRaisesRegex(ValueError,'duplicate_parent_failure'):self.runmerge()
    def test_duplicate_retry_across_children(self):
        pi=self.pin('pi.json',self.parentinv);self.parent['inventory_sha256']=pi[1];pm=self.pin('pm.json',self.parent);ri=self.pin('ri.json',self.retryinv);self.retry['inventory_sha256']=ri[1];rm=self.pin('rm.json',self.retry)
        with self.assertRaisesRegex(ValueError,'exact_unique_parent_failure'):m.merge(pi,pm,[ri+rm,ri+rm],[],self.out)
    def test_pinned_hash_and_safe_path_guards(self):
        path,good=self.pin('pin.json',self.parentinv)
        with self.assertRaisesRegex(ValueError,'pinned_input_hash'):m.pinned(path,'0'*64)
        for name in ['../bad','/absolute','C:/bad','a\\b','a/./b','']:
            with self.assertRaises(ValueError):m.relative(name)
    def test_new_directory_only_and_no_approval(self):
        self.out.mkdir()
        with self.assertRaisesRegex(ValueError,'new_output_directory'):self.runmerge()
        self.assertEqual(list(self.out.iterdir()),[])
    def test_mapping_restore_and_denominator_guard(self):
        self.retry['entries'][0]['restore_path']='other/path'
        with self.assertRaisesRegex(ValueError,'mapping_mismatch'):self.runmerge()
if __name__=='__main__':unittest.main()
