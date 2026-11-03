"""Questions asked by plugins of interactive runs."""

from __future__ import annotations

import os
import secrets
from typing import Iterator

import pytest

from lib.database.connection import DatabaseConnection
from lib.runs.prompts import PromptError, PromptStore


@pytest.fixture
def store(tmp_path) -> Iterator[PromptStore]:
    connection = DatabaseConnection(tmp_path / "entropy.db")
    connection.open()
    yield PromptStore(connection, secrets.token_bytes(32))
    connection.close()


def test_a_secret_answer_is_kept_encrypted_and_deleted_once_read(store) -> None:
    prompt = store.ask(7, name="code", label="One-time code", secret=True, default="hidden")
    waiting = store.list([7], waiting_only=True)
    assert [item["label"] for item in waiting] == ["One-time code"]
    assert waiting[0]["default"] is None  # a secret's default is never shown

    store.answer(prompt, "s3cr3t", "admin")
    stored = store.connection.fetchone("SELECT answer FROM run_prompts WHERE id = ?", (prompt,))
    assert stored["answer"] and "s3cr3t" not in stored["answer"]

    assert store.wait(prompt, poll=0, sleep=lambda _: None) == "s3cr3t"
    row = store.connection.fetchone("SELECT state, answer FROM run_prompts WHERE id = ?", (prompt,))
    assert (row["state"], row["answer"]) == ("consumed", None)
    assert store.list([7], waiting_only=True) == []


def test_answers_are_checked_and_given_once(store) -> None:
    prompt = store.ask(7, name="colour", label="Colour", choices=["red", "blue"])
    with pytest.raises(PromptError, match="offered answers"):
        store.answer(prompt, "green", "admin")
    store.answer(prompt, "blue", "admin")
    with pytest.raises(PromptError, match="already answered"):
        store.answer(prompt, "red", "admin")


def test_unanswered_questions_time_out_or_are_withdrawn(store) -> None:
    prompt = store.ask(7, name="x", label="X")
    with pytest.raises(PromptError, match="No answer within"):
        store.wait(prompt, timeout=0, sleep=lambda _: None)
    assert store.get(prompt)["state"] == "expired"

    other = store.ask(8, name="y", label="Y")
    store.expire([8])
    with pytest.raises(PromptError, match="withdrawn"):
        store.wait(other, poll=0, sleep=lambda _: None)


def test_secrets_need_the_vault_key(tmp_path) -> None:
    connection = DatabaseConnection(tmp_path / "entropy.db")
    connection.open()
    store = PromptStore(connection, None)
    prompt = store.ask(1, name="p", label="Password", secret=True)
    with pytest.raises(PromptError, match="vault key"):
        store.answer(prompt, "x", "admin")
    connection.close()


def test_automated_runs_get_the_default_or_fail(monkeypatch) -> None:
    from types import SimpleNamespace

    from lib.plugins.context import PluginContext
    from lib.plugins.exceptions import PluginValueError
    from lib.plugins.mode import PluginMode
    from lib.runs.prompts import RUN_MODE_ENV

    monkeypatch.setenv(RUN_MODE_ENV, "automated")
    context = PluginContext.__new__(PluginContext)
    context._mode = PluginMode.WORKFLOW
    context._runtime = SimpleNamespace()
    assert context.ask("Colour", default="red") == "red"
    assert context.can_ask is False
    monkeypatch.setenv(RUN_MODE_ENV, "interactive")
    assert context.can_ask is True
    monkeypatch.setenv(RUN_MODE_ENV, "automated")
    with pytest.raises(PluginValueError, match="automated"):
        context.ask("Code", secret=True)
    assert os.environ[RUN_MODE_ENV] == "automated"


def test_interactive_runs_ask_for_what_was_left_empty(monkeypatch) -> None:
    from types import SimpleNamespace

    import lib.runs.prompts as prompts
    from lib.plugins import contract
    from lib.plugins.runner import PluginRunner

    asked = []

    class Store:
        def ask(self, job_id, *, name, **_):
            asked.append(name)
            return name

        def wait(self, prompt):
            return {"conn": '{"host": "h"}', "note": "hello", "source": "/tmp/a"}.get(prompt, "")

    monkeypatch.setenv(prompts.RUN_MODE_ENV, "interactive")
    monkeypatch.setattr(prompts, "prompts_for", lambda _: Store())
    declared = contract.normalize(
        {
            "arguments": [
                {"name": "conn", "type": "dictionary", "required": True},
                {"name": "source", "type": "string"},
                {"name": "count", "type": "integer"},
                {"name": "mode", "default": "fast"},
                {"name": "archive", "type": "dictionary"},
                {"name": "given", "type": "string"},
                {"name": "quiet", "type": "string", "prompt": False},
                {"name": "note", "type": "string", "prompt": True},
            ],
            "outputs": [],
        }
    )
    context = SimpleNamespace(_entropy=None, node=None, job_id=1)
    values = PluginRunner._prompt_missing(context, declared, {"given": "x"}, "demo.p")
    # Only required arguments and those that say "prompt": true; other empty
    # optional arguments (with or without a default) are not asked.
    assert asked == ["conn", "note"]
    assert values == {"given": "x", "conn": {"host": "h"}, "note": "hello"}

    asked.clear()
    monkeypatch.setenv(prompts.RUN_MODE_ENV, "automated")
    assert PluginRunner._prompt_missing(context, declared, {}, "demo.p") == {}
    assert asked == []


# ----------------------------------------------------------------------
# Arguments given as ${ask}
# ----------------------------------------------------------------------


def _ask_contract():
    from lib.plugins import contract

    return contract.normalize(
        {
            "arguments": [
                {"name": "password", "type": "string", "required": True},
                {"name": "hosts", "type": "list"},
                {"name": "note", "type": "string"},
                {"name": "given", "type": "string"},
            ],
            "outputs": [],
        }
    )


def test_interactive_runs_ask_for_ask_arguments(monkeypatch) -> None:
    from types import SimpleNamespace

    import lib.runs.prompts as prompts
    from lib.plugins.runner import PluginRunner

    asked = []

    class Store:
        def ask(self, job_id, *, name, secret, **_):
            asked.append((name, secret))
            return name

        def wait(self, prompt):
            return {"password": "s3cret", "hosts": '["a", "b"]', "note": ""}[prompt]

    monkeypatch.setenv(prompts.RUN_MODE_ENV, "interactive")
    monkeypatch.setattr(prompts, "prompts_for", lambda _: Store())
    context = SimpleNamespace(_entropy=None, node=None, job_id=1)

    values = PluginRunner._ask_marked(
        context,
        _ask_contract(),
        {"password": "${ask:secret}", "hosts": "${ask}", "note": "${ask}", "given": "x"},
        "demo.p",
    )

    # Optional ones too; every question is posted before waiting.
    assert asked == [("password", True), ("hosts", False), ("note", False)]
    # Typed like any answer; an empty optional answer leaves the argument out.
    assert values == {"password": "s3cret", "hosts": ["a", "b"], "given": "x"}


def test_an_empty_answer_to_a_required_ask_argument_fails(monkeypatch) -> None:
    from types import SimpleNamespace

    import lib.runs.prompts as prompts
    from lib.plugins.exceptions import PluginValueError
    from lib.plugins.runner import PluginRunner

    class Store:
        def ask(self, job_id, *, name, **_):
            return name

        def wait(self, prompt):
            return ""

    monkeypatch.setenv(prompts.RUN_MODE_ENV, "interactive")
    monkeypatch.setattr(prompts, "prompts_for", lambda _: Store())
    context = SimpleNamespace(_entropy=None, node=None, job_id=1)

    with pytest.raises(PluginValueError, match="'password' needs a value"):
        PluginRunner._ask_marked(context, _ask_contract(), {"password": "${ask}"}, "demo.p")


def test_automated_runs_cannot_answer_ask_arguments(monkeypatch) -> None:
    from types import SimpleNamespace

    import lib.runs.prompts as prompts
    from lib.plugins.exceptions import PluginValueError
    from lib.plugins.runner import PluginRunner

    monkeypatch.setenv(prompts.RUN_MODE_ENV, "automated")
    context = SimpleNamespace(_entropy=None, node=None, job_id=1)

    with pytest.raises(PluginValueError, match="password is set to \\$\\{ask\\}"):
        PluginRunner._ask_marked(context, _ask_contract(), {"password": "${ask}"}, "demo.p")

    # Nothing marked: nothing to ask, even in automated runs.
    assert PluginRunner._ask_marked(context, None, {"a": "b"}, "demo.p") == {"a": "b"}


def test_ent_asks_ask_arguments_in_the_terminal(monkeypatch) -> None:
    from types import SimpleNamespace

    import lib.runs.prompts as prompts
    from lib.plugins.runner import PluginRunner

    monkeypatch.delenv(prompts.RUN_MODE_ENV, raising=False)
    monkeypatch.setattr("sys.stdin.isatty", lambda: True)
    monkeypatch.setattr("builtins.input", lambda label: " hello ")
    monkeypatch.setattr("getpass.getpass", lambda label: "s3cret")
    context = SimpleNamespace(_entropy=None, node=None, job_id=None)

    # Plugins without a contract are asked too.
    assert PluginRunner._ask_marked(
        context, None, {"user": "${ask}", "password": "${ask:secret}"}, "demo.p"
    ) == {"user": "hello", "password": "s3cret"}


def test_resolvers_leave_ask_markers_for_the_plugin_runner() -> None:
    from unittest.mock import Mock

    from lib.workflow.arguments import WorkflowArgumentResolver
    from lib.workflow.variables import WorkflowVariableResolver

    arguments = {"password": "${ask:secret}", "note": "${ask}", "plain": "x"}

    assert WorkflowVariableResolver(Mock(), 1, set()).resolve(arguments, {}) == arguments
    assert WorkflowArgumentResolver().resolve(arguments, variables={}, step_results={}) == arguments


def test_waiting_counts_only_count_unanswered_questions_of_the_runs_asked(store) -> None:
    answered = store.ask(1, name="a", label="A")
    store.ask(1, name="b", label="B")
    store.ask(1, name="c", label="C")
    store.ask(2, name="d", label="D")
    store.ask(3, name="e", label="E")
    store.answer(answered, "yes", "owner")

    assert store.waiting_counts([1, 2, 9]) == {1: 2, 2: 1}
    assert store.waiting_counts([]) == {}


def test_active_runs_are_marked_when_they_wait_on_someone(store) -> None:
    from types import SimpleNamespace

    from core.web.routes.runs import _add_waiting_counts

    store.ask(1, name="a", label="A")
    context = SimpleNamespace(database_manager=SimpleNamespace(connection=store.connection))
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(entropy_context=context)))
    items = [{"id": 1}, {"id": 2}]

    _add_waiting_counts(request, items)

    assert items == [{"id": 1, "waiting_for_input": 1}, {"id": 2, "waiting_for_input": 0}]
