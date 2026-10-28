"""Read-only look inside ZIP-format artifacts (zip, jar, war, ear, whl)."""

from __future__ import annotations

import zipfile
from pathlib import Path
from typing import Any, Dict, List

# Listings stop here; the count of all entries is still reported.
MAX_ENTRIES = 5000
# Entries are read into memory to be previewed; larger ones are downloaded whole.
MAX_ENTRY_BYTES = 50 * 1024 * 1024
TOO_LARGE = "'{}' is too large to preview; download the archive instead."


class ArchiveError(ValueError):
    """The archive or entry cannot be listed or read."""


def list_entries(path: Path, limit: int = MAX_ENTRIES) -> Dict[str, Any]:
    """The archive's entries: name, sizes, and whether each is a folder or encrypted."""

    if not zipfile.is_zipfile(path):
        raise ArchiveError("This file is not a ZIP archive.")
    try:
        with zipfile.ZipFile(path) as archive:
            infos = archive.infolist()
    except (OSError, zipfile.BadZipFile) as exc:
        raise ArchiveError(f"Unable to read the archive: {exc}") from exc
    entries: List[Dict[str, Any]] = [
        {
            "name": info.filename,
            "size": info.file_size,
            "compressed": info.compress_size,
            "directory": info.is_dir(),
            "encrypted": bool(info.flag_bits & 0x1),
            "modified": "{:04d}-{:02d}-{:02d} {:02d}:{:02d}:{:02d}".format(*info.date_time),
        }
        for info in infos[:limit]
    ]
    return {"entries": entries, "total": len(infos), "truncated": len(infos) > limit}


def read_entry(path: Path, name: str, limit: int = MAX_ENTRY_BYTES) -> bytes:
    """One file inside the archive, refusing folders, encrypted and oversized entries."""

    if not zipfile.is_zipfile(path):
        raise ArchiveError("This file is not a ZIP archive.")
    try:
        with zipfile.ZipFile(path) as archive:
            try:
                info = archive.getinfo(name)
            except KeyError:
                raise ArchiveError(f"'{name}' is not in the archive.") from None
            if info.is_dir():
                raise ArchiveError(f"'{name}' is a folder.")
            if info.flag_bits & 0x1:
                raise ArchiveError(f"'{name}' is encrypted.")
            if info.file_size > limit:
                raise ArchiveError(TOO_LARGE.format(name))
            # The declared size can lie (zip bombs): stop reading past the limit.
            with archive.open(info) as source:
                data = source.read(limit + 1)
    except (OSError, zipfile.BadZipFile) as exc:
        raise ArchiveError(f"Unable to read '{name}': {exc}") from exc
    if len(data) > limit:
        raise ArchiveError(TOO_LARGE.format(name))
    return data
