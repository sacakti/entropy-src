"""
Tests for consolidate.db_scripts: the combined plan, and the plugin over real
release packages, resolved by the real sqlplus.generic resolver.
"""

from __future__ import annotations

import json
import zipfile
from contextlib import nullcontext
from pathlib import Path
from typing import Any, Dict, List
from unittest.mock import Mock

import pytest
import yaml

from lib.executor import LinuxExecutor
from lib.plugins import contract
from lib.plugins.arguments import PluginArguments
from resources.plugins.consolidate.db_scripts.exceptions import ConsolidationDefinitionError
from resources.plugins.consolidate.db_scripts.planner import parse_plan
from resources.plugins.consolidate.db_scripts.plugin import ConsolidateDbScriptsPlugin
from resources.plugins.sqlplus.generic.resolver import SqlPlusResolver

PLUGIN_DIRECTORY = (
    Path(__file__).resolve().parents[3] / "resources" / "plugins" / "consolidate" / "db_scripts"
)


def plan(**applications: str) -> str:
    return yaml.safe_dump(
        {
            "applications": {
                name: {"schema": schema, "calling_script": f"{name}_call.sql"}
                for name, schema in applications.items()
            }
        },
        sort_keys=False,
    )


def _folder(path: Path, files: Dict[str, str]) -> Path:
    for name, content in files.items():
        target = path / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content)
    return path


def _zip(path: Path, files: Dict[str, str]) -> Path:
    with zipfile.ZipFile(path, "w") as archive:
        for name, content in files.items():
            archive.writestr(name, content)
    return path


# ----------------------------------------------------------------------
# Plans
# ----------------------------------------------------------------------


@pytest.mark.parametrize(
    ("value", "message"),
    [
        ({}, "'applications'"),
        ("text", "'applications'"),
        ({"applications": {}}, "'applications'"),
        ({"applications": {"A": "x"}}, "must be a mapping"),
        ({"applications": {"A": {"calling_script": "a.sql"}}}, "schema is missing"),
        ({"applications": {"A": {"schema": "S"}}}, "calling script is missing"),
        ({"applications": {"../up": {"schema": "S", "calling_script": "a.sql"}}}, "folder under"),
        ({"applications": {"..": {"schema": "S", "calling_script": "a.sql"}}}, "folder under"),
        (
            {"applications": {"H01/../up": {"schema": "S", "calling_script": "a.sql"}}},
            "folder under",
        ),
        (
            {"applications": {"/H01/App1": {"schema": "S", "calling_script": "a.sql"}}},
            "folder under",
        ),
    ],
)
def test_malformed_plans_name_their_release(value: Any, message: str) -> None:
    with pytest.raises(ConsolidationDefinitionError) as error:
        parse_plan(value, "H1")

    assert str(error.value).startswith("Release 'H1'") and message in str(error.value)


def test_a_plan_keeps_its_order_and_other_fields() -> None:
    entries = parse_plan(
        {
            "applications": {
                "B": {"schema": " S2 ", "calling_script": "sub/b.sql", "note": "n"},
                "A": {"schema": "S1", "calling_script": "a.sql"},
            }
        },
        "H1",
    )

    assert [entry.application for entry in entries] == ["H1__B", "H1__A"]
    assert entries[0].definition() == {"note": "n", "schema": "S2", "calling_script": "b.sql"}


def test_grouped_applications_get_one_flat_folder_each() -> None:
    entries = parse_plan(
        {
            "applications": {
                "H01/App1": {"schema": "S1", "calling_script": "c.sql"},
                "H02\\App1": {"schema": "S2", "calling_script": "c.sql"},
            }
        },
        "R1",
    )

    assert [entry.source_application for entry in entries] == ["H01/App1", "H02/App1"]
    assert [entry.application for entry in entries] == ["R1__H01__App1", "R1__H02__App1"]


# ----------------------------------------------------------------------
# Plugin
# ----------------------------------------------------------------------


class TestPlugin:

    @pytest.fixture(autouse=True)
    def setup(self, tmp_path: Path) -> None:
        self.releases = tmp_path / "releases"
        self.releases.mkdir()
        self.output = tmp_path / "output"
        self.executor = LinuxExecutor()
        self.context = Mock()
        self.context.outputs = {}
        self.context.artifacts = {}
        self.context.activity.return_value = nullcontext()
        self.context.workspace = tmp_path / "workspace"
        self.context.filesystem = self.executor
        self.context.archive = self.executor

    def _run(self, **arguments: Any):
        arguments.setdefault("release_directory", str(self.releases))
        arguments.setdefault("output_directory", str(self.output))
        self.context.arguments = PluginArguments(arguments)
        return ConsolidateDbScriptsPlugin(self.context).execute()

    def _order(self) -> List[str]:
        return [step["application"] for step in self.context.outputs["steps"]]

    def _standard_releases(self) -> None:
        # H9 (folder), H10 (ZIP inside one folder, JSON plan), H101 (ZIP, App2 before App1).
        _folder(
            self.releases / "H9",
            {
                "DBScripts/execution_plan.yaml": plan(App1="S1", App2="S2"),
                "DBScripts/App1/App1_call.sql": "@child.sql\n",
                "DBScripts/App1/child.sql": "select 9 from dual;\n",
                "DBScripts/App1/sub/deep.sql": "select 1 from dual;\n",
                "DBScripts/App2/App2_call.sql": "select 2 from dual;\n",
            },
        )
        _zip(
            self.releases / "H10.zip",
            {
                "H10/DBScripts/execution_plan.json": json.dumps(
                    {"applications": {"App1": {"schema": "S1", "calling_script": "App1_call.sql"}}}
                ),
                "H10/DBScripts/App1/App1_call.sql": "select 10 from dual;\n",
            },
        )
        _zip(
            self.releases / "H101.zip",
            {
                "DBScripts/execution_plan.yaml": plan(App2="OTHER", App1="S1"),
                "DBScripts/App2/App2_call.sql": "select 3 from dual;\n",
                "DBScripts/App1/App1_call.sql": "select 4 from dual;\n",
            },
        )

    def test_every_execution_runs_in_release_order(self) -> None:
        self._standard_releases()

        result = self._run()

        assert result.success and result.changed
        assert self._order() == [
            "H9__App1",
            "H9__App2",
            "H10__App1",
            "H101__App2",
            "H101__App1",
        ]

    def test_the_real_sqlplus_resolver_runs_it_with_the_right_schemas(self) -> None:
        self._standard_releases()

        self._run()

        database = self.context.outputs["database"]

        executions = SqlPlusResolver().resolve_plan(
            connection={"IP": "h", "PORT": 1521, "SID": "s"},
            schemas={name: {"username": name, "password": "p"} for name in ("S1", "S2", "OTHER")},
            execution_plan=database["execution_plan"],
            scripts=database["scripts"],
        )

        assert [(item.application, item.schema) for item in executions] == [
            ("H9__App1", "S1"),
            ("H9__App2", "S2"),
            ("H10__App1", "S1"),
            ("H101__App2", "OTHER"),
            ("H101__App1", "S1"),
        ]
        assert executions[2].script.read_text() == "select 10 from dual;\n"

    def test_the_plan_on_disk_is_what_a_release_would_ship(self) -> None:
        self._standard_releases()

        self._run()

        database = self.output / "DBScripts"
        written = self.executor.read_yaml(database / "execution_plan.yaml")

        assert list(written["applications"]) == self._order()
        assert written == self.context.outputs["database"]["execution_plan"]

    def test_scripts_are_copied_unchanged_with_their_folders(self) -> None:
        self._standard_releases()

        self._run()

        folder = self.output / "DBScripts" / "H9__App1"

        assert (folder / "App1_call.sql").read_text() == "@child.sql\n"
        assert (folder / "child.sql").read_text() == "select 9 from dual;\n"
        assert (folder / "sub" / "deep.sql").read_text() == "select 1 from dual;\n"

    def test_leftovers_of_earlier_runs_and_packaging_are_not_copied(self) -> None:
        _folder(
            self.releases / "H1",
            {
                "DBScripts/execution_plan.yaml": plan(App1="S1"),
                "DBScripts/App1/App1_call.sql": "select 1 from dual;\n",
                "DBScripts/App1/.entropy/sqlplus/old_spool.sql": "stale",
                "DBScripts/App1/.DS_Store": "x",
                "DBScripts/App1/._App1_call.sql": "x",
                "__MACOSX/DBScripts/App1/._App1_call.sql": "x",
            },
        )

        self._run()

        copied = sorted(
            path.name
            for path in (self.output / "DBScripts" / "H1__App1").rglob("*")
            if path.is_file()
        )

        assert copied == ["App1_call.sql"]

    def test_a_folder_outside_the_plan_is_left_out_with_a_warning(self) -> None:
        _folder(
            self.releases / "H1",
            {
                "DBScripts/execution_plan.yaml": plan(App1="S1"),
                "DBScripts/App1/App1_call.sql": "select 1 from dual;\n",
                "DBScripts/App2/App2_call.sql": "select 2 from dual;\n",
            },
        )

        result = self._run()

        assert self._order() == ["H1__App1"]
        assert not (self.output / "DBScripts" / "H1__App2").exists()
        assert any("DBScripts/App2 is not in the" in warning for warning in result.warnings)

    def test_grouped_applications_are_consolidated_and_resolved(self) -> None:
        _folder(
            self.releases / "R1",
            {
                "DBScripts/execution_plan.yaml": yaml.safe_dump(
                    {
                        "applications": {
                            "H01/App1": {"schema": "S1", "calling_script": "call.sql"},
                            "H02/App1": {"schema": "S2", "calling_script": "call.sql"},
                        }
                    },
                    sort_keys=False,
                ),
                "DBScripts/H01/App1/call.sql": "@child.sql\n",
                "DBScripts/H01/App1/child.sql": "select 1 from dual;\n",
                "DBScripts/H02/App1/call.sql": "select 2 from dual;\n",
                "DBScripts/H02/App3/call.sql": "select 3 from dual;\n",
                "DBScripts/H03/App4/call.sql": "select 4 from dual;\n",
            },
        )

        result = self._run()

        assert result.success
        assert self._order() == ["R1__H01__App1", "R1__H02__App1"]
        assert (self.output / "DBScripts" / "R1__H01__App1" / "child.sql").is_file()

        # The group folders themselves are not reported, only what the plan misses.
        unplanned = [warning for warning in result.warnings if "is not in the" in warning]
        assert len(unplanned) == 2
        assert any("DBScripts/H02/App3 is not in the" in warning for warning in unplanned)
        assert any("DBScripts/H03 is not in the" in warning for warning in unplanned)

        database = self.context.outputs["database"]
        executions = SqlPlusResolver().resolve_plan(
            connection={"IP": "h", "PORT": 1521, "SID": "s"},
            schemas={name: {"username": name, "password": "p"} for name in ("S1", "S2")},
            execution_plan=database["execution_plan"],
            scripts=database["scripts"],
        )

        assert [(item.application, item.schema) for item in executions] == [
            ("R1__H01__App1", "S1"),
            ("R1__H02__App1", "S2"),
        ]
        assert executions[1].script.read_text() == "select 2 from dual;\n"

    def test_a_missing_grouped_calling_script_names_its_folder(self) -> None:
        _folder(
            self.releases / "R1",
            {
                "DBScripts/execution_plan.yaml": yaml.safe_dump(
                    {"applications": {"H01/App1": {"schema": "S1", "calling_script": "c.sql"}}}
                ),
                "DBScripts/H01/App1/other.sql": "select 1 from dual;\n",
            },
        )

        result = self._run()

        assert not result.success
        assert "DBScripts/H01/App1" in result.errors[0]["message"]

    def test_scripts_without_a_plan_are_left_out_with_a_warning(self) -> None:
        _folder(self.releases / "H1", {"DBScripts/App1/a.sql": "select 1 from dual;\n"})

        result = self._run()

        assert result.success and not result.changed
        assert any("no execution plan" in warning for warning in result.warnings)
        assert self.context.outputs["database"]["execution_plan"] is None

    def test_a_missing_calling_script_fails_naming_its_release(self) -> None:
        _folder(
            self.releases / "H1",
            {
                "DBScripts/execution_plan.yaml": plan(App1="S1"),
                "DBScripts/App1/other.sql": "select 1 from dual;\n",
            },
        )

        result = self._run()

        assert result.success is False
        assert result.errors[0]["message"].startswith("Release 'H1': calling script")

    def test_an_empty_calling_script_is_kept_with_a_warning(self) -> None:
        _folder(
            self.releases / "H1",
            {
                "DBScripts/execution_plan.yaml": plan(App1="S1"),
                "DBScripts/App1/App1_call.sql": "\n",
            },
        )

        result = self._run()

        assert self._order() == ["H1__App1"]
        assert any("is empty" in warning for warning in result.warnings)

    def test_releases_without_database_scripts_are_skipped_quietly(self) -> None:
        _folder(self.releases / "H1", {"App/yamls/d.yaml": "a: 1\n"})

        result = self._run()

        assert result.success and not result.changed and result.warnings == []
        assert self.context.outputs["database"]["execution_plan"] is None
        assert not (self.output / "DBScripts").exists()

    def test_invalid_plan_file_fails_cleanly(self) -> None:
        _folder(self.releases / "H1", {"DBScripts/execution_plan.json": "{not json"})

        result = self._run()

        assert result.success is False
        assert "execution_plan.json is not valid" in result.errors[0]["message"]

    def test_listed_releases_keep_the_given_order(self) -> None:
        for name in ("H1", "H2"):
            _folder(
                self.releases / name,
                {
                    "DBScripts/execution_plan.yaml": plan(App1="S1"),
                    "DBScripts/App1/App1_call.sql": f"select '{name}' from dual;\n",
                },
            )

        self.context.arguments = PluginArguments(
            {
                "releases": [str(self.releases / "H2"), str(self.releases / "H1")],
                "output_directory": str(self.output),
            }
        )

        assert ConsolidateDbScriptsPlugin(self.context).execute().success
        assert self._order() == ["H2__App1", "H1__App1"]


def test_contract_matches_the_source() -> None:
    declared = contract.declared(contract.read_manifest(PLUGIN_DIRECTORY))

    assert declared is not None
    assert contract.check_source(PLUGIN_DIRECTORY, declared) == []
