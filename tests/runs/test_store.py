"""Tests for run storage, schedules, housekeeping and node metrics."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from lib.database.connection import DatabaseConnection
from lib.database.objects.events import WorkflowEventsTable
from lib.database.objects.jobs import WorkflowJobsTable
from lib.runs.housekeeping import Housekeeping
from lib.runs.nodes import LocalMetrics, NodeStore, exposition
from lib.runs.schedules import ScheduleError, ScheduleStore
from lib.runs.store import RunStore, iso_utc


@pytest.fixture
def connection(tmp_path: Path, monkeypatch) -> DatabaseConnection:
    # Permission seeding needs the authorization tables; not under test here.
    monkeypatch.setattr(
        "lib.authorization.initializer.AuthorizationInitializer.reconcile",
        lambda self: None,
    )
    connection = DatabaseConnection(tmp_path / "entropy.db")
    WorkflowJobsTable().create(connection)
    WorkflowEventsTable().create(connection)
    # Columns added by migrations 004 and 005.
    for column in ("user_id INTEGER", "username TEXT", "full_name TEXT"):
        connection.execute(f"ALTER TABLE workflow_jobs ADD COLUMN {column}")
    connection.execute(
        "CREATE TABLE users"
        " (id INTEGER PRIMARY KEY, username TEXT, full_name TEXT, is_active INTEGER)"
    )
    return connection


def _job(connection: DatabaseConnection, state: str, finished_days_ago: float = 0) -> int:
    finished = (datetime.now(timezone.utc) - timedelta(days=finished_days_ago)).isoformat()
    cursor = connection.execute(
        "INSERT INTO workflow_jobs"
        " (execution_id, workflow, state, pid, workspace, created_at, finished_at, username)"
        " VALUES (?, 'deploy', ?, 0, '/tmp', ?, ?, 'admin')",
        (uuid.uuid4().hex, state, finished, finished if state != "running" else None),
    )
    connection.commit()
    return int(cursor.lastrowid)


def test_list_filters_by_tab_and_joins_metadata(connection) -> None:
    store = RunStore(connection)
    running = _job(connection, "running")
    done = _job(connection, "completed")
    store.record(done, node="local", kind="plugin", target="builtin.hello", trigger="manual")

    items, total = store.list(tab="active")
    assert total == 1 and items[0]["id"] == running and items[0]["trigger"] == "cli"

    items, _ = store.list(search="hello")
    assert [item["id"] for item in items] == [done]
    assert items[0]["kind"] == "plugin"

    assert store.counts() == {"active": 1, "completed": 1, "failed": 0, "cancelled": 0, "all": 2}
    assert store.running_on("local") == 1


def test_iso_utc_normalises_sqlite_timestamps() -> None:
    assert iso_utc("2026-10-20 09:31:49") == "2026-10-20T09:31:49+00:00"
    assert iso_utc(None) is None


def test_archive_moves_old_finished_runs(connection, tmp_path) -> None:
    old = _job(connection, "failed", finished_days_ago=40)
    recent = _job(connection, "completed", finished_days_ago=1)
    connection.execute(
        "INSERT INTO workflow_events (job_id, execution_id, event_type, created_at)"
        " VALUES (?, 'e', 'message', 'x')",
        (old,),
    )
    connection.commit()

    housekeeping = Housekeeping(connection)
    result = housekeeping.run(plugin_runs=tmp_path / "none", worker_logs=tmp_path / "none")

    assert result["archived_jobs"] == 1 and result["archived_events"] == 1
    remaining = [row["id"] for row in connection.fetchall("SELECT id FROM workflow_jobs")]
    assert remaining == [recent]
    assert housekeeping.archive_counts() == {"jobs": 1, "events": 1}

    with pytest.raises(ValueError):
        housekeeping.update_settings({"runs.archive_after_days": 0})


def test_schedule_validation_and_failed_runs(connection) -> None:
    store = ScheduleStore(connection)
    schedule = store.create(
        {"name": "Nightly", "kind": "workflow", "target": "deploy", "cron": "0 2 * * *"}, 1, "admin"
    )
    assert schedule["next_run_at"]

    with pytest.raises(ScheduleError):
        store.create(
            {"name": "nightly", "kind": "workflow", "target": "deploy", "cron": "0 2 * * *"},
            1,
            "admin",
        )
    with pytest.raises(ScheduleError):
        store.create(
            {"name": "Bad", "kind": "workflow", "target": "deploy", "cron": "nope"}, 1, "admin"
        )

    job = _job(connection, "running")
    run = store.add_run(schedule["id"], trigger="schedule", job_id=job)
    store.add_run(schedule["id"], trigger="schedule", error="Owner is disabled.")
    connection.execute("UPDATE workflow_jobs SET state = 'failed' WHERE id = ?", (job,))
    connection.commit()

    failed = store.sync()
    assert [item["id"] for item in failed] == [run["id"]]
    assert len(store.runs(failed_only=True)) == 2

    store.mark_retried(run["id"])
    assert len(store.runs(failed_only=True)) == 1

    assert store.delete([schedule["id"]]) == 1
    assert store.runs() == []


def test_local_node_and_exposition(connection, tmp_path) -> None:
    nodes = NodeStore(connection)
    assert [node["name"] for node in nodes.list()] == ["local"]

    metrics = LocalMetrics(tmp_path).collect()
    metrics.update(agent_up=True, running_jobs=2)
    nodes.add_sample("local", metrics)
    assert len(nodes.history("local")) == 1

    text = exposition([{"name": "local", "kind": "local", "metrics": metrics}])
    assert 'entropy_node_up{node="local",kind="local"} 1' in text
    assert 'entropy_node_running_jobs{node="local",kind="local"} 2' in text
    assert "# TYPE entropy_node_disk_usage_percent gauge" in text
