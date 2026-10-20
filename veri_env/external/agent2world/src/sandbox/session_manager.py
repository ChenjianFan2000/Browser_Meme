from __future__ import annotations
"""
沙箱会话管理器
"""
import threading
import time
import os
import uuid
from typing import Dict, Optional, List, Any
from .persistent_sandbox import PersistentEnvironmentSandbox


class SandboxSessionManager:
    def __init__(self):
        self._sessions: Dict[str, PersistentEnvironmentSandbox] = {}
        self._lock = threading.RLock()
        self._cleanup_thread = None
        self._running = True
        
        self._process_id = os.getpid()
        self._process_uuid = str(uuid.uuid4())[:8]
        
        self._start_cleanup_thread()
    
    def _start_cleanup_thread(self):
        """启动清理线程"""
        def cleanup_loop():
            while self._running:
                try:
                    self._cleanup_expired_sessions()
                    time.sleep(300)
                except Exception as e:
                    print(f"[SESSION_MANAGER] Process {self._process_id} cleanup thread error: {e}")
        
        self._cleanup_thread = threading.Thread(target=cleanup_loop, daemon=True)
        self._cleanup_thread.start()
    
    def _cleanup_expired_sessions(self):
        """清理过期的会话 - 只清理本进程创建的session"""
        with self._lock:
            expired_sessions = []
            for session_id, session in self._sessions.items():
                if (session_id.startswith(f"p{self._process_id}_") and 
                    session.is_timeout()):
                    expired_sessions.append(session_id)
            
            for session_id in expired_sessions:
                print(f"[SESSION_MANAGER] Process {self._process_id} cleaning up expired session: {session_id}")
                session = self._sessions.pop(session_id, None)
                if session:
                    try:
                        session.cleanup_session()
                    except Exception as e:
                        print(f"[SESSION_MANAGER] Error cleaning up session {session_id}: {e}")
    
    def create_session(
        self,
        session_id: Optional[str] = None,
        memory_limit_mb: int = 512,
        timeout_minutes: int = 30,
        debug: bool = False,
        **kwargs
    ) -> PersistentEnvironmentSandbox:
        """创建新的持久化会话"""
        with self._lock:
            if session_id is None:
                unique_id = str(uuid.uuid4())[:8]
                session_id = f"p{self._process_id}_{self._process_uuid}_{unique_id}"
            else:
                session_id = f"p{self._process_id}_{self._process_uuid}_{session_id}"
            
            session = PersistentEnvironmentSandbox(
                memory_limit_mb=memory_limit_mb,
                timeout_minutes=timeout_minutes,
                debug=debug,
                session_id=session_id,
                **kwargs
            )
            
            self._sessions[session.session_id] = session
            print(f"[SESSION_MANAGER] Process {self._process_id} created session: {session_id}")
            return session
    
    def get_session(self, session_id: str) -> Optional[PersistentEnvironmentSandbox]:
        """获取会话"""
        with self._lock:
            session = self._sessions.get(session_id)
            if session and not session.is_timeout():
                session.touch()
                return session
            elif session:
                # 只有确实超时才清理
                if session.is_timeout():
                    self._sessions.pop(session_id, None)
                    try:
                        session.cleanup_session()
                    except Exception as e:
                        print(f"[SESSION_MANAGER] Error cleaning up expired session {session_id}: {e}")
            return None
    
    def remove_session(self, session_id: str) -> bool:
        """移除会话"""
        with self._lock:
            session = self._sessions.pop(session_id, None)
            if session:
                try:
                    session.cleanup_session()
                    print(f"[SESSION_MANAGER] Process {self._process_id} removed session: {session_id}")
                    return True
                except Exception as e:
                    print(f"[SESSION_MANAGER] Error removing session {session_id}: {e}")
            return False
    
    def list_sessions(self) -> List[Dict[str, Any]]:
        """列出所有活跃会话"""
        with self._lock:
            sessions = []
            for session_id, session in self._sessions.items():
                try:
                    if not session.is_timeout():
                        sessions.append({
                            'session_id': session_id,
                            'created_at': session.created_at,
                            'last_accessed': session.last_accessed,
                            'timeout_minutes': session.timeout_minutes,
                            'time_remaining': session.get_remaining_time(),
                            'memory_limit_mb': session.memory_limit_mb,
                            'process_id': self._process_id,
                        })
                    else:
                        sessions.append({
                            'session_id': session_id,
                            'status': 'expired',
                            'time_remaining': 0,
                            'process_id': self._process_id,
                        })
                except Exception as e:
                    print(f"[SESSION_MANAGER] Error getting session info for {session_id}: {e}")
            return sessions
    
    def cleanup_all_sessions(self):
        """清理所有会话"""
        with self._lock:
            session_ids = list(self._sessions.keys())
            for session_id in session_ids:
                session = self._sessions.pop(session_id, None)
                if session:
                    try:
                        session.cleanup_session()
                        print(f"[SESSION_MANAGER] Process {self._process_id} cleaned up session: {session_id}")
                    except Exception as e:
                        print(f"[SESSION_MANAGER] Error cleaning up session {session_id}: {e}")
            self._sessions.clear()
    
    def get_session_stats(self) -> Dict[str, Any]:
        """获取会话统计信息"""
        with self._lock:
            total_sessions = len(self._sessions)
            active_sessions = 0
            expired_sessions = 0
            
            for session in self._sessions.values():
                try:
                    if session.is_timeout():
                        expired_sessions += 1
                    else:
                        active_sessions += 1
                except Exception:
                    expired_sessions += 1
            
            return {
                'total_sessions': total_sessions,
                'active_sessions': active_sessions,
                'expired_sessions': expired_sessions,
                'session_ids': list(self._sessions.keys()),
                'process_id': self._process_id,
            }
    
    def extend_session_timeout(self, session_id: str, additional_minutes: int = 5) -> bool:
        """延长会话超时时间"""
        with self._lock:
            session = self._sessions.get(session_id)
            if session and not session.is_timeout():
                try:
                    session.extend_timeout(additional_minutes)
                    print(f"[SESSION_MANAGER] Process {self._process_id} extended timeout for session: {session_id}")
                    return True
                except Exception as e:
                    print(f"[SESSION_MANAGER] Error extending timeout for session {session_id}: {e}")
            return False
    
    def shutdown(self):
        """关闭会话管理器"""
        print(f"[SESSION_MANAGER] Process {self._process_id} shutting down session manager")
        self._running = False
        if self._cleanup_thread and self._cleanup_thread.is_alive():
            self._cleanup_thread.join(timeout=2.0)
        self.cleanup_all_sessions()


_process_session_managers: Dict[int, SandboxSessionManager] = {}
_manager_lock = threading.Lock()


def get_global_session_manager() -> SandboxSessionManager:
    process_id = os.getpid()
    
    with _manager_lock:
        if process_id not in _process_session_managers:
            print(f"[SESSION_MANAGER] Creating new session manager for process {process_id}")
            _process_session_managers[process_id] = SandboxSessionManager()
        
        return _process_session_managers[process_id]


_global_session_manager = get_global_session_manager()
