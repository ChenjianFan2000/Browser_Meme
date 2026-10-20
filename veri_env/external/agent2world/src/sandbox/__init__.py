from __future__ import annotations
from .persistent_sandbox import PersistentEnvironmentSandbox, EnvironmentSandbox
from .session_manager import SandboxSessionManager, _global_session_manager
from .core import cleanup_all_sandboxes
from .utils import get_requirements
from .api import (
    run_environment_safely,
    create_true_sandbox,
    get_sandbox_session,
    list_sandbox_sessions,
    cleanup_sandbox_session,
    get_or_create_session,
    execute_in_sandbox,
    cleanup_all_sandbox_sessions,
    get_sandbox_session_stats,
    extend_sandbox_session_timeout,
    exec_bash,
    get_sandbox_stats,
    
    create_persistent_sandbox,
    create_true_persistent_sandbox,
)

get_true_persistent_session = get_sandbox_session
list_true_persistent_sessions = list_sandbox_sessions
cleanup_true_persistent_session = cleanup_sandbox_session
execute_in_persistent_sandbox = execute_in_sandbox
list_persistent_sessions = list_sandbox_sessions
cleanup_persistent_session = cleanup_sandbox_session
cleanup_all_persistent_sessions = cleanup_all_sandbox_sessions
get_persistent_session_stats = get_sandbox_session_stats
extend_persistent_session_timeout = extend_sandbox_session_timeout

__all__ = [
    'PersistentEnvironmentSandbox',
    'EnvironmentSandbox', 
    'SandboxSessionManager',
    

    'exec_bash',
    'run_environment_safely',
    
    'create_true_sandbox',
    'get_sandbox_session', 
    'list_sandbox_sessions',
    'cleanup_sandbox_session',
    'get_or_create_session',
    'execute_in_sandbox',
    'cleanup_all_sandbox_sessions',
    'get_sandbox_session_stats',
    'extend_sandbox_session_timeout',
    'get_sandbox_stats',

    'create_persistent_sandbox',
    'create_true_persistent_sandbox',
    'get_true_persistent_session',
    'list_true_persistent_sessions',
    'cleanup_true_persistent_session',
    'execute_in_persistent_sandbox',
    'list_persistent_sessions',
    'cleanup_persistent_session',
    'cleanup_all_persistent_sessions',
    'get_persistent_session_stats',
    'extend_persistent_session_timeout',

    'cleanup_all_sandboxes',
    'get_requirements',
]
