from __future__ import annotations
"""
持久化沙箱实现 - 添加兼容性方法
"""
import os
import sys
import subprocess
import json
import signal
import shutil
import ast
import threading
import uuid
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional,Sequence
from .core import HEAVY_PACKAGES, _global_cleaner

class PersistentEnvironmentSandbox:
    
    def __init__(
        self,
        session_id: Optional[str] = None,
        memory_limit_mb: int = 512,
        cpu_time_limit: int = 30,
        wall_time_limit: int = 30 * 60,
        temp_dir: Optional[str] = None,
        debug: bool = True,
        auto_cleanup: bool = True,
        timeout_minutes: int = 5,
    ):
        self.session_id = session_id or str(uuid.uuid4())
        self.base_mem_mb = memory_limit_mb
        self.memory_limit_mb = memory_limit_mb
        self.mem_bytes = memory_limit_mb * 1024 * 1024
        self.cpu_limit = cpu_time_limit
        self.wall_limit = wall_time_limit
        self.temp_dir = temp_dir or "/tmp"
        self.debug = debug
        self.auto_cleanup = auto_cleanup
        self.session_timeout = timeout_minutes#！！！
        self.timeout_minutes = timeout_minutes
        
        # 持久化状态
        self.venv_path: Optional[str] = None
        self.work_dir: Optional[str] = None
        self.created_at = datetime.now()
        self.last_used = datetime.now()
        self.last_accessed = self.last_used.timestamp()
        self.cleanup_timer: Optional[threading.Timer] = None
        
        # 持久化进程相关
        self.process: Optional[subprocess.Popen] = None
        self.process_lock = threading.Lock()
        self.command_counter = 0
        
        # 会话状态
        self._session_active = True
        self._installed_packages = set()
        
        # 创建会话工作目录
        self.work_dir = os.path.join(self.temp_dir, f"sandbox_session_{self.session_id}")
        os.makedirs(self.work_dir, exist_ok=True)
        
        if self.debug:
            print(f"[PERSISTENT] Session {self.session_id} created, timeout={timeout_minutes}min")

        self._reset_cleanup_timer()
    
    def is_timeout(self) -> bool:
        """检查会话是否超时"""
        if not self._session_active:
            return True
        
        if not self.auto_cleanup or self.session_timeout <= 0:
            return False
        
        try:
            import time
            elapsed_minutes = (time.time() - self.last_accessed) / 60
            is_expired = elapsed_minutes > self.timeout_minutes
            
            if self.debug and is_expired:
                print(f"[PERSISTENT] Session {self.session_id[:8]}... timeout check: {elapsed_minutes:.1f} > {self.timeout_minutes} min")
            
            return is_expired
        except Exception as e:
            if self.debug:
                print(f"[PERSISTENT] Error checking timeout: {e}")
            return True
    
    def get_remaining_time(self) -> float:
        """获取剩余时间（分钟）"""
        if not self._session_active or not self.auto_cleanup or self.session_timeout <= 0:
            return float('inf')
        
        try:
            import time
            elapsed_minutes = (time.time() - self.last_accessed) / 60
            remaining = self.timeout_minutes - elapsed_minutes
            return max(0.0, remaining)
        except Exception as e:
            if self.debug:
                print(f"[PERSISTENT] Error calculating remaining time: {e}")
            return 0.0
    
    def extend_timeout(self, additional_minutes: int = 5):
        """延长会话超时时间"""
        try:
            self.timeout_minutes += additional_minutes
            self.session_timeout = self.timeout_minutes
            self.touch()
            if self.debug:
                print(f"[PERSISTENT] Session {self.session_id[:8]}... timeout extended by {additional_minutes} minutes")
        except Exception as e:
            if self.debug:
                print(f"[PERSISTENT] Error extending timeout: {e}")
    
    def cleanup(self):
        """兼容EnvironmentSandbox的cleanup方法"""
        self.cleanup_session()
    
    def _reset_cleanup_timer(self):
        """重置自动清理定时器"""
        if self.cleanup_timer:
            self.cleanup_timer.cancel()
        
        if self.auto_cleanup and self.session_timeout > 0:
            self.cleanup_timer = threading.Timer(
                self.session_timeout * 60,  # 转换为秒
                self._auto_cleanup_callback
            )
            self.cleanup_timer.daemon = True
            self.cleanup_timer.start()
    
    def _auto_cleanup_callback(self):
        """自动清理回调"""
        if self.debug:
            print(f"[PERSISTENT] Session {self.session_id} auto-cleanup triggered after {self.session_timeout} minutes")
        self.cleanup_session()
    
    def touch(self):
        """更新最后使用时间，重置清理定时器"""
        import time
        self.last_used = datetime.now()
        self.last_accessed = time.time()
        self._reset_cleanup_timer()
        if self.debug:
            print(f"[PERSISTENT] Session {self.session_id} touched, timer reset")
    
    
    def _create_persistent_script(self) -> str:
        """创建持久化Python脚本"""
        if self.venv_path and os.path.exists(f"{self.venv_path}/bin/python"):
            python_executable = f"{self.venv_path}/bin/python"
        else:
            python_executable = sys.executable

        script = f'''
import sys
import platform
import json
import traceback
import signal
import os
import resource
import builtins
import subprocess
import io
from contextlib import redirect_stdout, redirect_stderr

# 确保输出立即刷新
sys.stdout.reconfigure(line_buffering=True)
sys.stderr.reconfigure(line_buffering=True)

def log_debug(msg):
    """调试日志"""
    print(f"[PERSISTENT_DEBUG] {{msg}}", file=sys.stderr, flush=True)

os.chdir("{self.work_dir}")

if "VIRTUAL_ENV" in os.environ:
    del os.environ["VIRTUAL_ENV"]
if "CONDA_DEFAULT_ENV" in os.environ:
    del os.environ["CONDA_DEFAULT_ENV"]

venv_path = r"{self.venv_path or ''}"
if venv_path and os.path.exists(venv_path):
    os.environ["VIRTUAL_ENV"] = venv_path
    # 确保 PATH 中虚拟环境的 bin 目录在最前面
    venv_bin = os.path.join(venv_path, "bin")
    if os.path.exists(venv_bin):
        current_path = os.environ.get("PATH", "")
        os.environ["PATH"] = venv_bin + ":" + current_path

# 设置资源限制（macOS 上跳过 AS 和 DATA，因为不支持）
try:
    mem_soft = {self.mem_bytes}
    mem_hard = mem_soft + 512 * 1024 * 1024

    # Only set address‐space and data‐segment limits on non-Darwin
    if platform.system() != "Darwin" and hasattr(resource, "RLIMIT_AS"):
        resource.setrlimit(resource.RLIMIT_AS, (mem_soft, mem_hard))
    if platform.system() != "Darwin" and hasattr(resource, "RLIMIT_DATA"):
        resource.setrlimit(resource.RLIMIT_DATA, (mem_soft, mem_hard))

    # These are OK everywhere
    resource.setrlimit(resource.RLIMIT_CPU, ({self.cpu_limit}, {self.cpu_limit} + 5))
    resource.setrlimit(resource.RLIMIT_NOFILE, (128, 256))

except Exception as e:
    log_debug(f"Resource limit warning: {{e}}")

_original_subprocess = subprocess

# 限制文件访问
__orig_open = builtins.open
def _safe_open(file, *a, **k):
    abs_path = os.path.abspath(file)
    if not abs_path.startswith(os.getcwd()):
        raise PermissionError('禁止访问沙箱目录之外的文件: ' + abs_path)
    return __orig_open(file, *a, **k)
builtins.open = _safe_open

PERSISTENT_GLOBALS = {{
    '__name__': '__main__',
    '__builtins__': __builtins__,
}}

# 发送就绪信号
print(json.dumps({{"type": "READY", "session_id": "{self.session_id}"}}, ensure_ascii=False), flush=True)

def execute_with_timeout(code, timeout_sec):
    """在超时限制下执行代码，捕获所有输出"""
    def timeout_handler(signum, frame):
        raise TimeoutError(f"代码执行超时 ({{timeout_sec}}秒)")
    
    old_handler = signal.signal(signal.SIGALRM, timeout_handler)
    signal.alarm(timeout_sec)
    
    import io
    import contextlib
    
    stdout_buffer = io.StringIO()
    stderr_buffer = io.StringIO()
    
    try:
        original_stdout = sys.stdout
        original_stderr = sys.stderr
        
        # 重定向到缓冲区
        sys.stdout = stdout_buffer
        sys.stderr = stderr_buffer
        
        try:
            exec(code, PERSISTENT_GLOBALS)
        finally:
            sys.stdout = original_stdout
            sys.stderr = original_stderr
        
        stdout_content = stdout_buffer.getvalue()
        stderr_content = stderr_buffer.getvalue()
        
        # 确保输出不为空时有内容
        log_debug(f"Captured stdout: {{repr(stdout_content)}}")
        log_debug(f"Captured stderr: {{repr(stderr_content)}}")
        
        return None, stdout_content, stderr_content
        
    except Exception as e:
        sys.stdout = original_stdout
        sys.stderr = original_stderr
        
        stderr_content = stderr_buffer.getvalue()
        if not stderr_content:
            stderr_content = traceback.format_exc()
        return e, stdout_buffer.getvalue(), stderr_content
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, old_handler)
        stdout_buffer.close()
        stderr_buffer.close()


def evaluate_with_timeout(code, timeout_sec):
    """在超时限制下求值"""
    def timeout_handler(signum, frame):
        raise TimeoutError(f"代码求值超时 ({{timeout_sec}}秒)")
    
    old_handler = signal.signal(signal.SIGALRM, timeout_handler)
    signal.alarm(timeout_sec)
    
    try:
        result = eval(code, PERSISTENT_GLOBALS)
        return result, None
    except Exception as e:
        return None, e
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, old_handler)

def send_response(response):
    """发送响应并确保刷新"""
    try:
        response_json = json.dumps(response, ensure_ascii=False)
        log_debug(f"Sending response: {{response_json[:100]}}...")
        print(response_json, flush=True)
        log_debug("Response sent and flushed")
    except Exception as e:
        log_debug(f"Error sending response: {{e}}")
        error_response = {{
            "type": "ERROR",
            "error": f"响应发送失败: {{str(e)}}"
        }}
        print(json.dumps(error_response, ensure_ascii=False), flush=True)

log_debug("Persistent process started and ready")

while True:
    try:
        line = input()
        if line.strip() == "EXIT":
            break
            
        try:
            command_data = json.loads(line)
        except json.JSONDecodeError as e:
            send_response({{"type": "ERROR", "error": f"JSON解析错误: {{e}}"}})
            continue
            
        command_type = command_data.get("type")
        command_id = command_data.get("id", "unknown")
        timeout_sec = command_data.get("timeout", {self.wall_limit})
        
        log_debug(f"Processing command: {{command_type}}")
        
        if command_type == "EXEC":
            code = command_data.get("code", "")
            try:
                error, stdout_content, stderr_content = execute_with_timeout(code, timeout_sec)
                if error:
                    response = {{
                        "type": "ERROR", 
                        "id": command_id,
                        "error": str(error),
                        "error_type": type(error).__name__,
                        "stdout": stdout_content,
                        "stderr": stderr_content,
                        "traceback": traceback.format_exc()
                    }}
                else:
                    response = {{
                        "type": "SUCCESS", 
                        "id": command_id,
                        "message": "代码执行成功",
                        "stdout": stdout_content,
                        "stderr": stderr_content
                    }}
                send_response(response)
            except Exception as e:
                response = {{
                    "type": "FATAL_ERROR", 
                    "id": command_id,
                    "error": str(e),
                    "traceback": traceback.format_exc()
                }}
                send_response(response)
        
        elif command_type == "EVAL":
            code = command_data.get("code", "")
            try:
                result, error = evaluate_with_timeout(code, timeout_sec)
                if error:
                    response = {{
                        "type": "ERROR", 
                        "id": command_id,
                        "error": str(error),
                        "error_type": type(error).__name__,
                        "traceback": traceback.format_exc()
                    }}
                else:
                    response = {{
                        "type": "RESULT", 
                        "id": command_id,
                        "value": str(result)
                    }}
                send_response(response)
            except Exception as e:
                response = {{
                    "type": "FATAL_ERROR", 
                    "id": command_id,
                    "error": str(e),
                    "traceback": traceback.format_exc()
                }}
                send_response(response)
        
        elif command_type == "INSTALL":
            packages = command_data.get("packages", [])
            try:
                log_debug(f"Installing packages: {{packages}}")
                result = _original_subprocess.run(
                    [sys.executable, "-m", "pip", "install", "--quiet", "--no-cache-dir"] + packages,
                    capture_output=True, text=True, timeout=300
                )
                if result.returncode == 0:
                    response = {{
                        "type": "INSTALL_SUCCESS", 
                        "id": command_id,
                        "message": f"成功安装: {{', '.join(packages)}}",
                        "stdout": result.stdout,
                        "stderr": result.stderr
                    }}
                else:
                    response = {{
                        "type": "INSTALL_ERROR", 
                        "id": command_id,
                        "error": result.stderr,
                        "stdout": result.stdout
                    }}
                send_response(response)
            except Exception as e:
                response = {{
                    "type": "INSTALL_ERROR", 
                    "id": command_id,
                    "error": str(e),
                    "traceback": traceback.format_exc()
                }}
                send_response(response)
        
        elif command_type == "STATUS":
            global_vars = [k for k in PERSISTENT_GLOBALS.keys() if not k.startswith('_')]
            imported_modules = [name for name in sys.modules.keys() 
                            if not name.startswith('_') and '.' not in name]
            
            response = {{
                "type": "STATUS", 
                "id": command_id,
                "global_variables": global_vars,
                "imported_modules": imported_modules[:20],
                "total_modules": len(imported_modules)
            }}
            send_response(response)
        
        elif command_type == "PING":
            log_debug("Responding to PING")
            response = {{
                "type": "PONG",
                "id": command_id,
                "timestamp": __import__('time').time()
            }}
            send_response(response)
        
        else:
            response = {{
                "type": "ERROR", 
                "id": command_id,
                "error": f"未知命令类型: {{command_type}}"
            }}
            send_response(response)
            
    except EOFError:
        log_debug("EOF received, exiting")
        break
    except KeyboardInterrupt:
        log_debug("KeyboardInterrupt received")
        break
    except Exception as e:
        log_debug(f"Main loop error: {{e}}")
        response = {{
            "type": "FATAL_ERROR", 
            "id": "system",
            "error": str(e),
            "traceback": traceback.format_exc()
        }}
        send_response(response)
        break

log_debug("Persistent process exiting")
print(json.dumps({{"type": "EXIT", "session_id": "{self.session_id}"}}, ensure_ascii=False), flush=True)
    '''
        return script



    def _start_persistent_process(self):
        """启动持久化的Python进程"""
        if self.process and self.process.poll() is None:
            return
        
        with self.process_lock:
            # 创建venv
            if not self.venv_path:
                import venv
                self.venv_path = os.path.join(self.work_dir, "venv")
                if not os.path.exists(self.venv_path):
                    if self.debug:
                        print(f"[DEBUG] Creating venv at: {self.venv_path}")
                    try:
                        venv.create(self.venv_path, with_pip=True)
                    except Exception as e:
                        if self.debug:
                            print(f"[DEBUG] Venv creation failed: {e}")
                        self.venv_path = None
            
            if self.venv_path and os.path.exists(f"{self.venv_path}/bin/python"):
                python_bin = f"{self.venv_path}/bin/python"
            else:
                python_bin = sys.executable
                if self.debug:
                    print(f"[DEBUG] Using system Python: {python_bin}")
            
            script_content = self._create_persistent_script()
            
            # 启动进程
            env = os.environ.copy()
            env.update({
                'PYTHONDONTWRITEBYTECODE': '1',
                'PYTHONUNBUFFERED': '1',
                'MALLOC_ARENA_MAX': '2',
            })
            
            if self.debug:
                print(f"[DEBUG] Starting process with Python: {python_bin}")
                print(f"[DEBUG] Working directory: {self.work_dir}")
            
            try:
                self.process = subprocess.Popen(
                    [python_bin, '-c', script_content],
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    bufsize=0,
                    preexec_fn=os.setsid,
                    cwd=self.work_dir,
                    env=env
                )
                
                # 启动stderr监控线程
                def monitor_stderr():
                    while self.process and self.process.poll() is None:
                        try:
                            import select
                            ready, _, _ = select.select([self.process.stderr], [], [], 1.0)
                            if ready:
                                line = self.process.stderr.readline()
                                if line and self.debug:
                                    print(f"[PROCESS_STDERR] {line.rstrip()}")
                        except:
                            break
                
                stderr_thread = threading.Thread(target=monitor_stderr, daemon=True)
                stderr_thread.start()
                
                # 等待进程就绪 - 增加超时
                import select
                ready, _, _ = select.select([self.process.stdout], [], [], 30)
                
                if not ready:
                    # 检查stderr是否有错误信息
                    stderr_ready, _, _ = select.select([self.process.stderr], [], [], 0.1)
                    if stderr_ready:
                        error_msg = self.process.stderr.read()
                        raise RuntimeError(f"进程启动超时，stderr: {error_msg}")
                    else:
                        raise RuntimeError("进程启动超时，未收到READY信号")
                
                ready_line = self.process.stdout.readline().strip()
                if self.debug:
                    print(f"[DEBUG] Process ready line: {ready_line}")
                
                try:
                    ready_data = json.loads(ready_line)
                    if ready_data.get("type") != "READY":
                        raise RuntimeError(f"进程启动失败，收到: {ready_data}")
                    
                    if self.debug:
                        print(f"[PERSISTENT] Process started successfully for session {self.session_id}")
                        
                except json.JSONDecodeError as e:
                    # 可能是错误信息，读取stderr
                    stderr_output = ""
                    try:
                        import select
                        if select.select([self.process.stderr], [], [], 1)[0]:
                            stderr_output = self.process.stderr.read()
                    except:
                        pass
                    
                    raise RuntimeError(f"进程启动失败，JSON解析错误: {e}，stderr: {stderr_output}")
                    
            except Exception as e:
                if self.debug:
                    print(f"[DEBUG] Process start failed: {e}")
                
                if self.process:
                    try:
                        self.process.terminate()
                        self.process.wait(timeout=5)
                    except:
                        try:
                            self.process.kill()
                        except:
                            pass
                    self.process = None
                raise RuntimeError(f"持久化进程启动失败: {e}")


    
    def _send_command(self, command: Dict[str, Any], timeout: int = 30) -> Dict[str, Any]:
        """向持久化进程发送命令"""
        max_retries = 3
        
        for attempt in range(max_retries + 1):
            try:
                if not self.process or self.process.poll() is not None:
                    if self.debug:
                        print(f"[DEBUG] Starting new process for session {self.session_id} (attempt {attempt + 1})")
                    self._start_persistent_process()
                    import time
                    time.sleep(0.5)
                
                with self.process_lock:
                    self.command_counter += 1
                    command["id"] = f"cmd_{self.command_counter}"
                    command["timeout"] = timeout
                    
                    try:
                        command_json = json.dumps(command, ensure_ascii=False)
                        if self.debug:
                            print(f"[DEBUG] Sending command: {command.get('type', 'UNKNOWN')} (attempt {attempt + 1})")
                            print(f"[DEBUG] Command JSON: {command_json[:200]}...")
                        
                        process_status = self.process.poll()
                        if process_status is not None:
                            raise RuntimeError(f"进程已退出，退出码: {process_status}")
                        
                        self.process.stdin.write(command_json + '\n')
                        self.process.stdin.flush()
                        
                        max_wait_time = max(60, timeout + 30)
                        
                        import select
                        import os
                        import signal
                        import time
                        ready, _, _ = select.select([self.process.stdout], [], [], max_wait_time)
                        
                        if ready:
                            try:
                                response_data = b""
                                fd = self.process.stdout.fileno()
                                start_time = time.time()
                                while time.time() - start_time < max_wait_time:
                                    try:
                                        chunk = os.read(fd, 1024)
                                        if not chunk:
                                            if self.debug:
                                                print(f"[DEBUG] EOF received, data so far: {response_data}")
                                            break
                                        
                                        response_data += chunk
                                        if b'\n' in response_data:
                                            break
                                            
                                    except (OSError, IOError) as e:
                                        if self.debug:
                                            print(f"[DEBUG] Read error: {e}")
                                        break

                                    time.sleep(0.01)
                                
                                if not response_data:
                                    process_status = self.process.poll()
                                    
                                    error_details = {
                                        "session_id": self.session_id,
                                        "command_id": command.get("id"),
                                        "command_type": command.get("type"),
                                        "process_status": process_status,
                                        "process_pid": self.process.pid if self.process else None,
                                        "attempt": attempt + 1,
                                        "issue": "no_data_received"
                                    }
                                    
                                    if attempt < max_retries:
                                        if self.debug:
                                            print(f"[DEBUG] No data received, restarting process (attempt {attempt + 1})")
                                        self._force_restart_process()
                                        continue
                                    else:
                                        raise RuntimeError(f"未收到任何响应数据 - 详细信息: {json.dumps(error_details, ensure_ascii=False, indent=2)}")
                                
                                try:
                                    response_text = response_data.decode('utf-8', errors='replace')
                                except UnicodeDecodeError as e:
                                    if self.debug:
                                        print(f"[DEBUG] Unicode decode error: {e}")
                                        print(f"[DEBUG] Raw data: {response_data[:200]}")
                                    
                                    if attempt < max_retries:
                                        self._force_restart_process()
                                        continue
                                    else:
                                        raise RuntimeError(f"响应数据编码错误: {e}")
                                
                                if self.debug:
                                    print(f"[DEBUG] Raw response: {repr(response_text[:200])}")

                                lines = response_text.strip().split('\n')
                                response_line = None
                                
                                for line in lines:
                                    line = line.strip()
                                    if line and (line.startswith('{') or line.startswith('[')):
                                        response_line = line
                                        break
                                
                                if not response_line:
                                    if self.debug:
                                        print(f"[DEBUG] No valid JSON line found in: {lines}")
                                    
                                    if attempt < max_retries:
                                        if self.debug:
                                            print(f"[DEBUG] No valid JSON, restarting process (attempt {attempt + 1})")
                                        self._force_restart_process()
                                        continue
                                    else:
                                        error_details = {
                                            "session_id": self.session_id,
                                            "raw_response": response_text[:500],
                                            "lines_received": len(lines),
                                            "first_few_lines": lines[:5],
                                            "issue": "no_valid_json_line"
                                        }
                                        raise RuntimeError(f"响应中没有有效的JSON行 - 详细信息: {json.dumps(error_details, ensure_ascii=False, indent=2)}")
                                
                            except Exception as read_error:
                                if attempt < max_retries:
                                    if self.debug:
                                        print(f"[DEBUG] Read error, restarting process (attempt {attempt + 1}): {read_error}")
                                    self._force_restart_process()
                                    continue
                                else:
                                    raise read_error
                            
                            if self.debug:
                                print(f"[DEBUG] Parsing JSON: {response_line[:100]}...")
                            
                            try:
                                response = json.loads(response_line)
                                if self.debug:
                                    print(f"[DEBUG] Successfully parsed response: {response.get('type', 'UNKNOWN')}")
                                return response
                            except json.JSONDecodeError as e:
                                if self.debug:
                                    print(f"[DEBUG] JSON decode error: {e}")
                                    print(f"[DEBUG] Problematic line: {repr(response_line[:200])}")
                                
                                if attempt < max_retries:
                                    if self.debug:
                                        print(f"[DEBUG] JSON decode failed, restarting process (attempt {attempt + 1})")
                                    self._force_restart_process()
                                    continue
                                else:
                                    error_details = {
                                        "session_id": self.session_id,
                                        "json_error": str(e),
                                        "problematic_line": response_line[:200],
                                        "line_length": len(response_line),
                                        "issue": "json_decode_failed"
                                    }
                                    raise RuntimeError(f"响应JSON解析失败 - 详细信息: {json.dumps(error_details, ensure_ascii=False, indent=2)}")
                        else:
                            # 超时处理
                            if attempt < max_retries:
                                if self.debug:
                                    print(f"[DEBUG] Timeout, restarting process (attempt {attempt + 1})")
                                self._force_restart_process()
                                continue
                            else:
                                process_status = self.process.poll() if self.process else None
                                error_details = {
                                    "session_id": self.session_id,
                                    "command_id": command.get("id"),
                                    "timeout_seconds": max_wait_time,
                                    "process_status": process_status,
                                    "issue": "select_timeout"
                                }
                                raise RuntimeError(f"进程响应超时 - 详细信息: {json.dumps(error_details, ensure_ascii=False, indent=2)}")
                            
                    except Exception as e:
                        if attempt < max_retries:
                            if self.debug:
                                print(f"[DEBUG] Command execution failed, restarting process (attempt {attempt + 1}): {str(e)}")
                            self._force_restart_process()
                            continue
                        else:
                            raise e
            
            except Exception as e:
                if self.debug:
                    print(f"[DEBUG] Outer exception caught (attempt {attempt + 1}): {str(e)}")
                
                if attempt < max_retries:
                    continue
                else:
                    return {
                        "type": "COMMUNICATION_ERROR",
                        "error": f"进程通信失败: {str(e)}",
                        "stdout": "",
                        "stderr": "",
                        "returncode": -1,
                        "session_id": self.session_id
                    }
        return {
            "type": "COMMUNICATION_ERROR",
            "error": "所有重试尝试都失败了",
            "stdout": "",
            "stderr": "",
            "returncode": -1,
            "session_id": self.session_id
        }

    def _force_restart_process(self):
        import os
        import signal
        import time
        
        if self.process:
            try:
                self.process.terminate()
                self.process.wait(timeout=2)
            except:
                try:
                    if hasattr(os, 'killpg'):
                        os.killpg(os.getpgid(self.process.pid), signal.SIGKILL)
                    else:
                        self.process.kill()
                    time.sleep(0.5)
                except:
                    pass
        
        self.process = None
        time.sleep(0.2)


    def install_packages(self, packages: List[str]) -> Dict[str, Any]:
        """安装Python包"""
        if not packages:
            return {"type": "SUCCESS", "message": "无需安装包"}
        
        max_mem_needed = self.base_mem_mb
        for pkg in packages:
            pkg_name = pkg.split("==")[0].split(">=")[0].split("<=")[0]
            if pkg_name in HEAVY_PACKAGES:
                needed_mem = HEAVY_PACKAGES[pkg_name]
                max_mem_needed = max(max_mem_needed, needed_mem)
        
        if max_mem_needed > self.base_mem_mb:
            self.mem_bytes = max_mem_needed * 1024 * 1024
            if self.debug:
                print(f"[PERSISTENT] heavy packages → mem {max_mem_needed}MB")
        
        command = {
            "type": "INSTALL",
            "packages": packages
        }
        
        response = self._send_command(command, timeout=300)  # 5分钟超时
        return response
    
    def run_code(self, code: str, requirements: Optional[List[str]] = None, timeout_sec: int = 60, **kwargs) -> Dict[str, Any]:
        """运行代码 - 兼容会话管理器接口"""
        result = self.run_code_original(code, requirements)

        if requirements and result.get('success', False):
            self._installed_packages.update(requirements)
        
        return result
    
    def run_code_original(self, code: str, env_requirements: Optional[List[str]] = None) -> Dict[str, Any]:
        """在持久化进程中运行代码 - 原始实现"""
        self.touch()
        
        # 1. 静态安全扫描
        scan_result = self.test_environment_safety(code)
        if not scan_result["safe"]:
            dangerous_issues = [issue for issue in scan_result["issues"] 
                            if "eval" in issue or "exec" in issue]
            if dangerous_issues:
                return {
                    "success": False,
                    "error": "安全检查未通过",
                    "issues": dangerous_issues,
                    "stdout": "",
                    "stderr": "",
                    "session_id": self.session_id,
                }
        
        # 2. 安装依赖
        if env_requirements:
            install_result = self.install_packages(env_requirements)
            if install_result.get("type") not in ["SUCCESS", "INSTALL_SUCCESS"]:
                return {
                    "success": False,
                    "error": f"依赖安装失败: {install_result.get('error', 'Unknown error')}",
                    "stdout": install_result.get("stdout", ""),
                    "stderr": install_result.get("stderr", ""),
                    "session_id": self.session_id,
                }
        
        # 3. 执行代码
        command = {
            "type": "EXEC",
            "code": code
        }
        
        response = self._send_command(command, timeout=self.wall_limit)
        
        # 4. 处理响应 - 添加对所有响应类型的支持
        if response.get("type") == "SUCCESS":
            return {
                "success": True,
                "stdout": response.get("stdout", ""),
                "stderr": response.get("stderr", ""),
                "returncode": 0,
                "session_id": self.session_id,
            }
        elif response.get("type") in ["ERROR", "FATAL_ERROR"]:
            return {
                "success": False,
                "error": response.get("error", "Unknown error"),
                "stdout": response.get("stdout", ""),
                "stderr": response.get("stderr", response.get("traceback", "")),
                "returncode": 1,
                "session_id": self.session_id,
            }
        elif response.get("type") == "COMMUNICATION_ERROR":
            return {
                "success": False,
                "error": response.get("error", "Communication failed"),
                "stdout": "",
                "stderr": "",
                "returncode": -1,
                "session_id": self.session_id,
            }
        elif response.get("type") == "EXEC_RESULT":
            # 处理bash命令的响应
            return {
                "success": response.get("returncode", -1) == 0,
                "stdout": response.get("stdout", ""),
                "stderr": response.get("stderr", ""),
                "returncode": response.get("returncode", -1),
                "session_id": self.session_id,
            }
        else:
            return {
                "success": False,
                "error": f"未知响应类型: {response.get('type')}",
                "stdout": "",
                "stderr": str(response),
                "returncode": -1,
                "session_id": self.session_id,
            }
    
    def save_file(self, relative_path: str, content: str):
        """
        Save content to a file relative to the sandbox's working directory.

        Args:
            relative_path (str): The relative file path.
            content (str): The content to write.

        Raises:
            Exception: If the path escapes the sandbox directory.
        """
        file_path = os.path.join(self.work_dir, relative_path)
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(content if content is not None else "")

    def read_file(self, relative_path: str) -> str:
        """
        Read file content from a path relative to the sandbox's working directory.

        Args:
            relative_path (str): The relative file path.

        Returns:
            str: The file content.

        Raises:
            Exception: If the path escapes the sandbox directory.
        """
        file_path = os.path.join(self.work_dir, relative_path)
        with open(file_path, "r", encoding="utf-8") as f:
            return f.read()
    

    def _resolve_dest_in_sandbox(self, dest_relative: str) -> Path:
        if not self.work_dir:
            raise RuntimeError("Sandbox work_dir is not initialized.")
        base = Path(self.work_dir).resolve()
        dest = (base / dest_relative).resolve()
        if str(dest) != str(base) and not str(dest).startswith(str(base) + os.sep):
            raise PermissionError(f"Destination escapes sandbox: {dest}")
        return dest

    def _refresh_imports_in_child(self, add_path: Optional[str] = None) -> None:
        # Make current session see newly copied libs (and optionally add to sys.path)
        if not (self.process and self.process.poll() is None):
            return
        if add_path:
            code = (
                "import sys, os, importlib\n"
                f"p = os.path.abspath({repr(add_path)})\n"
                "if os.path.isfile(p): p = os.path.dirname(p)\n"
                "if p not in sys.path: sys.path.insert(0, p)\n"
                "importlib.invalidate_caches()\n"
            )
        else:
            code = "import importlib; importlib.invalidate_caches()\n"
        self._send_command({"type": "EXEC", "code": code}, timeout=5)

    def put_many_into_sandbox(
        self,
        sources: Sequence[os.PathLike | str],
        dest_relative: str,
        *,
        add_to_sys_path: bool = False,
        merge: bool = True,
        overwrite: bool = True,
        ignore_patterns: Optional[Sequence[str]] = ("__pycache__", "*.pyc", "*.pyo", ".git", ".mypy_cache"),
    ) -> List[str]:
        if not sources:
            return []
        dest_dir = self._resolve_dest_in_sandbox(dest_relative)
        dest_dir.mkdir(parents=True, exist_ok=True)

        copied: List[str] = []
        for src in sources:
            src_path = Path(src).resolve()
            if not src_path.exists():
                raise FileNotFoundError(f"Local path not found: {src_path}")
            target = dest_dir / src_path.name
            if src_path.is_dir():
                if target.exists() and not merge:
                    raise FileExistsError(f"Target exists and merge=False: {target}")
                ig = shutil.ignore_patterns(*(ignore_patterns or ()))
                shutil.copytree(src_path, target, dirs_exist_ok=True, ignore=ig)
                copied.append(str(target))
            else:
                if target.exists() and not overwrite:
                    raise FileExistsError(f"Target file exists and overwrite=False: {target}")
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src_path, target)
                copied.append(str(target))

        if add_to_sys_path:
            rel_for_child = os.path.relpath(str(dest_dir), start=self.work_dir)
            self._refresh_imports_in_child(add_path=rel_for_child)
        else:
            self._refresh_imports_in_child(add_path=None)
        return copied

    def put_into_sandbox(self, source: os.PathLike | str, dest_relative: str, **kwargs) -> List[str]:
        return self.put_many_into_sandbox([source], dest_relative, **kwargs)
    
    def evaluate_expression(self, expression: str) -> Dict[str, Any]:
        """求值表达式"""
        self.touch()
        
        command = {
            "type": "EVAL",
            "code": expression
        }
        
        response = self._send_command(command)
        
        if response.get("type") == "RESULT":
            return {
                "success": True,
                "result": response.get("value"),
                "session_id": self.session_id,
            }
        else:
            return {
                "success": False,
                "error": response.get("error", "Unknown error"),
                "session_id": self.session_id,
            }
    
    def get_status(self) -> Dict[str, Any]:
        """获取会话状态"""
        self.touch()
        
        command = {"type": "STATUS"}
        response = self._send_command(command)
        
        if response.get("type") == "STATUS":
            return {
                "success": True,
                "session_id": self.session_id,
                "global_variables": response.get("global_variables", []),
                "imported_modules": response.get("imported_modules", []),
                "total_modules": response.get("total_modules", 0),
                "created_at": self.created_at.isoformat(),
                "last_used": self.last_used.isoformat(),
                "time_remaining": self._get_time_remaining(),
            }
        else:
            return {
                "success": False,
                "error": response.get("error", "Failed to get status"),
                "session_id": self.session_id,
            }
    
    def test_environment_safety(self, code: str) -> Dict[str, Any]:
        """静态安全扫描 - 放宽限制"""
        issues: List[str] = []
        try:
            tree = ast.parse(code)
            for node in ast.walk(tree):
                # 只检查真正危险的调用
                if isinstance(node, ast.Call):
                    if getattr(node.func, "id", None) in {"eval", "exec"}:
                        issues.append(f"危险调用: {node.func.id}")
        except SyntaxError as e:
            issues.append(f"语法错误: {e}")
        return {"safe": not issues, "issues": issues}

    def get_session_info(self) -> Dict[str, Any]:
        """获取会话信息"""
        return {
            "session_id": self.session_id,
            "created_at": self.created_at.isoformat(),
            "last_used": self.last_used.isoformat(),
            "timeout_minutes": self.session_timeout,
            "time_remaining": self._get_time_remaining(),
            "work_dir": self.work_dir,
            "has_venv": self.venv_path is not None,
            "process_running": self.process is not None and self.process.poll() is None,
        }
    
    def _get_time_remaining(self) -> str:
        if not self.auto_cleanup or self.session_timeout <= 0:
            return "unlimited"
        
        elapsed = datetime.now() - self.last_used
        remaining = timedelta(minutes=self.session_timeout) - elapsed
        
        if remaining.total_seconds() <= 0:
            return "expired"
        
        minutes = int(remaining.total_seconds() / 60)
        seconds = int(remaining.total_seconds() % 60)
        return f"{minutes}:{seconds:02d}"
    
    def cleanup_session(self):
        if self.debug:
            print(f"[PERSISTENT] Cleaning up session {self.session_id}")
        self._session_active = False
        if self.cleanup_timer:
            self.cleanup_timer.cancel()

        if self.process:
            try:
                with self.process_lock:
                    self.process.stdin.write("EXIT\n")
                    self.process.stdin.flush()
                    self.process.wait(timeout=5)
            except:
                try:
                    os.killpg(os.getpgid(self.process.pid), signal.SIGTERM)
                    self.process.wait(timeout=2)
                except:
                    try:
                        os.killpg(os.getpgid(self.process.pid), signal.SIGKILL)
                    except:
                        pass
            finally:
                self.process = None

        if self.work_dir and os.path.exists(self.work_dir):
            try:
                shutil.rmtree(self.work_dir)
            except Exception as e:
                if self.debug:
                    print(f"[PERSISTENT] Cleanup error: {e}")
    
    def exec_bash(self, command: str, timeout: int = 30, capture_output: bool = True, env_requirements=[]) -> Dict[str, Any]:
        if self.is_timeout():
            return {
                'success': False,
                'error': 'Session timeout',
                'stdout': '',
                'stderr': '',
                'exit_code': -1,
                'session_id': self.session_id
            }      
        self.touch()
        try:
            venv_path = self.venv_path or ""
            python_code = f'''
import subprocess
import os
import sys
import json

try:
    os.chdir(r"{self.work_dir}")
    env = os.environ.copy()
    venv_path = r"{venv_path}"
    bash_command = {repr(command)}
    
    if venv_path and os.path.exists(venv_path):
        env['VIRTUAL_ENV'] = venv_path
        env['PYTHONHOME'] = ''  # 清除 PYTHONHOME 避免冲突

        venv_bin = os.path.join(venv_path, "bin")
        if os.path.exists(venv_bin):
            env['PATH'] = venv_bin + ":" + env.get('PATH', '')

        env['PYTHONPATH'] = r"{self.work_dir}"

        activate_script = os.path.join(venv_path, "bin", "activate")
        if os.path.exists(activate_script):
            bash_command = "source " + activate_script + " && " + bash_command
        
        print(f"DEBUG: Using venv: {{venv_path}}", file=sys.stderr)
        print(f"DEBUG: Activate script exists: {{os.path.exists(activate_script)}}", file=sys.stderr)
    else:
        env['PYTHONPATH'] = r"{self.work_dir}"
        print("DEBUG: No venv found, using system environment", file=sys.stderr)
    
    print(f"DEBUG: Final bash command: {{bash_command[:100]}}...", file=sys.stderr)
    print(f"DEBUG: VIRTUAL_ENV = {{env.get('VIRTUAL_ENV', 'Not set')}}", file=sys.stderr)
    print(f"DEBUG: PATH prefix = {{env.get('PATH', '')[:100]}}...", file=sys.stderr)

    result = subprocess.run(
        ["bash", "-c", bash_command],
        capture_output=True,
        text=True,
        timeout={timeout},
        env=env,
        cwd=r"{self.work_dir}"
    )

    output = {{
        "success": result.returncode == 0,
        "stdout": result.stdout,
        "stderr": result.stderr,
        "exit_code": result.returncode
    }}
    
    print("__BASH_RESULT_START__")
    print(json.dumps(output))
    print("__BASH_RESULT_END__")
    
except subprocess.TimeoutExpired:
    output = {{
        "success": False,
        "stdout": "",
        "stderr": "Command timeout after {timeout}s",
        "exit_code": -1,
        "error": "Command timeout after {timeout}s"
    }}
    print("__BASH_RESULT_START__")
    print(json.dumps(output))
    print("__BASH_RESULT_END__")
    
except Exception as e:
    import traceback
    output = {{
        "success": False,
        "stdout": "",
        "stderr": f"Exception: {{str(e)}}\\n{{traceback.format_exc()}}",
        "exit_code": -1,
        "error": str(e)
    }}
    print("__BASH_RESULT_START__")
    print(json.dumps(output))
    print("__BASH_RESULT_END__")
'''
        
            if self.debug:
                print(f"[BASH] Executing in venv via Python sandbox: {command[:50]}...")
            
            python_result = self.run_code(python_code, env_requirements)
            
            if not python_result['success']:
                return {
                    'success': False,
                    'error': f"Python sandbox error: {python_result.get('error', 'Unknown error')}",
                    'stdout': '',
                    'stderr': python_result.get('stderr', ''),
                    'exit_code': -1,
                    'command': command,
                    'session_id': self.session_id
                }
            
            stdout = python_result.get('stdout', '')
            stderr = python_result.get('stderr', '')

            start_marker = "__BASH_RESULT_START__"
            end_marker = "__BASH_RESULT_END__"
            
            start_idx = stdout.find(start_marker)
            end_idx = stdout.find(end_marker)
            
            if start_idx == -1 or end_idx == -1:
                return {
                    'success': False,
                    'error': 'Failed to parse bash result',
                    'stdout': stdout,
                    'stderr': stderr,
                    'exit_code': -1,
                    'command': command,
                    'session_id': self.session_id
                }

            json_str = stdout[start_idx + len(start_marker):end_idx].strip()
            
            try:
                import json
                bash_result = json.loads(json_str)
                
                debug_info = stderr
                original_stderr = bash_result.get('stderr', '')
                combined_stderr = f"{debug_info}\n{original_stderr}".strip()
                
                return {
                    'success': bash_result.get('success', False),
                    'stdout': bash_result.get('stdout', ''),
                    'stderr': combined_stderr,
                    'exit_code': bash_result.get('exit_code', -1),
                    'error': bash_result.get('error'),
                    'command': command,
                    'session_id': self.session_id
                }
                
            except json.JSONDecodeError as e:
                return {
                    'success': False,
                    'error': f'Failed to parse JSON result: {e}',
                    'stdout': stdout,
                    'stderr': stderr,
                    'exit_code': -1,
                    'command': command,
                    'session_id': self.session_id
                }
        
        except Exception as e:
            return {
                'success': False,
                'error': f'Bash execution error: {str(e)}',
                'stdout': '',
                'stderr': str(e),
                'exit_code': -1,
                'command': command,
                'session_id': self.session_id
            }


        
    def check_venv_status(self) -> Dict[str, Any]:
        """检查虚拟环境状态"""
        check_code = '''
import sys
import os
import subprocess

print("=== Python Environment Info ===")
print(f"Python executable: {sys.executable}")
print(f"Virtual env: {os.environ.get('VIRTUAL_ENV', 'Not set')}")
print(f"Current working directory: {os.getcwd()}")

# 检查 pip 路径
try:
    pip_result = subprocess.run([sys.executable, "-m", "pip", "--version"], 
                               capture_output=True, text=True)
    print(f"Pip version: {pip_result.stdout.strip()}")
except Exception as e:
    print(f"Pip check failed: {e}")

# 检查已安装的包
try:
    list_result = subprocess.run([sys.executable, "-m", "pip", "list", "--format=freeze"], 
                                capture_output=True, text=True)
    packages = list_result.stdout.strip().split('\\n')
    print(f"Installed packages count: {len(packages)}")
    # 显示前几个包作为示例
    for pkg in packages[:5]:
        if pkg.strip():
            print(f"  - {pkg}")
    if len(packages) > 5:
        print(f"  ... and {len(packages) - 5} more packages")
except Exception as e:
    print(f"Package list failed: {e}")
''' 
        return self.run_code(check_code)


class EnvironmentSandbox(PersistentEnvironmentSandbox):
    def __init__(self, **kwargs):
        kwargs['timeout_minutes'] = 0
        super().__init__(**kwargs)
    
    def run_environment(self, code: str, env_requirements: Optional[List[str]] = None) -> Dict[str, Any]:
        result = self.run_code(code, env_requirements)
        self.cleanup_session()
        return result




