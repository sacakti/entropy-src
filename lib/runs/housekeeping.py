"""
Housekeeping: archive finished runs and their events after a retention
period, purge very old archives and remove leftover run files.
"""

from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List

from lib.database.connection import DatabaseConnection
from lib.database.objects.settings import SettingsTable

from .store import ensure_run_schema, utcnow

DEFAULTS = {
    # Finished runs older than this move to the archive tables.
    "runs.archive_after_days": 30,
    # Archived runs older than this are deleted (0 keeps them forever).
    "runs.purge_archive_after_days": 365,
}

LIMITS = {
    "runs.archive_after_days": (1, 3650),
    "runs.purge_archive_after_days": (0, 36500),
}

# Ad-hoc plugin run definitions are only needed while the worker starts.
PLUGIN_RUN_FILE_AGE = timedelta(days=1)


def _columns(connection: DatabaseConnection, table: str) -> List[str]:
    return [row["name"] for row in connection.fetchall(f"PRAGMA table_info({table})")]


class Housekeeping:
    """Archive policy for workflow jobs and events."""

    def __init__(self, connection: DatabaseConnection) -> None:
        ensure_run_schema(connection)
        SettingsTable().create(connection)
        self.connection = connection

    # ------------------------------------------------------------------
    # Settings
    # ------------------------------------------------------------------

    def settings(self) -> Dict[str, int]:
        rows = self.connection.fetchall(
            "SELECT key, value FROM settings WHERE key IN (?, ?)",
            tuple(DEFAULTS),
        )
        stored = {row["key"]: row["value"] for row in rows}
        result = {}
        for key, default in DEFAULTS.items():
            try:
                result[key] = int(stored.get(key, default))
            except (TypeError, ValueError):
                result[key] = default
        return result

    def update_settings(self, values: Dict[str, Any]) -> Dict[str, int]:
        with self.connection.transaction():
            for key, value in values.items():
                if key not in DEFAULTS:
                    continue
                low, high = LIMITS[key]
                number = int(value)
                if not low <= number <= high:
                    raise ValueError(f"{key} must be between {low} and {high}.")
                self.connection.execute(
                    "INSERT OR REPLACE INTO settings (key, value, updated_at) VALUES (?, ?, ?)",
                    (key, str(number), utcnow()),
                )
        return self.settings()

    # ------------------------------------------------------------------
    # Archive
    # ------------------------------------------------------------------

    def _copy(self, source: str, target: str, where: str, parameters: tuple) -> None:
        # Copy the columns both tables share, so schema changes never break it.
        shared = [
            c
            for c in _columns(self.connection, source)
            if c in set(_columns(self.connection, target))
        ]
        names = ", ".join(shared)
        self.connection.execute(
            f"INSERT INTO {target} ({names}) SELECT {names} FROM {source} WHERE {where}",  # nosec B608
            parameters,
        )

    def archive(self, older_than_days: int) -> Dict[str, int]:
        cutoff = (datetime.now(timezone.utc) - timedelta(days=older_than_days)).isoformat()
        finished = (
            "state IN ('completed', 'failed', 'cancelled')"
            " AND COALESCE(finished_at, created_at) < ?"
        )
        ids = [
            int(row["id"])
            for row in self.connection.fetchall(
                f"SELECT id FROM workflow_jobs WHERE {finished}",  # nosec B608
                (cutoff,),
            )
        ]
        if not ids:
            return {"jobs": 0, "events": 0}

        events = 0
        # Chunked to stay below SQLite's bound-parameter limit.
        for start in range(0, len(ids), 500):
            chunk = tuple(ids[start : start + 500])
            marks = ", ".join("?" for _ in chunk)
            with self.connection.transaction():
                self._copy("workflow_jobs", "workflow_jobs_archive", f"id IN ({marks})", chunk)
                self._copy(
                    "workflow_events", "workflow_events_archive", f"job_id IN ({marks})", chunk
                )
                self._copy("run_metadata", "run_metadata_archive", f"job_id IN ({marks})", chunk)
                events += self.connection.execute(
                    f"DELETE FROM workflow_events WHERE job_id IN ({marks})", chunk  # nosec B608
                ).rowcount
                self.connection.execute(
                    f"DELETE FROM run_metadata WHERE job_id IN ({marks})", chunk
                )  # nosec B608
                self.connection.execute(
                    f"DELETE FROM workflow_jobs WHERE id IN ({marks})", chunk
                )  # nosec B608

        return {"jobs": len(ids), "events": events}

    def purge_archive(self, older_than_days: int) -> int:
        if older_than_days <= 0:
            return 0
        cutoff = (datetime.now(timezone.utc) - timedelta(days=older_than_days)).isoformat()
        with self.connection.transaction():
            ids = [
                row["id"]
                for row in self.connection.fetchall(
                    "SELECT id FROM workflow_jobs_archive"
                    " WHERE COALESCE(finished_at, created_at) < ?",
                    (cutoff,),
                )
            ]
            for start in range(0, len(ids), 500):
                chunk = tuple(ids[start : start + 500])
                marks = ", ".join("?" for _ in chunk)
                self.connection.execute(
                    f"DELETE FROM workflow_events_archive WHERE job_id IN ({marks})", chunk
                )  # nosec B608
                self.connection.execute(
                    f"DELETE FROM run_metadata_archive WHERE job_id IN ({marks})", chunk
                )  # nosec B608
                self.connection.execute(
                    f"DELETE FROM workflow_jobs_archive WHERE id IN ({marks})", chunk
                )  # nosec B608
        return len(ids)

    def archive_counts(self) -> Dict[str, int]:
        jobs = self.connection.fetchone("SELECT COUNT(*) AS n FROM workflow_jobs_archive")
        events = self.connection.fetchone("SELECT COUNT(*) AS n FROM workflow_events_archive")
        return {"jobs": int(jobs["n"]), "events": int(events["n"])}

    @staticmethod
    def remove_files(directory: Path, older_than: timedelta, pattern: str) -> int:
        if not directory.is_dir():
            return 0
        cutoff = time.time() - older_than.total_seconds()
        removed = 0
        for path in directory.glob(pattern):
            try:
                if path.is_file() and path.stat().st_mtime < cutoff:
                    path.unlink()
                    removed += 1
            except OSError:
                continue
        return removed

    def run(self, *, plugin_runs: Path, worker_logs: Path) -> Dict[str, int]:
        settings = self.settings()
        archived = self.archive(settings["runs.archive_after_days"])
        purged = self.purge_archive(settings["runs.purge_archive_after_days"])

        # Worker logs belong to live jobs; archived ones are no longer viewable.
        live = {
            f"workflow-worker-{row['id']}.log"
            for row in self.connection.fetchall("SELECT id FROM workflow_jobs")
        }
        logs = 0
        if worker_logs.is_dir():
            for path in worker_logs.glob("workflow-worker-*.log"):
                if path.name not in live:
                    try:
                        path.unlink()
                        logs += 1
                    except OSError:
                        continue

        files = self.remove_files(plugin_runs, PLUGIN_RUN_FILE_AGE, "*.json")
        return {
            "archived_jobs": archived["jobs"],
            "archived_events": archived["events"],
            "purged_jobs": purged,
            "removed_logs": logs,
            "removed_files": files,
        }
