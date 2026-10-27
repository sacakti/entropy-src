"""Release traceability workbook: data sheets, filters and pivot tables."""

from __future__ import annotations

import zipfile
from pathlib import Path

from lib.releases.report import build_workbook


def _release(release_id: int, tasks):
    return {
        "id": release_id, "name": f"Payments {release_id}", "version": "1.0", "environment": "SIT",
        "stage": "task_queue", "workflow_name": "deploy", "workflow_job_id": 7, "workflow_state": "completed",
        "description": "", "tags": ["urgent"], "created_by": "admin", "created_at": "2026-10-01 10:00:00",
        "updated_at": "2026-10-02 10:00:00", "tasks": tasks,
    }


def _task(key, status, assignee=None, group=None, attachments=0):
    return {
        "id": int(key.split("-")[1]), "key": key, "title": f"Task {key}", "description": "Details",
        "status": status, "assignee": assignee, "assigned_by": "pm" if assignee else None,
        "assigned_at": "2026-10-01 11:00:00" if assignee else None, "external_ref": "INC-1",
        "remarks": "Note", "due_date": None, "group_names": group, "attachment_count": attachments,
        "comments": [{"author": "pm", "body": "Go", "created_at": "2026-10-01 12:00:00"}],
    }


def test_workbook_has_formatted_sheets_and_pivots(tmp_path: Path) -> None:
    releases = [
        _release(1, [_task("ENTASK-01", "done", "alice", "Sprint 1", 2), _task("ENTASK-02", "todo")]),
        _release(2, [_task("ENTASK-03", "reopened", "bob", "Sprint 1")]),
    ]
    promotions = [{"promotion_number": "HANDOFF-000001", "target_environment": "UAT", "status": "completed",
                   "created_at": "2026-10-03 09:00:00", "releases": [{"id": 1}]}]
    path = tmp_path / "out.xlsx"
    build_workbook(path, "Default", releases, promotions, "Admin")
    with zipfile.ZipFile(path) as archive:
        names = set(archive.namelist())
        workbook = archive.read("xl/workbook.xml").decode()
        tasks = archive.read("xl/worksheets/sheet3.xml").decode()
        releases_xml = archive.read("xl/worksheets/sheet2.xml").decode()
        cache = archive.read("xl/pivotCache/pivotCacheDefinition1.xml").decode()
    assert {"xl/pivotTables/pivotTable1.xml", "xl/pivotTables/pivotTable3.xml",
            "xl/pivotCache/pivotCacheRecords1.xml"} <= names
    assert 'name="Summary"' in workbook and 'name="PivotData" sheetId="4" state="hidden"' in workbook
    assert "<autoFilter" in tasks and "ENTASK-01" in tasks and "by pm on 2026-10-01 11:00" in tasks
    assert ">Yes<" in tasks and ">No<" in tasks and "HANDOFF-000001 → UAT" in releases_xml
    assert '<s v="Reopened"/>' in cache and '<s v="(No group)"/>' in cache
