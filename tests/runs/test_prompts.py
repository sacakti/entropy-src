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
    with pytest.raises(PluginValueError, match="automated"):
        context.ask("Code", secret=True)
    assert os.environ[RUN_MODE_ENV] == "automated"
