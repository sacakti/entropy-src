"""
Tests for release.context_builder's database context: flat (DBScripts/App1)
and grouped (DBScripts/H01/App1) layouts, resolved by sqlplus.generic.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import Mock

from lib.executor import LinuxExecutor
from resources.plugins.release.context_builder.analyzer import ReleaseAnalyzer
from resources.plugins.sqlplus.generic.resolver import SqlPlusResolver

DEFINITION = {
    "path": "DBScripts",
    "type": "directory",
    "scripts": {"extensions": [".sql"]},
    "execution_plan": {"names": ["execution_plan.yaml"]},
}


def _analyzer() -> ReleaseAnalyzer:
    return ReleaseAnalyzer(
        filesystem=LinuxExecutor(),
        archive=Mock(),
        message=Mock(),
        log=Mock(),
        activity=Mock(),
    )


def _write(root: Path, files: dict) -> None:
    for name, content in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)


def test_grouped_scripts_carry_their_folder_and_resolve(tmp_path: Path) -> None:
    _write(
        tmp_path,
        {
            "DBScripts/execution_plan.yaml": (
                "applications:\n"
                "  H01/App1:\n    schema: S1\n    calling_script: calling_script.sql\n"
                "  H02/App1:\n    schema: S2\n    calling_script: calling_script.sql\n"
            ),
            "DBScripts/H01/App1/calling_script.sql": "select 1 from dual;\n",
            "DBScripts/H02/App1/calling_script.sql": "select 2 from dual;\n",
        },
    )

    database = _analyzer()._analyse_database(root=tmp_path, definition=DEFINITION)

    assert sorted((item["application"], item["directory"]) for item in database["scripts"]) == [
        ("App1", "H01/App1"),
        ("App1", "H02/App1"),
    ]

    executions = SqlPlusResolver().resolve_plan(
        connection={"IP": "h", "PORT": 1521, "SID": "s"},
        schemas={
            "S1": {"username": "a", "password": "p"},
            "S2": {"username": "b", "password": "p"},
        },
        execution_plan=database["execution_plan"],
        scripts=database["scripts"],
    )

    assert [(item.application, item.script.read_text()) for item in executions] == [
        ("H01/App1", "select 1 from dual;\n"),
        ("H02/App1", "select 2 from dual;\n"),
    ]


def test_flat_scripts_keep_their_folder_name(tmp_path: Path) -> None:
    _write(
        tmp_path,
        {
            "DBScripts/execution_plan.yaml": (
                "applications:\n  App1:\n    schema: S1\n    calling_script: calling_script.sql\n"
            ),
            "DBScripts/App1/calling_script.sql": "select 1 from dual;\n",
        },
    )

    database = _analyzer()._analyse_database(root=tmp_path, definition=DEFINITION)

    assert [(item["application"], item["directory"]) for item in database["scripts"]] == [
        ("App1", "App1"),
    ]
