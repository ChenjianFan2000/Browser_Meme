"""Owned-process resource and orphan-cleanup regressions; no browser/site/model."""
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
import unittest

from harness.replica.monitor import supervise
from harness.replica.resource_guard import ResourceGuard, directory_bytes, proc_snapshot


class RuntimeResourceTest(unittest.TestCase):
    def test_monitor_cleans_detached_child_after_leader_exits(self):
        with tempfile.TemporaryDirectory() as value:
            root = Path(value)
            marker = root/'child.json'
            source = ("import subprocess,sys,json,pathlib; "
                      "p=subprocess.Popen([sys.executable,'-c','import time;time.sleep(30)'],start_new_session=True); "
                      f"pathlib.Path({str(marker)!r}).write_text(json.dumps({{'pid':p.pid}}))")
            result = supervise([sys.executable, '-c', source], root/'watch', timeout=5,
                idle_timeout=3, interval=.03, min_memory_bytes=0, min_disk_bytes=0)
            pid = json.loads(marker.read_text())['pid']
            current = proc_snapshot().get(pid)
            self.assertTrue(current is None or current['state'] == 'Z')
            self.assertTrue(result['process_tree_clean'])
            self.assertEqual(result['reason'], 'completed')

    def test_descendant_cpu_memory_and_disk_trigger_frozen_limits(self):
        with tempfile.TemporaryDirectory() as value:
            root = Path(value)
            ready = root/'ready'
            payload = root/'payload'
            child_code = ("import time,pathlib; a=bytearray(24*1024*1024); "
                          f"pathlib.Path({str(payload)!r}).write_bytes(b'x'*65536); "
                          f"pathlib.Path({str(ready)!r}).touch(); "
                          "end=time.monotonic()+10\nwhile time.monotonic()<end: pass")
            source = "import subprocess,sys; subprocess.run([sys.executable,'-c',"+repr(child_code)+"])"
            child = subprocess.Popen([sys.executable, '-c', source], start_new_session=True)
            try:
                guard = ResourceGuard([child.pid], root,
                    limits={'cpu_seconds': .04, 'rss_bytes': 20*1024*1024, 'disk_growth_bytes': 32768})
                deadline = time.monotonic()+5
                sample = None
                while time.monotonic() < deadline:
                    sample = guard.sample()
                    if set(sample['exceeded']) == {'cpu_seconds', 'rss_bytes', 'disk_growth_bytes'}:
                        break
                    time.sleep(.02)
                self.assertIsNotNone(sample)
                self.assertEqual(set(sample['exceeded']), {'cpu_seconds', 'rss_bytes', 'disk_growth_bytes'})
                self.assertTrue(sample['stop_required'])
                self.assertGreaterEqual(len(sample['processes']), 2)
                self.assertGreater(sample['rss_bytes'], next(row['rss_bytes'] for row in sample['processes'] if row['pid'] == child.pid))
                self.assertEqual(sample['cpu_measurement'], 'sampled_identity_self_cpu_cumulative_lower_bound')
            finally:
                os.killpg(child.pid, signal.SIGKILL)
                child.wait(timeout=3)

    def test_disk_counts_regular_files_once_and_excludes_symlinks(self):
        with tempfile.TemporaryDirectory() as value:
            root = Path(value)
            data = root/'data'
            data.write_bytes(b'x'*512)
            os.link(data, root/'hardlink')
            (root/'symlink').symlink_to('/proc/meminfo')
            self.assertEqual(directory_bytes(root)['logical_bytes'], 512)

    def test_rejects_missing_or_unbounded_resource_limits(self):
        with tempfile.TemporaryDirectory() as value:
            for limits in ({}, {'cpu_seconds': float('inf'), 'rss_bytes': 1, 'disk_growth_bytes': 1},
                           {'cpu_seconds': 1, 'rss_bytes': True, 'disk_growth_bytes': 1}):
                with self.assertRaises(ValueError):
                    ResourceGuard([os.getpid()], value, limits=limits)


if __name__ == '__main__':
    unittest.main()
