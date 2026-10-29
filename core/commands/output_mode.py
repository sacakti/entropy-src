"""
Output modes for CLI commands, shared with the ent client and browser shell
(lib/remote_cli/contract.py): detailed by default, or `-o table|wide|json|
yaml|name`, `ENT_OUTPUT`, or the saved `ent config set output`.
"""

from __future__ import annotations

import json
from argparse import ArgumentParser, Namespace, _ArgumentGroup
from pathlib import Path
from typing import Any, Callable, Dict, Optional, Sequence

from lib.remote_cli.contract import OUTPUT_ENV, OUTPUT_MODES, resolve_output
from lib.remote_cli.output import Column, render


def add_output_argument(
    parser: ArgumentParser | _ArgumentGroup,
) -> None:
    """
    Add `-o/--output` to a command (or to a group of exclusive options).
    """

    parser.add_argument(
        "-o",
        "--output",
        choices=OUTPUT_MODES,
        help=f"Output mode (default: ${OUTPUT_ENV}, then `ent config set output`, then detailed).",
    )


class Preferences:
    """
    Per-user CLI preferences: <home>/config/cli-preferences.json.
    """

    def __init__(
        self,
        context: Any,
    ) -> None:

        assert context.bootstrap is not None

        self.path = Path(context.bootstrap.home) / "config" / "cli-preferences.json"

    def _all(self) -> Dict[str, Dict[str, str]]:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except (OSError, ValueError):
            return {}

    def get(self, user_id: int, key: str) -> Optional[str]:
        value = self._all().get(str(user_id), {}).get(key)
        return str(value) if value else None

    def set(self, user_id: int, key: str, value: Optional[str]) -> None:
        data = self._all()
        mine = data.setdefault(str(user_id), {})
        if value is None:
            mine.pop(key, None)
        else:
            mine[key] = value
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        temporary.replace(self.path)


def output_mode(
    context: Any,
    args: Namespace,
) -> str:
    """
    -o, else $ENT_OUTPUT, else the user's saved preference, else detailed.
    """

    saved = None
    session = context.session_manager.current() if context.session_manager else None
    if session is not None:
        saved = Preferences(context).get(session.user_id, "output")
    return resolve_output(getattr(args, "output", None), saved)


def _cell(value: Any) -> str:
    return "" if value is None else str(value)


def emit(
    context: Any,
    args: Namespace,
    *,
    title: str,
    columns: Sequence[Column],
    items: Sequence[Any],
    kind: str,
    name: Optional[Callable[[Any], Any]] = None,
    data: Any = None,
) -> None:
    """
    Show `items` in the command's output mode. Detailed uses the console's
    own tables; the other modes print plain text, like the ent client.
    """

    mode = output_mode(context, args)

    if mode == "detailed":
        if not items:
            context.ui.info(f"No {kind}s found.")
            return
        context.ui.table(
            title=title,
            columns=[column[0].title() for column in columns],
            rows=[[_cell(column[1](item)) for column in columns] for item in items],
        )
        return

    text = render(mode, items, columns, title=title, kind=kind, name=name, data=data)
    if text:
        context.ui.text(text)
