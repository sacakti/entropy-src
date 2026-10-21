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
