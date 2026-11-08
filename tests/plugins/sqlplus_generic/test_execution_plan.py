"""
Tests for sqlplus.generic plan mode: execution-plan applications keyed by their
folder under DBScripts, flat ('App1') or grouped ('H01/App1').
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

import pytest

from resources.plugins.sqlplus.generic.exceptions import GenericPluginError
from resources.plugins.sqlplus.generic.resolver import SqlPlusResolver

CONNECTION = {"IP": "db.local", "PORT": 1521, "SID": "orcl"}
SCHEMAS = {
    "S1": {"username": "u1", "password": "p1"},
    "S2": {"username": "u2", "password": "p2"},
}


def _resolve(applications: Dict[str, Any], scripts: List[Dict[str, str]]):
    return SqlPlusResolver().resolve_plan(
        connection=CONNECTION,
        schemas=SCHEMAS,
        execution_plan={"applications": applications},
        scripts=scripts,
    )


def _script(directory: str, name: str = "calling_script.sql") -> Dict[str, str]:
    return {
        "application": Path(directory).name,
        "directory": directory,
        "script": f"/rel/DBScripts/{directory}/{name}",
    }


def test_grouped_applications_resolve_to_their_own_folders() -> None:
    executions = _resolve(
        {
            "H01/App1": {"schema": "S1", "calling_script": "calling_script.sql"},
            "H02/App1": {"schema": "S2", "calling_script": "calling_script.sql"},
        },
        [_script("H02/App1"), _script("H01/App1")],
    )

    assert [(item.application, item.schema, str(item.script)) for item in executions] == [
        ("H01/App1", "S1", "/rel/DBScripts/H01/App1/calling_script.sql"),
        ("H02/App1", "S2", "/rel/DBScripts/H02/App1/calling_script.sql"),
    ]


@pytest.mark.parametrize("key", ["H01\\App1", "H01/App1/", "H01//App1", "./H01/App1"])
def test_grouped_keys_are_normalised(key: str) -> None:
    executions = _resolve(
        {key: {"schema": "S1", "calling_script": "calling_script.sql"}},
        [_script("H01/App1")],
    )

    assert executions[0].application == "H01/App1"


def test_flat_layout_still_resolves() -> None:
    executions = _resolve(
        {"App1": {"schema": "S1", "calling_script": "calling_script.sql"}},
        [_script("App1"), _script("App1/tables", "calling_script.sql")],
    )

    assert str(executions[0].script) == "/rel/DBScripts/App1/calling_script.sql"


def test_contexts_without_directory_match_on_the_folder_name() -> None:
    executions = _resolve(
        {"App1": {"schema": "S1", "calling_script": "calling_script.sql"}},
        [{"application": "App1", "script": "/rel/DBScripts/App1/calling_script.sql"}],
    )

    assert executions[0].application == "App1"


def test_a_grouped_key_does_not_match_another_group() -> None:
    with pytest.raises(GenericPluginError, match="'H01/App1' was not found"):
        _resolve(
            {"H01/App1": {"schema": "S1", "calling_script": "calling_script.sql"}},
            [_script("H02/App1")],
        )


def test_a_plain_name_does_not_match_a_grouped_folder() -> None:
    with pytest.raises(GenericPluginError, match="was not found"):
        _resolve(
            {"App1": {"schema": "S1", "calling_script": "calling_script.sql"}},
            [_script("H01/App1")],
        )


@pytest.mark.parametrize("key", ["../App1", "H01/../App1", "/H01/App1", "/", "."])
def test_keys_outside_dbscripts_are_refused(key: str) -> None:
    with pytest.raises(GenericPluginError, match="must be a folder"):
        _resolve(
            {key: {"schema": "S1", "calling_script": "calling_script.sql"}},
            [_script("App1")],
        )
