"""Real child/grandchild lifetime test, unrelated to website behavior."""
import ctypes
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest

from harness.process_group import OwnedProcessGroup


@unittest.skipUnless(os.name == "nt", "Windows Job Object regression")
class OwnedProcessGroupTests(unittest.TestCase):
    def test_job_reaps_grandchild_after_worker_exits(self):
        from ctypes import wintypes as w
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            worker = root / "worker.py"
            worker.write_text(
                "import pathlib,subprocess,sys,time\n"
                "root=pathlib.Path(sys.argv[1])\n"
                "while not (root/'go').exists(): time.sleep(.02)\n"
                "child=subprocess.Popen([sys.executable,'-c','import time; time.sleep(60)'])\n"
                "(root/'pid').write_text(str(child.pid))\n", encoding="utf-8")
            child = subprocess.Popen([sys.executable, str(worker), str(root)], creationflags=subprocess.CREATE_NO_WINDOW)
            group = OwnedProcessGroup(child)
            handle = None
            try:
                (root / "go").touch()
                deadline = time.monotonic() + 10
                while not (root / "pid").exists() and time.monotonic() < deadline:
                    time.sleep(.02)
                self.assertTrue((root / "pid").exists())
                child.wait(timeout=10)
                grandchild = int((root / "pid").read_text())
                kernel = ctypes.WinDLL("kernel32", use_last_error=True)
                kernel.OpenProcess.argtypes = [w.DWORD, w.BOOL, w.DWORD]
                kernel.OpenProcess.restype = w.HANDLE
                kernel.WaitForSingleObject.argtypes = [w.HANDLE, w.DWORD]
                kernel.WaitForSingleObject.restype = w.DWORD
                kernel.CloseHandle.argtypes = [w.HANDLE]
                handle = kernel.OpenProcess(0x100000, False, grandchild)
                self.assertTrue(handle)
                self.assertEqual(kernel.WaitForSingleObject(handle, 0), 258)
                group.close()
                self.assertEqual(kernel.WaitForSingleObject(handle, 5000), 0)
            finally:
                group.close()
                if handle:
                    kernel.CloseHandle(handle)


if __name__ == "__main__":
    unittest.main()
