"""
Run orchestration tables: run metadata, nodes, node metrics, schedules
and the archive of old jobs.
"""

from lib.database.base import DatabaseObject
from lib.database.connection import DatabaseConnection


class RunMetadataTable(DatabaseObject):
    """
    Where and why a workflow job ran. Kept beside workflow_jobs so the
    job schema used by the CLI stays unchanged.
    """

    NAME = "run_metadata"

    def create(
        self,
        connection: DatabaseConnection,
    ) -> None:

        connection.execute("""
            CREATE TABLE IF NOT EXISTS run_metadata
            (
                job_id       INTEGER PRIMARY KEY,
                node         TEXT NOT NULL DEFAULT 'local',
                kind         TEXT NOT NULL DEFAULT 'workflow'
                    CHECK (kind IN ('workflow', 'plugin')),
                target       TEXT NOT NULL,
                trigger      TEXT NOT NULL DEFAULT 'manual'
                    CHECK (trigger IN ('manual', 'schedule', 'retry', 'cli')),
                schedule_id  INTEGER,
                created_at   TEXT NOT NULL
            )
            """)

        connection.execute("""
            CREATE INDEX IF NOT EXISTS idx_run_metadata_schedule
            ON run_metadata (schedule_id)
            """)


class NodesTable(DatabaseObject):
    """
    Execution nodes. The server Entropy is installed on is the 'local' node.
    """

    NAME = "nodes"

    def create(
        self,
        connection: DatabaseConnection,
    ) -> None:

        connection.execute("""
            CREATE TABLE IF NOT EXISTS nodes
            (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                name          TEXT NOT NULL UNIQUE,
                kind          TEXT NOT NULL DEFAULT 'remote'
                    CHECK (kind IN ('local', 'remote')),
                host          TEXT NOT NULL DEFAULT '',
                description   TEXT NOT NULL DEFAULT '',
                enabled       INTEGER NOT NULL DEFAULT 1,
                info          TEXT,
                token_hash    TEXT,
                created_at    TEXT NOT NULL,
                updated_at    TEXT NOT NULL,
                last_seen_at  TEXT
            )
            """)


class NodeMetricsTable(DatabaseObject):
    """
    Periodic resource samples per node.
    """

    NAME = "node_metrics"

    def create(
        self,
        connection: DatabaseConnection,
    ) -> None:

        connection.execute("""
            CREATE TABLE IF NOT EXISTS node_metrics
            (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                node            TEXT NOT NULL,
                sampled_at      TEXT NOT NULL,
                cpu_percent     REAL,
                memory_percent  REAL,
                disk_percent    REAL,
                load1           REAL,
                running_jobs    INTEGER NOT NULL DEFAULT 0,
                agent_up        INTEGER NOT NULL DEFAULT 0
            )
            """)

        connection.execute("""
            CREATE INDEX IF NOT EXISTS idx_node_metrics_node
            ON node_metrics (node, sampled_at)
            """)


class SchedulesTable(DatabaseObject):
    """
    Cron schedules for workflows and plugins.
    """

    NAME = "schedules"

    def create(
        self,
        connection: DatabaseConnection,
    ) -> None:

        connection.execute("""
            CREATE TABLE IF NOT EXISTS schedules
            (
                id               INTEGER PRIMARY KEY AUTOINCREMENT,
                name             TEXT NOT NULL UNIQUE,
                description      TEXT NOT NULL DEFAULT '',
                kind             TEXT NOT NULL
                    CHECK (kind IN ('workflow', 'plugin')),
                target           TEXT NOT NULL,
                cron             TEXT NOT NULL,
                timezone         TEXT NOT NULL DEFAULT 'UTC',
                node             TEXT NOT NULL DEFAULT 'local',
                parameters       TEXT NOT NULL DEFAULT '{}',
                enabled          INTEGER NOT NULL DEFAULT 1,
                user_id          INTEGER NOT NULL,
                username         TEXT NOT NULL,
                created_at       TEXT NOT NULL,
                updated_at       TEXT NOT NULL,
                next_run_at      TEXT,
                last_run_at      TEXT
            )
            """)


class ScheduleRunsTable(DatabaseObject):
    """
    Each firing of a schedule, kept so failures can be retriggered.
    """

    NAME = "schedule_runs"

    def create(
        self,
        connection: DatabaseConnection,
    ) -> None:

        connection.execute("""
            CREATE TABLE IF NOT EXISTS schedule_runs
            (
                id             INTEGER PRIMARY KEY AUTOINCREMENT,
                schedule_id    INTEGER NOT NULL,
                job_id         INTEGER,
                trigger        TEXT NOT NULL DEFAULT 'schedule'
                    CHECK (trigger IN ('schedule', 'manual', 'retry')),
                state          TEXT NOT NULL,
                error          TEXT,
                retry_of       INTEGER,
                created_at     TEXT NOT NULL,
                finished_at    TEXT
            )
            """)

        connection.execute("""
            CREATE INDEX IF NOT EXISTS idx_schedule_runs_schedule
            ON schedule_runs (schedule_id, created_at)
            """)


class RunArchiveTables(DatabaseObject):
    """
    Archive copies of workflow_jobs and workflow_events for housekeeping.
    """

    NAME = "workflow_jobs_archive"

    def create(
        self,
        connection: DatabaseConnection,
    ) -> None:

        # Same columns as the live tables, without their constraints.
        connection.execute("""
            CREATE TABLE IF NOT EXISTS workflow_jobs_archive
            AS SELECT * FROM workflow_jobs WHERE 0
            """)

        connection.execute("""
            CREATE TABLE IF NOT EXISTS workflow_events_archive
            AS SELECT * FROM workflow_events WHERE 0
            """)

        connection.execute("""
            CREATE TABLE IF NOT EXISTS run_metadata_archive
            AS SELECT * FROM run_metadata WHERE 0
            """)


class NodeJobsTable(DatabaseObject):
    """
    Runs dispatched to remote nodes: the agent claims them, streams their
    events back and reports their final state.
    """

    NAME = "node_jobs"

    def create(
        self,
        connection: DatabaseConnection,
    ) -> None:

        connection.execute("""
            CREATE TABLE IF NOT EXISTS node_jobs
            (
                job_id          INTEGER PRIMARY KEY,
                node            TEXT NOT NULL,
                spec            TEXT NOT NULL,
                status          TEXT NOT NULL DEFAULT 'pending'
                    CHECK (status IN ('pending', 'claimed', 'finished')),
                stop_requested  INTEGER NOT NULL DEFAULT 0,
                created_at      TEXT NOT NULL,
                claimed_at      TEXT,
                updated_at      TEXT NOT NULL
            )
            """)

        connection.execute("""
            CREATE INDEX IF NOT EXISTS idx_node_jobs_node
            ON node_jobs (node, status)
            """)


class NodeProvisioningTable(DatabaseObject):
    """
    Setup attempts of remote nodes with their progress log. Credentials
    are never stored here.
    """

    NAME = "node_provisioning"

    def create(
        self,
        connection: DatabaseConnection,
    ) -> None:

        connection.execute("""
            CREATE TABLE IF NOT EXISTS node_provisioning
            (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                node         TEXT NOT NULL,
                action       TEXT NOT NULL DEFAULT 'install'
                    CHECK (action IN ('install', 'uninstall')),
                status       TEXT NOT NULL DEFAULT 'running'
                    CHECK (status IN ('running', 'succeeded', 'failed')),
                log          TEXT NOT NULL DEFAULT '[]',
                error        TEXT,
                user_id      INTEGER,
                username     TEXT,
                created_at   TEXT NOT NULL,
                finished_at  TEXT
            )
            """)


# Columns added to `nodes` for remote nodes (name, declaration).
NODE_COLUMNS = (
    ("port", "INTEGER NOT NULL DEFAULT 22"),
    ("ssh_user", "TEXT NOT NULL DEFAULT ''"),
    ("install_dir", "TEXT NOT NULL DEFAULT ''"),
    ("host_key", "TEXT"),
    ("server_url", "TEXT"),
    ("agent_version", "TEXT"),
    ("last_metrics", "TEXT"),
    ("max_jobs", "INTEGER NOT NULL DEFAULT 2"),
)


def upgrade_nodes_table(
    connection: DatabaseConnection,
) -> None:
    """Add remote-node columns that older `nodes` tables lack."""

    existing = {row["name"] for row in connection.fetchall("PRAGMA table_info(nodes)")}

    for name, declaration in NODE_COLUMNS:
        if name not in existing:
            connection.execute(f"ALTER TABLE nodes ADD COLUMN {name} {declaration}")


# Columns added to `run_metadata` (and its archive) after it was created:
# - options: the run's plan (selected/skipped steps, tags, node per step);
# - parent_job_id: set on each segment of a run that spans several nodes;
# - heartbeat_at: set on such a run while the main node coordinates it.
RUN_METADATA_COLUMNS = (
    ("options", "TEXT"),
    ("rerun_config", "TEXT"),
    ("parent_job_id", "INTEGER"),
    ("heartbeat_at", "TEXT"),
)


def upgrade_run_metadata_table(
    connection: DatabaseConnection,
) -> None:
    """Add run_metadata columns that older tables lack."""

    for table in ("run_metadata", "run_metadata_archive"):
        existing = {row["name"] for row in connection.fetchall(f"PRAGMA table_info({table})")}
        if not existing:
            continue
        for name, declaration in RUN_METADATA_COLUMNS:
            if name not in existing:
                connection.execute(f"ALTER TABLE {table} ADD COLUMN {name} {declaration}")

    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_run_metadata_parent ON run_metadata (parent_job_id)"
    )


RUN_TABLES = (
    RunMetadataTable,
    NodesTable,
    NodeMetricsTable,
    SchedulesTable,
    ScheduleRunsTable,
    RunArchiveTables,
    NodeJobsTable,
    NodeProvisioningTable,
)


def create_run_tables(
    connection: DatabaseConnection,
) -> None:
    """Create every run orchestration table (idempotent)."""

    for table in RUN_TABLES:
        table().create(connection)

    upgrade_nodes_table(connection)
    upgrade_run_metadata_table(connection)
