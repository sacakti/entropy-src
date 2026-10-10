"""
Background images table.
"""

from lib.database.base import DatabaseObject
from lib.database.connection import DatabaseConnection


class BackgroundImagesTable(DatabaseObject):

    NAME = "background_images"

    def create(
        self,
        connection: DatabaseConnection,
    ) -> None:

        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS background_images
            (
                id             INTEGER PRIMARY KEY AUTOINCREMENT,
                image_key      TEXT UNIQUE,
                owner_user_id  INTEGER,
                name           TEXT NOT NULL,
                mime_type      TEXT NOT NULL,
                size_bytes     INTEGER NOT NULL,
                image_data     BLOB NOT NULL,
                source         TEXT NOT NULL DEFAULT 'upload',
                created_at     TEXT NOT NULL,

                FOREIGN KEY (owner_user_id)
                    REFERENCES users(id),

                CHECK (source IN ('builtin', 'upload')),
                CHECK (size_bytes > 0)
            )
            """
        )
