"""Tests for remote-node dispatch, packaging, SSH messages and setup validation."""

from __future__ import annotations

import io
import json
import tarfile
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from lib.database.connection import DatabaseConnection
from lib.database.objects.events import WorkflowEventsTable
from lib.database.objects.jobs import WorkflowJobsTable
from lib.nodes.dispatch import NodeDispatcher, token_hash
from lib.nodes.packaging import agent_requirements, plugin_bundle, runtime_bundle
from lib.nodes.provision import ProvisionError, ProvisionRequest
from lib.nodes.ssh import _explain
from lib.runs.nodes import NodeStore
from lib.workflow.jobs.manager import WorkflowJobManager


@pytest.fixture
def context(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(
        "lib.authorization.initializer.AuthorizationInitializer.reconcile",
        lambda self: None,
    )
    connection = DatabaseConnection(tmp_path / "entropy.db")
    WorkflowJobsTable().create(connection)
    WorkflowEventsTable().create(connection)
    for column in ("user_id INTEGER", "username TEXT", "full_name TEXT"):
        connection.execute(f"ALTER TABLE workflow_jobs ADD COLUMN {column}")

    manager = WorkflowJobManager(
        SimpleNamespace(database_manager=SimpleNamespace(connection=connection))
    )
    return SimpleNamespace(
        database_manager=SimpleNamespace(connection=connection),
        workflow_job_manager=manager,
        bootstrap=SimpleNamespace(project_root=tmp_path),
    )


def _node(context, name="edge-1", token="secret-token"):
    store = NodeStore(context.database_manager.connection)
    store.save_remote(
        name,
        host="10.0.0.5",
        port=22,
        ssh_user="deploy",
        install_dir="~/.entropy-agent",
        server_url="https://entropy.example.com",
    )
    store.set_token(name, token_hash(token))
    return store


def _job(context, node="edge-1"):
    job = context.workflow_job_manager.create(
        execution_id=f"deploy_{uuid.uuid4().hex[:8]}",
        workflow="deploy",
        workspace=Path(f"node:{node}"),
        pid=0,
        user_id=1,
        username="admin",
        full_name="Administrator",
    )
    return job.require_id()


def test_agents_authenticate_by_token_hash(context) -> None:
    _node(context)
    dispatcher = NodeDispatcher(context)

    assert dispatcher.authenticate("secret-token")["name"] == "edge-1"
    assert dispatcher.authenticate("wrong") is None
    assert dispatcher.authenticate("") is None


def test_claim_report_and_finish(context) -> None:
    _node(context)
    dispatcher = NodeDispatcher(context)
    node = dispatcher.authenticate("secret-token")
    job_id = _job(context)
    dispatcher.enqueue(job_id, "edge-1", {"job_id": job_id, "definition": "{}"})

    assert dispatcher.claim(node, 0) == {"job_id": job_id, "definition": "{}"}
    assert dispatcher.claim(node, 0) is None

    dispatcher.report(
        node,
        job_id,
        {
            "events": [
                {
                    "type": "step.started",
                    "node_type": "step",
                    "node_name": "Build",
                    "created_at": "2026-10-20T10:00:00+00:00",
                }
            ],
            "log": "building\n",
            "state": "running",
        },
    )
    assert context.workflow_job_manager.get(job_id).state.value == "running"
    events = context.workflow_job_manager.events(job_id)
    assert events[0].event_type == "step.started"
    assert events[0].created_at.replace(tzinfo=timezone.utc).hour == 10
    assert (
        context.bootstrap.project_root / "tmp" / f"workflow-worker-{job_id}.log"
    ).read_text() == "building\n"

    dispatcher.report(node, job_id, {"state": "completed", "exit_code": 0, "final": True})
    assert context.workflow_job_manager.get(job_id).state.value == "completed"


def test_reports_are_limited_to_the_assigned_node(context) -> None:
    _node(context)
    _node(context, "edge-2", "other-token")
    dispatcher = NodeDispatcher(context)
    job_id = _job(context)
    dispatcher.enqueue(job_id, "edge-1", {})

    with pytest.raises(LookupError):
        dispatcher.report(dispatcher.authenticate("other-token"), job_id, {"state": "failed"})


def test_stop_cancels_pending_and_flags_claimed_runs(context) -> None:
    _node(context)
    dispatcher = NodeDispatcher(context)
    node = dispatcher.authenticate("secret-token")

    pending = _job(context)
    dispatcher.enqueue(pending, "edge-1", {})
    assert dispatcher.request_stop(pending)
    assert context.workflow_job_manager.get(pending).state.value == "cancelled"

    claimed = _job(context)
    dispatcher.enqueue(claimed, "edge-1", {"job_id": claimed})
    dispatcher.claim(node, 0)
    dispatcher.report(node, claimed, {"state": "starting"})
    dispatcher.request_stop(claimed)
    assert dispatcher.heartbeat(node, {"metrics": {}})["stop"] == [claimed]

    # A claim the agent never acknowledged is cancelled outright.
    lost = _job(context)
    dispatcher.enqueue(lost, "edge-1", {"job_id": lost})
    dispatcher.claim(node, 0)
    dispatcher.request_stop(lost)
    assert context.workflow_job_manager.get(lost).state.value == "cancelled"
    assert dispatcher.report(node, lost, {"state": "starting"})["stop"] is True

    assert not dispatcher.request_stop(999)


def test_runs_on_lost_or_removed_nodes_fail(context) -> None:
    store = _node(context)
    dispatcher = NodeDispatcher(context)
    job_id = _job(context)
    dispatcher.enqueue(job_id, "edge-1", {})

    # Seen recently: nothing happens.
    store.touch("edge-1")
    assert dispatcher.reconcile() == 0

    stale = (datetime.now(timezone.utc) - timedelta(minutes=10)).isoformat()
    context.database_manager.connection.execute(
        "UPDATE nodes SET last_seen_at = ? WHERE name = 'edge-1'", (stale,)
    )
    context.database_manager.connection.commit()
    assert dispatcher.reconcile() == 1
    assert context.workflow_job_manager.get(job_id).state.value == "failed"


def test_heartbeat_records_metrics(context) -> None:
    store = _node(context)
    dispatcher = NodeDispatcher(context)
    metrics = {
        "cpu": {"percent": 12.5, "count": 4},
        "memory": {"percent": 40.0},
        "disk": {"percent": 70.0},
        "load": [0.5, 0.4, 0.3],
    }
    dispatcher.heartbeat(
        dispatcher.authenticate("secret-token"), {"metrics": metrics, "version": "1"}
    )

    node = store.get("edge-1")
    assert node["last_metrics"]["cpu"]["percent"] == 12.5
    assert node["agent_version"] == "1"
    assert len(store.history("edge-1")) == 1


def test_runtime_bundle_is_deterministic_and_skips_web_assets(tmp_path: Path) -> None:
    root = tmp_path / "project"
    (root / "lib" / "assets" / "backgrounds").mkdir(parents=True)
    (root / "lib" / "assets" / "backgrounds" / "big.webm").write_bytes(b"x" * 1000)
    (root / "lib" / "agent").mkdir(parents=True)
    (root / "lib" / "agent" / "agent.py").write_text("print('hi')\n")
    (root / "lib" / "agent" / "__pycache__").mkdir()
    (root / "lib" / "agent" / "__pycache__" / "agent.cpython-39.pyc").write_bytes(b"x")
    (root / "core").mkdir()
    (root / "entropy.py").write_text("")

    first, digest = runtime_bundle(root, tmp_path / "cache-1")
    second, again = runtime_bundle(root, tmp_path / "cache-2")
    assert digest == again

    with tarfile.open(first) as archive:
        names = archive.getnames()
    assert "lib/agent/agent.py" in names
    assert not any("assets" in name or "__pycache__" in name for name in names)


def test_plugin_bundle_round_trips(tmp_path: Path) -> None:
    plugin = tmp_path / "hello"
    plugin.mkdir()
    (plugin / "plugin.json").write_text(json.dumps({"name": "hello"}))
    data, digest = plugin_bundle(plugin)

    assert plugin_bundle(plugin)[1] == digest
    with tarfile.open(fileobj=io.BytesIO(data)) as archive:
        assert archive.getnames() == ["plugin.json"]


def test_agent_requirements_leave_out_the_web_server() -> None:
    requirements = agent_requirements(Path(__file__).resolve().parents[2])
    names = requirements.lower()
    assert "fastapi" not in names and "uvicorn" not in names
    assert "rich" in names


def test_ssh_errors_are_explained_without_details() -> None:
    assert "Authentication failed" in _explain("nodeuser@host: Permission denied (password).")
    assert "host key changed" in _explain(
        "@@@ WARNING: REMOTE HOST IDENTIFICATION HAS CHANGED! @@@"
    )
    assert "refused" in _explain("ssh: connect to host x port 22: Connection refused")


@pytest.mark.parametrize(
    "changes",
    [
        {"name": "local"},
        {"name": "Bad Name"},
        {"host": "bad host"},
        {"port": 70000},
        {"ssh_user": "a b"},
        {"server_url": "ftp://x"},
        {"python": "pypy"},
        {"install_dir": "relative/dir"},
        {"install_dir": "~/../etc"},
        {"max_jobs": 0},
    ],
)
def test_setup_requests_are_validated(changes) -> None:
    values = dict(
        name="edge-1",
        host="10.0.0.5",
        port=22,
        ssh_user="deploy",
        server_url="https://entropy.example.com",
    )
    values.update(changes)
    with pytest.raises(ProvisionError):
        ProvisionRequest(**values).validate()


def test_setup_request_forgets_secrets() -> None:
    request = ProvisionRequest(
        name="edge-1",
        host="h",
        port=22,
        ssh_user="u",
        server_url="https://x",
        password="pw",
    )
    request.validate()
    request.forget_secrets()
    assert request.password is None and request.private_key is None and request.passphrase is None


def test_unacknowledged_claims_are_handed_out_again(context) -> None:
    _node(context)
    dispatcher = NodeDispatcher(context)
    node = dispatcher.authenticate("secret-token")
    job_id = _job(context)
    dispatcher.enqueue(job_id, "edge-1", {"job_id": job_id})
    assert dispatcher.claim(node, 0)["job_id"] == job_id

    # The response was lost: no report ever arrived.
    old = (datetime.now(timezone.utc) - timedelta(minutes=2)).isoformat()
    context.database_manager.connection.execute(
        "UPDATE node_jobs SET claimed_at = ?, updated_at = ? WHERE job_id = ?",
        (old, old, job_id),
    )
    context.database_manager.connection.commit()
    assert dispatcher.claim(node, 0)["job_id"] == job_id

    # Acknowledged claims stay with the agent.
    dispatcher.report(node, job_id, {"state": "starting"})
    assert context.workflow_job_manager.get(job_id).state.value == "starting"
    assert dispatcher.claim(node, 0) is None
