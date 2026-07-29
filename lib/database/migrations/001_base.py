"""
Initial database schema.
"""

from .base import BaseMigration


class Migration001(BaseMigration):

    VERSION = 1
    DESCRIPTION = "Initial database schema"

    def upgrade(
        self,
        connection,
    ):

        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations
            (
                version     INTEGER PRIMARY KEY,
                description TEXT NOT NULL,
                applied_at  TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS settings
            (
                key         TEXT PRIMARY KEY,
                value       TEXT,
                updated_at  TEXT
            );

            CREATE TABLE IF NOT EXISTS licenses
            (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                license_key     TEXT UNIQUE,
                edition         TEXT,
                customer        TEXT,
                email           TEXT,
                issued_at       TEXT,
                expires_at      TEXT,
                activated_at    TEXT,
                status          TEXT,
                signature       TEXT
            );

            CREATE TABLE IF NOT EXISTS plugins
            (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                name            TEXT UNIQUE,
                namespace       TEXT,
                version         TEXT,
                enabled         INTEGER,
                installed_at    TEXT
            );

            CREATE TABLE IF NOT EXISTS deployments
            (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                workflow        TEXT,
                started_at      TEXT,
                finished_at     TEXT,
                duration_ms     INTEGER,
                status          TEXT
            );
            """
        )
