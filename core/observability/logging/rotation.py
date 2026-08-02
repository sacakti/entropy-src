"""
Logging handler helpers.
"""

from __future__ import annotations

from logging.handlers import RotatingFileHandler
from pathlib import Path

DEFAULT_MAX_BYTES = 20 * 1024 * 1024

DEFAULT_BACKUP_COUNT = 10


def create_handler(
    file: Path,
    *,
    max_bytes: int = DEFAULT_MAX_BYTES,
    backup_count: int = DEFAULT_BACKUP_COUNT,
) -> RotatingFileHandler:
    """
    Create a rotating file handler.
    """

    file.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    return RotatingFileHandler(
        filename=file,
        maxBytes=max_bytes,
        backupCount=backup_count,
        encoding="utf-8",
    )
