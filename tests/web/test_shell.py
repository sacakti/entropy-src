"""The web shell: which commands it runs, and how."""

from __future__ import annotations

import pytest

from core.web.routes.shell import parse


@pytest.mark.parametrize(
    "command, argv",
    [
        ("workflow list", ["workflow", "list"]),
        ("ent wf ls", ["wf", "ls"]),
        ("job get 42 -o json", ["job", "get", "42", "-o", "json"]),
        (
            'workflow run deploy --var "msg=hello world"',
            ["workflow", "run", "deploy", "--var", "msg=hello world"],
        ),
        ("help", ["help"]),
    ],
)
def test_commands_without_ent(command: str, argv: list) -> None:
    assert parse(command) == argv


@pytest.mark.parametrize(
    "command, reason",
    [
        ("login https://elsewhere", "signed in as you"),
        ("context use other", "signed in as you"),
        ("job logs 4 -f", "does not wait"),
        ("job wait 4", "does not wait"),
        ("workflow run deploy --follow", "does not wait"),
        ("workflow apply -f /etc/passwd", "read files"),
        ("workflow validate --file=x.yaml", "read files"),
        ("rm -rf /", "Unknown command"),
        ("ent", "Type a command"),
        ('workflow get "unterminated', "Cannot parse"),
    ],
)
def test_refused_commands_say_why(command: str, reason: str) -> None:
    with pytest.raises(ValueError, match=reason):
        parse(command)


# ----------------------------------------------------------------------
# Shared contract, project and output preference
# ----------------------------------------------------------------------


def test_contract_words_are_in_the_vocabulary() -> None:
    from core.web.routes.shell import VOCABULARY

    for word in ("project", "proj", "config", "workflow", "wf", "job", "runs"):
        assert word in VOCABULARY


@pytest.mark.parametrize(
    "argv, stdout, effects",
    [
        (["config", "set", "output", "table"], "output set to table", {"output": "table"}),
        (["config", "unset", "output"], "using detailed", {"output": None}),
        (["project", "remove"], "default project", {"project": None}),
        (["proj", "unset"], "default project", {"project": None}),
    ],
)
def test_page_settings_are_answered_by_the_shell(argv: list, stdout: str, effects: dict) -> None:
    from core.web.routes.shell import browser_settings

    result = browser_settings(None, None, argv, None)  # type: ignore[arg-type]
    assert result is not None and stdout in result["stdout"]
    assert result["effects"] == effects


def test_config_view_and_bad_mode() -> None:
    from core.web.routes.shell import browser_settings

    view = browser_settings(None, None, ["config", "view"], "wide")  # type: ignore[arg-type]
    assert view is not None and "output: wide (saved)" in view["stdout"]
    bad = browser_settings(None, None, ["config", "set", "output", "fancy"], None)  # type: ignore[arg-type]
    assert bad is not None and bad["exit_code"] == 2 and "effects" not in bad
    # Everything else runs in the client.
    assert browser_settings(None, None, ["project", "list"], None) is None  # type: ignore[arg-type]
    assert browser_settings(None, None, ["wf", "ls"], None) is None  # type: ignore[arg-type]


def test_project_set_checks_visibility(monkeypatch: pytest.MonkeyPatch) -> None:
    from core.web.routes import shell

    class Store:
        def get(self, key: str):
            return {
                "app-1": {"id": 1, "key": "app-1", "name": "App 1"},
                "secret": {"id": 2, "key": "secret", "name": "S"},
            }.get(key)

    monkeypatch.setattr(shell, "projects", lambda request: Store())
    monkeypatch.setattr(shell, "visible_projects", lambda request, user: {1})

    ok = shell.browser_settings(None, None, ["project", "set", "app-1"], None)  # type: ignore[arg-type]
    assert ok is not None and ok["effects"] == {"project": "app-1"}
    for key in ("secret", "missing"):
        refused = shell.browser_settings(None, None, ["project", "use", key], None)  # type: ignore[arg-type]
        assert refused is not None and refused["exit_code"] == 1 and "effects" not in refused


def test_the_client_runs_in_the_page_project_and_output(monkeypatch: pytest.MonkeyPatch) -> None:
    import json
    import subprocess
    from pathlib import Path

    from core.web.routes import shell

    seen: dict = {}

    def fake_run(argv, *, env, **_):
        seen["config"] = json.loads(Path(env["ENT_CONFIG"]).read_text())
        seen["env"] = env
        return subprocess.CompletedProcess(argv, 0, b"ok", b"")

    monkeypatch.setattr(shell.subprocess, "run", fake_run)
    result = shell.run(["wf", "ls"], "token", "http://127.0.0.1:8000", "app-1", "table")
    assert result["stdout"] == "ok"
    assert seen["config"]["contexts"]["shell"]["project"] == "app-1"
    assert seen["env"]["ENT_OUTPUT"] == "table"

    shell.run(["wf", "ls"], "token", "http://127.0.0.1:8000")
    assert "project" not in seen["config"]["contexts"]["shell"]
    assert "ENT_OUTPUT" not in seen["env"]
