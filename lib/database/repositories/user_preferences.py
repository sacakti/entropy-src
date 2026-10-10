"""
User preferences repository.
"""

from __future__ import annotations

from lib.database.connection import DatabaseConnection
from lib.database.repository import Repository


class UserPreferencesRepository(Repository):
    """
    User preferences repository.
    """

    DEFAULT_THEME = "dark"
    DEFAULT_ACCENT_COLOR = "#d7ff63"
    DEFAULT_BACKGROUND_FIT = "cover"
    DEFAULT_BACKGROUND_OPACITY = 35

    def __init__(
        self,
        connection: DatabaseConnection,
    ) -> None:

        super().__init__(
            connection,
        )

    # ------------------------------------------------------------------
    # Get
    # ------------------------------------------------------------------

    def get(
        self,
        user_id: int,
    ) -> dict:
        """
        Return preferences for a user.

        Create a default preferences record when one does not exist.
        """

        with self.connection.transaction():

            self.execute(
                """
                INSERT OR IGNORE INTO user_preferences
                (
                    user_id,
                    theme,
                    accent_color,
                    background_image_id,
                    created_at,
                    updated_at
                )
                VALUES
                (
                    ?,
                    ?,
                    ?,
                    NULL,
                    datetime('now'),
                    datetime('now')
                )
                """,
                (
                    user_id,
                    self.DEFAULT_THEME,
                    self.DEFAULT_ACCENT_COLOR,
                ),
            )

        row = self.fetchone(
            """
            SELECT
                user_id,
                theme,
                accent_color,
                background_image_id,
                background_fit,
                background_opacity,
                created_at,
                updated_at
            FROM user_preferences
            WHERE user_id = ?
            """,
            (
                user_id,
            ),
        )

        if row is None:
            raise RuntimeError(
                f"Unable to retrieve preferences for user '{user_id}'.",
            )

        return dict(row)

    # ------------------------------------------------------------------
    # Update
    # ------------------------------------------------------------------

    def update(
        self,
        user_id: int,
        theme: str,
        accent_color: str,
        background_image_id: int | None,
        background_fit: str = DEFAULT_BACKGROUND_FIT,
        background_opacity: int = DEFAULT_BACKGROUND_OPACITY,
    ) -> dict:
        """
        Update preferences for a user.
        """

        with self.connection.transaction():
            self.execute(
                """
                INSERT INTO user_preferences
                (
                    user_id,
                    theme,
                    accent_color,
                    background_image_id,
                    background_fit,
                    background_opacity,
                    created_at,
                    updated_at
                )
                VALUES
                (
                    ?,
                    ?,
                    ?,
                    ?,
                    ?,
                    ?,
                    datetime('now'),
                    datetime('now')
                )
                ON CONFLICT(user_id)
                DO UPDATE SET
                    theme = excluded.theme,
                    accent_color = excluded.accent_color,
                    background_image_id = excluded.background_image_id,
                    background_fit = excluded.background_fit,
                    background_opacity = excluded.background_opacity,
                    updated_at = datetime('now')
                """,
                (
                    user_id,
                    theme,
                    accent_color,
                    background_image_id,
                    background_fit,
                    background_opacity,
                ),
            )

        return self.get(user_id)

