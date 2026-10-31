"""
Workflow variables set to ${ask} / ${ask:secret} are entered when the run starts.
"""

from __future__ import annotations

from unittest.mock import Mock

import pytest

from lib.models.workflow import Workflow, WorkflowExecutionOptions, WorkflowStep
from lib.runs.prompts import PromptError
from lib.workflow.arguments import WorkflowArgumentResolver
from lib.workflow.exceptions import WorkflowArgumentError
from lib.workflow.overrides import WorkflowArgumentOverrides
from lib.workflow.variables import WorkflowVariableResolver
from lib.workflow.variables.ask import DRY_RUN_PLACEHOLDER, ask_marker, asked_variables

# ----------------------------------------------------------------------
# Marker
# ----------------------------------------------------------------------


@pytest.mark.parametrize(
    "value, expected",
    [
        ("${ask}", False),
        (" ${ask} ", False),
        ("${ask:secret}", True),
        ("${askme}", None),
        ("${ask:other}", None),
        ("prefix ${ask}", None),
        ("", None),
        (None, None),
        (5, None),
        ({"ask": True}, None),
    ],
)
def test_ask_marker(value, expected) -> None:
    assert ask_marker(value) is expected


def test_asked_variables_keeps_order_and_secrecy() -> None:
    variables = {"environment": "SIT", "release": "${ask}", "password": "${ask:secret}"}

    assert asked_variables(variables) == {"release": False, "password": True}


# ----------------------------------------------------------------------
# Runner
# ----------------------------------------------------------------------


class FakeStore:
    def __init__(self, answers: dict) -> None:
        self.answers = answers
        self.asked: list[dict] = []

    def ask(self, job_id: int, **prompt) -> str:
        self.asked.append({"job_id": job_id, **prompt})
        return prompt["name"]

    def wait(self, prompt: str) -> str:
        answer = self.answers[prompt]
        if isinstance(answer, Exception):
            raise answer
        return answer


def _with_variables(runtime, **variables) -> None:
    runtime.set_variables(variables)


def test_nothing_to_ask_changes_nothing(workflow_runner, runtime, monkeypatch) -> None:
    monkeypatch.setenv("ENTROPY_RUN_MODE", "automated")
    _with_variables(runtime, environment="SIT")

    workflow_runner._ask_variables(runtime, set())

    assert runtime.variables == {"environment": "SIT"}


def test_terminal_run_asks_in_the_terminal(workflow_runner, runtime, monkeypatch) -> None:
    monkeypatch.delenv("ENTROPY_RUN_MODE", raising=False)
    monkeypatch.setattr("sys.stdin.isatty", lambda: True)
    typed = iter(["", " H010 "])
    monkeypatch.setattr("builtins.input", lambda label: next(typed))
    monkeypatch.setattr("getpass.getpass", lambda label: "s3cret")
    _with_variables(runtime, environment="SIT", release="${ask}", password="${ask:secret}")
    secrets: set = set()

    workflow_runner._ask_variables(runtime, secrets)

    # An empty answer is asked again.
    assert runtime.variables == {"environment": "SIT", "release": "H010", "password": "s3cret"}
    assert secrets == {"s3cret"}


def test_interactive_run_asks_on_the_run_screen(workflow_runner, runtime, monkeypatch) -> None:
    monkeypatch.setenv("ENTROPY_RUN_MODE", "interactive")
    store = FakeStore({"release": "H010", "password": "s3cret"})
    monkeypatch.setattr("lib.runs.prompts.prompts_for", lambda context: store)
    runtime.job_id = 42
    _with_variables(runtime, release="${ask}", password="${ask:secret}", environment="SIT")
    secrets: set = set()

    workflow_runner._ask_variables(runtime, secrets)

    assert runtime.variables == {"release": "H010", "password": "s3cret", "environment": "SIT"}
    assert secrets == {"s3cret"}
    # Every question is posted before any answer is awaited.
    assert [(item["job_id"], item["name"], item["secret"]) for item in store.asked] == [
        (42, "release", False),
        (42, "password", True),
    ]


@pytest.mark.parametrize(
    "answer, message",
    [
        ("", "needs a value"),
        (PromptError("No answer within an hour."), "was not entered: No answer"),
    ],
)
def test_interactive_run_fails_without_an_answer(
    workflow_runner, runtime, monkeypatch, answer, message
) -> None:
    monkeypatch.setenv("ENTROPY_RUN_MODE", "interactive")
    monkeypatch.setattr(
        "lib.runs.prompts.prompts_for", lambda context: FakeStore({"release": answer})
    )
    runtime.job_id = 42
    _with_variables(runtime, release="${ask}")

    with pytest.raises(WorkflowArgumentError, match=message):
        workflow_runner._ask_variables(runtime, set())


def test_automated_run_fails_up_front(workflow_runner, runtime, monkeypatch) -> None:
    monkeypatch.setenv("ENTROPY_RUN_MODE", "automated")
    _with_variables(runtime, release="${ask}", password="${ask:secret}")

    with pytest.raises(WorkflowArgumentError, match="release, password must be entered"):
        workflow_runner._ask_variables(runtime, set())


def test_terminal_run_without_a_terminal_fails(workflow_runner, runtime, monkeypatch) -> None:
    monkeypatch.delenv("ENTROPY_RUN_MODE", raising=False)
    monkeypatch.setattr("sys.stdin.isatty", lambda: False)
    _with_variables(runtime, release="${ask}")

    with pytest.raises(WorkflowArgumentError, match="--var NAME=VALUE"):
        workflow_runner._ask_variables(runtime, set())


# ----------------------------------------------------------------------
# Dry run
# ----------------------------------------------------------------------


def test_dry_run_accepts_asked_variables(workflow_runner) -> None:
    workflow_runner._argument_overrides = WorkflowArgumentOverrides()
    workflow_runner._argument_resolver = WorkflowArgumentResolver()
    workflow = Workflow(
        name="deploy",
        version="1.0.0",
        variables={"release": "${ask}"},
        steps=[
            WorkflowStep(name="extract", plugin="custom.demo", arguments={"path": "${release}"})
        ],
    )

    result = workflow_runner._validate_dry_run(
        workflow=workflow,
        steps=workflow.steps,
        resolver=WorkflowVariableResolver(Mock(), 1, set()),
        options=WorkflowExecutionOptions(),
    )

    assert result.errors == []
    assert DRY_RUN_PLACEHOLDER == "<entered at run time>"
