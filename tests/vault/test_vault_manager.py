"""
Vault manager tests.
"""

from __future__ import annotations

import sqlite3
import tempfile
from pathlib import Path

from lib.executor import LinuxExecutor
from lib.vault import (
    VaultCipher,
    VaultEntryExistsError,
    VaultEntryNotFoundError,
    VaultKeyProvider,
    VaultManager,
    VaultRepository,
    VaultSerializer,
    VaultValueType,
)

from lib.database.connection import DatabaseConnection
from lib.database.objects.vault import VaultEntriesTable


def main() -> None:

    executor = LinuxExecutor()

    with tempfile.TemporaryDirectory() as directory:

        root = Path(directory)

        database_path = root / "vault.db"
        key_path = root / "vault" / "master.key"

        # ---------------------------------------------------------
        # Database
        # ---------------------------------------------------------

        connection = DatabaseConnection(
            database_path,
        )

        connection.open()

        VaultEntriesTable().create(
            connection,
        )

        repository = VaultRepository(
            connection,
        )

        serializer = VaultSerializer()

        manager = VaultManager(
            repository=repository,
            serializer=serializer,
            executor=executor,
            key_path=key_path,
        )

        # ---------------------------------------------------------
        # Plain string
        # ---------------------------------------------------------

        manager.add(
            key="app_url",
            value="https://example.com",
            value_type=VaultValueType.STRING,
            sensitive=False,
        )

        assert manager.get(
            "app_url",
        ) == "https://example.com"

        print("Plain string: PASS")

        # ---------------------------------------------------------
        # Plain JSON
        # ---------------------------------------------------------

        manager.add(
            key="sitdb",
            value={
                "ip": "10.10.10.10",
                "port": 1521,
                "sid": "SITDB",
            },
            value_type=VaultValueType.JSON,
            sensitive=False,
        )

        assert manager.get(
            "sitdb",
        ) == {
            "ip": "10.10.10.10",
            "port": 1521,
            "sid": "SITDB",
        }

        print("Plain JSON: PASS")

        # ---------------------------------------------------------
        # Encrypted JSON
        # ---------------------------------------------------------

        manager.add(
            key="schema1_sit",
            value={
                "username": "schema1",
                "password": "my-secret-password",
            },
            value_type=VaultValueType.JSON,
            sensitive=True,
        )

        resolved = manager.get(
            "schema1_sit",
        )

        assert resolved == {
            "username": "schema1",
            "password": "my-secret-password",
        }

        print("Encrypted JSON: PASS")

        # ---------------------------------------------------------
        # Verify database does NOT contain plaintext
        # ---------------------------------------------------------

        row = connection.fetchone(
            """
            SELECT value
            FROM vault_entries
            WHERE key = ?
            """,
            ("schema1_sit",),
        )

        assert row is not None

        stored_value = row["value"]

        assert "my-secret-password" not in stored_value
        assert "schema1" not in stored_value

        print("Encrypted database value: PASS")

        # ---------------------------------------------------------
        # Encrypted string
        # ---------------------------------------------------------

        manager.add(
            key="secret_token",
            value="very-secret-token",
            value_type=VaultValueType.STRING,
            sensitive=True,
        )

        assert manager.get(
            "secret_token",
        ) == "very-secret-token"

        row = connection.fetchone(
            """
            SELECT value
            FROM vault_entries
            WHERE key = ?
            """,
            ("secret_token",),
        )

        assert row is not None

        assert "very-secret-token" not in row["value"]

        print("Encrypted string: PASS")

        # ---------------------------------------------------------
        # Duplicate key
        # ---------------------------------------------------------

        try:

            manager.add(
                key="app_url",
                value="https://another.example.com",
                value_type=VaultValueType.STRING,
            )

        except VaultEntryExistsError:

            print("Duplicate key detection: PASS")

        else:

            raise AssertionError(
                "Duplicate Vault key was accepted.",
            )

        # ---------------------------------------------------------
        # Missing key
        # ---------------------------------------------------------

        try:

            manager.get(
                "does_not_exist",
            )

        except VaultEntryNotFoundError:

            print("Missing key detection: PASS")

        else:

            raise AssertionError(
                "Missing Vault key was accepted.",
            )

        # ---------------------------------------------------------
        # Invalid keys
        # ---------------------------------------------------------

        invalid_keys = (
            "schema one",
            "schema-one",
            "schema+one",
            "schema/one",
            "schema*one",
            "schema.one",
            "",
        )

        for key in invalid_keys:

            try:

                manager.add(
                    key=key,
                    value="value",
                    value_type=VaultValueType.STRING,
                )

            except ValueError:

                continue

            raise AssertionError(
                f"Invalid Vault key was accepted: {key!r}",
            )

        print("Key validation: PASS")

        # ---------------------------------------------------------
        # Valid key
        # ---------------------------------------------------------

        manager.add(
            key="schema_123",
            value="valid",
            value_type=VaultValueType.STRING,
        )

        assert manager.get(
            "schema_123",
        ) == "valid"

        print("Valid key: PASS")

        # ---------------------------------------------------------
        # Update
        # ---------------------------------------------------------

        manager.update(
            key="app_url",
            value="https://updated.example.com",
            value_type=VaultValueType.STRING,
            sensitive=False,
        )

        assert manager.get(
            "app_url",
        ) == "https://updated.example.com"

        print("Update: PASS")

        # ---------------------------------------------------------
        # Update plaintext -> encrypted
        # ---------------------------------------------------------

        manager.update(
            key="app_url",
            value="https://secret.example.com",
            value_type=VaultValueType.STRING,
            sensitive=True,
        )

        assert manager.get(
            "app_url",
        ) == "https://secret.example.com"

        row = connection.fetchone(
            """
            SELECT value, sensitive
            FROM vault_entries
            WHERE key = ?
            """,
            ("app_url",),
        )

        assert row is not None
        assert bool(row["sensitive"]) is True
        assert "https://secret.example.com" not in row["value"]

        print("Update plaintext -> encrypted: PASS")

        # ---------------------------------------------------------
        # Update encrypted -> plaintext
        # ---------------------------------------------------------

        manager.update(
            key="app_url",
            value="https://public.example.com",
            value_type=VaultValueType.STRING,
            sensitive=False,
        )

        assert manager.get(
            "app_url",
        ) == "https://public.example.com"

        row = connection.fetchone(
            """
            SELECT value, sensitive
            FROM vault_entries
            WHERE key = ?
            """,
            ("app_url",),
        )

        assert row is not None
        assert bool(row["sensitive"]) is False
        assert row["value"] == '"https://public.example.com"'

        print("Update encrypted -> plaintext: PASS")

        # ---------------------------------------------------------
        # List
        # ---------------------------------------------------------

        entries = manager.list()

        keys = {
            entry.key
            for entry in entries
        }

        assert "app_url" in keys
        assert "sitdb" in keys
        assert "schema1_sit" in keys
        assert "secret_token" in keys

        print("List: PASS")

        # ---------------------------------------------------------
        # Sensitive metadata
        # ---------------------------------------------------------

        entry = manager.get_entry(
            "schema1_sit",
        )

        assert entry.sensitive is True
        assert entry.type is VaultValueType.JSON

        # get_entry must NOT decrypt the value.
        assert "my-secret-password" not in entry.value

        print("Sensitive metadata protection: PASS")

        # ---------------------------------------------------------
        # Delete
        # ---------------------------------------------------------

        manager.delete(
            "schema_123",
        )

        assert not manager.exists(
            "schema_123",
        )

        print("Delete: PASS")

        # ---------------------------------------------------------
        # Delete missing
        # ---------------------------------------------------------

        try:

            manager.delete(
                "does_not_exist",
            )

        except VaultEntryNotFoundError:

            print("Delete missing key: PASS")

        else:

            raise AssertionError(
                "Deleting a missing Vault key did not fail.",
            )

        connection.close()

    print("All Vault manager tests passed.")


if __name__ == "__main__":
    main()
