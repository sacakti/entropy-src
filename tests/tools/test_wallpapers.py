"""Wallpapers move from database BLOBs to files."""

from __future__ import annotations

from pathlib import Path

import pytest

from lib.database.connection import DatabaseConnection
from lib.database.objects.background_images import BackgroundImagesTable
from lib.system import wallpapers
from lib.system.wallpapers import move_blobs_to_files, move_one, store_wallpaper, wallpaper_file


@pytest.fixture()
def connection(tmp_path: Path) -> DatabaseConnection:
    database = DatabaseConnection(tmp_path / "entropy.db")
    BackgroundImagesTable().create(database)
    return database


def add(connection: DatabaseConnection, data: bytes) -> int:
    with connection.transaction():
        cursor = connection.execute(
            "INSERT INTO background_images"
            " (name, mime_type, size_bytes, image_data, source, created_at)"
            " VALUES ('b', 'video/mp4', ?, ?, 'upload', '2026-01-01')",
            (len(data), data),
        )
    return int(cursor.lastrowid)


def stored(connection: DatabaseConnection, image_id: int) -> int:
    row = connection.fetchone(
        "SELECT length(image_data) AS n FROM background_images WHERE id = ?", (image_id,)
    )
    return int(row["n"])


def test_blobs_move_to_files_once(connection: DatabaseConnection, tmp_path: Path):
    root = tmp_path / "wallpapers"
    first, second = add(connection, b"video-one"), add(connection, b"image-two")

    result = move_blobs_to_files(connection, root)

    assert result == {"moved": 2, "bytes": 18, "vacuumed": False}
    assert wallpaper_file(root, first).read_bytes() == b"video-one"
    assert wallpaper_file(root, second).read_bytes() == b"image-two"
    assert stored(connection, first) == 0 and stored(connection, second) == 0
    # Nothing left to move the second time; files are kept.
    assert move_blobs_to_files(connection, root)["moved"] == 0
    assert move_one(connection, root, first) == wallpaper_file(root, first)


def test_large_moves_compact_the_database(
    connection: DatabaseConnection, tmp_path: Path, monkeypatch
):
    monkeypatch.setattr(wallpapers, "VACUUM_AFTER_BYTES", 1024)
    add(connection, b"x" * 400_000)
    database = tmp_path / "entropy.db"
    before = database.stat().st_size

    result = move_blobs_to_files(connection, tmp_path / "wallpapers")

    assert result["vacuumed"] is True
    assert database.stat().st_size < before / 4


def test_missing_row_and_missing_file(connection: DatabaseConnection, tmp_path: Path):
    root = tmp_path / "wallpapers"
    image_id = add(connection, b"data")
    move_one(connection, root, image_id)
    wallpaper_file(root, image_id).unlink()  # moved, but its file is gone since

    assert move_one(connection, root, image_id) is None
    assert move_one(connection, root, 999) is None


def test_store_is_atomic(tmp_path: Path):
    root = tmp_path / "wallpapers"
    target = store_wallpaper(root, 7, b"bytes")

    assert target.read_bytes() == b"bytes"
    assert [path.name for path in root.iterdir()] == ["7"]
