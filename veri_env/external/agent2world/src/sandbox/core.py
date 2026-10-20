from __future__ import annotations
"""
沙箱核心功能模块
"""
import os
import sys
import subprocess
import tempfile
import signal
import json
import resource
import shutil
import ast
import threading
import time
import atexit
from pathlib import Path
from typing import Dict, Any, List, Optional, Set
import uuid
from datetime import datetime, timedelta
HEAVY_PACKAGES = {
    "numpy": 1536,      # 1.5GB
    "pandas": 2048,     # 2GB  
    "torch": 4096,      # 4GB
    "tensorflow": 4096, # 4GB
    "scipy": 1536,      # 1.5GB
}


class SandboxCleaner:
    
    def __init__(self):
        self.cleanup_items: Set[str] = set()
        self.lock = threading.Lock()
        self._registered = False
    
    def register_cleanup(self, path: str):
        with self.lock:
            self.cleanup_items.add(path)
            if not self._registered:
                atexit.register(self.cleanup_all)
                self._registered = True
    
    def remove_cleanup(self, path: str):
        with self.lock:
            self.cleanup_items.discard(path)
    
    def cleanup_all(self):
        with self.lock:
            for item in list(self.cleanup_items):
                try:
                    if os.path.exists(item):
                        if os.path.isdir(item):
                            shutil.rmtree(item)
                        else:
                            os.unlink(item)
                except Exception:
                    pass  
            self.cleanup_items.clear()

_global_cleaner = SandboxCleaner()


def cleanup_all_sandboxes():
    from .session_manager import _global_session_manager
    _global_cleaner.cleanup_all()
    _global_session_manager.cleanup_all_sessions()
    print(" 所有沙箱已清理完成")
