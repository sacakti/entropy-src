"""
Migration executor.
"""


class MigrationExecutor:

    def __init__(self, connection, registry, context):

        self._connection = connection
        self._registry = registry
        self._context = context

    def execute(self):

        self._context.output.rule("Database Migration")

        self._context.output.database.info("Discovering migrations...")

        migrations = sorted(
            self._registry.list(),
            key=lambda m: m.VERSION,
        )

        self._context.output.database.success(f"Found {len(migrations)} migration(s).")

        self._create_history()

        self._connection.connection.commit()

        applied_count = 0
        pending = []

        for migration in migrations:

            if self._applied(migration.VERSION):

                applied_count += 1

            else:

                pending.append(migration)

        self._context.output.database.info("Checking migration history...")

        self._context.output.database.info(f"Applied migrations : {applied_count}")

        self._context.output.database.info(f"Pending migrations : {len(pending)}")

        if not pending:

            self._context.output.database.success("Database is already up to date.")

            self._context.output.system.info("Database migration completed.")

            return

        self._context.output.database.info("Applying pending migrations...")

        for migration in pending:

            self._execute_migration(migration)

        self._context.output.database.success("Database migration completed.")

    def _execute_migration(
        self,
        migration,
    ):

        self._context.output.database.info(f"{migration.VERSION:03d} " f"{migration.DESCRIPTION}")

        try:

            migration.validate()

            migration.upgrade(self._connection.connection)

            self._record(migration)

            self._connection.connection.commit()

            self._context.output.database.success(f"Applied {migration.VERSION:03d}")

            self._context.output.system.info(
                f"Migration {migration.VERSION:03d} " f"({migration.DESCRIPTION}) applied."
            )

        except Exception as exc:

            self._connection.connection.rollback()

            self._context.output.database.error(f"Migration {migration.VERSION:03d} failed.")

            self._context.output.system.error(str(exc))

            raise

    def _create_history(self):

        self._connection.connection.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations
            (
                version INTEGER PRIMARY KEY,
                description TEXT NOT NULL,
                applied_at TEXT NOT NULL
            )
            """
        )

    def _applied(
        self,
        version,
    ):

        cursor = self._connection.connection.execute(
            """
            SELECT 1
            FROM schema_migrations
            WHERE version = ?
            """,
            (version,),
        )

        return cursor.fetchone() is not None

    def _record(self, migration):

        self._connection.connection.execute(
            """
            INSERT INTO schema_migrations(
                version,
                description,
                applied_at
            )
            VALUES(
                ?,
                ?,
                datetime('now')
            )
            """,
            (migration.VERSION, migration.DESCRIPTION),
        )
