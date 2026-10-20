"""The container entrypoint: preparing the Entropy home on the volume."""

from __future__ import annotations

from pathlib import Path

import pytest

from lib.install import container
from lib.system import install


@pytest.fixture
def volume(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("ENTROPY_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("ENTROPY_WORKSPACE", str(tmp_path / "workspace"))
    monkeypatch.delenv("ENTROPY_ADMIN_PASSWORD", raising=False)
    monkeypatch.delenv("ENTROPY_ADMIN_PASSWORD_FILE", raising=False)
    return tmp_path


def test_first_start_needs_an_admin_password(volume: Path) -> None:
    with pytest.raises(SystemExit, match="ENTROPY_ADMIN_PASSWORD"):
        container.initialize()


# The Entropy context keeps its log file open for the life of the process.
@pytest.mark.filterwarnings("ignore::pytest.PytestUnraisableExceptionWarning")
def test_initialize_is_idempotent(volume: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    secret = volume / "password"
    secret.write_text("C0ntainer!Pass#2026\n", encoding="utf-8")
    monkeypatch.setenv("ENTROPY_ADMIN_PASSWORD_FILE", str(secret))

    home = container.initialize()

    assert (home / "database" / "entropy.db").is_file()
    assert (home / "config" / "entropy.json").is_file()
    assert (home / container.MARKER).is_file()
    assert (volume / "workspace" / "workflows").is_dir()

    # A restart (or a new image) only migrates; the password is not needed.
    monkeypatch.delenv("ENTROPY_ADMIN_PASSWORD_FILE")
    assert container.initialize() == home


def test_scratch_directory(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.delenv("ENTROPY_TMP", raising=False)
    assert install.scratch_directory(tmp_path) == tmp_path / "tmp"

    monkeypatch.setenv("ENTROPY_TMP", "/var/lib/entropy/home/tmp")
    assert install.scratch_directory(tmp_path) == Path("/var/lib/entropy/home/tmp")
