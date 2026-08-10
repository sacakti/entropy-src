"""
Plugin repository.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from lib.database.connection import DatabaseConnection
from lib.database.repository import Repository
from lib.models.plugin import Plugin
from lib.plugins.exceptions import PluginNotFoundError


class PluginRepository(Repository):
    """
    Plugin repository.
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
        plugin: Plugin,
    ) -> Plugin:
        """
        Register a plugin.
        """

        with self.connection.transaction():

            cursor = self.execute(
                """
                INSERT INTO plugin_registry
                (
                    namespace,
                    name,
                    version,
                    path,
                    enabled,
                    installed_at
                )
                VALUES
                (
                    ?,
                    ?,
                    ?,
                    ?,
                    ?,
                    datetime('now')
                )
                """,
                (
                    plugin.namespace,
                    plugin.name,
                    plugin.version,
                    str(plugin.path),
                    int(plugin.enabled),
                ),
            )

            plugin.id = cursor.lastrowid

        assert plugin.id is not None

        return self.get(
            plugin.id,
        )

    # ------------------------------------------------------------------
    # Get
    # ------------------------------------------------------------------

    def get(
        self,
        plugin_id: int,
    ) -> Plugin:
        """
        Return a plugin by identifier.
        """

        row = self.connection.fetchone(
            """
            SELECT *
            FROM plugin_registry
            WHERE id = ?
            """,
            (plugin_id,),
        )

        if row is None:

            raise PluginNotFoundError(
                str(plugin_id),
            )

        return self._from_row(
            row,
        )

    def get_by_name(
        self,
        namespace: str,
        name: str,
    ) -> Plugin:
        """
        Return a plugin by namespace and name.
        """

        row = self.connection.fetchone(
            """
            SELECT *
            FROM plugin_registry
            WHERE namespace = ?
              AND name = ?
            """,
            (
                namespace,
                name,
            ),
        )

        if row is None:

            raise PluginNotFoundError(
                f"{namespace}.{name}",
            )

        return self._from_row(
            row,
        )

    # ------------------------------------------------------------------
    # Exists
    # ------------------------------------------------------------------

    def exists(
        self,
        namespace: str,
        name: str,
    ) -> bool:
        """
        Return True if the plugin exists.
        """

        return (
            self.connection.fetchone(
                """
                SELECT 1
                FROM plugin_registry
                WHERE namespace = ?
                  AND name = ?
                LIMIT 1
                """,
                (
                    namespace,
                    name,
                ),
            )
            is not None
        )

    # ------------------------------------------------------------------
    # List
    # ------------------------------------------------------------------

    def list(
        self,
    ) -> list[Plugin]:
        """
        Return installed plugins.
        """

        rows = self.connection.fetchall(
            """
            SELECT *
            FROM plugin_registry
            ORDER BY namespace,
                     name
            """
        )

        return [
            self._from_row(
                row,
            )
            for row in rows
        ]

    # ------------------------------------------------------------------
    # Enable
    # ------------------------------------------------------------------

    def enable(
        self,
        plugin_id: int,
    ) -> None:
        """
        Enable a plugin.
        """

        with self.connection.transaction():

            self.execute(
                """
                UPDATE plugin_registry
                SET enabled = 1
                WHERE id = ?
                """,
                (plugin_id,),
            )

    # ------------------------------------------------------------------
    # Disable
    # ------------------------------------------------------------------

    def disable(
        self,
        plugin_id: int,
    ) -> None:
        """
        Disable a plugin.
        """

        with self.connection.transaction():

            self.execute(
                """
                UPDATE plugin_registry
                SET enabled = 0
                WHERE id = ?
                """,
                (plugin_id,),
            )

    # ------------------------------------------------------------------
    # Delete
    # ------------------------------------------------------------------

    def delete(
        self,
        plugin_id: int,
    ) -> None:
        """
        Remove a plugin.
        """

        with self.connection.transaction():

            self.execute(
                """
                DELETE
                FROM plugin_registry
                WHERE id = ?
                """,
                (plugin_id,),
            )

    # ------------------------------------------------------------------
    # Mapper
    # ------------------------------------------------------------------

    @staticmethod
    def _from_row(
        row,
    ) -> Plugin:
        """
        Convert a database row into a Plugin.
        """

        return Plugin(
            id=row["id"],
            namespace=row["namespace"],
            name=row["name"],
            version=row["version"],
            path=Path(
                row["path"],
            ),
            enabled=bool(
                row["enabled"],
            ),
            installed_at=(
                datetime.fromisoformat(
                    row["installed_at"],
                )
                if row["installed_at"]
                else None
            ),
        )

    def get_by_qualified_name(
        self,
        qualified_name: str,
    ) -> Plugin:

        namespace, name = qualified_name.split(".", 1)

        return self.get_by_name(namespace, name)

    # Update path
    def update_path(
        self,
        plugin_id: int,
        path: Path,
    ) -> None:
        """
        Update the installed plugin filesystem path.
        """

        with self.connection.transaction():

            self.execute(
                """
                UPDATE plugin_registry
                SET path = ?
                WHERE id = ?
                """,
                (
                    str(path),
                    plugin_id,
                ),
            )

    def relocate_paths(
        self,
        source: Path,
        destination: Path,
    ) -> None:

        plugins = self.list()

        for plugin in plugins:

            try:

                relative = plugin.path.relative_to(
                    source,
                )

            except ValueError:

                continue

            new_path = (destination / relative).resolve()

            assert plugin.id is not None

            with self.connection.transaction():

                self.update_path(
                    plugin.id,
                    new_path,
                )
