"""Reporting finished runs (notifications, e-mail)."""

from __future__ import annotations

from test_store import _job, connection  # noqa: F401 - fixture

from lib.runs.outcomes import RunOutcomes, describe
from lib.runs.store import RunStore


def test_reports_each_finished_run_once(connection) -> None:  # noqa: F811
    store = RunStore(connection)
    before = _job(connection, "completed")
    store.record(before, node="local", kind="workflow", target="deploy", trigger="manual")

    outcomes = RunOutcomes(connection)
    # Runs finished before reporting started are not news.
    assert outcomes.collect() == []

    running = _job(connection, "running")
    store.record(running, node="edge", kind="plugin", target="builtin.hello", trigger="manual")
    failed = _job(connection, "failed")
    store.record(failed, node="local", kind="workflow", target="deploy", trigger="manual")

    reported = outcomes.collect()
    assert [item["job_id"] for item in reported] == [failed]
    assert describe(reported[0])["level"] == "error"
    assert outcomes.collect() == []

    connection.execute("UPDATE workflow_jobs SET state = 'completed' WHERE id = ?", (running,))
    connection.commit()
    reported = outcomes.collect()
    assert [(item["kind"], item["target"]) for item in reported] == [("plugin", "builtin.hello")]
    assert describe(reported[0])["title"] == "Plugin 'builtin.hello' completed"


def test_segments_of_multi_node_runs_are_not_reported(connection) -> None:  # noqa: F811
    store = RunStore(connection)
    outcomes = RunOutcomes(connection)
    parent = _job(connection, "completed")
    store.record(parent, node="local", kind="workflow", target="deploy", trigger="manual")
    segment = _job(connection, "completed")
    store.record(
        segment,
        node="edge",
        kind="workflow",
        target="deploy",
        trigger="manual",
        parent_job_id=parent,
    )

    assert [item["job_id"] for item in outcomes.collect()] == [parent]
