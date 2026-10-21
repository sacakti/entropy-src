"""
E-mail alerts when runs finish, set per workflow and per schedule.

A workflow's alert covers every run of it (manual, scheduled, CLI); a
schedule's alert covers that schedule's runs (of a workflow or a plugin).
Each says who to write to and for which outcomes.
"""

from __future__ import annotations

import json
import logging
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from lib.database.connection import DatabaseConnection

LOGGER = logging.getLogger("entropy.runs")
OUTCOMES = ("completed", "failed", "cancelled")
LOG_TAIL_LINES = 40


def ensure_alerts_schema(connection: DatabaseConnection) -> None:
    if getattr(connection, "_entropy_alerts_ready", False):
        return
    with connection.transaction():
        connection.execute("""
            CREATE TABLE IF NOT EXISTS run_alerts
            (
                kind        TEXT NOT NULL CHECK (kind IN ('workflow', 'schedule')),
                target      TEXT NOT NULL,
                emails      TEXT NOT NULL DEFAULT '[]',
                on_success  INTEGER NOT NULL DEFAULT 0,
                on_failure  INTEGER NOT NULL DEFAULT 1,
                on_cancel   INTEGER NOT NULL DEFAULT 0,
                updated_by  TEXT,
                updated_at  TEXT NOT NULL,
                PRIMARY KEY (kind, target)
            )
            """)
    connection._entropy_alerts_ready = True


def _payload(row: Any) -> Dict[str, Any]:
    return {
        "emails": json.loads(row["emails"] or "[]"),
        "on_success": bool(row["on_success"]),
        "on_failure": bool(row["on_failure"]),
        "on_cancel": bool(row["on_cancel"]),
        "updated_by": row["updated_by"],
        "updated_at": row["updated_at"],
    }


EMPTY = {
    "emails": [],
    "on_success": False,
    "on_failure": True,
    "on_cancel": False,
    "updated_by": None,
    "updated_at": None,
}


class RunAlerts:
    def __init__(self, connection: DatabaseConnection) -> None:
        ensure_alerts_schema(connection)
        self.connection = connection

    def get(self, kind: str, target: Any) -> Dict[str, Any]:
        row = self.connection.fetchone(
            "SELECT * FROM run_alerts WHERE kind = ? AND target = ?", (kind, str(target))
        )
        return _payload(row) if row else dict(EMPTY)

    def set(
        self,
        kind: str,
        target: Any,
        *,
        emails: List[str],
        on_success: bool,
        on_failure: bool,
        on_cancel: bool,
        user: str,
    ) -> Dict[str, Any]:
        from lib.system.mailer import addresses

        cleaned = addresses(emails)
        with self.connection.transaction():
            if not cleaned:
                self.connection.execute(
                    "DELETE FROM run_alerts WHERE kind = ? AND target = ?", (kind, str(target))
                )
            else:
                self.connection.execute(
                    "INSERT OR REPLACE INTO run_alerts (kind, target, emails, on_success,"
                    " on_failure, on_cancel, updated_by, updated_at)"
                    " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        kind,
                        str(target),
                        json.dumps(cleaned),
                        int(on_success),
                        int(on_failure),
                        int(on_cancel),
                        user,
                        datetime.now(timezone.utc).isoformat(),
                    ),
                )
        return self.get(kind, target)

    def forget(self, kind: str, target: Any) -> None:
        with self.connection.transaction():
            self.connection.execute(
                "DELETE FROM run_alerts WHERE kind = ? AND target = ?", (kind, str(target))
            )

    def recipients(self, outcome: Dict[str, Any]) -> List[str]:
        """Addresses to write to about a finished run."""

        flag = {"completed": "on_success", "failed": "on_failure", "cancelled": "on_cancel"}[
            outcome["state"]
        ]
        found: List[str] = []
        rules = []
        if outcome.get("kind") == "workflow":
            rules.append(self.get("workflow", outcome["target"]))
        if outcome.get("schedule_id"):
            rules.append(self.get("schedule", outcome["schedule_id"]))
        for rule in rules:
            if rule[flag]:
                found.extend(email for email in rule["emails"] if email not in found)
        return found


def _log_tail(path: Path) -> str:
    try:
        with path.open("r", encoding="utf-8", errors="replace") as handle:
            lines = handle.readlines()[-LOG_TAIL_LINES:]
    except OSError:
        return ""
    return "".join(lines).rstrip()


def compose(
    outcome: Dict[str, Any], public_url: str, project: Optional[str], log: str
) -> Dict[str, str]:
    """Subject and text of an alert e-mail."""

    from .outcomes import describe

    text = describe(outcome)
    subject = f"[Entropy] {text['title']} (run #{outcome['job_id']})"
    lines = [text["message"], ""]
    if project:
        lines.append(f"Project:     {project}")
    lines.append(f"Started by:  {outcome.get('username') or 'unknown'}")
    if outcome.get("schedule_name"):
        lines.append(f"Schedule:    {outcome['schedule_name']}")
    if outcome.get("node"):
        lines.append(f"Node:        {outcome['node']}")
    if public_url:
        lines.append(f"Open run:    {public_url.rstrip('/')}/#/runs/{outcome['job_id']}")
    if log and outcome["state"] != "completed":
        lines += ["", "Last lines of the output:", "", log]
    lines += [
        "",
        "--",
        "Sent by Entropy. Change these alerts in the workflow's or schedule's settings.",
    ]
    return {"subject": subject, "text": "\n".join(lines) + "\n"}


def send_alerts(context: Any, outcomes: List[Dict[str, Any]]) -> None:
    """E-mail whoever asked to hear about these runs (in the background)."""

    connection = context.database_manager.connection
    alerts = RunAlerts(connection)
    work = [(outcome, alerts.recipients(outcome)) for outcome in outcomes]
    work = [(outcome, to) for outcome, to in work if to]
    if not work:
        return

    from lib.authorization.projects import Projects, default_project_id
    from lib.system.settings import settings_for

    store = settings_for(context)
    smtp = store.values("smtp")
    if not smtp.get("enabled"):
        LOGGER.info("Run alerts not sent: e-mail is not set up.")
        return
    public_url = store.get("general")["public_url"]
    projects = Projects(connection)
    from .service import RunService

    service = RunService(context)
    messages = []
    for outcome, to in work:
        project = projects.get(outcome.get("project_id") or default_project_id(connection))
        log = _log_tail(service.log_path(outcome["job_id"]))
        messages.append(
            (to, compose(outcome, public_url, project["name"] if project else None, log))
        )

    def deliver() -> None:
        from lib.system.mailer import MailError, send_mail

        for to, message in messages:
            try:
                send_mail(smtp, to, message["subject"], message["text"])
            except MailError as exc:
                LOGGER.warning("Run alert to %s not sent: %s", ", ".join(to), exc)

    # SMTP can be slow; the background loop must not wait for it.
    threading.Thread(target=deliver, name="entropy-alerts", daemon=True).start()
