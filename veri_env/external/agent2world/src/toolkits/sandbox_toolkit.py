# -*- coding: utf-8 -*-
"""
SandboxToolkit
--------------
Expose ONLY the high-level APIs as tools:
  - file_tool(action, file_path, content=None)
  - code_tool(action, code=None, bash_cmd=None, env_requirements=None)

Additionally provides NON-tool programmatic APIs (NOT exposed via get_tools):
  - import_file_map(file_map: dict[str, str], add_to_sys_path=False, merge=True)
    * Supports BOTH:
        - directory mapping:  "utils/llm.py" -> "utils"
        - file mapping:       "utils/llm.py" -> "utils/llm.py"  (exact dest path, can rename)
    * Left side may be a glob pattern. If destination is a single file path,
      there must be exactly ONE match on the left and it must be a file.
  - extend_default_file_map(file_map: dict[str, str])

Behavior
--------
- A persistent sandbox session is created/reused.
- Default files (default_file_map) can be uploaded once on first use.
- Default requirements (pip) can be installed once on first use.

Notes
-----
- For exact file mapping we write text via session.save_file(dest, text).
  If you need binary files, extend this class with a save_binary helper.
"""

from __future__ import annotations

import glob
import os
from collections import defaultdict
from typing import Any, Dict, List, Optional, Tuple
from typing_extensions import Literal
from loguru import logger

from src.sandbox import create_persistent_sandbox
from src.toolkits import FunctionTool
from src.toolkits.base import BaseToolkit

MAX_RETURN_CHARS = 20_000


class SandboxToolkit(BaseToolkit):
    """Provision & reuse a persistent sandbox. Expose only file_tool / code_tool."""

    def __init__(
        self,
        *,
        memory_limit_mb: int = 512,
        timeout_minutes: int = 5,
        default_file_map: Optional[dict[str, str]] = None,
        default_requirements: Optional[list[str]] = None,
        session: Any = None,
        bootstrap_on_init: bool = True,
        on_bootstrap_error: Literal["ignore", "raise", "log"] = "ignore",
    ) -> None:
        """
        Args:
            memory_limit_mb (int): Memory limit (MB) used when creating a new sandbox.
            timeout_minutes (int): Idle timeout (minutes) used when creating a new sandbox.
            default_file_map (Optional[dict[str, str]]): Host->sandbox path mapping to upload on first use.
                Supports dir mapping (dest is a directory) and exact file mapping (dest is a file path).
            default_requirements (Optional[list[str]]): Pip packages to install once on first use.
            session (Any): Existing sandbox session to reuse instead of creating a new one.
            bootstrap_on_init (bool): If True, attempt eager bootstrap during initialization.
            on_bootstrap_error (Literal["ignore","raise","log"]): Behavior when eager bootstrap fails.
        """
        self._session = session
        self._initialized = session is not None

        self._memory_limit_mb = memory_limit_mb
        self._timeout_minutes = timeout_minutes
        self._default_file_map = default_file_map or {}
        self._default_requirements = default_requirements or []
        self._on_bootstrap_error = on_bootstrap_error

        if bootstrap_on_init:
            try:
                # Only ensure sandbox and upload default files once.
                self._ensure_sandbox()
            except Exception as e:
                if self._on_bootstrap_error == "raise":
                    raise
                if self._on_bootstrap_error == "log":
                    logger.exception(f"Sandbox eager bootstrap failed: {e}")

    # ----------------------------- exported tool methods -----------------------------

    def file_tool(
        self,
        action: str,
        file_path: str,
        content: Optional[str] = None,
    ) -> dict[str, Any]:
        r"""
        Read or write a text/python file inside the shared sandbox workspace.

        Args:
            action (str): Operation to perform. Use **"save"** to write text, or **"read"** to read text.
            file_path (str): File path relative to the sandbox root.
            content (str,optional): Text to write when `action="save"`. If omitted, an empty string is written.

        Returns:
            dict[str, Any]: JSON object indicating success or failure.
                - On **save**: includes a success flag and a short message.
                - On **read**: includes a success flag, a (possibly truncated) text snippet, and total character length.
                - On error: includes a failure flag and a human-readable error message.
        """
        try:
            session = self._ensure_sandbox()
            if action == "save":
                session.save_file(file_path, "" if content is None else str(content))
                # Keep original wording for compatibility with upstream consumers
                return {"success": True, "content": f"You success save content in {file_path}"}
            elif action == "read":
                text = session.read_file(file_path)
                snippet, total_len = self._safe_snippet(text)
                return {"success": True, "content": snippet, "full_length": total_len}
            else:
                return {"success": False, "error": f"Unknown action '{action}'"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def _normalize_result(self,result: Dict[str, Any]) -> Dict[str, Any]:
        """Normalize keys so callers can rely on a consistent payload."""
        result.setdefault("returncode", result.get("returncode", 0))
        result.setdefault("stdout", result.get("stdout", ""))
        result.setdefault("stderr", result.get("stderr", ""))
        result.setdefault("success", result.get("returncode", 0) == 0)
        result.setdefault("error", None)
        return result

    def run_code(
        self,
        code: str = None,
        env_requirements: Optional[list[str]] = None,
    ) -> dict[str, Any]:
        r"""
        Execute Python code or a shell command inside the shared sandbox.

        Args:
            code (str): Python source to execute when using this `run_code` tool.
            env_requirements (list[str],optional): Pip package names to install **for this call** before execution.

        Returns:
            dict[str, Any]: JSON object indicating execution success or failure,
                including textual outputs (stdout, stderr), process return code,
                and a human-readable error message on failure.
        """
        try:
            if not code:
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": "",
                    "returncode": -1,
                    "error": "Missing 'code' for run_code",
                }
            session = self._ensure_sandbox()
            per_call_reqs = env_requirements or []
            result = session.run_code(code, per_call_reqs)
            return self._normalize_result(result)
        except Exception as e:
            return {
                "success": False,
                "stdout": "",
                "stderr": "",
                "returncode": -1,
                "error": str(e),
            }

    def run_bash(
        self,
        bash_cmd: str = None,
        env_requirements: Optional[list[str]] = None,
    ) -> dict[str, Any]:
        r"""
        Execute Python code or a shell command inside the shared sandbox.

        Args:
            bash_cmd (str): Shell command to execute when using this `run_bash` tool.
            env_requirements (list[str],optional): Pip package names to install **for this call** before execution.

        Returns:
            dict[str, Any]: JSON object indicating execution success or failure,
                including textual outputs (stdout, stderr), process return code,
                and a human-readable error message on failure.
        """
        try:
            if not bash_cmd:
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": "",
                    "returncode": -1,
                    "error": "Missing 'bash_cmd' for run_bash",
                }
            session = self._ensure_sandbox()
            per_call_reqs = env_requirements or []
            result = session.exec_bash(
                bash_cmd,
                timeout=60 * 20,
                env_requirements=per_call_reqs,
            )
            return self._normalize_result(result)
        except Exception as e:
            return {
                "success": False,
                "stdout": "",
                "stderr": "",
                "returncode": -1,
                "error": str(e),
            }
    # ------------------------------- non-tool public APIs -------------------------------

    def import_file_map(
        self,
        file_map: dict[str, str],
        *,
        add_to_sys_path: bool = False,
        merge: bool = True,
    ) -> dict[str, Any]:
        """
        Programmatic API (NOT exposed via get_tools) to import files/dirs into the sandbox.

        Supports BOTH:
          - directory mapping:  "utils/llm.py" -> "utils"
          - file mapping:       "utils/llm.py" -> "utils/llm.py"  (exact dest path, can rename)

        Left side may be a glob pattern. If destination is a single FILE path, there must be:
          - exactly ONE match on the left, and
          - the match must be a FILE (not a directory).

        Args:
            file_map (dict[str,str]): mapping host_path_or_glob -> sandbox_destination
            add_to_sys_path (bool): add destination directory to sys.path inside sandbox (for dir mappings).
            merge (bool): merge into existing destination directory.

        Returns:
            dict[str,Any]: {
              "success": bool,
              "imported": List[Tuple[str, str]],  # (host_path, dest_relative or exact file)
              "missing": List[str],               # host patterns with no matches
              "error": Optional[str]
            }
        """
        def _is_file_like_path(p: str) -> bool:
            # Heuristic: treat as "file path" iff last segment has an extension.
            base = os.path.basename(p.rstrip("/"))
            root, ext = os.path.splitext(base)
            return bool(root) and bool(ext)

        try:
            session = self._ensure_sandbox()

            imported: List[Tuple[str, str]] = []
            missing: List[str] = []

            # Split into: directory batches and exact file pairs
            dir_batches: Dict[str, List[str]] = defaultdict(list)  # dest_dir -> [host_paths]
            file_pairs: List[Tuple[str, str]] = []                 # [(host_file, dest_file)]

            for host_pattern, dest in file_map.items():
                matches = glob.glob(host_pattern)
                if not matches:
                    missing.append(host_pattern)
                    continue

                if _is_file_like_path(dest):
                    # exact file target
                    if len(matches) != 1:
                        return {
                            "success": False,
                            "imported": [],
                            "missing": missing,
                            "error": (
                                f"Ambiguous mapping: '{host_pattern}' matched {len(matches)} paths, "
                                f"but destination '{dest}' is a single file path."
                            ),
                        }
                    src = matches[0]
                    if os.path.isdir(src):
                        return {
                            "success": False,
                            "imported": [],
                            "missing": missing,
                            "error": (
                                f"Invalid mapping: source '{src}' is a directory but destination '{dest}' "
                                f"is a file path. Map directories to a destination directory instead."
                            ),
                        }
                    file_pairs.append((src, dest))
                else:
                    # destination is a directory – batch upload
                    dir_batches[dest].extend(matches)

            # Upload directories/files to a destination directory
            for dest_dir, host_paths in dir_batches.items():
                session.put_many_into_sandbox(
                    host_paths,
                    dest_relative=dest_dir,
                    add_to_sys_path=add_to_sys_path,
                    merge=merge,
                )
                # record what likely landed (basename under dest_dir)
                imported.extend((hp, os.path.join(dest_dir, os.path.basename(hp))) for hp in host_paths)

            # Exact file-to-file uploads (text mode)
            for host_path, dest_file in file_pairs:
                with open(host_path, "r", encoding="utf-8") as f:
                    text = f.read()
                session.save_file(dest_file, text)
                imported.append((host_path, dest_file))
                # If caller wants sys.path behavior, we consider the parent directory
                if add_to_sys_path:
                    parent = os.path.dirname(dest_file).rstrip("/") or "."
                    try:
                        # If your session supports adding to sys.path persistently,
                        # you can expose a method and call it here.
                        pass
                    except Exception:
                        pass

            return {"success": True, "imported": imported, "missing": missing, "error": None}

        except Exception as e:
            return {"success": False, "imported": [], "missing": [], "error": str(e)}

    def only_read_file(self, file_path: str) -> str:
        session = self._ensure_sandbox()
        text = session.read_file(file_path)
        return text
    
    def extend_default_file_map(self, file_map: dict[str, str]) -> None:
        """
        Update the toolkit's default file_map (used during first bootstrap).
        This does NOT immediately upload; call `import_file_map(...)` to upload now.
        """
        self._default_file_map.update(file_map)

    # ------------------------------- internal helpers -------------------------------

    def _ensure_sandbox(self):
        """Create the persistent sandbox on first use; bootstrap files & default deps once."""
        if self._session is None:
            self._session = create_persistent_sandbox(
                memory_limit_mb=self._memory_limit_mb,
                timeout_minutes=self._timeout_minutes,
            )
            self._initialized = False

        if not self._initialized:
            self._initialized = True
            # Upload initial files (default_file_map) – supports dir and exact file mapping
            if self._default_file_map:
                res = self.import_file_map(self._default_file_map)
                if not res.get("success"):
                    logger.error(f"Default file_map import failed: {res.get('error')}")

            # Install default requirements once (if any)
            if self._default_requirements:
                try:
                    self._session.run_code("", self._default_requirements)
                except Exception as e:
                    logger.error(f"Default requirements installation failed: {e}")

            

        return self._session

    def _safe_snippet(self, text: str) -> tuple[str, int]:
        """Return (snippet, total_length) with truncation for very large content."""
        total_len = len(text)
        if total_len > MAX_RETURN_CHARS:
            half = MAX_RETURN_CHARS // 2
            return (
                f"{text[:half]}\n\n... (omitted {total_len - MAX_RETURN_CHARS} chars) ...\n\n{text[-half:]}",
                total_len,
            )
        return (text, total_len)

    # ------------------------------- tool exposure ----------------------------------

    def get_tools(self) -> list[FunctionTool]:
        """Expose only file_tool and code_tool as FunctionTool."""
        return [
            FunctionTool(self.file_tool),
            FunctionTool(self.run_code),
            FunctionTool(self.run_bash),
        ]
