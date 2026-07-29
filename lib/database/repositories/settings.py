"""
Settings repository.
"""

from lib.models.database import Setting

from ..repository import Repository


class SettingsRepository(Repository):

    def get(
        self,
        key: str,
    ):

        cursor = self.execute(
            """
            SELECT
                key,
                value,
                updated_at
            FROM settings
            WHERE key = ?
            """,
            (key,),
        )

        row = cursor.fetchone()

        if row is None:
            return None

        return Setting(
            key=row["key"],
            value=row["value"],
            updated_at=row["updated_at"],
        )

    def save(
        self,
        setting: Setting,
    ):

        self.execute(
            """
            INSERT OR REPLACE
            INTO settings
            (
                key,
                value,
                updated_at
            )
            VALUES
            (
                ?,
                ?,
                datetime('now')
            )
            """,
            (
                setting.key,
                setting.value,
            ),
        )

        self.commit()

    def delete(
        self,
        key: str,
    ):

        self.execute(
            """
            DELETE
            FROM settings
            WHERE key = ?
            """,
            (key,),
        )

        self.commit()

    def exists(
        self,
        key: str,
    ) -> bool:

        cursor = self.execute(
            """
            SELECT 1
            FROM settings
            WHERE key = ?
            """,
            (key,),
        )

        return cursor.fetchone() is not None
