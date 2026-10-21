"""Workflow drafts: definitions saved with errors."""

from __future__ import annotations

from pathlib import Path

from lib.database.connection import DatabaseConnection
from lib.workflow.drafts import WorkflowDrafts


def _drafts(tmp_path: Path) -> WorkflowDrafts:
    return WorkflowDrafts(DatabaseConnection(tmp_path / "entropy.db"))


def test_save_list_and_delete(tmp_path: Path) -> None:
    drafts = _drafts(tmp_path)
    saved = drafts.save(
        draft_id=None,
        workflow=None,
        title="broken",
        format="yaml",
        definition="name: broken\nsteps: [",
        errors=["syntax"],
        user="alice",
    )

    assert drafts.get(saved["id"])["definition"] == "name: broken\nsteps: ["
    assert [item["title"] for item in drafts.list()] == ["broken"]
    assert "definition" not in drafts.list()[0]
    assert drafts.delete(saved["id"]) is True
    assert drafts.list() == []


def test_one_draft_per_workflow(tmp_path: Path) -> None:
    drafts = _drafts(tmp_path)
    first = drafts.save(
        draft_id=None,
        workflow="deploy",
        title="deploy",
        format="json",
        definition="{}",
        errors=["a"],
        user="alice",
    )
    second = drafts.save(
        draft_id=None,
        workflow="deploy",
        title="deploy",
        format="json",
        definition='{"name": "deploy"}',
        errors=[],
        user="bob",
    )

    assert second["id"] == first["id"]
    assert second["updated_by"] == "bob"
    drafts.delete_for_workflow("deploy")
    assert drafts.for_workflow("deploy") is None
