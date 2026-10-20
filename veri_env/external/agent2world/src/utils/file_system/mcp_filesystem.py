"""
mcp_filesystem.py
-----------------
A minimal JSON-registry file layer for MCP environments.

Key features
============
* save_text(...)      – create / overwrite text-based documents (.pdf, .docx …)
* save_binary(...)    – create / overwrite binary (image, audio, video …)
* update_meta(...)    – patch extracted_text, raw bytes, or metadata
* load_text(...)      – return extracted_text (full)
* slice_text(...)     – return extracted_text[start:end]
* delete_file(...)    – remove entry (and placeholder) from registry

All entries live in: <root>/registry.json
Actual files (or 1-byte placeholders) are stored under:
    <root>/docs/   (text documents)
    <root>/media/  (images / audio / video)

Content hash
============
* SHA-256 is always computed on the exact bytes written to disk
  (or on the placeholder bytes if no payload provided).

Usage
-----
    from pathlib import Path
    from mcp_filesystem import MCPFileSystem

    fs = MCPFileSystem(Path("temp/data/document_edit_mcp"))
    fs.save_text("report", fmt="pdf", text="Hello world", meta={"page_count": 1})
    txt = fs.load_text("report")
    fs.delete_file("report")
"""

from __future__ import annotations
import json
import inspect
import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, List, Optional


# -----------------------------------------------------------------------------#
#                               Helper functions                               #
# -----------------------------------------------------------------------------#

def _sha256(data: bytes) -> str:
    """Compute SHA-256 hex digest of given bytes."""
    h = hashlib.sha256()
    h.update(data)
    return h.hexdigest()


def _now_iso() -> str:
    """Return current UTC time as ISO-8601 string with 'Z' suffix."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


# -----------------------------------------------------------------------------#
#                                Main class                                    #
# -----------------------------------------------------------------------------#
class MCPFileSystem:
    """Lightweight JSON-registry file system for MCP servers."""

    REGISTRY_FILE = "registry.json"
    DOCS_DIR = "docs"
    MEDIA_DIR = "media"

    # Inline threshold for JSON payloads (bytes)
    INLINE_LIMIT = 256 * 1024  # 256 KB
    # Formats considered structured when in JSON
    K_STRUCTURED: set = {"json"}

    def __init__(self, root: str | Path):
        """
        Initialize the file system under the given root directory.
        Creates registry.json if missing.
        """
        self.root = Path(root)
        self.registry_path = self.root / self.REGISTRY_FILE
        self.root.mkdir(parents=True, exist_ok=True)
        if not self.registry_path.exists():
            self._write_registry({})

    # ---------------------------- existence check -------------------------- #
    def file_exists(self, file_path: str) -> bool:
        """
        Return True if file_path is registered or the corresponding file exists on disk.

        Args:
            file_path (str): Relative path under root, used as the registry key.

        Returns:
            bool: True if the file is in registry.json or exists on disk.
        """
        try:
            _ = self._get_entry(file_path)
            return True
        except FileNotFoundError:
            rel = file_path.lstrip("/")     
            return (self.root / rel).exists()
        except Exception as e:
            print(f"Error checking file existence: {e}")
            return False

    # ---------------------------- create / overwrite ------------------------ #
    def save_text(
        self,
        file_path: str,
        fmt: str,
        text: str,
        meta: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Create or overwrite a text document (.txt, .pdf, .json, etc.).
        Small JSON payloads (<= INLINE_LIMIT) are inlined into the registry;
        otherwise, writes full content or a placeholder.

        Args:
            file_path (str): Relative path under root to save the file.
            fmt (str): File format extension (e.g. "txt", "json").
            text (str): UTF-8 text content to save.
            meta (Optional[Dict[str, Any]]): Optional metadata to store.

        Returns:
            None

        Raises:
            OSError: If writing to disk fails.
        """
        meta = meta or {}
        fmt_lower = fmt.lower()
        content_bytes = text.encode("utf-8")
        is_json = fmt_lower in self.K_STRUCTURED
        inline_ok = is_json

        # Write file: real content if not inline, otherwise placeholder
        if inline_ok:
            # write 1-byte placeholder to keep path exist
            self._write_bytes(file_path, b"\0")
        else:
            self._write_bytes(file_path, content_bytes)

        entry: Dict[str, Any] = {
            "file_path": file_path,
            "path": file_path,
            "format": fmt_lower,
            "content_hash": _sha256(content_bytes),
            "metadata": meta,
            "last_modified": _now_iso(),
            "extracted_text": text if inline_ok else "",
        }
        self._upsert_entry(file_path, entry)

    def save_binary(
        self,
        file_path: str,
        fmt: str,
        raw_bytes: Optional[bytes] = None,
        meta: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Create or overwrite a binary file (images, audio, video, etc.).
        If raw_bytes is None, writes a 1-byte placeholder.

        Args:
            file_path (str): Relative path under root to save the file.
            fmt (str): File format extension (e.g. "png", "mp3").
            raw_bytes (Optional[bytes]): Content bytes; placeholder if None.
            meta (Optional[Dict[str, Any]]): Optional metadata to store.

        Returns:
            None

        Raises:
            OSError: If writing to disk fails.
        """
        meta = meta or {}
        payload = raw_bytes if raw_bytes is not None else b"\0"
        fmt_lower = fmt.lower()
        self._write_bytes(file_path, payload)

        entry: Dict[str, Any] = {
            "file_path": file_path,
            "path": file_path,
            "format": fmt_lower,
            "content_hash": _sha256(payload),
            "metadata": meta,
            "last_modified": _now_iso(),
            "data_kind": "unstructured",
        }
        self._upsert_entry(file_path, entry)

    # ---------------------------- read -------------------------------------- #
    def load_text(self, file_path: str) -> str:
        """
        Return the stored text for file_path.
        If the entry was inlined, returns that; otherwise reads the file from disk.

        Args:
            file_path (str): Relative path under root.

        Returns:
            str: The extracted text content.

        Raises:
            FileNotFoundError: If the registry entry or disk file does not exist.
            OSError: If reading from disk fails.
        """
        entry = self._get_entry(file_path)
        return entry.get("extracted_text", "")

    def load_info(self, file_path: str) -> Dict[str, Any]:
        """
        Return both extracted_text and metadata for file_path.

        Args:
            file_path (str): Relative path under root.

        Returns:
            Dict[str, Any]: {
                "extracted_text": str,
                "metadata": Dict[str, Any]
            }

        Raises:
            FileNotFoundError: If the registry entry does not exist.
        """
        entry = self._get_entry(file_path)
        text = entry.get("extracted_text", "")
        return {"extracted_text": text, "metadata": entry.get("metadata", {})}

    def slice_text(self, file_id: str, start: int, end: int) -> str:
        """
        Return a substring of the extracted text for file_path.

        Args:
            file_path (str): Relative path under root.
            start (int): Starting character index (inclusive).
            end (int): Ending character index (exclusive).

        Returns:
            str: The substring text segment.

        Raises:
            FileNotFoundError: If the registry entry does not exist.
        """
        return self.load_text(file_id)[start:end]

    # ---------------------------- update ------------------------------------ #
    def update_meta(
        self,
        file_path: str,
        *,
        extracted_text: Optional[str] = None,
        raw_bytes: Optional[bytes] = None,
        metadata_patch: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Patch an existing entry’s text, bytes, or metadata and refresh its hash and timestamp.

        Args:
            file_path (str): Relative path under root.
            extracted_text (Optional[str]): New full text to inline.
            raw_bytes (Optional[bytes]): New raw bytes to write.
            metadata_patch (Optional[Dict[str, Any]]): Keys to merge into metadata.

        Returns:
            None

        Raises:
            FileNotFoundError: If the registry entry does not exist.
            OSError: If writing to disk fails.
        """
        entry = self._get_entry(file_path)
        changed = False

        if extracted_text is not None:
            entry["extracted_text"] = extracted_text
            entry["content_hash"] = _sha256(extracted_text.encode("utf-8"))
            changed = True

        if raw_bytes is not None:
            self._write_bytes(entry["path"], raw_bytes)
            entry["content_hash"] = _sha256(raw_bytes)
            # if binary, inline remains False
            changed = True

        if metadata_patch:
            entry["metadata"] = {**entry.get("metadata", {}), **metadata_patch}
            changed = True

        if changed:
            entry["last_modified"] = _now_iso()
            self._upsert_entry(file_path, entry)

    # ---------------------------- delete ------------------------------------ #
    def delete_file(self, file_path: str, remove_disk: bool = True) -> bool:
        """
        Remove an entry from the registry, optionally deleting its disk file.

        Args:
            file_path (str): Relative path under root.
            remove_disk (bool): If True, delete the file or placeholder from disk.

        Returns:
            bool: True if the entry existed and was removed; False otherwise.

        Raises:
            OSError: If deletion from disk fails unexpectedly.
        """
        reg = self._read_registry()
        if file_path not in reg:
            return False
        if remove_disk:
            try:
                (self.root / reg[file_path]["path"]).unlink()
            except FileNotFoundError:
                pass
        del reg[file_path]
        self._write_registry(reg)
        return True

    # --------------------------- query ------------------------------------ #
    def list_files(
        self,
        formats: Optional[List[str]] = None,
        *,
        with_meta: bool = False
    ) -> List[Any]:
        """
        List the registered files, optionally filtering by format.

        Args:
            formats (Optional[List[str]]): List of format strings to include
                (case-insensitive). If None, includes all.
            with_meta (bool): If True, return full registry entries; otherwise,
                return just file_path strings.

        Returns:
            List[Any]:
                - If with_meta=False: List[str] of file_path keys.
                - If with_meta=True: List[Dict[str, Any]] of registry entries.
        """
        registry = self._read_registry()
        records = registry.values()

        if formats:
            fmt_set = {f.lower() for f in formats}
            records = [r for r in records if r["format"] in fmt_set]

        if with_meta:
            return [dict(r) for r in records]
        return [r["file_path"] for r in records]

    # --------------------------------------------------------------------- #
    #                            internal helpers                           #
    # --------------------------------------------------------------------- #
    def _write_bytes(self, rel_path: str, data: bytes) -> None:
        """Write raw bytes to disk under root/rel_path."""
        path = self.root / rel_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    def _read_registry(self) -> Dict[str, Any]:
        """Load the registry JSON into memory."""
        return json.loads(self.registry_path.read_text(encoding="utf-8"))

    def _write_registry(self, reg: Dict[str, Any]) -> None:
        """Persist the registry JSON to disk."""
        self.registry_path.write_text(json.dumps(reg, ensure_ascii=False, indent=2))

    def _get_entry(self, file_id: str) -> Dict[str, Any]:
        """Retrieve a single registry entry or raise FileNotFoundError."""
        reg = self._read_registry()
        if file_id not in reg:
            raise FileNotFoundError(file_id)
        return reg[file_id]

    def _upsert_entry(self, file_id: str, entry: Dict[str, Any]) -> None:
        """Insert or update a registry entry and save registry."""
        reg = self._read_registry()
        reg[file_id] = entry
        self._write_registry(reg)

    @staticmethod
    def describe_api(methods: Optional[List[str]] = None) -> str:
        """
        Auto-generate a Markdown summary of the public methods.

        Args:
            methods (Optional[List[str]]): Names of methods to include. If None,
                includes all public methods.

        Returns:
            str: A Markdown-formatted list of method signatures and summaries.
        """
        lines = ["MCPFileSystem API", "-----------------"]
        for name, func in inspect.getmembers(MCPFileSystem, predicate=inspect.isfunction):
            if name.startswith("_"):
                continue
            if methods and name not in methods:
                continue

            sig = inspect.signature(func)
            doc = inspect.getdoc(func) or ""
            # first paragraph only
            summary = doc.strip().split("\n\n", 1)[0].replace("\n", " ")
            lines.append(f"- `{name}{sig}`  \n    {summary}")

        return "\n".join(lines)

    @property
    def registry(self) -> Dict[str, Any]:
        """
        Read-only view of the current registry contents.

        Returns:
            Dict[str, Any]: The in-memory registry loaded from registry.json.
        """
        return self._read_registry()
