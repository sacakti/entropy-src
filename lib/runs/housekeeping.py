"""
Housekeeping: archive finished runs and their events after a retention
period, purge very old archives and remove leftover run files.
"""

from __future__ import annotations

import io
import json
import tarfile
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
    "runs.archive_rules": {
        "schedule": False,
        "plugin": False,
        "completed": False,
        "failed": False,
        "cancelled": False,
        "workflows": [],
    },
    # Notifications older than this are deleted (0 keeps them forever).
    "notifications.keep_days": 90,
}

LIMITS = {
    "runs.archive_after_days": (1, 3650),
    "runs.purge_archive_after_days": (0, 36500),
    "notifications.keep_days": (0, 3650),
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

    def settings(self) -> Dict[str, Any]:
        rows = self.connection.fetchall(
            "SELECT key, value FROM settings WHERE key IN ("
            + ", ".join("?" for _ in DEFAULTS)
            + ")",
            tuple(DEFAULTS),
        )
        stored = {row["key"]: row["value"] for row in rows}
        result: Dict[str, Any] = {}
        for key, default in DEFAULTS.items():
            if key == "runs.archive_rules":
                try:
                    value = json.loads(stored.get(key, "{}"))
                    result[key] = self._normalize_rules(value)
                except (TypeError, ValueError):
                    result[key] = default
                continue
            try:
                result[key] = int(stored.get(key, default))
            except (TypeError, ValueError):
                result[key] = default
        return result

    @staticmethod
    def _normalize_rules(value: Any) -> Dict[str, Any]:
        if not isinstance(value, dict):
            raise ValueError("Archive rules must be an object.")
        for key in ("schedule", "plugin", "completed", "failed", "cancelled"):
            if key in value and not isinstance(value[key], bool):
                raise ValueError(f"The {key} archive rule must be true or false.")
        workflows = value.get("workflows", [])
        if not isinstance(workflows, list) or len(workflows) > 100:
            raise ValueError("Workflow archive rules must be a list of at most 100 rules.")
        normalized = []
        for rule in workflows:
            if not isinstance(rule, dict) or rule.get("mode") not in ("exact", "startswith"):
                raise ValueError("Each workflow rule needs mode 'exact' or 'startswith'.")
            pattern = rule.get("pattern")
            if not isinstance(pattern, str) or not pattern.strip() or len(pattern) > 200:
                raise ValueError("Workflow rule patterns must be 1 to 200 characters.")
            normalized.append({"mode": rule["mode"], "pattern": pattern.strip()})
        return {
            "schedule": value.get("schedule", False),
            "plugin": value.get("plugin", False),
            "completed": value.get("completed", False),
            "failed": value.get("failed", False),
            "cancelled": value.get("cancelled", False),
            "workflows": normalized,
        }

    def update_settings(self, values: Dict[str, Any]) -> Dict[str, Any]:
        with self.connection.transaction():
            for key, value in values.items():
                if key not in DEFAULTS:
                    continue
                if key == "runs.archive_rules":
                    rules = self._normalize_rules(value)
                    self.connection.execute(
                        "INSERT OR REPLACE INTO settings (key, value, updated_at) VALUES (?, ?, ?)",
                        (key, json.dumps(rules), utcnow()),
                    )
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

    def archive(
        self, older_than_days: int, rules: Dict[str, Any] | None = None
    ) -> Dict[str, int]:
        cutoff = (datetime.now(timezone.utc) - timedelta(days=older_than_days)).isoformat()
        rules = self._normalize_rules(rules or {})
        archive_match = ["COALESCE(j.finished_at, j.created_at) < ?"]
        parameters: List[Any] = [cutoff]
        if rules["schedule"]:
            archive_match.append("m.trigger = 'schedule'")
        if rules["plugin"]:
            archive_match.append("m.kind = 'plugin'")
        for state in ("completed", "failed", "cancelled"):
            if rules[state]:
                archive_match.append("j.state = '" + state + "'")
        for rule in rules["workflows"]:
            if rule["mode"] == "exact":
                archive_match.append("(m.kind = 'workflow' AND LOWER(j.workflow) = LOWER(?))")
            else:
                archive_match.append(
                    "(m.kind = 'workflow' AND LOWER(j.workflow) LIKE LOWER(?) ESCAPE '\\')"
                )
            pattern = rule["pattern"]
            if rule["mode"] == "startswith":
                pattern = pattern.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
            parameters.append(pattern)
        finished = (
            "j.state IN ('completed', 'failed', 'cancelled') AND ("
            + " OR ".join(archive_match)
            + ")"
        )
        ids = [
            int(row["id"])
            for row in self.connection.fetchall(
                "SELECT j.id FROM workflow_jobs j"
                " LEFT JOIN run_metadata m ON m.job_id = j.id"
                f" WHERE {finished}",
                tuple(parameters),
            )
        ]
        if not ids:
            return {"jobs": 0, "events": 0}
        return self._archive_ids(ids)

    def archive_selected(self, job_ids: List[int], project_id: int | None) -> Dict[str, int]:
        ids = sorted(set(job_ids))
        if not ids or len(ids) > 500:
            raise ValueError("Select between 1 and 500 runs to archive.")
        from lib.authorization.projects import default_project_id

        default_id = default_project_id(self.connection)
        marks = ", ".join("?" for _ in ids)
        rows = self.connection.fetchall(
            "SELECT j.id, j.state FROM workflow_jobs j"
            " LEFT JOIN run_metadata m ON m.job_id = j.id"
            f" WHERE j.id IN ({marks}) AND IFNULL(m.project_id, ?) = ?",
            tuple(ids) + (default_id, project_id),
        )
        found = {int(row["id"]): row["state"] for row in rows}
        if set(found) != set(ids):
            raise ValueError("One or more selected runs no longer exist in this project.")
        if any(state not in ("completed", "failed", "cancelled") for state in found.values()):
            raise ValueError("Only completed, failed or cancelled runs can be archived.")
        result = self._archive_ids(ids)
        result["jobs"] = len(ids)
        return result

    def _descendants(self, job_ids: List[int], metadata_table: str) -> List[int]:
        """Include coordinated child jobs so archive operations stay complete."""

        ids = list(dict.fromkeys(int(job_id) for job_id in job_ids))
        known = set(ids)
        frontier = list(ids)
        while frontier:
            next_frontier = []
            for start in range(0, len(frontier), 500):
                chunk = tuple(frontier[start : start + 500])
                marks = ", ".join("?" for _ in chunk)
                children = [
                    int(row["job_id"])
                    for row in self.connection.fetchall(
                        f"SELECT job_id FROM {metadata_table} WHERE parent_job_id IN ({marks})",
                        chunk,
                    )
                    if int(row["job_id"]) not in known
                ]
                known.update(children)
                ids.extend(children)
                next_frontier.extend(children)
            frontier = next_frontier
        return ids

    def _archive_ids(self, job_ids: List[int]) -> Dict[str, int]:
        ids = self._descendants(job_ids, "run_metadata")

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

    def purge_archive(
        self,
        older_than_days: int,
        *,
        purge_all: bool = False,
        project_id: int | None = None,
    ) -> int:
        if older_than_days <= 0 and not purge_all:
            return 0
        cutoff = (
            (datetime.now(timezone.utc) - timedelta(days=older_than_days)).isoformat()
            if not purge_all
            else None
        )
        with self.connection.transaction():
            conditions: List[str] = []
            parameters: List[Any] = []
            if not purge_all:
                conditions.append("COALESCE(j.finished_at, j.created_at) < ?")
                parameters.append(cutoff)
            if project_id is not None:
                from lib.authorization.projects import default_project_id

                default_id = default_project_id(self.connection)
                conditions.append("IFNULL(m.project_id, ?) = ?")
                parameters.extend([default_id, project_id])
            condition = " WHERE " + " AND ".join(conditions) if conditions else ""
            ids = [
                row["id"]
                for row in self.connection.fetchall(
                    "SELECT j.id FROM workflow_jobs_archive j"
                    " LEFT JOIN run_metadata_archive m ON m.job_id = j.id"
                    + condition,
                    tuple(parameters),
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

    def export_archive(
        self,
        *,
        project_id: int | None,
        older_than_days: int | None = None,
        export_all: bool = False,
        job_ids: List[int] | None = None,
    ) -> bytes:
        """Build a portable tar.gz with archived job, metadata and event rows."""

        conditions: List[str] = []
        parameters: List[Any] = []
        selected_ids = sorted(set(job_ids or []))
        if job_ids is not None and (not selected_ids or len(selected_ids) > 500):
            raise ValueError("Select between 1 and 500 archived runs to export.")
        if selected_ids:
            conditions.append("j.id IN (" + ", ".join("?" for _ in selected_ids) + ")")
            parameters.extend(selected_ids)
        elif not export_all and older_than_days is not None:
            cutoff = (datetime.now(timezone.utc) - timedelta(days=older_than_days)).isoformat()
            conditions.append("COALESCE(j.finished_at, j.created_at) < ?")
            parameters.append(cutoff)
        if project_id is not None:
            from lib.authorization.projects import default_project_id

            conditions.append("IFNULL(m.project_id, ?) = ?")
            parameters.extend([default_project_id(self.connection), project_id])
        clause = " WHERE " + " AND ".join(conditions) if conditions else ""
        jobs = self.connection.fetchall(
            "SELECT j.id FROM workflow_jobs_archive j"
            " LEFT JOIN run_metadata_archive m ON m.job_id = j.id"
            + clause
            + " ORDER BY j.id",
            tuple(parameters),
        )
        job_ids = [int(row["id"]) for row in jobs]
        if selected_ids and len(job_ids) != len(selected_ids):
            raise ValueError("One or more selected archived runs no longer exist in this project.")
        if selected_ids:
            job_ids = self._descendants(job_ids, "run_metadata_archive")
        job_data = []
        event_data = []
        for start in range(0, len(job_ids), 500):
            chunk = tuple(job_ids[start : start + 500])
            marks = ", ".join("?" for _ in chunk)
            job_rows = self.connection.fetchall(
                f"SELECT * FROM workflow_jobs_archive WHERE id IN ({marks}) ORDER BY id", chunk
            )
            metadata_rows = self.connection.fetchall(
                f"SELECT * FROM run_metadata_archive WHERE job_id IN ({marks}) ORDER BY job_id", chunk
            )
            metadata = {}
            for row in metadata_rows:
                item = dict(row)
                # Rerun inputs can include credentials; keep them available in
                # the live database for execution, but exclude them from the
                # broadly downloadable run archive.
                item.pop("rerun_config", None)
                metadata[int(row["job_id"])] = item
            job_data.extend(
                {"job": dict(row), "metadata": metadata.get(int(row["id"]))}
                for row in job_rows
            )
            event_data.extend(
                dict(row)
                for row in self.connection.fetchall(
                    f"SELECT * FROM workflow_events_archive WHERE job_id IN ({marks}) ORDER BY id",
                    chunk,
                )
            )

        created = datetime.now(timezone.utc).isoformat()
        files = {
            "manifest.json": {
                "format": "entropy-run-archive",
                "version": 1,
                "created_at": created,
                "project_id": project_id,
                "jobs": len(job_data),
                "events": len(event_data),
            },
            "runs.json": job_data,
            "events.json": event_data,
        }
        output = io.BytesIO()
        with tarfile.open(fileobj=output, mode="w:gz") as archive:
            for name, value in files.items():
                payload = json.dumps(value, indent=2, default=str).encode("utf-8")
                info = tarfile.TarInfo(name)
                info.size = len(payload)
                info.mtime = int(time.time())
                archive.addfile(info, io.BytesIO(payload))
        return output.getvalue()

    def purge_selected(self, job_ids: List[int], project_id: int) -> int:
        ids = sorted(set(job_ids))
        if not ids or len(ids) > 500:
            raise ValueError("Select between 1 and 500 archived runs to purge.")
        from lib.authorization.projects import default_project_id

        default_id = default_project_id(self.connection)
        marks = ", ".join("?" for _ in ids)
        rows = self.connection.fetchall(
            "SELECT j.id FROM workflow_jobs_archive j"
            " LEFT JOIN run_metadata_archive m ON m.job_id = j.id"
            f" WHERE j.id IN ({marks}) AND IFNULL(m.project_id, ?) = ?",
            tuple(ids) + (default_id, project_id),
        )
        if {int(row["id"]) for row in rows} != set(ids):
            raise ValueError("One or more selected archived runs no longer exist in this project.")
        selected_count = len(ids)
        ids = self._descendants(ids, "run_metadata_archive")
        with self.connection.transaction():
            for start in range(0, len(ids), 500):
                chunk = tuple(ids[start : start + 500])
                marks = ", ".join("?" for _ in chunk)
                self.connection.execute(
                    f"DELETE FROM workflow_events_archive WHERE job_id IN ({marks})", chunk
                )
                self.connection.execute(
                    f"DELETE FROM run_metadata_archive WHERE job_id IN ({marks})", chunk
                )
                self.connection.execute(
                    f"DELETE FROM workflow_jobs_archive WHERE id IN ({marks})", chunk
                )
        return selected_count

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

    def purge_notifications(self, keep_days: int) -> int:
        if keep_days <= 0:
            return 0
        exists = self.connection.fetchone(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'notifications'"
        )
        if exists is None:
            return 0
        cutoff = (datetime.now(timezone.utc) - timedelta(days=keep_days)).strftime(
            "%Y-%m-%d %H:%M:%S"
        )
        with self.connection.transaction():
            return self.connection.execute(
                "DELETE FROM notifications WHERE created_at < ?", (cutoff,)
            ).rowcount

    def run(self, *, plugin_runs: Path, worker_logs: Path) -> Dict[str, int]:
        settings = self.settings()
        archived = self.archive(settings["runs.archive_after_days"], settings["runs.archive_rules"])
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
        notifications = self.purge_notifications(settings["notifications.keep_days"])
        return {
            "removed_notifications": notifications,
            "archived_jobs": archived["jobs"],
            "archived_events": archived["events"],
            "purged_jobs": purged,
            "removed_logs": logs,
            "removed_files": files,
        }
