"""
Extension repository.
"""

from __future__ import annotations

import json
from datetime import datetime

from lib.database.connection import DatabaseConnection
from lib.database.repository import Repository
from lib.extensions.exceptions import ExtensionNotFoundError
from lib.models.extensions import Extension


class ExtensionRepository(Repository):
    """
    Repository for installed extensions.
    """

    def __init__(
        self,
        connection: DatabaseConnection,
    ) -> None:

        super().__init__(
            connection,
        )

    # ------------------------------------------------------------------
    # Create
    # ------------------------------------------------------------------

    def create(
        self,
        extension: Extension,
    ) -> Extension:
        """
        Register an installed extension.
        """

        self.execute(
            """
            INSERT INTO extensions
            (
                name,
                version,
                wheel,
                installer,
                installed_at,
                python_tag,
                platform_tag,
                dist_info,
                entry_points
            )
            VALUES
            (
                ?,
                ?,
                ?,
                ?,
                ?,
                ?,
                ?,
                ?,
                ?
            )
            """,
            (
                extension.name,
                extension.version,
                extension.wheel,
                extension.installer,
                self._datetime_to_string(
                    extension.installed_at,
                ),
                extension.python_tag,
                extension.platform_tag,
                extension.dist_info,
                json.dumps(
                    extension.entry_points,
                ),
            ),
        )

        self.connection.commit()

        return self.get_by_name(
            extension.name,
        )

    # ------------------------------------------------------------------
    # Get
    # ------------------------------------------------------------------

    def get(
        self,
        extension_id: int,
    ) -> Extension:
        """
        Return an extension by database identifier.
        """

        row = self.fetchone(
            """
            SELECT *
            FROM extensions
            WHERE id = ?
            """,
            (
                extension_id,
            ),
        )

        if row is None:

            raise ExtensionNotFoundError(
                str(extension_id),
            )

        return self._from_row(
            row,
        )

    def get_by_name(
        self,
        name: str,
    ) -> Extension:
        """
        Return an extension by name.
        """

        row = self.fetchone(
            """
            SELECT *
            FROM extensions
            WHERE name = ?
            """,
            (
                name,
            ),
        )

        if row is None:

            raise ExtensionNotFoundError(
                name,
            )

        return self._from_row(
            row,
        )

    # ------------------------------------------------------------------
    # Exists
    # ------------------------------------------------------------------

    def exists(
        self,
        name: str,
    ) -> bool:
        """
        Return True if an extension is registered.
        """

        return (
            self.fetchone(
                """
                SELECT 1
                FROM extensions
                WHERE name = ?
                LIMIT 1
                """,
                (
                    name,
                ),
            )
            is not None
        )

    # ------------------------------------------------------------------
    # Version
    # ------------------------------------------------------------------

    def version(
        self,
        name: str,
    ) -> str | None:
        """
        Return the installed extension version.

        Returns None when the extension is not registered.
        """

        row = self.fetchone(
            """
            SELECT version
            FROM extensions
            WHERE name = ?
            """,
            (
                name,
            ),
        )

        if row is None:

            return None

        return row["version"]

    # ------------------------------------------------------------------
    # List
    # ------------------------------------------------------------------

    def list(
        self,
    ) -> list[Extension]:
        """
        Return all installed extensions.
        """

        rows = self.fetchall(
            """
            SELECT *
            FROM extensions
            ORDER BY name
            """
        )

        return [
            self._from_row(
                row,
            )
            for row in rows
        ]

    # ------------------------------------------------------------------
    # Delete
    # ------------------------------------------------------------------

    def delete(
        self,
        name: str,
    ) -> None:
        """
        Remove an extension from the registry.
        """

        self.execute(
            """
            DELETE
            FROM extensions
            WHERE name = ?
            """,
            (
                name,
            ),
        )

        self.connection.commit()

    # ------------------------------------------------------------------
    # Mapping
    # ------------------------------------------------------------------

    @classmethod
    def _from_row(
        cls,
        row,
    ) -> Extension:
        """
        Convert a database row into an Extension.
        """

        return Extension(
            name=row["name"],
            version=row["version"],
            wheel=row["wheel"],
            installer=row["installer"],
            installed_at=cls._datetime_from_string(
                row["installed_at"],
            ),
            python_tag=row["python_tag"],
            platform_tag=row["platform_tag"],
            dist_info=row["dist_info"],
            entry_points=json.loads(
                row["entry_points"] or "[]",
            ),
        )

    # ------------------------------------------------------------------
    # Date / Time
    # ------------------------------------------------------------------

    @staticmethod
    def _datetime_to_string(
        value: datetime,
    ) -> str:
        """
        Convert datetime to SQLite-compatible text.
        """

        return value.isoformat()

    @staticmethod
    def _datetime_from_string(
        value: str,
    ) -> datetime:
        """
        Convert SQLite text into datetime.
        """

        return datetime.fromisoformat(
            value,
        )

    # ------------------------------------------------------------------
    # Update
    # ------------------------------------------------------------------
    def update(
        self,
        extension: Extension,
    ) -> None:
        """
        Update an installed extension record.
        """

        self.execute(
            """
            UPDATE extensions
            SET
                version = ?,
                wheel = ?,
                installer = ?,
                installed_at = ?,
                python_tag = ?,
                platform_tag = ?,
                dist_info = ?,
                entry_points = ?
            WHERE name = ?
            """,
            (
                extension.version,
                extension.wheel,
                extension.installer,
                extension.installed_at.isoformat(),
                extension.python_tag,
                extension.platform_tag,
                extension.dist_info,
                json.dumps(
                    extension.entry_points,
                ),
                extension.name,
            ),
        )

        self.connection.commit()
