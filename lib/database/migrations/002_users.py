from abc import abstractmethod

from lib.database.migrations.base import BaseMigration


class UsersMigration(BaseMigration):

    VERSION = 2

    DESCRIPTION = "Create users table"

    @abstractmethod
    def validate(self):
        ...

    def upgrade(self, connection):

        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS users
            (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,

                username        TEXT NOT NULL UNIQUE,

                password_hash   TEXT NOT NULL,

                full_name       TEXT,

                email           TEXT,

                group_id        INTEGER,

                system          INTEGER NOT NULL DEFAULT 0,

                is_active       INTEGER NOT NULL DEFAULT 1,

                created_at      TEXT NOT NULL,

                updated_at      TEXT NOT NULL
            )
            """
        )

    def downgrade(self, connection):

        connection.execute(
            """
            DROP TABLE IF EXISTS users
            """
        )
