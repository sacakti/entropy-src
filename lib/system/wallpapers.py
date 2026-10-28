"""
Wallpaper files on disk.

Wallpapers (images and videos up to 100 MiB) used to be stored as BLOBs in the
background_images table. Every video range request then read the whole video
from SQLite while holding the shared database lock, which stalled every other
request. Their bytes now live in <home>/wallpapers/<id>; the table keeps the
metadata and an empty image_data. Older rows are moved out once, at server
start, after which the database is compacted.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, Optional

from lib.database.connection import DatabaseConnection

# Compact the database after moving at least this much out of it.
VACUUM_AFTER_BYTES = 64 * 1024 * 1024


def wallpaper_root(home: Path) -> Path:
    return Path(home) / "wallpapers"


def wallpaper_file(root: Path, image_id: int) -> Path:
    return root / str(int(image_id))


def store_wallpaper(root: Path, image_id: int, data: bytes) -> Path:
    """Write a wallpaper's bytes atomically; returns its file."""

    root.mkdir(parents=True, exist_ok=True)
    target = wallpaper_file(root, image_id)
    partial = target.with_name(f".{target.name}.part")
    with partial.open("wb") as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())
    if partial.stat().st_size != len(data):
        partial.unlink(missing_ok=True)
        raise OSError(f"Wallpaper {image_id} was not written completely.")
    os.replace(partial, target)
    return target


def remove_wallpaper(root: Path, image_id: int) -> None:
    wallpaper_file(root, image_id).unlink(missing_ok=True)


def move_one(connection: DatabaseConnection, root: Path, image_id: int) -> Optional[Path]:
    """Move one row's BLOB to its file (no-op when it is already a file)."""

    row = connection.fetchone(
        "SELECT image_data FROM background_images WHERE id = ? AND length(image_data) > 0",
        (image_id,),
    )
    if row is None:
        target = wallpaper_file(root, image_id)
        return target if target.is_file() else None
    target = store_wallpaper(root, image_id, bytes(row["image_data"]))
    with connection.transaction():
        connection.execute(
            "UPDATE background_images SET image_data = X'' WHERE id = ?", (image_id,)
        )
    return target


def move_blobs_to_files(connection: DatabaseConnection, root: Path) -> Dict[str, Any]:
    """
    Move every wallpaper still stored in the database to a file, one at a
    time (so memory stays bounded), then compact the database.
    """

    rows = connection.fetchall(
        "SELECT id, length(image_data) AS stored FROM background_images "
        "WHERE length(image_data) > 0 ORDER BY id"
    )
    moved = 0
    moved_bytes = 0
    for row in rows:
        move_one(connection, root, int(row["id"]))
        moved += 1
        moved_bytes += int(row["stored"])
    vacuumed = False
    if moved_bytes >= VACUUM_AFTER_BYTES:
        # Gives the freed pages back to the file system (a 4 GB file shrinks to its data).
        connection.execute("VACUUM")
        vacuumed = True
    return {"moved": moved, "bytes": moved_bytes, "vacuumed": vacuumed}
