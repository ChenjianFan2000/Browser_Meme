"""Read-only, uncached Windows drive latency diagnostic; writes only a G: report."""
import ctypes as c
from ctypes import wintypes as w
import json
from pathlib import Path
import time

root = Path(__file__).resolve().parents[2]
path = root / '.runtime/downloads/ubuntu-base-24.04.4-base-amd64.tar.gz'
k = c.WinDLL('kernel32', use_last_error=True)
k.CreateFileW.argtypes = [w.LPCWSTR, w.DWORD, w.DWORD, c.c_void_p, w.DWORD, w.DWORD, w.HANDLE]
k.CreateFileW.restype = w.HANDLE
k.VirtualAlloc.argtypes = [c.c_void_p, c.c_size_t, w.DWORD, w.DWORD]
k.VirtualAlloc.restype = c.c_void_p
k.SetFilePointerEx.argtypes = [w.HANDLE, c.c_longlong, c.POINTER(c.c_longlong), w.DWORD]
k.ReadFile.argtypes = [w.HANDLE, c.c_void_p, w.DWORD, c.POINTER(w.DWORD), c.c_void_p]
k.CloseHandle.argtypes = [w.HANDLE]
k.VirtualFree.argtypes = [c.c_void_p, c.c_size_t, w.DWORD]
handle = k.CreateFileW(str(path), 0x80000000, 7, None, 3, 0x20000000 | 0x10000000, None)
if handle == w.HANDLE(-1).value:
    raise c.WinError(c.get_last_error())
buffer = k.VirtualAlloc(None, 4096, 0x3000, 0x04)
if not buffer:
    k.CloseHandle(handle)
    raise c.WinError(c.get_last_error())
durations = []
try:
    for offset in (0, 4*1024**2, 16*1024**2, 8*1024**2, 24*1024**2):
        actual = w.DWORD()
        started = time.perf_counter()
        if not k.SetFilePointerEx(handle, offset, None, 0):
            raise c.WinError(c.get_last_error())
        if not k.ReadFile(handle, buffer, 4096, c.byref(actual), None):
            raise c.WinError(c.get_last_error())
        durations.append(round((time.perf_counter()-started)*1000, 3))
finally:
    k.CloseHandle(handle)
    k.VirtualFree(buffer, 0, 0x8000)
report = {'path': str(path), 'uncached_4k_read_ms': durations}
(root / '.runtime/logs/windows-storage-read.json').write_text(json.dumps(report, indent=2))
print(json.dumps(report, indent=2))
