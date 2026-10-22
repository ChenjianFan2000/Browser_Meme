"""Small real Python-process shards, using generated synthetic files only."""
import contextlib
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest

import run_export_shards_v001 as tool


class ShardTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix="phase2-export-shards-synthetic-")
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)/"source"; self.root.mkdir()
        self.originals={}; rows=[]
        for n in range(16):
            name=f"scope/file-{n:03d}.json"
            data=json.dumps({'keep':n,'access_'+'token':'synthetic-value'}).encode()
            path=self.root/name; path.parent.mkdir(parents=True,exist_ok=True); path.write_bytes(data)
            self.originals[name]=data
            rows.append({'source_path':name,'archive_path':name,'expected_original_sha256':hashlib.sha256(data).hexdigest()})
        self.rows=rows
        self.inventory=self.root/'inventory.json'
        self.save_inventory()

    def save_inventory(self):
        value={'schema_version':1,'status':'inventory_only_not_publication_approval','source_root':str(self.root),'entries':self.rows,
               'excluded_roots':[{'source_path':'excluded-cache','reason':'synthetic exclusion','content_read_or_hashed':False}]}
        self.inventory.write_text(json.dumps(value),encoding='utf-8')

    def run_shards(self,name,count,**kwargs):
        with contextlib.redirect_stdout(io.StringIO()):
            return tool.run_shards(self.root,self.inventory,self.root/name,shards=count,jobs=count,**kwargs)

    def test_one_two_eight_processes_equivalent_complete_and_originals_unchanged(self):
        views=[]
        for count in [1,2,8]:
            value=self.run_shards(f'exports-{count}',count)
            self.assertEqual(value['status'],'exported_pending_independent_approval')
            self.assertEqual(value['counts'],{'included':16,'excluded':1,'redacted':16})
            self.assertTrue(value['coverage']['all_original_entries_accounted_for'])
            self.assertEqual(len(value['shards']),count)
            self.assertEqual(value['inventory_sha256'],hashlib.sha256(self.inventory.read_bytes()).hexdigest())
            for shard in value['shards']:
                self.assertEqual(shard['exit_code'],0)
                self.assertEqual(shard['manifest_sha256'],hashlib.sha256((self.root/shard['manifest_path']).read_bytes()).hexdigest())
                self.assertTrue((self.root/shard['stdout_path']).exists())
                self.assertTrue((self.root/shard['stderr_path']).exists())
            normalized=[]
            for entry in value['entries']:
                data=(self.root/entry['source_path']).read_bytes()
                self.assertEqual(hashlib.sha256(data).hexdigest(),entry['export_sha256'])
                normalized.append({k:entry[k] for k in ['archive_path','original_sha256','export_sha256','treatment','redaction_counts']})
            views.append(normalized)
        self.assertEqual(views[0],views[1]); self.assertEqual(views[1],views[2])
        for name,data in self.originals.items(): self.assertEqual((self.root/name).read_bytes(),data)

    def test_child_failure_and_auth_exclusion_aggregate_without_approval(self):
        (self.root/'scope/unknown.bin').write_bytes(b'\xff\x00synthetic-binary')
        (self.root/'scope/auth.json').write_bytes(b'synthetic blocked store')
        for name in ['scope/unknown.bin','scope/auth.json']: self.rows.append({'source_path':name,'archive_path':name})
        self.save_inventory()
        value=self.run_shards('exports-blocked',2)
        self.assertEqual(value['status'],'export_blocked')
        self.assertEqual(len(value['failures']),1)
        self.assertEqual(value['failures'][0]['source_path'],'scope/unknown.bin')
        self.assertEqual(value['counts']['included'],16)
        self.assertEqual(value['counts']['excluded'],2)
        self.assertEqual(value['coverage']['excluded_entry_count'],1)
        self.assertTrue(value['coverage']['all_original_entries_accounted_for'])
        self.assertTrue(value['not_yet_approved_for_publication'])

    def test_missing_child_manifest_keeps_every_entry_as_failure(self):
        stub=self.root/'synthetic_failed_exporter.py'; stub.write_text('raise SystemExit(7)\n',encoding='utf-8')
        value=self.run_shards('exports-no-child-result',2,exporter=stub)
        self.assertEqual(value['status'],'export_blocked')
        self.assertEqual(len(value['failures']),16)
        self.assertEqual(value['coverage']['failure_entry_count'],16)
        self.assertEqual(value['counts']['included'],0)
        self.assertEqual(len(value['shard_failures']),2)

    def test_duplicates_traversal_hash_and_existing_output_refused(self):
        self.rows[1]['archive_path']=self.rows[0]['archive_path']; self.save_inventory()
        with self.assertRaises(ValueError): self.run_shards('bad-duplicate',2)
        self.assertFalse((self.root/'bad-duplicate').exists())
        self.rows[1]['archive_path']='../escape'; self.save_inventory()
        with self.assertRaises(ValueError): self.run_shards('bad-traversal',2)
        self.rows[1]['archive_path']='scope/file-001.json'; self.save_inventory()
        with self.assertRaises(ValueError): self.run_shards('bad-pin',2,inventory_sha256='0'*64)
        (self.root/'existing').mkdir()
        with self.assertRaises(ValueError): self.run_shards('existing',2)


if __name__=='__main__': unittest.main(verbosity=2)
