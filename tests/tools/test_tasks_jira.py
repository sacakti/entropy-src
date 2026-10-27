"""Task keys, types, groups, attachments and Jira imports."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from lib.database.connection import DatabaseConnection
from lib.tasks.jira import JiraImportError, import_issues, parse, parse_date
from lib.tasks.store import TaskStore, ensure_tasks_schema


@pytest.fixture()
def store(tmp_path: Path) -> TaskStore:
    connection = DatabaseConnection(tmp_path / "entropy.db")
    ensure_tasks_schema(connection)
    return TaskStore(connection)


def test_keys_are_unique_incremental_and_follow_the_prefix(store: TaskStore) -> None:
    first = store.create(1, "One", "", "", None, None, "admin")
    second = store.create(1, "Two", "", "", None, None, "admin", type="bug", external_ref="JIRA-7")
    other_project = store.create(2, "Elsewhere", "", "", None, None, "admin")
    assert (first["key"], second["key"], other_project["key"]) == (
        "ENTASK-01",
        "ENTASK-02",
        "ENTASK-01",
    )
    assert second["type"] == "bug" and second["external_ref"] == "JIRA-7"

    store.update_settings(1, "OPS", None)
    assert store.create(1, "Three", "", "", None, None, "admin")["key"] == "OPS-03"
    # Back to the first prefix: numbers keep going, keys are never reused.
    store.update_settings(1, "ENTASK", None)
    assert store.create(1, "Four", "", "", None, None, "admin")["key"] == "ENTASK-04"
    assert store.settings(1)["next_key"] == "ENTASK-05"


def test_existing_tasks_get_keys(tmp_path: Path) -> None:
    connection = DatabaseConnection(tmp_path / "old.db")
    connection.execute(
        "CREATE TABLE tasks (id INTEGER PRIMARY KEY AUTOINCREMENT, project_id INTEGER NOT NULL,"
        "title TEXT NOT NULL, description TEXT NOT NULL DEFAULT '', remarks TEXT NOT NULL DEFAULT '',"
        "status TEXT NOT NULL DEFAULT 'todo', assignee TEXT, creator TEXT NOT NULL, reminder_at TEXT,"
        "reminder_sent INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL DEFAULT (datetime('now')),"
        "updated_at TEXT NOT NULL DEFAULT (datetime('now')))"
    )
    for title in ("a", "b"):
        connection.execute("INSERT INTO tasks(project_id,title,creator) VALUES (1,?,'x')", (title,))
    ensure_tasks_schema(connection)
    store = TaskStore(connection)
    assert sorted(task["key"] for task in store.list(1)) == ["ENTASK-01", "ENTASK-02"]
    assert {task["type"] for task in store.list(1)} == {"issue"}
    assert store.create(1, "c", "", "", None, None, "x")["key"] == "ENTASK-03"


def test_groups_and_attachments(store: TaskStore) -> None:
    task = store.create(1, "Fix login", "", "", None, None, "admin")
    group = store.create_group(1, "Release 2.4", "release", "", "REL-24", "admin")
    store.add_to_group(group["id"], [task["id"]])
    assert store.get(task["id"])["group_ids"] == [group["id"]]
    assert store.groups(1)[0]["task_count"] == 1

    store.add_attachment(task["id"], "log.txt", "text/plain", 12, "admin", storage_name="x-log.txt")
    attachment = store.get(task["id"])["attachments"][0]
    assert attachment["filename"] == "log.txt" and "storage_name" not in attachment

    store.delete_group(group["id"])
    assert store.get(task["id"])["group_ids"] == []
    removed = store.delete(task["id"])
    assert removed[0]["storage_name"] == "x-log.txt" and store.get(task["id"]) is None


JIRA_XML = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="0.92"><channel><title>Jira</title>
<item>
  <title>[APP-1] Login fails</title><key id="1">APP-1</key><summary>Login fails</summary>
  <type id="1">Bug</type><status id="3" category="indeterminate">In Progress</status>
  <assignee username="writer">Will Writer</assignee><reporter username="pm">Pat PM</reporter>
  <created>Tue, 2 Jan 2024 10:00:00 +0000</created>
  <description>&lt;p&gt;Users see &lt;b&gt;500&lt;/b&gt;.&lt;/p&gt;</description>
  <fixVersion>Release 2.4</fixVersion>
  <comments><comment id="9" author="pm" created="Wed, 3 Jan 2024 09:00:00 +0000">&lt;p&gt;Any news?&lt;/p&gt;</comment></comments>
  <attachments><attachment id="5" name="trace.log" size="2048" author="pm" created="Wed, 3 Jan 2024 09:01:00 +0000"/></attachments>
  <customfields><customfield id="customfield_10014" key="com.pyxis.greenhopper.jira:gh-epic-link">
    <customfieldname>Epic Link</customfieldname><customfieldvalues><customfieldvalue>APP-9</customfieldvalue></customfieldvalues>
  </customfield></customfields>
</item>
<item><key>APP-9</key><summary>Authentication</summary><type>Epic</type><status>Open</status>
  <assignee username="-1">Unassigned</assignee></item>
</channel></rss>"""

JIRA_CSV = (
    "Summary,Issue key,Issue Type,Status,Assignee,Created,Fix Version/s,Fix Version/s,Comment,Comment,Attachment\n"
    '"Slow report",APP-2,Story,Done,someone@corp,02/Jan/24 10:00 AM,R1,R2,'
    '"03/Jan/24 9:00 AM;pm;First; with semicolon","04/Jan/24 9:00 AM;dev;Second",'
    '"03/Jan/24 9:01 AM;pm;shot.png;https://jira.example/secure/attachment/1/shot.png"\n'
)

JIRA_JSON = json.dumps(
    {
        "issues": [
            {
                "key": "APP-3",
                "fields": {
                    "summary": "Add audit log",
                    "issuetype": {"name": "Spike"},
                    "status": {"name": "Closed", "statusCategory": {"key": "done"}},
                    "assignee": {"displayName": "Will Writer", "emailAddress": "will@corp"},
                    "created": "2024-01-02T10:00:00.000+0100",
                    "description": {
                        "type": "doc",
                        "content": [
                            {
                                "type": "paragraph",
                                "content": [{"type": "text", "text": "Who did what"}],
                            }
                        ],
                    },
                    "comment": {
                        "comments": [
                            {
                                "author": {"displayName": "Pat PM"},
                                "body": "Ship it",
                                "created": "2024-01-03T10:00:00.000+0000",
                            }
                        ]
                    },
                    "attachment": [
                        {
                            "filename": "spec.pdf",
                            "size": 10,
                            "content": "https://jira.example/a/spec.pdf",
                        }
                    ],
                    "fixVersions": [{"name": "Release 2.4"}],
                    "customfield_10020": [{"id": 4, "name": "Sprint 7", "state": "closed"}],
                },
            }
        ]
    }
)

MEMBERS = [{"username": "writer", "full_name": "Will Writer", "email": "will@corp"}]


def test_parse_three_formats() -> None:
    xml = parse(JIRA_XML.encode(), "export.xml")
    assert [(issue.key, issue.type, issue.status) for issue in xml] == [
        ("APP-1", "bug", "in_progress"),
        ("APP-9", "epic", "todo"),
    ]
    assert xml[0].description == "Users see 500." and xml[0].epic_key == "APP-9"
    assert xml[0].comments[0] == {
        "author": "pm",
        "body": "Any news?",
        "created": "2024-01-03 09:00:00",
    }
    assert xml[0].groups == [("release", "Release 2.4")] and xml[1].assignee == {}

    rows = parse(JIRA_CSV.encode(), "export.csv")
    assert rows[0].status == "done" and rows[0].groups == [("release", "R1"), ("release", "R2")]
    assert rows[0].comments[0]["body"] == "First; with semicolon" and len(rows[0].comments) == 2
    assert rows[0].attachments[0]["url"].endswith("shot.png")

    rest = parse(JIRA_JSON.encode(), "search.json")
    assert (
        rest[0].type == "spike"
        and rest[0].status == "done"
        and rest[0].description == "Who did what"
    )
    assert ("sprint", "Sprint 7") in rest[0].groups and rest[0].created == "2024-01-02 09:00:00"

    with pytest.raises(JiraImportError):
        parse(b"Name,Value\nx,1\n", "other.csv")


def test_import_creates_then_updates(store: TaskStore) -> None:
    issues = parse(JIRA_XML.encode(), "export.xml") + parse(JIRA_JSON.encode(), "search.json")
    summary = import_issues(store, 1, issues, MEMBERS, "admin", group="Q1 intake")
    assert summary["created"] == 3 and summary["comments"] == 2 and summary["attachments"] == 2
    assert "spike" in summary["types_added"] and "spike" in store.settings(1)["types"]
    assert set(summary["groups"]) == {
        "Release 2.4",
        "APP-9 Authentication",
        "Q1 intake",
        "Sprint 7",
    }

    tasks = {task["external_ref"]: task for task in store.list(1)}
    login = tasks["APP-1"]
    assert (
        login["key"].startswith("ENTASK-")
        and login["assignee"] == "writer"
        and login["type"] == "bug"
    )
    assert tasks["APP-3"]["assignee"] == "writer"  # matched by e-mail
    names = {group["id"]: group["name"] for group in store.groups(1)}
    assert {names[group_id] for group_id in login["group_ids"]} == {
        "Release 2.4",
        "APP-9 Authentication",
        "Q1 intake",
    }
    assert login["attachments"][0]["filename"] == "trace.log"

    again = import_issues(store, 1, issues, MEMBERS, "admin")
    assert (again["created"], again["updated"], again["comments"], again["attachments"]) == (
        0,
        3,
        0,
        0,
    )
    assert len(store.list(1)) == 3


def test_dates() -> None:
    assert parse_date("02/Jan/24 1:05 PM") == "2024-01-02 13:05:00"
    assert parse_date("2024-01-02T10:00:00Z") == "2024-01-02 10:00:00"
    assert parse_date("nonsense") is None
