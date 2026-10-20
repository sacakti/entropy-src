"""
Main-node side of remote execution: queue runs for nodes, authenticate
agents, hand out runs, and record the events, output and state agents
report back.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from lib.database.connection import DatabaseConnection
from lib.runs.nodes import NodeStore
from lib.runs.store import ensure_run_schema, utcnow

# A remote run whose node has not been heard from for this long fails.
NODE_LOST_AFTER = timedelta(minutes=5)

# Agents acknowledge a claim at once. One never acknowledged was answered
# to a connection that is gone (e.g. an agent restarted mid long-poll), so
# the run is handed out again.
CLAIM_LEASE = timedelta(seconds=15)

EVENT_FIELDS = ("source", "level", "message", "node_type", "node_id", "node_name")


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _parse(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


class NodeDispatcher:
    """Node job queue and agent reports."""

    def __init__(self, context: Any) -> None:
        self._context = context
        self.connection: DatabaseConnection = context.database_manager.connection
        ensure_run_schema(self.connection)
        self.nodes = NodeStore(self.connection)

    # ------------------------------------------------------------------
    # Agents
    # ------------------------------------------------------------------

    def authenticate(self, token: str) -> Optional[Dict[str, Any]]:
        if not token or len(token) > 200:
            return None
        return self.nodes.by_token_hash(token_hash(token))

    def heartbeat(self, node: Dict[str, Any], payload: Dict[str, Any]) -> Dict[str, Any]:
        metrics = payload.get("metrics") or {}
        info = payload.get("info") or {}
        self.nodes.record_heartbeat(node["name"], metrics, info, str(payload.get("version") or ""))

        # Agents may omit a metric; the sample is then skipped.
        with contextlib.suppress(KeyError, IndexError, TypeError):
            self.nodes.add_sample(node["name"], metrics)

        rows = self.connection.fetchall(
            "SELECT job_id FROM node_jobs"
            " WHERE node = ? AND status = 'claimed' AND stop_requested = 1",
            (node["name"],),
        )
        return {"stop": [row["job_id"] for row in rows], "max_jobs": node.get("max_jobs") or 2}

    def claim(self, node: Dict[str, Any], wait: float) -> Optional[Dict[str, Any]]:
        """Hand the oldest pending run to the agent, waiting up to `wait` seconds."""

        deadline = time.monotonic() + max(0.0, min(wait, 30.0))
        while True:
            self._requeue_unacknowledged(node["name"])
            if node.get("enabled", True):
                with self.connection.transaction():
                    row = self.connection.fetchone(
                        "SELECT job_id, spec FROM node_jobs"
                        " WHERE node = ? AND status = 'pending' ORDER BY job_id LIMIT 1",
                        (node["name"],),
                    )
                    if row is not None:
                        now = utcnow()
                        self.connection.execute(
                            "UPDATE node_jobs"
                            " SET status = 'claimed', claimed_at = ?, updated_at = ?"
                            " WHERE job_id = ? AND status = 'pending'",
                            (now, now, row["job_id"]),
                        )
                        return json.loads(row["spec"])
            if time.monotonic() >= deadline:
                return None
            time.sleep(1)

    def _requeue_unacknowledged(self, node: str) -> None:
        cutoff = (datetime.now(timezone.utc) - CLAIM_LEASE).isoformat()
        with self.connection.transaction():
            self.connection.execute(
                """
                UPDATE node_jobs SET status = 'pending', claimed_at = NULL
                WHERE node = ? AND status = 'claimed' AND stop_requested = 0
                  AND claimed_at < ? AND updated_at = claimed_at
                """,
                (node, cutoff),
            )

    def _owned(self, node: Dict[str, Any], job_id: int) -> Dict[str, Any]:
        row = self.connection.fetchone(
            "SELECT * FROM node_jobs WHERE job_id = ? AND node = ?",
            (job_id, node["name"]),
        )
        if row is None:
            raise LookupError(f"Run #{job_id} is not assigned to node '{node['name']}'.")
        return dict(row)

    def report(self, node: Dict[str, Any], job_id: int, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Record events, console output and state reported for a run."""

        record = self._owned(node, job_id)
        jobs = self._context.workflow_job_manager
        job = jobs.get(job_id)

        # Any report acknowledges the claim.
        with self.connection.transaction():
            self.connection.execute(
                "UPDATE node_jobs SET updated_at = ? WHERE job_id = ?",
                (utcnow(), job_id),
            )

        events = payload.get("events") or []
        if events:
            self._insert_events(job_id, job.execution_id, events)

        log = payload.get("log") or ""
        if log:
            path = (
                Path(self._context.bootstrap.project_root) / "tmp" / f"workflow-worker-{job_id}.log"
            )
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("a", encoding="utf-8") as handle:
                handle.write(log)

        self._apply_state(job_id, str(payload.get("state") or ""), payload.get("exit_code"))

        if payload.get("final"):
            with self.connection.transaction():
                self.connection.execute(
                    "UPDATE node_jobs SET status = 'finished', updated_at = ? WHERE job_id = ?",
                    (utcnow(), job_id),
                )
            # A run that ended without a final state is a failure.
            current = jobs.get(job_id)
            if current.state.value not in ("completed", "failed", "cancelled"):
                jobs.fail(job_id, 1)

        # Also stop runs cancelled before the agent acknowledged them.
        stop = bool(record["stop_requested"]) or jobs.get(job_id).state.value == "cancelled"
        return {"stop": stop}

    def _insert_events(self, job_id: int, execution_id: str, events: List[Dict[str, Any]]) -> None:
        with self.connection.transaction():
            for event in events[:2000]:
                created = _parse(event.get("created_at")) or datetime.now(timezone.utc)
                payload = event.get("payload")
                self.connection.execute(
                    """
                    INSERT INTO workflow_events
                    (job_id, execution_id, event_type, source, level, message,
                     node_type, node_id, node_name, payload, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        job_id,
                        execution_id,
                        str(event.get("type") or "message")[:64],
                        *[
                            (str(event[field])[:20000] if event.get(field) is not None else None)
                            for field in EVENT_FIELDS
                        ],
                        json.dumps(payload) if payload is not None else None,
                        # Same format SQLite's datetime('now') writes.
                        created.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
                    ),
                )

    def _apply_state(self, job_id: int, state: str, exit_code: Any) -> None:
        jobs = self._context.workflow_job_manager
        current = jobs.get(job_id).state.value
        if current in ("completed", "failed", "cancelled"):
            return

        try:
            if state in ("starting", "running", "paused") and current == "queued":
                jobs.start(job_id)
                current = "starting"
            if state in ("running", "paused") and current == "starting":
                jobs.running(job_id)
            if state == "completed":
                jobs.complete(job_id, int(exit_code or 0))
            elif state == "failed":
                jobs.fail(job_id, int(exit_code if exit_code is not None else 1))
            elif state == "cancelled":
                jobs.cancel(job_id, int(exit_code if exit_code is not None else 130))
        except Exception:  # noqa: BLE001 - an out-of-order report must not fail the request
            pass

    # ------------------------------------------------------------------
    # Main node
    # ------------------------------------------------------------------

    def enqueue(self, job_id: int, node: str, spec: Dict[str, Any]) -> None:
        now = utcnow()
        with self.connection.transaction():
            self.connection.execute(
                "INSERT INTO node_jobs (job_id, node, spec, status, created_at, updated_at)"
                " VALUES (?, ?, ?, 'pending', ?, ?)",
                (job_id, node, json.dumps(spec), now, now),
            )

    def request_stop(self, job_id: int) -> bool:
        """
        Ask the node to stop a run. A run no agent claimed yet is
        cancelled at once. Returns False when it is not a node run.
        """

        row = self.connection.fetchone(
            "SELECT status, claimed_at, updated_at FROM node_jobs WHERE job_id = ?",
            (job_id,),
        )
        if row is None:
            return False

        unacknowledged = row["status"] == "claimed" and row["updated_at"] == row["claimed_at"]
        if row["status"] == "pending" or unacknowledged:
            with self.connection.transaction():
                self.connection.execute(
                    "UPDATE node_jobs SET status = 'finished', updated_at = ? WHERE job_id = ?",
                    (utcnow(), job_id),
                )
            self._context.workflow_job_manager.cancel(job_id)
        else:
            with self.connection.transaction():
                self.connection.execute(
                    "UPDATE node_jobs SET stop_requested = 1, updated_at = ? WHERE job_id = ?",
                    (utcnow(), job_id),
                )
        return True

    def reconcile(self) -> int:
        """Fail runs on nodes that disappeared or were removed."""

        now = datetime.now(timezone.utc)
        rows = self.connection.fetchall(
            "SELECT j.job_id, j.node, j.status, n.last_seen_at, n.name AS known"
            " FROM node_jobs j LEFT JOIN nodes n ON n.name = j.node"
            " WHERE j.status != 'finished'"
        )
        jobs = self._context.workflow_job_manager
        fixed = 0

        for row in rows:
            seen = _parse(row["last_seen_at"])
            lost = row["known"] is None or seen is None or now - seen > NODE_LOST_AFTER
            if not lost:
                continue

            message = (
                f"Node '{row['node']}' was removed."
                if row["known"] is None
                else f"Node '{row['node']}' has not reported for "
                f"{int(NODE_LOST_AFTER.total_seconds() // 60)} minutes."
            )
            try:
                job = jobs.get(row["job_id"])
                jobs.event(
                    job_id=row["job_id"],
                    execution_id=job.execution_id,
                    event_type="message",
                    source="entropy.nodes",
                    level="error",
                    message=message,
                )
                if job.state.value not in ("completed", "failed", "cancelled"):
                    jobs.fail(row["job_id"], 1)
            except Exception:  # noqa: BLE001 - keep reconciling the rest
                pass

            with self.connection.transaction():
                self.connection.execute(
                    "UPDATE node_jobs SET status = 'finished', updated_at = ? WHERE job_id = ?",
                    (utcnow(), row["job_id"]),
                )
            fixed += 1

        return fixed
