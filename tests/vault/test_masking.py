"""Vault values a run reads stay out of its messages."""

from __future__ import annotations

from types import SimpleNamespace

from lib.vault.masking import MASK, mask, secret_values
from lib.workflow.variables.resolver import WorkflowVariableResolver


def test_secret_values_of_strings_and_objects() -> None:
    assert secret_values("s3cret-token") == ["s3cret-token"]
    assert secret_values("abc") == []  # too short to mask safely
    sftp = {
        "host": "h.example",
        "port": "22",
        "user": "bob",
        "password": "pw-123",
        "keys": ["k-1234"],
    }
    assert sorted(secret_values(sftp)) == ["k-1234", "pw-123"]


def test_mask_replaces_longest_first() -> None:
    text = "login pw-123 and pw-1234"
    assert mask(text, ["pw-123", "pw-1234"]) == f"login {MASK} and {MASK}"


def test_resolver_registers_what_it_reads() -> None:
    vault = SimpleNamespace(
        resolve=lambda namespace, key, user: '{"host": "h", "password": "pw-123"}',
        resolve_matching=lambda namespace, key, user: {},
    )
    secrets: set = set()
    resolver = WorkflowVariableResolver(vault, 1, secrets)
    value = resolver.resolve({"sftp": "${entv:prod/sftp}"}, {})
    assert value == {"sftp": {"host": "h", "password": "pw-123"}}
    assert secrets == {"pw-123"}
