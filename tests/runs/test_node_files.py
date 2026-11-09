"""
Runs on another node reach files picked on the main node: copied to the node's
workspace ('fetch') or through a folder both see ('shared').
"""

from __future__ import annotations

import io
import json
import tarfile
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict, List

import pytest
from fastapi import HTTPException

from lib.agent.agent import Agent
from lib.database.connection import DatabaseConnection
from lib.database.objects.events import WorkflowEventsTable
from lib.database.objects.jobs import WorkflowJobsTable
from lib.nodes import files
from lib.nodes.files import FileAccessError, normalize, plan
from lib.runs.nodes import NodeStore


def _definition(*values: Any) -> str:
    return json.dumps(
        {
            "name": "deploy",
            "steps": [
                {"name": f"s{index}", "plugin": "x.y", "arguments": {"value": value}}
                for index, value in enumerate(values)
            ],
        }
    )


def _arguments(definition: str) -> List[Any]:
    return [step["arguments"]["value"] for step in json.loads(definition)["steps"]]


@pytest.fixture
def main(tmp_path: Path) -> Dict[str, Path]:
    """A main node: a releases folder with a package and a folder, and an Oracle home."""

    releases = tmp_path / "releases"
    (releases / "SR01" / "DBScripts").mkdir(parents=True)
    (releases / "SR01.zip").write_bytes(b"zip" * 100)
    (releases / "SR01" / "DBScripts" / "a.sql").write_text("select 1 from dual;")
    oracle = tmp_path / "oracle"
    oracle.mkdir()
    return {"releases": releases, "oracle": oracle}


# ----------------------------------------------------------------------
# Settings
# ----------------------------------------------------------------------


def test_settings_are_normalized() -> None:
    assert normalize(None) == {"mode": "off"}
    assert normalize({"mode": "fetch", "workspace": "/data/entropy/files/"}) == {
        "mode": "fetch",
        "workspace": "/data/entropy/files",
        "sources": [],
        "max_gb": 5,
    }
    shared = normalize(
        {
            "mode": "shared",
            "mappings": [
                {"main": "/mnt/share", "node": "/data/share"},
                {"main": "/mnt/share/releases", "node": "/releases"},
            ],
        }
    )
    # The most specific folder is tried first.
    assert [pair["main"] for pair in shared["mappings"]] == ["/mnt/share/releases", "/mnt/share"]


@pytest.mark.parametrize(
    "value",
    [
        {"mode": "copy"},
        {"mode": "fetch"},
        {"mode": "fetch", "workspace": "relative/path"},
        {"mode": "fetch", "workspace": "/"},
        {"mode": "fetch", "workspace": "/data/../etc"},
        {"mode": "fetch", "workspace": "/data", "max_gb": 0},
        {"mode": "shared", "mappings": []},
        {"mode": "shared", "mappings": [{"main": "/mnt/share"}]},
    ],
)
def test_bad_settings_are_refused(value) -> None:
    with pytest.raises(FileAccessError):
        normalize(value)


def test_the_store_keeps_settings_and_reads_bad_ones_as_off(tmp_path: Path, monkeypatch) -> None:
    # As in test_nodes_remote: the run schema does not need the permission tables here.
    monkeypatch.setattr(
        "lib.authorization.initializer.AuthorizationInitializer.reconcile",
        lambda self: None,
    )
    connection = DatabaseConnection(tmp_path / "entropy.db")
    WorkflowJobsTable().create(connection)
    WorkflowEventsTable().create(connection)
    store = NodeStore(connection)
    store.save_remote(
        "edge-1", host="h", port=22, ssh_user="u", install_dir="~/.a", server_url="https://m"
    )
    assert store.get("edge-1")["file_access"] == {"mode": "off"}

    node = store.set_file_access("edge-1", {"mode": "fetch", "workspace": "/data/files"})
    assert node["file_access"]["workspace"] == "/data/files"

    connection.execute("UPDATE nodes SET file_access = 'not json' WHERE name = 'edge-1'")
    assert store.get("edge-1")["file_access"] == {"mode": "off"}


# ----------------------------------------------------------------------
# Plan
# ----------------------------------------------------------------------


def test_fetch_copies_files_in_its_folders_and_rewrites_their_paths(main) -> None:
    package = str(main["releases"] / "SR01.zip")
    folder = str(main["releases"] / "SR01")
    settings = normalize({"mode": "fetch", "workspace": "/data/files"})
    definition = _definition(
        package, folder, str(main["oracle"]), "/not/there.zip", "${release}/x.zip", "text"
    )

    result = plan(settings, definition, {"release": package}, [main["releases"]])

    staged = {item["path"]: item for item in result["files"]}
    assert set(staged) == {package, folder}
    assert staged[package]["kind"] == "file" and staged[package]["size"] == 300
    assert staged[folder]["kind"] == "directory"
    values = _arguments(result["definition"])
    # Only files under the folders to send from change; the Oracle home exists on both.
    assert values[0] == staged[package]["target"]
    assert values[0].startswith("/data/files/") and values[0].endswith("/SR01.zip")
    assert values[1] == staged[folder]["target"]
    assert values[2:] == [str(main["oracle"]), "/not/there.zip", "${release}/x.zip", "text"]
    assert result["variables"] == {"release": staged[package]["target"]}


def test_the_same_content_gets_the_same_place(main) -> None:
    settings = normalize({"mode": "fetch", "workspace": "/data/files"})
    package = str(main["releases"] / "SR01.zip")
    first = plan(settings, _definition(package), {}, [main["releases"]])
    again = plan(settings, _definition(package), {}, [main["releases"]])
    assert first["files"][0]["target"] == again["files"][0]["target"]

    (main["releases"] / "SR01.zip").write_bytes(b"changed")
    changed = plan(settings, _definition(package), {}, [main["releases"]])
    assert changed["files"][0]["target"] != first["files"][0]["target"]


def test_fetch_refuses_more_than_the_size_limit(main) -> None:
    settings = normalize({"mode": "fetch", "workspace": "/data/files", "max_gb": 0.0000001})
    with pytest.raises(FileAccessError, match="GB limit"):
        plan(settings, _definition(str(main["releases"] / "SR01.zip")), {}, [main["releases"]])


def test_configured_sources_replace_the_defaults(main) -> None:
    settings = normalize(
        {"mode": "fetch", "workspace": "/data/files", "sources": [str(main["oracle"])]}
    )
    result = plan(settings, _definition(str(main["releases"] / "SR01.zip")), {}, [main["releases"]])
    assert result["files"] == []


def test_shared_rewrites_paths_and_names_folders_to_check(main) -> None:
    settings = normalize(
        {"mode": "shared", "mappings": [{"main": str(main["releases"]), "node": "/share"}]}
    )
    result = plan(
        settings,
        _definition(str(main["releases"] / "SR01.zip"), str(main["oracle"])),
        {},
        [],
    )
    assert _arguments(result["definition"]) == ["/share/SR01.zip", str(main["oracle"])]
    assert result["files"] == [] and result["checks"] == ["/share"]


def test_shared_refuses_main_files_outside_the_share(main, tmp_path) -> None:
    other = tmp_path / "elsewhere.zip"
    other.write_bytes(b"x")
    settings = normalize({"mode": "shared", "mappings": [{"main": "/mnt/share", "node": "/s"}]})
    with pytest.raises(FileAccessError, match="not in a folder shared"):
        plan(settings, _definition(str(other)), {}, [])


def test_off_changes_nothing(main) -> None:
    definition = _definition(str(main["releases"] / "SR01.zip"))
    result = plan({"mode": "off"}, definition, {"a": 1}, [main["releases"]])
    assert result == {"definition": definition, "variables": {"a": 1}, "files": [], "checks": []}


# ----------------------------------------------------------------------
# Node: copying before the run
# ----------------------------------------------------------------------


class FakeClient:
    def __init__(self, payloads: Dict[str, bytes]) -> None:
        self.payloads = payloads
        self.calls: List[str] = []

    def download_to(self, path: str, destination: Path, *, timeout: float = 600) -> int:
        self.calls.append(path)
        data = self.payloads[path]
        destination.write_bytes(data)
        return len(data)


def _tar(files_: Dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w") as archive:
        for name, data in files_.items():
            info = tarfile.TarInfo(name)
            info.size = len(data)
            archive.addfile(info, io.BytesIO(data))
    return buffer.getvalue()


def test_the_node_copies_files_once(tmp_path: Path) -> None:
    workspace = tmp_path / "files"
    spec = {
        "files": [
            {
                "index": 0,
                "name": "SR01.zip",
                "kind": "file",
                "size": 3,
                "key": "k1",
                "target": str(workspace / "k1" / "SR01.zip"),
            },
            {
                "index": 1,
                "name": "SR01",
                "kind": "directory",
                "size": 9,
                "key": "k2",
                "target": str(workspace / "k2" / "SR01"),
            },
        ]
    }
    client = FakeClient(
        {
            "/api/agent/jobs/5/files/0": b"zip",
            "/api/agent/jobs/5/files/1": _tar({"./DBScripts/a.sql": b"select 1;"}),
        }
    )
    agent = SimpleNamespace(client=client)

    Agent._ensure_files(agent, 5, spec)  # type: ignore[arg-type]
    Agent._ensure_files(agent, 6, spec)  # type: ignore[arg-type]

    assert (workspace / "k1" / "SR01.zip").read_bytes() == b"zip"
    assert (workspace / "k2" / "SR01" / "DBScripts" / "a.sql").read_text() == "select 1;"
    # The second run found both already there.
    assert len(client.calls) == 2


def test_the_node_refuses_incomplete_files_and_unsafe_archives(tmp_path: Path) -> None:
    short = {
        "index": 0,
        "name": "a.zip",
        "kind": "file",
        "size": 10,
        "key": "k",
        "target": str(tmp_path / "k" / "a.zip"),
    }
    client = FakeClient({"/api/agent/jobs/1/files/0": b"abc"})
    with pytest.raises(RuntimeError, match="incomplete"):
        Agent._ensure_files(SimpleNamespace(client=client), 1, {"files": [short]})  # type: ignore[arg-type]
    assert not (tmp_path / "k" / "a.zip").exists()

    folder = {**short, "kind": "directory", "target": str(tmp_path / "d" / "x")}
    client = FakeClient({"/api/agent/jobs/1/files/0": _tar({"../escape.txt": b"x"})})
    with pytest.raises(RuntimeError, match="unsafe"):
        Agent._ensure_files(SimpleNamespace(client=client), 1, {"files": [folder]})  # type: ignore[arg-type]
    assert not (tmp_path / "d" / "escape.txt").exists()


def test_the_node_checks_shared_folders(tmp_path: Path) -> None:
    agent = SimpleNamespace(client=FakeClient({}))
    Agent._ensure_files(agent, 1, {"checks": [str(tmp_path)]})  # type: ignore[arg-type]
    with pytest.raises(RuntimeError, match="not mounted"):
        Agent._ensure_files(agent, 1, {"checks": [str(tmp_path / "missing")]})  # type: ignore[arg-type]


# ----------------------------------------------------------------------
# Main node: handing the files out
# ----------------------------------------------------------------------


def _serve(monkeypatch, record: Dict[str, Any], index: int):
    from core.web.routes import agent as routes

    class Dispatcher:
        def _owned(self, node, job_id):
            if node["name"] != record["node"]:
                raise LookupError("not yours")
            return record

    monkeypatch.setattr(routes, "_dispatcher", lambda request: Dispatcher())
    return routes.job_file(5, index, SimpleNamespace(), {"name": "edge-1"})


def test_only_the_files_named_for_the_run_are_served(monkeypatch, main) -> None:
    package = main["releases"] / "SR01.zip"
    record = {
        "node": "edge-1",
        "spec": json.dumps({"file_paths": [str(package), str(main["releases"] / "SR01")]}),
    }

    response = _serve(monkeypatch, record, 0)
    assert Path(response.path) == package
    assert response.headers["x-entropy-size"] == "300"

    folder = _serve(monkeypatch, record, 1)
    with tarfile.open(folder.path) as archive:
        assert "./DBScripts/a.sql" in archive.getnames()
    Path(folder.path).unlink()

    for index in (2, -1):
        with pytest.raises(HTTPException) as caught:
            _serve(monkeypatch, record, index)
        assert caught.value.status_code == 404
    with pytest.raises(HTTPException):
        _serve(monkeypatch, {**record, "node": "other"}, 0)


def test_files_module_exports() -> None:
    assert files.MODES == ("off", "fetch", "shared")


def test_starting_a_run_explains_what_cannot_reach_the_node(tmp_path: Path) -> None:
    from lib.runs.service import RunError, RunService

    home = tmp_path / "home"
    (home / "artifacts" / "1").mkdir(parents=True)
    package = home / "artifacts" / "1" / "SR01.zip"
    package.write_bytes(b"zip")
    service = RunService.__new__(RunService)
    service._context = SimpleNamespace(bootstrap=SimpleNamespace(home=str(home)), paths=None)

    fetch = {"name": "edge-1", "file_access": normalize({"mode": "fetch", "workspace": "/f"})}
    staged = service._stage_files(fetch, _definition(str(package)), {})
    # Uploaded artifacts are sent by default.
    assert [item["path"] for item in staged["files"]] == [str(package)]

    shared = {
        "name": "edge-1",
        "file_access": normalize({"mode": "shared", "mappings": [{"main": "/mnt", "node": "/s"}]}),
    }
    with pytest.raises(RunError) as caught:
        service._stage_files(shared, _definition(str(package)), {})
    assert caught.value.args[0].startswith("Node 'edge-1': These files")
