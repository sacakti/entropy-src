"""Listing and reading entries of ZIP-format artifacts."""

from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

from lib.artifacts.archive import ArchiveError, list_entries, read_entry


@pytest.fixture()
def archive(tmp_path: Path) -> Path:
    path = tmp_path / "app.war"
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as target:
        target.writestr("WEB-INF/", "")
        target.writestr("WEB-INF/web.xml", "<web-app/>")
        target.writestr("index.html", "<h1>Hi</h1>")
        target.writestr("big.log", "x" * 2000)
    return path


def test_lists_entries(archive: Path) -> None:
    listing = list_entries(archive)
    assert listing["total"] == 4 and not listing["truncated"]
    names = {entry["name"]: entry for entry in listing["entries"]}
    assert names["WEB-INF/"]["directory"] and names["big.log"]["size"] == 2000

    assert list_entries(archive, limit=2)["truncated"] is True


def test_reads_entries_within_limits(archive: Path) -> None:
    assert read_entry(archive, "WEB-INF/web.xml") == b"<web-app/>"
    with pytest.raises(ArchiveError, match="folder"):
        read_entry(archive, "WEB-INF/")
    with pytest.raises(ArchiveError, match="not in the archive"):
        read_entry(archive, "../etc/passwd")
    with pytest.raises(ArchiveError, match="too large"):
        read_entry(archive, "big.log", limit=1000)


def test_rejects_files_that_are_not_zips(tmp_path: Path) -> None:
    plain = tmp_path / "notes.txt"
    plain.write_text("hello")
    with pytest.raises(ArchiveError, match="not a ZIP"):
        list_entries(plain)
