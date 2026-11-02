"""Release packages keep python/bin/python3.9 for installations made before Python 3.13."""

from __future__ import annotations

import io
import tarfile
from pathlib import Path

from scripts.release import LEGACY_INTERPRETER, archive


def _cpython(path: Path, members: dict) -> Path:
    with tarfile.open(path, "w:gz") as tar:
        for name, link in members.items():
            info = tarfile.TarInfo(name)
            if link:
                info.type, info.linkname = tarfile.SYMTYPE, link
                tar.addfile(info)
            else:
                data = b"#!/bin/sh\n"
                info.size, info.mode = len(data), 0o755
                tar.addfile(info, io.BytesIO(data))
    return path


def _links(package: Path) -> dict:
    with tarfile.open(package) as tar:
        return {member.name: member.linkname for member in tar.getmembers() if member.issym()}


def test_versioned_interpreter_name_is_kept_as_a_link(tmp_path: Path) -> None:
    stage = tmp_path / "entropy-3.3.0"
    (stage / "application").mkdir(parents=True)
    (stage / "manifest.json").write_text("{}")
    python = _cpython(
        tmp_path / "cpython.tar.gz",
        {"python/bin/python3.13": None, "python/bin/python3": "python3.13"},
    )

    archive(stage, tmp_path / "out.tar.gz", python)

    links = _links(tmp_path / "out.tar.gz")
    assert links[f"entropy-3.3.0/{LEGACY_INTERPRETER}"] == "python3"
    assert links["entropy-3.3.0/python/bin/python3"] == "python3.13"


def test_no_link_when_the_name_exists_or_on_windows(tmp_path: Path) -> None:
    stage = tmp_path / "entropy-3.3.0"
    (stage / "application").mkdir(parents=True)
    windows = _cpython(tmp_path / "windows.tar.gz", {"python/python.exe": None})
    archive(stage, tmp_path / "windows-out.tar.gz", windows)
    assert not any("python3.9" in name for name in _links(tmp_path / "windows-out.tar.gz"))
