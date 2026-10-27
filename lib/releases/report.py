"""Release traceability as a formatted Excel workbook."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List

from lib.reports.xlsx import Pivot, Sheet, Summary, write_workbook

STAGES = {
    "workflow_queue": "Workflow queue",
    "workflow_done": "Workflow done",
    "task_queue": "Task queue",
    "completed": "Completed",
}
TASK_STATUSES = {"todo": "Open", "in_progress": "In progress", "done": "Closed", "reopened": "Reopened"}


def release_label(release: Dict[str, Any]) -> str:
    return f"{release['name']} {release['version']}".strip() if release.get("version") else release["name"]


def task_status(value: str) -> str:
    return TASK_STATUSES.get(value, value.replace("_", " ").title())


def assigned(task: Dict[str, Any]) -> str:
    if not task.get("assignee"):
        return ""
    parts = []
    if task.get("assigned_by"):
        parts.append(f"by {task['assigned_by']}")
    if task.get("assigned_at"):
        parts.append(f"on {str(task['assigned_at'])[:16]}")
    return " ".join(parts) or "Yes"


def comments(task: Dict[str, Any]) -> str:
    return "\n".join(
        f"{item['author']} ({str(item['created_at'])[:16]}): {item['body']}" for item in task.get("comments") or []
    )


def task_rows(releases: Iterable[Dict[str, Any]]) -> List[List[str]]:
    """ID, name, description, status, release, group, assignee, assigned, comments,
    attachments, external reference, remarks, due date."""

    rows = []
    for release in releases:
        for task in release["tasks"]:
            rows.append([
                task.get("key") or f"#{task['id']}",
                task["title"],
                task.get("description") or "",
                task_status(task["status"]),
                release_label(release),
                task.get("group_names") or "",
                task.get("assignee") or "Unassigned",
                assigned(task),
                comments(task),
                "Yes" if task.get("attachment_count") else "No",
                task.get("external_ref") or "",
                task.get("remarks") or "",
                task.get("due_date") or "",
            ])
    return rows


TASK_HEADER = ["ID", "Name", "Description", "Status", "Release", "Group", "Assignee", "Assigned",
               "Comments", "Attachments", "External ref no", "Remarks", "Due date"]


def build_workbook(path: Path, project: str, releases: List[Dict[str, Any]],
                   promotions: List[Dict[str, Any]], generated_by: str) -> None:
    stamp = datetime.now(timezone.utc).strftime("%d %b %Y %H:%M UTC")
    note = f"{project} · {len(releases)} release(s) · generated {stamp} by {generated_by}"

    release_rows = []
    for release in releases:
        history = [
            f"{item['promotion_number']} → {item['target_environment']} "
            f"({(item.get('workflow_state') or item['status']).replace('_', ' ')}, {str(item['created_at'])[:16]})"
            for item in promotions if any(entry["id"] == release["id"] for entry in item["releases"])
        ]
        closed = sum(1 for task in release["tasks"] if task["status"] == "done")
        run = ""
        if release.get("workflow_job_id"):
            run = f"#{release['workflow_job_id']} ({(release.get('workflow_state') or 'unknown').replace('_', ' ')})"
        release_rows.append([
            str(release["id"]), release["name"], release.get("version") or "",
            release.get("environment") or "", STAGES.get(release["stage"], release["stage"]),
            release["workflow_name"], run or "Not started", str(len(release["tasks"])),
            f"{closed}/{len(release['tasks'])}", "\n".join(history), ", ".join(release.get("tags") or []),
            release.get("description") or "", release["created_by"], str(release["created_at"])[:16],
            str(release["updated_at"])[:16],
        ])

    tasks = task_rows(releases)
    task_widths = [13, 32, 48, 12, 22, 20, 16, 24, 48, 12, 16, 32, 12]
    pivot_data = Sheet(
        "PivotData",
        ["ID", "Release", "Group", "Assignee", "Status"],
        [[row[0], row[4], row[5] or "(No group)", row[6], row[3]] for row in tasks],
    )
    order = tuple(TASK_STATUSES.values())
    summary = Summary(
        "Summary",
        pivot_data,
        [
            Pivot("Tasks by group and status", "Group", "Status", order),
            Pivot("Tasks by assignee and status", "Assignee", "Status", order),
            Pivot("Tasks by release and status", "Release", "Status", order),
        ],
        title="Release summary",
        note=note,
        counted="ID",
    )
    write_workbook(
        path,
        [
            Sheet("Releases",
                  ["Release ID", "Release", "Version", "Environment", "Stage", "Workflow", "Workflow run",
                   "Tasks", "Closed tasks", "Promotion history", "Tags", "Description", "Created by",
                   "Created", "Updated"],
                  release_rows, title="Releases", note=note,
                  widths=[11, 26, 11, 16, 16, 24, 20, 8, 12, 40, 18, 40, 14, 17, 17]),
            Sheet("Tasks", TASK_HEADER, tasks, title="Release tasks", note=note, widths=[float(w) for w in task_widths]),
        ],
        summary if tasks else None,
    )
