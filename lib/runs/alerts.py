"""
E-mail alerts when runs finish, set per workflow and per schedule.

A workflow's alert covers every run of it (manual, scheduled, CLI); a
schedule's alert covers that schedule's runs (of a workflow or a plugin).
Each says who to write to and for which outcomes.
"""

from __future__ import annotations

import json
import html
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
                subject_template TEXT NOT NULL DEFAULT '',
                body_template TEXT NOT NULL DEFAULT '',
                updated_by  TEXT,
                updated_at  TEXT NOT NULL,
                PRIMARY KEY (kind, target)
            )
            """)
        columns = {row["name"] for row in connection.fetchall("PRAGMA table_info(run_alerts)")}
        if "subject_template" not in columns:
            connection.execute("ALTER TABLE run_alerts ADD COLUMN subject_template TEXT NOT NULL DEFAULT ''")
        if "body_template" not in columns:
            connection.execute("ALTER TABLE run_alerts ADD COLUMN body_template TEXT NOT NULL DEFAULT ''")
    connection._entropy_alerts_ready = True


def _payload(row: Any) -> Dict[str, Any]:
    return {
        "emails": json.loads(row["emails"] or "[]"),
        "on_success": bool(row["on_success"]),
        "on_failure": bool(row["on_failure"]),
        "on_cancel": bool(row["on_cancel"]),
        "subject_template": row["subject_template"] or "",
        "body_template": row["body_template"] or "",
        "updated_by": row["updated_by"],
        "updated_at": row["updated_at"],
    }


EMPTY = {
    "emails": [],
    "on_success": False,
    "on_failure": True,
    "on_cancel": False,
    "subject_template": "",
    "body_template": "",
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
        subject_template: str = "",
        body_template: str = "",
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
                    " on_failure, on_cancel, subject_template, body_template, updated_by, updated_at)"
                    " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        kind,
                        str(target),
                        json.dumps(cleaned),
                        int(on_success),
                        int(on_failure),
                        int(on_cancel),
                        str(subject_template)[:998],
                        str(body_template)[:20000],
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
    outcome: Dict[str, Any], public_url: str, project: Optional[str], log: str,
    subject_template: str = "", body_template: str = "",
) -> Dict[str, str]:
    """Subject and text of an alert e-mail."""

    from .outcomes import describe

    text = describe(outcome)
    run_url = f"{public_url.rstrip('/')}/#/runs/{outcome['job_id']}" if public_url else ""
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
    default_body = "\n".join(lines) + "\n"
    values = {
        "status": outcome["state"], "title": text["title"], "run_id": str(outcome["job_id"]),
        "workflow": str(outcome.get("target") or ""), "schedule": str(outcome.get("schedule_name") or ""),
        "project": str(project or ""), "started_by": str(outcome.get("username") or "unknown"),
        "node": str(outcome.get("node") or ""), "run_url": run_url,
        "message": text["message"], "log": log,
    }
    def expand(template: str) -> str:
        for key, value in values.items():
            template = template.replace("{" + key + "}", value)
        return template
    subject = expand(subject_template).replace("\r", " ").replace("\n", " ").strip() if subject_template else f"[Entropy] {text['title']} (run #{outcome['job_id']})"
    body = expand(body_template) if body_template else default_body
    paragraphs = "".join(
        f"<p>{html.escape(part).replace(chr(10), '<br>')}</p>"
        for part in body.strip().split("\n\n") if part.strip()
    )
    badge_color = {"completed": "#16845b", "failed": "#c43d4b", "cancelled": "#a06c13"}.get(outcome["state"], "#526174")
    rich = (
        '<!doctype html><html><body style="margin:0;background:#f3f5f8;font-family:Arial,sans-serif;color:#182230">'
        '<div style="max-width:640px;margin:24px auto;background:#fff;border:1px solid #dce2ea;border-radius:12px;overflow:hidden">'
        '<div style="padding:22px 26px;background:#182230;color:#fff"><div style="font-size:12px;opacity:.75">ENTROPY RUN UPDATE</div>'
        f'<h1 style="font-size:21px;margin:10px 0 0">{html.escape(text["title"])}</h1></div>'
        f'<div style="padding:22px 26px"><span style="display:inline-block;background:{badge_color};color:#fff;border-radius:999px;padding:6px 12px;font-size:12px;font-weight:bold">{html.escape(outcome["state"].upper())}</span>'
        f'{paragraphs}<table style="border-collapse:collapse;width:100%;margin-top:20px;font-size:13px">'
        + "".join(f'<tr><td style="padding:8px;border-bottom:1px solid #e8ecf1;color:#667085">{html.escape(label)}</td><td style="padding:8px;border-bottom:1px solid #e8ecf1">{html.escape(value)}</td></tr>' for label, value in (("Run", str(outcome["job_id"])), ("Project", project or "—"), ("Started by", outcome.get("username") or "unknown"), ("Schedule", outcome.get("schedule_name") or "—"), ("Node", outcome.get("node") or "—")))
        + "</table>"
        + (f'<p style="margin-top:22px"><a href="{html.escape(run_url, quote=True)}" style="display:inline-block;background:#4361ee;color:#fff;text-decoration:none;padding:10px 16px;border-radius:7px">View run</a></p>' if run_url else "")
        + '</div><div style="padding:14px 26px;background:#f8fafc;color:#667085;font-size:11px">Sent by Entropy run alerts.</div></div></body></html>'
    )
    return {"subject": subject, "text": body, "html": rich}


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
        # Schedule content overrides workflow content for scheduled runs.
        rules = [alerts.get("schedule", outcome["schedule_id"])] if outcome.get("schedule_id") else []
        if outcome.get("kind") == "workflow":
            rules.append(alerts.get("workflow", outcome["target"]))
        rule = next((item for item in rules if item.get("subject_template") or item.get("body_template")), {})
        messages.append((to, compose(outcome, public_url, project["name"] if project else None, log,
                                     rule.get("subject_template", ""), rule.get("body_template", ""))))

    def deliver() -> None:
        from lib.system.mailer import MailError, send_mail

        for to, message in messages:
            try:
                send_mail(smtp, to, message["subject"], message["text"], message["html"])
            except MailError as exc:
                LOGGER.warning("Run alert to %s not sent: %s", ", ".join(to), exc)

    # SMTP can be slow; the background loop must not wait for it.
    threading.Thread(target=deliver, name="entropy-alerts", daemon=True).start()
