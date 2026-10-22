"""
Files kept in the vault: certificates (.crt, .pem), keystores (.pfx, .p12),
keys (id_rsa, .pub) and any other file a workflow needs.

A file entry's value is a dictionary:

    {"filename": "client.pfx", "content_type": "application/x-pkcs12",
     "size": 2345, "data": "<base64>"}

It is stored like every other secret (encrypted when sensitive). Workflows
use it as text with ${entv:namespace/key} (base64 for binary files) or as a
path to a private temporary copy with ${entvfile:namespace/key}.
"""

from __future__ import annotations

import atexit
import base64
import binascii
import os
import shutil
import tempfile
from typing import Any, Dict, Optional

MAX_FILE_BYTES = 5 * 1024 * 1024
FIELDS = ("filename", "content_type", "size", "data")


class VaultFileError(ValueError):
    """Not a usable vault file; the message says why."""


def safe_filename(name: str) -> str:
    name = os.path.basename(str(name or "").replace("\\", "/")).strip()
    return "".join(ch for ch in name if ch.isprintable() and ch not in '<>:"|?*')[:200] or "file"


def make_value(filename: str, content: bytes, content_type: Optional[str] = None) -> Dict[str, Any]:
    if len(content) > MAX_FILE_BYTES:
        raise VaultFileError(
            f"Files in the vault can be at most {MAX_FILE_BYTES // (1024 * 1024)} MB."
        )
    return {
        "filename": safe_filename(filename),
        "content_type": content_type or "application/octet-stream",
        "size": len(content),
        "data": base64.b64encode(content).decode("ascii"),
    }


def validate(value: Any) -> None:
    if not isinstance(value, dict) or any(field not in value for field in FIELDS):
        raise VaultFileError("A vault file needs filename, content_type, size and data.")
    try:
        content = base64.b64decode(str(value["data"]), validate=True)
    except (binascii.Error, ValueError):
        raise VaultFileError("The file data is not valid base64.") from None
    if len(content) > MAX_FILE_BYTES:
        raise VaultFileError("The file is too large.")


def content(value: Dict[str, Any]) -> bytes:
    return base64.b64decode(str(value["data"]))


def as_text(value: Dict[str, Any]) -> str:
    """The file as text: itself when it is text (PEM, .pub), else base64."""

    raw = content(value)
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return str(value["data"])


def metadata(value: Dict[str, Any]) -> Dict[str, Any]:
    return {key: value.get(key) for key in ("filename", "content_type", "size")}


# ----------------------------------------------------------------------
# Temporary copies for ${entvfile:...}
# ----------------------------------------------------------------------

_directory: Optional[str] = None


def _private_directory() -> str:
    global _directory
    if _directory is None or not os.path.isdir(_directory):
        base = os.environ.get("ENTROPY_TMP") or None
        _directory = tempfile.mkdtemp(prefix="entropy-vault-files-", dir=base)
        os.chmod(_directory, 0o700)
        # Copies live only as long as the process (the run) that needed them.
        atexit.register(shutil.rmtree, _directory, True)
    return _directory


def materialize(value: Dict[str, Any], label: str) -> str:
    """Write the file to a private (0600) temporary copy; returns its path."""

    validate(value)
    folder = tempfile.mkdtemp(prefix=safe_filename(label)[:40] + "-", dir=_private_directory())
    path = os.path.join(folder, safe_filename(value["filename"]))
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(content(value))
    return path
