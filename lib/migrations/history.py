"""
Migration history.
"""

from __future__ import annotations

from lib.database.connection import DatabaseConnection


class MigrationHistory:
    """
    Tracks applied database migrations.
    """

    def __init__(
        self,
        connection: DatabaseConnection,
    ) -> None:

        self._connection = connection

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def exists(
        self,
        version: int,
    ) -> bool:
        """
        Return True if the migration has been applied.
        """

        return (
            self._connection.fetchone(
                """
                SELECT 1
                FROM schema_migrations
                WHERE version = ?
                """,
                (version,),
            )
            is not None
        )

    def applied(self) -> list[int]:
        """
        Return applied migration versions.
        """

        rows = self._connection.fetchall(
            """
            SELECT version
            FROM schema_migrations
            ORDER BY version
            """
        )

        return [int(row["version"]) for row in rows]

    def latest(
        self,
    ) -> int | None:
        """
        Return the latest applied migration version.
        """

        row = self._connection.fetchone(
            """
            SELECT MAX(version) AS version
            FROM schema_migrations
            """
        )

        if row is None:
            return None

        version = row["version"]

        if version is None:
            return None

        return int(version)

    # ------------------------------------------------------------------
    # Commands
    # ------------------------------------------------------------------

    def record(
        self,
        version: int,
        description: str,
    ) -> None:
        """
        Record a successful migration.
        """

        self._connection.execute(
            """
            INSERT INTO schema_migrations
            (
                version,
                description,
                applied_at
            )
            VALUES
            (
                ?,
                ?,
                datetime('now')
            )
            """,
            (
                version,
                description,
            ),
        )

    def clear(self) -> None:
        """
        Remove migration history.
        """

        self._connection.execute(
            """
            DELETE
            FROM schema_migrations
            """
        )
