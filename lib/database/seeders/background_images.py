"""
Seed built-in background images.
"""

import mimetypes
from datetime import datetime, timezone
from pathlib import Path

from lib.database.connection import DatabaseConnection


class BackgroundImagesSeeder:
    """Insert built-in background images if they do not exist."""

    def __init__(self, assets_directory: Path) -> None:
        self._assets_directory = assets_directory

    def seed(self, connection: DatabaseConnection) -> None:
        images = (
            ("entropy", "Entropy", "entropy.jpg"),
            ("midnight", "Midnight", "midnight.jpg"),
            ("mountains-1", "Mountains", "mountain-1.png"),
            ("mountains-2", "Mountains", "mountain-2.jpg"),
            ("mountains-3", "Mountains", "mountain-3.jpg"),
            ("abstract-1", "Abstract", "abstract-1.jpg"),
            ("abstract-2", "Abstract", "abstract-2.jpg"),
            ("abstract-3", "Abstract", "abstract-3.jpg"),
        )

        with connection.transaction():
            for image_key, name, filename in images:
                existing = connection.fetchone(
                    """
                    SELECT 1
                    FROM background_images
                    WHERE image_key = ?
                    """,
                    (image_key,),
                )

                if existing is not None:
                    continue

                image_path = self._assets_directory / filename
                image_data = image_path.read_bytes()
                mime_type, _ = mimetypes.guess_type(filename)

                if mime_type is None or not mime_type.startswith("image/"):
                    raise ValueError(
                        f"Unsupported image type: {filename}"
                    )

                created_at = datetime.now(timezone.utc).isoformat()

                connection.execute(
                    """
                    INSERT INTO background_images
                    (
                        owner_user_id,
                        image_key,
                        name,
                        mime_type,
                        size_bytes,
                        image_data,
                        source,
                        created_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, 'builtin', ?)
                    """,
                    (
                        None,
                        image_key,
                        name,
                        mime_type,
                        len(image_data),
                        image_data,
                        created_at,
                    ),
                )
