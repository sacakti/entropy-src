"""Passphrase-encrypted vault exports."""

from __future__ import annotations

import json

import pytest

from lib.vault.portable import PortableVaultError, seal, unseal

PAYLOAD = {
    "namespaces": [
        {
            "name": "ops",
            "visibility": "private",
            "entries": [
                {"key": "db_password", "type": "string", "sensitive": True, "value": "s3cr3t!"},
            ],
        }
    ]
}


def test_round_trip_and_nothing_in_clear() -> None:
    data = seal(PAYLOAD, "correct horse battery")
    assert b"s3cr3t" not in data and b"db_password" not in data
    assert unseal(data, "correct horse battery")["namespaces"] == PAYLOAD["namespaces"]


def test_wrong_passphrase_short_passphrase_and_tampering() -> None:
    with pytest.raises(PortableVaultError, match="at least"):
        seal(PAYLOAD, "short")
    data = seal(PAYLOAD, "correct horse battery")
    with pytest.raises(PortableVaultError, match="Wrong passphrase"):
        unseal(data, "correct horse staple")
    envelope = json.loads(data)
    envelope["data"] = envelope["data"][:-6] + "AAAA=="
    with pytest.raises(PortableVaultError):
        unseal(json.dumps(envelope).encode(), "correct horse battery")


def test_refuses_other_files_and_costly_settings() -> None:
    with pytest.raises(PortableVaultError, match="not an Entropy vault"):
        unseal(b"{}", "correct horse battery")
    envelope = json.loads(seal(PAYLOAD, "correct horse battery"))
    envelope["kdf"]["n"] = 2**24
    with pytest.raises(PortableVaultError, match="unsupported"):
        unseal(json.dumps(envelope).encode(), "correct horse battery")
