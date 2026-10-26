"""sftp settings: add_host, known_hosts and algorithm preferences."""

from __future__ import annotations

import importlib
import sys
import types
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3] / "resources" / "plugins" / "custom" / "sftp"


def _module(name: str):
    if "sftp_plugin" not in sys.modules:
        package = types.ModuleType("sftp_plugin")
        package.__path__ = [str(ROOT)]
        sys.modules["sftp_plugin"] = package
    return importlib.import_module(f"sftp_plugin.{name}")


def _settings(settings):
    resolver = _module("resolver").SftpResolver()
    return resolver._resolve_settings(settings)


def test_add_host_and_known_hosts() -> None:
    settings = _settings({"add_host": True, "known_hosts": "~/hosts"})
    assert settings.add_host is True
    assert settings.known_hosts == Path("~/hosts").expanduser()
    assert _settings({}).add_host is False
    with pytest.raises(Exception, match="add_host"):
        _settings({"add_host": "yes"})


def test_algorithms_take_a_name_or_a_preference_list() -> None:
    settings = _settings(
        {
            "algorithms": {
                "ciphers": ["aes256-ctr", "aes128-ctr"],
                "host_key_algorithms": "ssh-ed25519",
            }
        }
    )
    assert settings.algorithms.cipher == ("aes256-ctr", "aes128-ctr")
    assert settings.algorithms.host_key == ("ssh-ed25519",)
    assert settings.algorithms.kex is None
    with pytest.raises(Exception, match="algorithm name or a list"):
        _settings({"algorithms": {"cipher": ["aes256-ctr", 3]}})


def test_defaults_skip_what_the_client_lacks_but_named_ones_must_exist() -> None:
    pytest.importorskip("paramiko")
    client = _module("client").SftpClient
    model = _module("model")
    supported = {"aes128-ctr", "aes256-ctr", "aes128-cbc"}
    assert client._choose("cipher", model.DEFAULT_CIPHERS, supported, explicit=False) == (
        "aes256-ctr",
        "aes128-ctr",
    )
    with pytest.raises(Exception, match="not supported here: chacha"):
        client._choose("cipher", ("chacha",), supported, explicit=True)
