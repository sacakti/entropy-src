"""The remote `ent` command line: contexts, arguments, packaging."""

from __future__ import annotations

import os
import stat
import subprocess
import sys
from pathlib import Path

import pytest

from lib.remote_cli.build import build_pyz
from lib.remote_cli.commands import CommandError, _values, main
from lib.remote_cli.config import Config, ConfigError, context_name, normalize_server


@pytest.fixture(autouse=True)
def config_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    path = tmp_path / "home" / "config.json"
    monkeypatch.setenv("ENT_CONFIG", str(path))
    monkeypatch.delenv("ENT_CONTEXT", raising=False)
    return path


def test_server_urls_are_normalized() -> None:
    assert normalize_server("entropy.example.com/") == "https://entropy.example.com"
    assert normalize_server("http://10.0.0.5:8000") == "http://10.0.0.5:8000"
    assert context_name("http://10.0.0.5:8000") == "10.0.0.5:8000"
    with pytest.raises(ConfigError):
        normalize_server("ftp://host")
    with pytest.raises(ConfigError):
        normalize_server("  ")


def test_contexts_are_saved_privately(config_file: Path) -> None:
    config = Config.load()
    config.upsert("a", {"server": "https://a", "token": "secret"})
    config.upsert("b", {"server": "https://b"}, make_current=False)
    config.save()

    assert stat.S_IMODE(config_file.stat().st_mode) == 0o600
    loaded = Config.load()
    assert loaded.current()["name"] == "a"
    assert loaded.current("b")["server"] == "https://b"
    assert loaded.find_server("https://b") == "b"


def test_context_from_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    config = Config()
    config.upsert("a", {"server": "https://a"})
    config.upsert("b", {"server": "https://b"}, make_current=False)

    monkeypatch.setenv("ENT_CONTEXT", "b")
    assert config.current()["name"] == "b"
    monkeypatch.setenv("ENT_CONTEXT", "missing")
    with pytest.raises(ConfigError):
        config.current()


def test_not_logged_in_is_a_clear_error(capsys: pytest.CaptureFixture) -> None:
    assert main(["workflow", "list"]) == 1
    assert "ent login" in capsys.readouterr().err


def test_values_parse_json_or_text() -> None:
    assert _values(["n=3", "flag=true", "name=demo", "items=[1, 2]", "empty="], "--var") == {
        "n": 3,
        "flag": True,
        "name": "demo",
        "items": [1, 2],
        "empty": "",
    }
    with pytest.raises(CommandError):
        _values(["novalue"], "--var")


def test_pyz_runs_on_its_own(tmp_path: Path) -> None:
    archive = tmp_path / "ent.pyz"
    archive.write_bytes(build_pyz("9.8.7"))

    # Outside the source tree, with an empty config: only the archive is used.
    env = dict(os.environ, ENT_CONFIG=str(tmp_path / "config.json"), PYTHONPATH="")
    result = subprocess.run(
        [sys.executable, "-I", str(archive), "version"],
        cwd=str(tmp_path),
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )

    assert result.returncode == 0, result.stderr
    assert "9.8.7" in result.stdout
