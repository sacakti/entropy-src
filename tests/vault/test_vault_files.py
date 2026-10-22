"""Files kept in the vault."""

from __future__ import annotations

import os
import stat
from pathlib import Path

import pytest

from lib.models.vault import VaultValueType
from lib.vault import files
from lib.vault.serializer import VaultSerializationError, VaultSerializer
from lib.workflow.exceptions import VariableNotFoundError
from lib.workflow.variables.resolver import WorkflowVariableResolver

PEM = b"-----BEGIN CERTIFICATE-----\nMIIB\n-----END CERTIFICATE-----\n"
BINARY = bytes(range(256))


def test_file_values_round_trip_through_the_serializer() -> None:
    serializer = VaultSerializer()
    value = files.make_value("../../etc/client.crt", PEM, "application/x-x509-ca-cert")
    assert value["filename"] == "client.crt"
    stored = serializer.serialize(value, VaultValueType.FILE)
    assert serializer.deserialize(stored, VaultValueType.FILE) == value
    with pytest.raises(VaultSerializationError):
        serializer.serialize({"filename": "x"}, VaultValueType.FILE)
    with pytest.raises(VaultSerializationError):
        serializer.serialize({**value, "data": "not base64!"}, VaultValueType.FILE)


def test_size_limit() -> None:
    with pytest.raises(files.VaultFileError):
        files.make_value("big.bin", b"0" * (files.MAX_FILE_BYTES + 1))


def test_text_and_private_copies(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("ENTROPY_TMP", str(tmp_path))
    pem = files.make_value("client.crt", PEM)
    binary = files.make_value("client.pfx", BINARY)
    assert files.as_text(pem) == PEM.decode()
    assert files.as_text(binary) == binary["data"]

    path = files.materialize(binary, "certs/client_pfx")
    assert Path(path).read_bytes() == BINARY
    assert os.path.basename(path) == "client.pfx"
    assert stat.S_IMODE(os.stat(path).st_mode) == 0o600


def test_resolver_uses_text_or_a_path(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("ENTROPY_TMP", str(tmp_path))
    pem = files.make_value("client.crt", PEM)
    vault_value = WorkflowVariableResolver._vault_value

    assert vault_value(pem, "certs/crt", False) == PEM.decode()
    path = vault_value(pem, "certs/crt", True)
    assert Path(path).read_bytes() == PEM
    with pytest.raises(VariableNotFoundError, match="not a file"):
        vault_value("plain secret", "certs/password", True)
    assert vault_value({"a": 1}, "certs/obj", False) == {"a": 1}
