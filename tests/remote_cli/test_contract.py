"""One command contract for the local ent, the remote ent client and the browser shell."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List

import pytest

from core.commands.config import ConfigCommand
from core.commands.job import JobCommand
from core.commands.project import ProjectCommand
from core.commands.workflow import WorkflowCommand
from lib.remote_cli import commands as remote
from lib.remote_cli.api import Client
from lib.remote_cli.config import Config
from lib.remote_cli.contract import (
    DEFAULT_OUTPUT,
    OUTPUT_ENV,
    PROJECT_ENV,
    RESOURCES,
    OutputModeError,
    resolve_output,
)
from lib.remote_cli.output import render

LOCAL_COMMANDS = {
    "workflow": WorkflowCommand,
    "job": JobCommand,
    "project": ProjectCommand,
    "config": ConfigCommand,
}


@pytest.fixture(autouse=True)
def config_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    path = tmp_path / "home" / "config.json"
    monkeypatch.setenv("ENT_CONFIG", str(path))
    for name in ("ENT_CONTEXT", OUTPUT_ENV, PROJECT_ENV):
        monkeypatch.delenv(name, raising=False)
    return path


def _choices(parser: argparse.ArgumentParser) -> Dict[str, argparse.ArgumentParser]:
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            return dict(action.choices)
    return {}


def _local_parser(name: str) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    command = LOCAL_COMMANDS[name]
    # configure() only builds arguments; the context is not needed for that.
    command.configure(object.__new__(command), parser)  # type: ignore[arg-type]
    return parser


# ----------------------------------------------------------------------
# Parity
# ----------------------------------------------------------------------


@pytest.mark.parametrize("item", RESOURCES, ids=lambda item: item.name)
def test_remote_client_accepts_every_resource_verb_and_alias(item: Any) -> None:
    resources = _choices(remote.build_parser())
    for noun in (item.name, *item.aliases):
        assert noun in resources, noun
        verbs = _choices(resources[noun])
        for verb in item.verbs:
            if verb.remote:
                for word in (verb.name, *verb.aliases):
                    assert word in verbs, f"{noun} {word}"


@pytest.mark.parametrize("name", sorted(LOCAL_COMMANDS))
def test_local_cli_accepts_the_same_verbs(name: str) -> None:
    item = next(resource for resource in RESOURCES if resource.name == name)
    command = LOCAL_COMMANDS[name]
    assert set(item.aliases) <= set(command.metadata.aliases)
    verbs = _choices(_local_parser(name))
    for verb in item.verbs:
        if verb.local:
            for word in (verb.name, *verb.aliases):
                assert word in verbs, f"{name} {word}"


def test_old_local_workflow_verbs_still_work() -> None:
    parser = _local_parser("workflow")
    assert parser.parse_args(["show", "deploy", "--yaml"]).yaml is True
    assert parser.parse_args(["remove", "deploy"]).name == "deploy"
    assert parser.parse_args(["add", "deploy.yaml"]).file == Path("deploy.yaml")
    assert parser.parse_args(["run", "deploy", "--var", "a=1", "-a", "b=2"]).arguments == [
        "a=1",
        "b=2",
    ]
    assert parser.parse_args(["ls", "-o", "table"]).output == "table"
    assert parser.parse_args(["apply", "-f", "x.yaml"]).file == Path("x.yaml")


# ----------------------------------------------------------------------
# Output modes
# ----------------------------------------------------------------------


def test_output_mode_precedence(monkeypatch: pytest.MonkeyPatch) -> None:
    assert resolve_output() == DEFAULT_OUTPUT == "detailed"
    assert resolve_output(saved="table") == "table"
    monkeypatch.setenv(OUTPUT_ENV, "wide")
    assert resolve_output(saved="table") == "wide"
    assert resolve_output("json", saved="table") == "json"
    monkeypatch.setenv(OUTPUT_ENV, "fancy")
    with pytest.raises(OutputModeError, match=OUTPUT_ENV):
        resolve_output()


def test_render_modes() -> None:
    items = [{"name": "deploy", "version": "1.0", "description": "Ship it"}]
    columns = [
        ("name", lambda w: w["name"], False),
        ("version", lambda w: w["version"], False),
        ("description", lambda w: w["description"], True),
    ]

    def show(mode: str) -> str:
        return render(mode, items, columns, title="Workflows", kind="workflow")

    assert show("table").splitlines() == ["NAME     VERSION", "deploy   1.0"]
    assert "DESCRIPTION" in show("wide")
    assert show("detailed").startswith("Workflows (1)\n┌")
    assert show("name") == "workflow/deploy"
    assert json.loads(show("json")) == items
    assert show("yaml").splitlines() == [
        "- name: deploy",
        '  version: "1.0"',
        "  description: Ship it",
    ]
    assert render("table", [], columns, title="x", kind="x") == "No resources found."


def test_saved_output_preference_is_used(capsys: pytest.CaptureFixture) -> None:
    assert remote.main(["config", "set", "output", "table"]) == 0
    assert Config.load().preference("output") == "table"
    capsys.readouterr()
    assert remote.main(["config", "view"]) == 0
    assert "output: table (saved)" in capsys.readouterr().out
    assert remote.main(["config", "set", "output", "fancy"]) == 1
    assert "unknown output mode" in capsys.readouterr().err


# ----------------------------------------------------------------------
# Projects
# ----------------------------------------------------------------------


def _login(project: Any = None) -> None:
    config = Config.load()
    values: Dict[str, Any] = {"server": "https://entropy.test", "token": "t"}
    if project:
        values["project"] = project
    config.upsert("test", values)
    config.save()


def test_client_sends_the_project_header(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: List[Dict[str, str]] = []

    class Response:
        def __enter__(self) -> Response:
            return self

        def __exit__(self, *_: Any) -> None:
            return None

        def read(self) -> bytes:
            return b'{"items": []}'

    def fake_urlopen(request: Any, **_: Any) -> Response:
        seen.append(dict(request.header_items()))
        return Response()

    monkeypatch.setattr("lib.remote_cli.api.urlopen", fake_urlopen)
    Client("https://entropy.test", "t", project="app-1").get("/workflows")
    Client("https://entropy.test", "t").get("/workflows")
    assert seen[0]["X-entropy-project"] == "app-1"
    assert "X-entropy-project" not in seen[1]


def test_project_set_is_saved_per_context_and_used(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    _login()
    projects = {"items": [{"key": "app-1", "name": "App 1"}], "current": "default"}
    clients: List[Client] = []

    def fake_get(self: Client, url_path: str, **_: Any) -> Any:
        clients.append(self)
        return projects if url_path == "/projects" else {"items": []}

    monkeypatch.setattr(Client, "get", fake_get)

    assert remote.main(["project", "set", "missing"]) == 1
    assert remote.main(["project", "use", "app-1"]) == 0
    assert Config.load().current()["project"] == "app-1"

    remote.main(["wf", "ls", "-o", "name"])
    assert clients[-1].project == "app-1"

    # --project and $ENT_PROJECT win for one command.
    remote.main(["-p", "other", "wf", "ls"])
    assert clients[-1].project == "other"
    monkeypatch.setenv(PROJECT_ENV, "env-project")
    remote.main(["wf", "ls"])
    assert clients[-1].project == "env-project"
    monkeypatch.delenv(PROJECT_ENV)

    assert remote.main(["project", "remove"]) == 0
    assert "project" not in Config.load().current()
    capsys.readouterr()


# ----------------------------------------------------------------------
# Local CLI output
# ----------------------------------------------------------------------


class _UI:
    def __init__(self) -> None:
        self.calls: List[Any] = []

    def table(self, title: str, columns: Any, rows: Any) -> None:
        self.calls.append(("table", title, list(columns), [list(row) for row in rows]))

    def text(self, message: str) -> None:
        self.calls.append(("text", message))

    def info(self, message: str) -> None:
        self.calls.append(("info", message))


def test_local_emit_uses_console_tables_or_plain_text(monkeypatch: pytest.MonkeyPatch) -> None:
    from types import SimpleNamespace

    from core.commands.output_mode import emit

    ui = _UI()
    context = SimpleNamespace(ui=ui, session_manager=None)
    columns = [("name", lambda w: w["name"], False), ("note", lambda w: w.get("note"), True)]
    items = [{"name": "deploy [prod]", "note": None}]

    emit(
        context,
        argparse.Namespace(output=None),
        title="T",
        columns=columns,
        items=items,
        kind="workflow",
    )
    assert ui.calls[-1] == ("table", "T", ["Name", "Note"], [["deploy [prod]", ""]])

    emit(
        context,
        argparse.Namespace(output="table"),
        title="T",
        columns=columns,
        items=items,
        kind="workflow",
    )
    assert ui.calls[-1] == ("text", "NAME\ndeploy [prod]")

    monkeypatch.setenv(OUTPUT_ENV, "name")
    emit(
        context,
        argparse.Namespace(output=None),
        title="T",
        columns=columns,
        items=items,
        kind="workflow",
    )
    assert ui.calls[-1] == ("text", "workflow/deploy [prod]")

    emit(
        context,
        argparse.Namespace(output="detailed"),
        title="T",
        columns=columns,
        items=[],
        kind="job",
    )
    assert ui.calls[-1] == ("info", "No jobs found.")


def test_rich_text_is_not_marked_up(capsys: pytest.CaptureFixture) -> None:
    from core.ui.rich_renderer import RichRenderer

    RichRenderer().text("NAME   [bold]x[/bold]")
    assert capsys.readouterr().out == "NAME   [bold]x[/bold]\n"
