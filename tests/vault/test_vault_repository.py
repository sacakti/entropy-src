"""
Vault repository tests.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from lib.database.connection import DatabaseConnection
from lib.database.objects.vault import VaultEntriesTable
from lib.database.repositories.vault import VaultRepository
from lib.models.vault import VaultEntry, VaultValueType


def main() -> None:

    with tempfile.TemporaryDirectory() as directory:

        database = Path(directory) / "vault.db"

        connection = DatabaseConnection(
            database,
        )

        connection.open()

        VaultEntriesTable().create(
            connection,
        )

        repository = VaultRepository(
            connection,
        )

        # ----------------------------------------------------------
        # Create
        # ----------------------------------------------------------

        entry = VaultEntry(
            key="app_url",
            value="https://example.com",
            type=VaultValueType.STRING,
            sensitive=False,
        )

        created = repository.create(
            entry,
        )

        assert created.id is not None
        assert created.key == "app_url"
        assert created.value == "https://example.com"
        assert created.type is VaultValueType.STRING
        assert created.sensitive is False

        print("Create: PASS")

        # ----------------------------------------------------------
        # Get
        # ----------------------------------------------------------

        loaded = repository.get_by_key(
            "app_url",
        )

        assert loaded is not None
        assert loaded.key == "app_url"
        assert loaded.value == "https://example.com"

        print("Get: PASS")

        # ----------------------------------------------------------
        # Exists
        # ----------------------------------------------------------

        assert repository.exists(
            "app_url",
        )

        assert not repository.exists(
            "missing",
        )

        print("Exists: PASS")

        # ----------------------------------------------------------
        # Update
        # ----------------------------------------------------------

        assert loaded is not None

        loaded.value = "https://updated.example.com"

        repository.update(
            loaded,
        )

        updated = repository.get_by_key(
            "app_url",
        )

        assert updated is not None
        assert updated.value == "https://updated.example.com"

        print("Update: PASS")

        # ----------------------------------------------------------
        # List
        # ----------------------------------------------------------

        entries = repository.list()

        assert len(entries) == 1
        assert entries[0].key == "app_url"

        print("List: PASS")

        # ----------------------------------------------------------
        # Delete
        # ----------------------------------------------------------

        repository.delete(
            "app_url",
        )

        assert not repository.exists(
            "app_url",
        )

        print("Delete: PASS")

        connection.close()

    print("All Vault repository tests passed.")


if __name__ == "__main__":
    main()
