"""
Jira exports into project tasks.

Reads the three dumps Jira produces:

- XML ("Export > XML", an RSS document of <item>s),
- CSV ("Export > CSV (all fields)"; repeated columns such as Comment,
  Attachment, Fix Version/s and Sprint are all read),
- JSON (REST API search results {"issues": [...]}, a list of issues or one).

Every issue becomes a task (the Jira key is kept as the task's external
reference, a new ENTASK-n key is given). Fix versions, sprints and epics
become task groups. Comments are kept with their author and date.
Attachments are kept as links to Jira: dumps hold no file contents.
Importing the same dump again updates the tasks it created.
"""

from __future__ import annotations

import csv
import html
import io
import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any, Dict, List, Optional, Sequence, Tuple
from xml.etree import ElementTree

from lib.tasks.store import TaskStore, normalize_type

MAX_ISSUES = 5000


class JiraImportError(ValueError):
    pass


@dataclass
class JiraIssue:
    key: str
    summary: str
    type: str = "issue"
    status: str = "todo"
    description: str = ""
    assignee: Dict[str, str] = field(default_factory=dict)
    reporter: str = ""
    created: Optional[str] = None
    due: Optional[str] = None
    comments: List[Dict[str, str]] = field(default_factory=list)
    attachments: List[Dict[str, Any]] = field(default_factory=list)
    # (kind, name): release (fix version), sprint, epic.
    groups: List[Tuple[str, str]] = field(default_factory=list)
    labels: List[str] = field(default_factory=list)
    epic_key: Optional[str] = None


# ----------------------------------------------------------------------
# Values
# ----------------------------------------------------------------------


def _due(value: Any) -> Optional[str]:
    """A Jira due date as YYYY-MM-DD."""

    parsed = parse_date(value) if value else None
    return parsed[:10] if parsed else None


def _import_status(current: str, incoming: str) -> Tuple[str, Optional[str]]:
    """Jira's status, kept within the task life cycle (closed -> reopened only)."""

    from lib.tasks.store import CLOSED, REOPENED

    if current == CLOSED and incoming != CLOSED:
        return REOPENED, "Reopened in Jira (import)."
    if current == REOPENED and incoming == "todo":
        return REOPENED, None
    return incoming, None

DONE = {
    "done",
    "closed",
    "resolved",
    "complete",
    "completed",
    "fixed",
    "released",
    "cancelled",
    "won't do",
    "rejected",
}
PROGRESS = {
    "in progress",
    "in review",
    "review",
    "in development",
    "in testing",
    "testing",
    "qa",
    "code review",
    "in qa",
    "blocked",
    "ready for review",
    "ready for test",
    "development",
}


def map_status(name: str, category: str = "") -> str:
    category = category.lower()
    if category in ("done",):
        return "done"
    if category in ("indeterminate", "in progress"):
        return "in_progress"
    text = name.strip().lower()
    if text in DONE:
        return "done"
    if text in PROGRESS or "progress" in text or "review" in text:
        return "in_progress"
    return "todo"


def map_type(name: str) -> str:
    text = name.strip().lower()
    aliases = {
        "": "issue",
        "sub-task": "task",
        "subtask": "task",
        "new feature": "story",
        "user story": "story",
        "enhancement": "improvement",
        "defect": "bug",
        "problem": "incident",
    }
    return aliases.get(text, normalize_type(text))


DATE_FORMATS = (
    "%d/%b/%y %I:%M %p",
    "%d/%b/%Y %I:%M %p",
    "%d/%b/%y %H:%M",
    "%d/%b/%Y %H:%M",
    "%Y-%m-%d %H:%M",
    "%Y-%m-%d %H:%M:%S",
    "%d/%m/%Y %H:%M",
    "%m/%d/%Y %H:%M",
    "%d/%b/%y",
    "%d/%b/%Y",
    "%Y-%m-%d",
)


def parse_date(value: Optional[str]) -> Optional[str]:
    """A Jira date in any export as 'YYYY-MM-DD HH:MM:SS' (UTC), like SQLite's datetime('now')."""

    if not value or not str(value).strip():
        return None
    text = str(value).strip()
    parsed: Optional[datetime] = None
    try:
        # 2024-01-02T10:00:00.000+0000 (REST) or ISO.
        parsed = datetime.fromisoformat(
            re.sub(r"([+-]\d{2})(\d{2})$", r"\1:\2", text.replace("Z", "+00:00"))
        )
    except ValueError:
        try:
            parsed = parsedate_to_datetime(text)  # RSS: Tue, 2 Jan 2024 10:00:00 +0000
        except (TypeError, ValueError, IndexError):
            for pattern in DATE_FORMATS:
                try:
                    parsed = datetime.strptime(text, pattern)
                    break
                except ValueError:
                    continue
    if parsed is None:
        return None
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
    return parsed.strftime("%Y-%m-%d %H:%M:%S")


def html_to_text(value: str) -> str:
    text = re.sub(r"(?i)<br\s*/?>", "\n", value or "")
    text = re.sub(r"(?i)</(p|div|li|h\d|tr)>", "\n", text)
    text = re.sub(r"(?i)<li[^>]*>", "- ", text)
    text = re.sub(r"<[^>]+>", "", text)
    text = html.unescape(text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def adf_to_text(value: Any) -> str:
    """Atlassian Document Format (Jira Cloud) or plain text."""

    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return "".join(adf_to_text(item) for item in value)
    if isinstance(value, dict):
        if value.get("type") == "text":
            return str(value.get("text", ""))
        if value.get("type") == "mention":
            return str((value.get("attrs") or {}).get("text", ""))
        if value.get("type") == "hardBreak":
            return "\n"
        inner = adf_to_text(value.get("content", []))
        if value.get("type") in ("paragraph", "heading", "listItem", "codeBlock", "blockquote"):
            return inner.rstrip("\n") + "\n"
        return inner
    return str(value)


def _person(value: Any) -> Dict[str, str]:
    if not value:
        return {}
    if isinstance(value, str):
        return {"name": value, "display": value}
    return {
        "name": str(value.get("name") or value.get("key") or value.get("accountId") or ""),
        "display": str(value.get("displayName") or value.get("name") or ""),
        "email": str(value.get("emailAddress") or ""),
    }


def _person_label(value: Dict[str, str]) -> str:
    return value.get("display") or value.get("name") or value.get("email") or ""


SPRINT_NAME = re.compile(r"name=([^,\]]+)")


def _sprint_names(value: Any) -> List[str]:
    if not value:
        return []
    items = value if isinstance(value, list) else [value]
    names = []
    for item in items:
        if isinstance(item, dict) and item.get("name"):
            names.append(str(item["name"]))
        elif isinstance(item, str):
            match = SPRINT_NAME.search(item)
            names.append(match.group(1) if match else item)
    return [name.strip() for name in names if name and name.strip()]


# ----------------------------------------------------------------------
# Formats
# ----------------------------------------------------------------------


def parse(data: bytes, filename: str = "") -> List[JiraIssue]:
    text = data.decode("utf-8-sig", errors="replace").lstrip()
    if not text:
        raise JiraImportError("The file is empty.")
    lower = filename.lower()
    if lower.endswith(".json") or text[:1] in "[{":
        issues = _from_json(text)
    elif lower.endswith(".xml") or text.startswith("<"):
        issues = _from_xml(text)
    else:
        issues = _from_csv(text)
    if not issues:
        raise JiraImportError("No Jira issues were found in the file.")
    if len(issues) > MAX_ISSUES:
        raise JiraImportError(
            f"The file has {len(issues)} issues; import at most {MAX_ISSUES} at a time."
        )
    return issues


def _from_json(text: str) -> List[JiraIssue]:
    try:
        document = json.loads(text)
    except ValueError as error:
        raise JiraImportError(f"The JSON file cannot be read: {error}") from None
    raw = document.get("issues", [document]) if isinstance(document, dict) else document
    issues = []
    for item in raw if isinstance(raw, list) else []:
        if not isinstance(item, dict):
            continue
        fields = item.get("fields") or item
        key = str(item.get("key") or fields.get("key") or "").strip()
        summary = str(fields.get("summary") or "").strip()
        if not key and not summary:
            continue
        status = fields.get("status") or {}
        status_name = status.get("name", "") if isinstance(status, dict) else str(status)
        category = (
            (status.get("statusCategory") or {}).get("key", "") if isinstance(status, dict) else ""
        )
        kind = fields.get("issuetype") or {}
        issue = JiraIssue(
            key=key,
            summary=summary or key,
            type=map_type(kind.get("name", "") if isinstance(kind, dict) else str(kind)),
            status=map_status(status_name, category),
            description=adf_to_text(fields.get("description")).strip(),
            assignee=_person(fields.get("assignee")),
            reporter=_person_label(_person(fields.get("reporter") or fields.get("creator"))),
            created=parse_date(fields.get("created")),
            due=_due(fields.get("duedate")),
            labels=[str(label) for label in fields.get("labels") or []],
        )
        comments = fields.get("comment") or {}
        for comment in (
            comments.get("comments", []) if isinstance(comments, dict) else comments
        ) or []:
            issue.comments.append(
                {
                    "author": _person_label(_person(comment.get("author"))) or "jira",
                    "body": adf_to_text(comment.get("body")).strip(),
                    "created": parse_date(comment.get("created")) or "",
                }
            )
        for attachment in fields.get("attachment") or []:
            issue.attachments.append(
                {
                    "filename": str(attachment.get("filename") or "attachment"),
                    "size": int(attachment.get("size") or 0),
                    "url": str(attachment.get("content") or attachment.get("self") or ""),
                    "author": _person_label(_person(attachment.get("author"))),
                    "created": parse_date(attachment.get("created")),
                    "mime": attachment.get("mimeType"),
                }
            )
        for version in fields.get("fixVersions") or []:
            if isinstance(version, dict) and version.get("name"):
                issue.groups.append(("release", str(version["name"])))
        for name, value in fields.items():
            if name == "sprint" or (
                name.startswith("customfield_")
                and isinstance(value, list)
                and value
                and "sprint" in json.dumps(value[0]).lower()
            ):
                issue.groups.extend(("sprint", sprint) for sprint in _sprint_names(value))
        parent = fields.get("parent") or {}
        parent_type = (
            ((parent.get("fields") or {}).get("issuetype") or {}).get("name", "")
            if isinstance(parent, dict)
            else ""
        )
        if isinstance(parent, dict) and parent.get("key") and parent_type.lower() == "epic":
            issue.epic_key = str(parent["key"])
        for name in ("epic", "Epic Link", "customfield_10014", "customfield_10008"):
            if isinstance(fields.get(name), str) and fields[name].strip():
                issue.epic_key = fields[name].strip()
        issues.append(issue)
    return issues


def _from_xml(text: str) -> List[JiraIssue]:
    try:
        root = ElementTree.fromstring(text.encode("utf-8"))
    except ElementTree.ParseError as error:
        raise JiraImportError(f"The XML file cannot be read: {error}") from None
    issues = []
    for item in root.iter("item"):

        def value(tag: str) -> str:
            element = item.find(tag)
            return (element.text or "").strip() if element is not None else ""

        key = value("key")
        summary = value("summary") or value("title")
        if not key and not summary:
            continue
        assignee = item.find("assignee")
        status = item.find("status")
        issue = JiraIssue(
            key=key,
            summary=summary or key,
            type=map_type(value("type")),
            status=map_status(
                value("status"), status.get("category", "") if status is not None else ""
            ),
            description=html_to_text(value("description")),
            assignee=(
                {
                    "name": assignee.get("username") or assignee.get("accountid") or "",
                    "display": (assignee.text or "").strip(),
                }
                if assignee is not None and (assignee.text or "").strip().lower() != "unassigned"
                else {}
            ),
            reporter=value("reporter"),
            created=parse_date(value("created")),
            due=_due(value("due")),
            labels=[
                (label.text or "").strip()
                for label in item.findall("labels/label")
                if (label.text or "").strip()
            ],
        )
        for comment in item.findall("comments/comment"):
            issue.comments.append(
                {
                    "author": comment.get("author") or "jira",
                    "body": html_to_text(comment.text or ""),
                    "created": parse_date(comment.get("created")) or "",
                }
            )
        for attachment in item.findall("attachments/attachment"):
            issue.attachments.append(
                {
                    "filename": attachment.get("name") or "attachment",
                    "size": int(attachment.get("size") or 0),
                    "url": "",
                    "author": attachment.get("author") or "",
                    "created": parse_date(attachment.get("created")),
                    "mime": None,
                }
            )
        for version in item.findall("fixVersion"):
            if (version.text or "").strip():
                issue.groups.append(("release", version.text.strip()))
        for custom in item.findall("customfields/customfield"):
            name = (custom.findtext("customfieldname") or "").strip().lower()
            values = [
                (entry.text or "").strip()
                for entry in custom.findall("customfieldvalues/customfieldvalue")
            ]
            if name == "sprint":
                issue.groups.extend(("sprint", sprint) for sprint in _sprint_names(values))
            elif name in ("epic link", "parent link") and values and values[0]:
                issue.epic_key = values[0]
        issues.append(issue)
    return issues


def _from_csv(text: str) -> List[JiraIssue]:
    try:
        dialect = csv.Sniffer().sniff(text[:4096], delimiters=",;\t")
        delimiter = dialect.delimiter
    except csv.Error:
        delimiter = ","
    rows = list(csv.reader(io.StringIO(text), delimiter=delimiter))
    if not rows:
        return []
    header = [cell.strip() for cell in rows[0]]
    lowered = [cell.lower() for cell in header]
    if "summary" not in lowered:
        raise JiraImportError(
            "The CSV file has no 'Summary' column; export it from Jira with all fields."
        )

    def all_of(row: Sequence[str], *names: str) -> List[str]:
        wanted = {name.lower() for name in names}
        return [
            row[index].strip()
            for index, name in enumerate(lowered)
            if name in wanted and index < len(row) and row[index].strip()
        ]

    def one(row: Sequence[str], *names: str) -> str:
        found = all_of(row, *names)
        return found[0] if found else ""

    issues = []
    for row in rows[1:]:
        if not any(cell.strip() for cell in row):
            continue
        key = one(row, "Issue key", "Key")
        summary = one(row, "Summary")
        if not key and not summary:
            continue
        assignee = one(row, "Assignee")
        issue = JiraIssue(
            key=key,
            summary=summary or key,
            type=map_type(one(row, "Issue Type", "Type")),
            status=map_status(one(row, "Status"), one(row, "Status Category")),
            description=one(row, "Description"),
            assignee=(
                {"name": one(row, "Assignee Id") or assignee, "display": assignee}
                if assignee
                else {}
            ),
            reporter=one(row, "Reporter"),
            created=parse_date(one(row, "Created")),
            due=_due(one(row, "Due Date", "Due date")),
            labels=all_of(row, "Labels"),
        )
        for entry in all_of(row, "Comment"):
            # "02/Jan/24 10:00 AM;author;body" (the body may hold ';').
            parts = entry.split(";", 2)
            if len(parts) == 3 and parse_date(parts[0]):
                issue.comments.append(
                    {
                        "author": parts[1] or "jira",
                        "body": parts[2].strip(),
                        "created": parse_date(parts[0]) or "",
                    }
                )
            else:
                issue.comments.append({"author": "jira", "body": entry, "created": ""})
        for entry in all_of(row, "Attachment", "Attachments"):
            # "02/Jan/24 10:00 AM;author;file.png;https://.../file.png"
            parts = entry.split(";")
            if len(parts) >= 4:
                issue.attachments.append(
                    {
                        "filename": parts[2],
                        "size": 0,
                        "url": ";".join(parts[3:]),
                        "author": parts[1],
                        "created": parse_date(parts[0]),
                        "mime": None,
                    }
                )
            else:
                issue.attachments.append(
                    {
                        "filename": entry.rsplit("/", 1)[-1],
                        "size": 0,
                        "url": entry,
                        "author": "",
                        "created": None,
                        "mime": None,
                    }
                )
        issue.groups.extend(
            ("release", name)
            for name in all_of(row, "Fix Version/s", "Fix versions", "Fix Version")
        )
        issue.groups.extend(("sprint", name) for name in all_of(row, "Sprint"))
        epic = one(row, "Custom field (Epic Link)", "Epic Link", "Parent", "Parent key")
        if epic and re.match(r"^[A-Z][A-Z0-9]+-\d+$", epic):
            issue.epic_key = epic
        issues.append(issue)
    return issues


# ----------------------------------------------------------------------
# Import
# ----------------------------------------------------------------------


def _member_for(person: Dict[str, str], members: List[Dict[str, Any]]) -> Optional[str]:
    if not person:
        return None
    candidates = {value.strip().lower() for value in person.values() if value and value.strip()}
    for member in members:
        for key in ("username", "email", "full_name"):
            if (member.get(key) or "").strip().lower() in candidates:
                return member["username"]
    return None


def import_issues(
    store: TaskStore,
    project_id: int,
    issues: List[JiraIssue],
    members: List[Dict[str, Any]],
    actor: str,
    *,
    group: Optional[str] = None,
    update_existing: bool = True,
) -> Dict[str, Any]:
    summary: Dict[str, Any] = {
        "created": 0,
        "updated": 0,
        "skipped": 0,
        "comments": 0,
        "attachments": 0,
        "groups": [],
        "types_added": [],
        "unassigned": [],
        "keys": [],
    }
    known_groups: Dict[Tuple[str, str], int] = {}

    def group_id(kind: str, name: str, external: Optional[str] = None) -> int:
        name = name.strip()[:120]
        cached = known_groups.get((kind, name.lower()))
        if cached:
            return cached
        existing = store.group_by_name(project_id, name)
        if existing is None:
            existing = store.create_group(
                project_id, name, kind, "Imported from Jira.", external, actor
            )
            summary["groups"].append(name)
        known_groups[(kind, name.lower())] = existing["id"]
        return existing["id"]

    epics = {issue.key: issue.summary for issue in issues if issue.type == "epic" and issue.key}
    new_types = sorted({issue.type for issue in issues})
    before = set(store.settings(project_id)["types"])
    store.add_types(project_id, new_types)
    summary["types_added"] = [name for name in new_types if name not in before]

    for issue in issues:
        groups = [group_id(kind, name) for kind, name in issue.groups]
        if issue.epic_key:
            title = epics.get(issue.epic_key)
            groups.append(
                group_id(
                    "epic", f"{issue.epic_key} {title}" if title else issue.epic_key, issue.epic_key
                )
            )
        if issue.type == "epic" and issue.key:
            groups.append(group_id("epic", f"{issue.key} {issue.summary}", issue.key))
        if group:
            groups.append(group_id("release", group))

        assignee = _member_for(issue.assignee, members)
        remarks = []
        if issue.assignee and not assignee:
            label = _person_label(issue.assignee)
            remarks.append(f"Jira assignee: {label}")
            if label not in summary["unassigned"]:
                summary["unassigned"].append(label)
        if issue.reporter:
            remarks.append(f"Jira reporter: {issue.reporter}")
        if issue.labels:
            remarks.append(f"Jira labels: {', '.join(issue.labels)}")

        existing = store.find_external(project_id, issue.key) if issue.key else None
        if existing and not update_existing:
            summary["skipped"] += 1
            continue
        title = issue.summary[:200]
        if existing:
            status, reason = _import_status(existing["status"], issue.status)
            values = {
                "title": title,
                "description": issue.description[:10000],
                "status": status,
                "type": issue.type,
                "assignee": assignee or existing["assignee"],
                "group_ids": sorted(set(existing["group_ids"]) | set(groups)),
            }
            if issue.due:
                values["due_date"] = issue.due
            store.update(existing["id"], values, actor, reason)
            task = existing
            summary["updated"] += 1
        else:
            task = store.create(
                project_id,
                title,
                issue.description[:10000],
                "\n".join(remarks)[:5000],
                assignee,
                None,
                actor,
                type=issue.type,
                external_ref=issue.key or None,
                status=issue.status,
                group_ids=groups,
                created_at=issue.created,
                due_date=issue.due,
            )
            summary["created"] += 1
        summary["keys"].append({"key": task["key"], "external_ref": issue.key})

        for comment in issue.comments:
            body = comment["body"][:5000]
            if body and not store.has_comment(task["id"], comment["author"], body):
                store.add_comment(
                    task["id"], comment["author"][:200], body, comment["created"] or None
                )
                summary["comments"] += 1
        known = {
            (item["filename"], item.get("url") or "") for item in store.attachments(task["id"])
        }
        for attachment in issue.attachments:
            if (attachment["filename"], attachment["url"] or "") in known:
                continue
            store.add_attachment(
                task["id"],
                attachment["filename"][:255],
                attachment.get("mime"),
                attachment["size"],
                attachment["author"] or actor,
                url=attachment["url"] or None,
                created_at=attachment.get("created"),
            )
            summary["attachments"] += 1
    return summary
