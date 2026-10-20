"""Wallpaper customization is off unless installed with ENTROPY_THEME_ENABLE=1."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from lib.system import install


@pytest.fixture
def home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.delenv("ENTROPY_THEME_ENABLE", raising=False)
    return tmp_path


def _record(home: Path, record: dict) -> None:
    path = install.record_path(home)
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(record), encoding="utf-8")


def test_off_by_default(home: Path) -> None:
    assert install.theme_enabled(home) is False


def test_enabled_by_install_record(home: Path) -> None:
    _record(home, {"features": {"theme": True}})
    assert install.theme_enabled(home) is True


def test_environment_overrides_record(home: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _record(home, {"features": {"theme": True}})
    monkeypatch.setenv("ENTROPY_THEME_ENABLE", "0")
    assert install.theme_enabled(home) is False

    monkeypatch.setenv("ENTROPY_THEME_ENABLE", "1")
    assert install.theme_enabled(install.record_path(home).parent / "missing") is True
