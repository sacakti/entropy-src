"""
Files a run on another node needs, such as a release package picked on the main node.

Each remote node says how it reaches the main node's files (its "file access"):

- ``off``: as before; paths are sent as they are.
- ``fetch``: files under the main node's ``sources`` folders are copied to the node's
  ``workspace`` before the run starts, through the agent's own connection, and the
  run's paths are changed to the copies. The node keeps them, so the same package is
  copied once.
- ``shared``: both see the same storage (NFS, SMB...). Paths under a mapping's ``main``
  folder are changed to its ``node`` folder; nothing is copied.

Only whole values that are absolute paths are recognised, e.g. ``"/opt/releases/SR01.zip"``
in a step argument or a run variable; a path built from parts (``"${dir}/SR01.zip"``) is not.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path, PurePosixPath
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

MODES = ("off", "fetch", "shared")
DEFAULT_MAX_GB = 5
MAX_MAPPINGS = 10
MAX_SOURCES = 10
MAX_FILES = 200
# Strings longer than this are not paths worth looking at.
_MAX_PATH = 4096


class FileAccessError(ValueError):
    """Settings that cannot work, or files a run cannot get on its node."""


def _absolute(value: Any, label: str) -> str:
    if (
        not isinstance(value, str)
        or not value.strip().startswith("/")
        or any(char in value for char in "\n\r\0")
        or ".." in PurePosixPath(value.strip()).parts
    ):
        raise FileAccessError(f"{label} must be an absolute path, got {value!r}.")
    text = value.strip()
    return text.rstrip("/") or "/"


def normalize(value: Any) -> Dict[str, Any]:
    """Well-formed file access settings; FileAccessError says what is wrong."""

    if value in (None, {}):
        return {"mode": "off"}
    if not isinstance(value, dict):
        raise FileAccessError("File access must be an object with a 'mode'.")
    mode = value.get("mode", "off")
    if mode not in MODES:
        raise FileAccessError(f"File access mode must be one of {', '.join(MODES)}.")
    if mode == "off":
        return {"mode": "off"}

    if mode == "fetch":
        workspace = _absolute(value.get("workspace"), "The node's workspace folder")
        if workspace == "/":
            raise FileAccessError("The node's workspace folder cannot be '/'.")
        sources = value.get("sources") or []
        if not isinstance(sources, list) or len(sources) > MAX_SOURCES:
            raise FileAccessError(f"Send files from at most {MAX_SOURCES} folders.")
        max_gb = value.get("max_gb", DEFAULT_MAX_GB)
        if (
            isinstance(max_gb, bool)
            or not isinstance(max_gb, (int, float))
            or not 0 < max_gb <= 1000
        ):
            raise FileAccessError("The size limit must be between 1 and 1000 GB.")
        return {
            "mode": "fetch",
            "workspace": workspace,
            "sources": [_absolute(item, "A folder to send files from") for item in sources],
            "max_gb": max_gb,
        }

    mappings = value.get("mappings") or []
    if not isinstance(mappings, list) or not 1 <= len(mappings) <= MAX_MAPPINGS:
        raise FileAccessError(f"A shared folder needs 1 to {MAX_MAPPINGS} folder pairs.")
    pairs = []
    for item in mappings:
        if not isinstance(item, dict):
            raise FileAccessError("Each shared folder pair needs 'main' and 'node'.")
        pairs.append(
            {
                "main": _absolute(item.get("main"), "The shared folder on the main node"),
                "node": _absolute(item.get("node"), "The shared folder on this node"),
            }
        )
    # The longest main folder first, so the most specific pair wins.
    pairs.sort(key=lambda pair: len(pair["main"]), reverse=True)
    return {"mode": "shared", "mappings": pairs}


def parse(text: Optional[str]) -> Dict[str, Any]:
    """Stored settings; anything unreadable is off."""

    try:
        return normalize(json.loads(text)) if text else {"mode": "off"}
    except (ValueError, FileAccessError):
        return {"mode": "off"}


def _under(path: str, folder: str) -> bool:
    return folder == "/" or path == folder or path.startswith(folder + "/")


def _strings(value: Any, visit: Callable[[str], Optional[str]]) -> Any:
    """`value` with every string replaced by what `visit` returns for it (None keeps it)."""

    if isinstance(value, str):
        replaced = visit(value)
        return value if replaced is None else replaced
    if isinstance(value, list):
        return [_strings(item, visit) for item in value]
    if isinstance(value, dict):
        return {key: _strings(item, visit) for key, item in value.items()}
    return value


def _candidate(text: str) -> Optional[str]:
    if (
        not text.startswith("/")
        or len(text) > _MAX_PATH
        or "${" in text
        or any(char in text for char in "\n\r\0")
    ):
        return None
    return os.path.normpath(text)


def _identity(path: Path) -> Tuple[str, int]:
    """A key that changes when the content may have (path, size, time) and the size."""

    if path.is_dir():
        size = 0
        newest = 0
        count = 0
        for root, _dirs, files in os.walk(path):
            for name in files:
                item = Path(root) / name
                try:
                    info = item.stat()
                except OSError:
                    continue
                size += info.st_size
                newest = max(newest, info.st_mtime_ns)
                count += 1
        stamp = f"dir|{path}|{size}|{count}|{newest}"
    else:
        info = path.stat()
        size = info.st_size
        stamp = f"file|{path}|{size}|{info.st_mtime_ns}"
    return hashlib.sha256(stamp.encode("utf-8")).hexdigest()[:24], size


def plan(
    settings: Dict[str, Any],
    definition: str,
    variables: Dict[str, Any],
    default_sources: Sequence[Path],
) -> Dict[str, Any]:
    """
    What a node needs to run this: the definition and variables with paths changed for
    it, the files to copy to it (fetch) and the folders it must see (shared).
    Raises FileAccessError when it cannot work (too large, or not on the share).
    """

    mode = settings.get("mode", "off")
    result: Dict[str, Any] = {
        "definition": definition,
        "variables": variables,
        "files": [],
        "checks": [],
    }
    if mode == "off":
        return result

    files: Dict[str, Dict[str, Any]] = {}
    checks: List[str] = []
    outside: List[str] = []

    if mode == "fetch":
        sources = [
            os.path.normpath(str(item))
            for item in (settings.get("sources") or [str(path) for path in default_sources])
        ]
        workspace = settings["workspace"]

        def visit(text: str) -> Optional[str]:
            path = _candidate(text)
            if path is None or not any(_under(path, source) for source in sources):
                return None
            entry = files.get(path)
            if entry is None:
                local = Path(path)
                if not local.exists():
                    return None
                key, size = _identity(local)
                entry = {
                    "index": len(files),
                    "path": path,
                    "name": local.name or "root",
                    "kind": "directory" if local.is_dir() else "file",
                    "size": size,
                    "key": key,
                    "target": f"{workspace}/{key}/{local.name or 'root'}",
                }
                files[path] = entry
            return str(entry["target"])

    else:
        mappings = settings["mappings"]

        def visit(text: str) -> Optional[str]:
            path = _candidate(text)
            if path is None:
                return None
            for pair in mappings:
                if _under(path, pair["main"]):
                    rest = path[len(pair["main"]) :].lstrip("/") if pair["main"] != "/" else path
                    target = f"{pair['node'].rstrip('/')}/{rest.lstrip('/')}".rstrip("/")
                    if pair["node"] not in checks:
                        checks.append(pair["node"])
                    return target or "/"
            # A main-node file the node cannot see would only fail later.
            if Path(path).is_file() and path not in outside:
                outside.append(path)
            return None

    try:
        document = json.loads(definition)
    except ValueError:
        document = None
    if document is not None:
        result["definition"] = json.dumps(_strings(document, visit))
    result["variables"] = _strings(dict(variables or {}), visit)

    if mode == "shared" and outside:
        raise FileAccessError(
            "These files are on the main node but not in a folder shared with the node: "
            + ", ".join(outside[:5])
            + ". Move them to the shared folder, or use 'Fetch from main' for this node."
        )

    listed = sorted(files.values(), key=lambda item: item["index"])
    if len(listed) > MAX_FILES:
        raise FileAccessError(f"The run names {len(listed)} files; at most {MAX_FILES} are sent.")
    total = sum(item["size"] for item in listed)
    limit = float(settings.get("max_gb", DEFAULT_MAX_GB)) * 1024**3
    if total > limit:
        raise FileAccessError(
            f"The run needs {total / 1024**3:.1f} GB of files on the node, more than its "
            f"{settings.get('max_gb', DEFAULT_MAX_GB)} GB limit."
        )
    result["files"] = listed
    result["checks"] = checks
    return result
