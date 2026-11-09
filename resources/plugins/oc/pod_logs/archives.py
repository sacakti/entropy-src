"""
Look inside log archives read from a pod: .zip, .tar(.gz/.tgz) and single .gz files.

Archives are read in memory and never extracted, so a member's name cannot reach the
server's disk, and members are read only up to a limit (compressed files can lie).
"""

from __future__ import annotations

import gzip
import io
import tarfile
import zipfile
from typing import Any, Dict, List

from .exceptions import PodLogsException

ARCHIVE_SUFFIXES = (".zip", ".tar.gz", ".tgz", ".tar")
GZIP_SUFFIX = ".gz"
MAX_MEMBERS = 5000


def is_archive(name: str) -> bool:
    return name.lower().endswith(ARCHIVE_SUFFIXES)


def is_gzip(name: str) -> bool:
    """A single compressed file (app.log.gz); a .tar.gz is an archive instead."""

    lowered = name.lower()
    return lowered.endswith(GZIP_SUFFIX) and not lowered.endswith(".tar.gz")


def members(name: str, data: bytes) -> List[Dict[str, Any]]:
    """The files in an archive: name (its path inside), size and modified (epoch seconds)."""

    found: List[Dict[str, Any]] = []
    try:
        if name.lower().endswith(".zip"):
            with zipfile.ZipFile(io.BytesIO(data)) as archive:
                for info in archive.infolist():
                    if not info.is_dir():
                        found.append(
                            {
                                "name": info.filename,
                                "size": info.file_size,
                                "modified": None,
                                "encrypted": bool(info.flag_bits & 0x1),
                            }
                        )
        else:
            with tarfile.open(fileobj=io.BytesIO(data), mode="r:*") as archive:
                for member in archive.getmembers():
                    if member.isfile():
                        found.append(
                            {
                                "name": member.name,
                                "size": member.size,
                                "modified": int(member.mtime),
                                "encrypted": False,
                            }
                        )
    except (OSError, EOFError, zipfile.BadZipFile, tarfile.TarError) as exc:
        raise PodLogsException(f"Unable to read the archive '{name}': {exc}") from exc
    return found[:MAX_MEMBERS]


def read_member(name: str, data: bytes, member: str, limit: int) -> bytes:
    """One file of an archive, refusing more than `limit` bytes."""

    try:
        if name.lower().endswith(".zip"):
            with zipfile.ZipFile(io.BytesIO(data)) as archive:
                info = archive.getinfo(member)
                if info.flag_bits & 0x1:
                    raise PodLogsException(f"'{member}' is encrypted.")
                with archive.open(info) as source:
                    content = source.read(limit + 1)
        else:
            with tarfile.open(fileobj=io.BytesIO(data), mode="r:*") as archive:
                extracted = archive.extractfile(member)
                if extracted is None:
                    raise PodLogsException(f"'{member}' is not a file.")
                content = extracted.read(limit + 1)
    except KeyError:
        raise PodLogsException(f"'{member}' is not in '{name}'.") from None
    except (OSError, EOFError, zipfile.BadZipFile, tarfile.TarError) as exc:
        raise PodLogsException(f"Unable to read '{member}' from '{name}': {exc}") from exc
    if len(content) > limit:
        raise PodLogsException(f"'{member}' is larger than {limit // (1024 * 1024)} MB.")
    return content


def gunzip(name: str, data: bytes, limit: int) -> bytes:
    try:
        with gzip.GzipFile(fileobj=io.BytesIO(data)) as source:
            content = source.read(limit + 1)
    except (OSError, EOFError) as exc:
        raise PodLogsException(f"Unable to decompress '{name}': {exc}") from exc
    if len(content) > limit:
        raise PodLogsException(f"'{name}' is larger than {limit // (1024 * 1024)} MB unpacked.")
    return content
