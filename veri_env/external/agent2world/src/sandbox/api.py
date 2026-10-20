from __future__ import annotations
"""
沙箱API接口 - 提供便捷的函数接口
"""
from typing import Dict, Any, List, Optional

from .persistent_sandbox import PersistentEnvironmentSandbox, EnvironmentSandbox
from .session_manager import _global_session_manager
def run_environment_safely(
    env_code: str,
    requirements: Optional[List[str]] = None,
    memory_limit_mb: int = 512,
    timeout_sec: int = 30,
    debug: bool = False,
    auto_cleanup: bool = True,
) -> Dict[str, Any]:
    sb = EnvironmentSandbox(
        memory_limit_mb=memory_limit_mb,
        cpu_time_limit=timeout_sec,
        wall_time_limit=timeout_sec + 5,
        debug=debug,
        auto_cleanup=auto_cleanup,
    )
    
    try:
        result = sb.run_environment(env_code, requirements)
        return result
    finally:
        if auto_cleanup:
            sb.cleanup_session()

def create_true_sandbox(
    memory_limit_mb: int = 512,
    timeout_minutes: int = 5,
    debug: bool = False,
    **kwargs
) -> PersistentEnvironmentSandbox:
    return _global_session_manager.create_session(
        memory_limit_mb=memory_limit_mb,
        timeout_minutes=timeout_minutes,
        debug=debug,
        **kwargs
    )


def get_sandbox_session(session_id: str) -> Optional[PersistentEnvironmentSandbox]:
    return _global_session_manager.get_session(session_id)


def list_sandbox_sessions() -> List[Dict[str, Any]]:
    return _global_session_manager.list_sessions()


def cleanup_sandbox_session(session_id: str) -> bool:
    session = _global_session_manager.get_session(session_id)
    if session:
        _global_session_manager.remove_session(session_id)
        return True
    return False


def get_or_create_session(session_id: Optional[str] = None, **kwargs) -> PersistentEnvironmentSandbox:
    if session_id:
        session = _global_session_manager.get_session(session_id)
        if session:
            return session
    
    return _global_session_manager.create_session(session_id=session_id, **kwargs)


def execute_in_sandbox(
    session_id: str, 
    code: str, 
    requirements: Optional[List[str]] = None
) -> Dict[str, Any]:
    session = _global_session_manager.get_session(session_id)
    if not session:
        return {"success": False, "error": f"Session {session_id} not found"}
    
    return session.run_code(code, requirements)


def cleanup_all_sandbox_sessions():
    _global_session_manager.cleanup_all_sessions()


def get_sandbox_session_stats() -> Dict[str, Any]:
    return _global_session_manager.get_session_stats()


def extend_sandbox_session_timeout(session_id: str, additional_minutes: int = 5) -> bool:
    return _global_session_manager.extend_session_timeout(session_id, additional_minutes)


def get_sandbox_stats() -> Dict[str, Any]:
    return _global_session_manager.get_session_stats()


def exec_bash(session_id: str, command: str, timeout: int = 30) -> Dict[str, Any]:
    """在沙箱中执行bash命令"""
    session = _global_session_manager.get_session(session_id)
    if not session:
        return {"success": False, "error": f"Session {session_id} not found"}
    
    return session.exec_bash(command, timeout)

create_persistent_sandbox = create_true_sandbox
create_true_persistent_sandbox = create_true_sandbox
get_true_persistent_session = get_sandbox_session
list_true_persistent_sessions = list_sandbox_sessions
cleanup_true_persistent_session = cleanup_sandbox_session
execute_in_persistent_sandbox = execute_in_sandbox
list_persistent_sessions = list_sandbox_sessions
cleanup_persistent_session = cleanup_sandbox_session
cleanup_all_persistent_sessions = cleanup_all_sandbox_sessions
get_persistent_session_stats = get_sandbox_session_stats
extend_persistent_session_timeout = extend_sandbox_session_timeout
