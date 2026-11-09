"""
sqlplus.invalid_objects_report checks only the schemas a release changes (from its
database context) or the ones named, instead of every schema it has credentials for.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any, List
from unittest.mock import MagicMock, patch

import pytest

from lib.plugins.arguments import PluginArguments
from resources.plugins.release.context_builder.analyzer import ReleaseAnalyzer
from resources.plugins.sqlplus.invalid_objects_report.exceptions import (
    InvalidObjectsReportPluginException,
)
from resources.plugins.sqlplus.invalid_objects_report.plugin import (
    _INVALID_MARKER,
    InvalidObjectsReportPlugin,
)
from resources.plugins.sqlplus.invalid_objects_report.resolver import (
    InvalidObjectsReportResolver as Resolver,
)

CONNECTION = {"IP": "db.local", "PORT": 1521, "SID": "orcl"}
# What ${entv:sit/schemas_*} gives: every schema the environment has.
CREDENTIALS = {
    name: {"username": name.lower(), "password": "p"}
    for name in ("APP1", "APP2", "HR_CORE", "HR_PAY", "BILLING")
}
PLAN = {
    "dir": "/release/DBScripts",
    "scripts": [],
    "execution_plan": {
        "applications": {
            "H01/App1": {"schema": "APP1", "calling_script": "a.sql"},
            "H02/App1": {"schema": "app1", "calling_script": "b.sql"},
            "Billing": {"schema": "BILLING", "calling_script": "c.sql"},
        }
    },
}


def test_plan_schemas_come_from_the_execution_plan_in_order() -> None:
    assert Resolver.plan_schemas(PLAN) == ["APP1", "app1", "BILLING"]
    assert Resolver.plan_schemas({**PLAN, "schemas": ["HR_PAY"]}) == ["HR_PAY"]
    assert Resolver.plan_schemas({"scripts": [], "execution_plan": None}) == []
    assert Resolver.plan_schemas(None) == []
    with pytest.raises(InvalidObjectsReportPluginException):
        Resolver.plan_schemas("not a context")


def test_select_matches_names_and_patterns_without_case() -> None:
    selected, missing, unmatched = Resolver.select(
        CREDENTIALS, ["app1", "APP1", "hr_*", "GHOST", "X*"]
    )
    assert list(selected) == ["APP1", "HR_CORE", "HR_PAY"]
    assert missing == ["GHOST"] and unmatched == ["X*"]


@pytest.mark.parametrize("value", [[""], [3], {"a": 1}])
def test_only_schemas_must_be_names(value) -> None:
    with pytest.raises(InvalidObjectsReportPluginException):
        Resolver.only_schemas(value)


def test_context_builder_lists_the_schemas_a_release_changes(tmp_path: Path) -> None:
    from lib.executor import LinuxExecutor

    plan = tmp_path / "DBScripts" / "execution_plan.yaml"
    plan.parent.mkdir()
    plan.write_text(
        "applications:\n"
        "  App1:\n    schema: APP1\n    calling_script: run.sql\n"
        "  App2:\n    schema: APP1\n    calling_script: run.sql\n"
        "  Hr:\n    schema: HR_PAY\n    calling_script: run.sql\n"
    )
    analyzer = ReleaseAnalyzer(
        filesystem=LinuxExecutor(),
        archive=MagicMock(),
        message=MagicMock(),
        log=MagicMock(),
        activity=MagicMock(),
    )

    database = analyzer._analyse_database(
        root=tmp_path,
        definition={
            "path": "DBScripts",
            "type": "directory",
            "execution_plan": {"names": ["execution_plan.yaml"]},
        },
    )

    assert database["schemas"] == ["APP1", "HR_PAY"]


# ----------------------------------------------------------------------
# The plugin
# ----------------------------------------------------------------------


def _run(tmp_path: Path, **arguments: Any):
    context = MagicMock()
    context.outputs = {}
    context.artifacts = {}
    context.workspace = tmp_path
    context.activity.return_value.__enter__ = lambda *_: None
    context.activity.return_value.__exit__ = lambda *_: None
    context.arguments = PluginArguments(
        {"connection": CONNECTION, "schemas": CREDENTIALS, **arguments}
    )
    checked: List[str] = []

    def execute(_sqlhome, execution) -> SimpleNamespace:
        checked.append(execution.schema)
        return SimpleNamespace(success=True, stdout=f"{_INVALID_MARKER}\n", stderr="")

    plugin = InvalidObjectsReportPlugin(context)
    with (
        patch(
            "resources.plugins.sqlplus.invalid_objects_report.plugin.SqlPlusExecutor"
        ) as executor,
        patch.object(InvalidObjectsReportPlugin, "_create_script", return_value=tmp_path / "s"),
        patch.object(InvalidObjectsReportPlugin, "_write_report", return_value=tmp_path / "r"),
    ):
        executor.return_value.execute.side_effect = execute
        result = plugin.execute()
    return result, checked


def test_without_a_selection_every_schema_is_checked(tmp_path) -> None:
    result, checked = _run(tmp_path)

    assert checked == list(CREDENTIALS)
    assert result.success and result.outputs["schemas"] == 5


def test_only_the_schemas_the_release_changes_are_checked(tmp_path) -> None:
    result, checked = _run(tmp_path, execution=PLAN)

    assert checked == ["APP1", "BILLING"]
    assert result.success
    assert result.outputs["checked_schemas"] == ["APP1", "BILLING"]


def test_named_schemas_are_added_to_the_release_ones(tmp_path) -> None:
    _, checked = _run(tmp_path, execution=PLAN, only_schemas=["HR_*"])

    assert checked == ["APP1", "BILLING", "HR_CORE", "HR_PAY"]


def test_a_release_without_database_changes_checks_nothing(tmp_path) -> None:
    result, checked = _run(tmp_path, execution={"scripts": [], "execution_plan": None})

    assert checked == []
    assert result.success and result.outputs["schemas"] == 0


def test_a_schema_without_credentials_is_an_error_in_the_report(tmp_path) -> None:
    result, checked = _run(tmp_path, only_schemas=["APP2", "PAYROLL"])

    assert checked == ["APP2"]
    assert not result.success
    assert result.outputs["checked_schemas"] == ["APP2", "PAYROLL"]
    assert result.errors == [
        {
            "schema": "PAYROLL",
            "type": "credentials",
            "message": (
                "Schema 'PAYROLL' is to be checked, but 'schemas' has no credentials for it."
            ),
        }
    ]
