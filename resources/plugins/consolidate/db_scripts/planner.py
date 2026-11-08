"""
Build one execution plan from the execution plans of several releases.

Unlike configuration, database scripts have no net result: each one changes the
database, so every script of every release runs, in release order, and none is
merged, skipped or edited.

Each execution of a release becomes one plan entry with its own folder,
<release>__<application>. An application may be grouped (DBScripts/H01/App1,
plan key 'H01/App1'); its folder is then <release>__H01__App1, so the
consolidated package stays one level deep. sqlplus.generic runs a calling script from its folder
in a new session under its plan's schema, so a script behaves as in its own
release: `@file` and `@@file` find the same files, and an `exit` ends only that
script. The plan keeps the order, including across applications.

No I/O happens here; the plugin reads the plans and copies the scripts.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import PurePosixPath
from typing import Any, Dict, List

from .exceptions import ConsolidationDefinitionError

SEPARATOR = "__"


# ----------------------------------------------------------------------
# Model
# ----------------------------------------------------------------------


@dataclass
class Entry:
    """One execution: an application's calling script, from one release."""

    release: str
    source_application: str
    schema: str
    calling_script: str
    # Other fields of the release's plan entry, kept as they are.
    extra: Dict[str, Any] = field(default_factory=dict)

    @property
    def application(self) -> str:
        return SEPARATOR.join([self.release, *self.source_application.split("/")])

    def definition(self) -> Dict[str, Any]:
        return {**self.extra, "schema": self.schema, "calling_script": self.calling_script}

    def report(self) -> Dict[str, str]:
        return {
            "application": self.application,
            "release": self.release,
            "source_application": self.source_application,
            "schema": self.schema,
            "calling_script": self.calling_script,
        }


@dataclass
class Plan:
    """The executions of all releases, in the order they must run."""

    entries: List[Entry] = field(default_factory=list)

    def add(self, entry: Entry) -> None:
        self.entries.append(entry)

    def document(self) -> Dict[str, Any]:
        return {"applications": {entry.application: entry.definition() for entry in self.entries}}


# ----------------------------------------------------------------------
# Parsing
# ----------------------------------------------------------------------


def parse_plan(plan: Any, release: str) -> List[Entry]:
    """Validate a release's execution plan as sqlplus.generic does."""

    applications = plan.get("applications") if isinstance(plan, dict) else None

    if not isinstance(applications, dict) or not applications:
        raise ConsolidationDefinitionError(
            f"Release '{release}': the execution plan needs a non-empty 'applications' mapping."
        )

    return [
        _entry(application, definition, release) for application, definition in applications.items()
    ]


def _entry(application: Any, definition: Any, release: str) -> Entry:
    where = f"Release '{release}'"

    # A folder under DBScripts: 'App1', or 'H01/App1' when applications are grouped.
    parts = (
        [part.strip() for part in application.replace("\\", "/").split("/")]
        if isinstance(application, str)
        else []
    )

    if (
        not parts
        or application.startswith(("/", "\\"))
        or any(part in ("", ".", "..") for part in parts)
    ):
        raise ConsolidationDefinitionError(
            f"{where}: application name '{application}' must be a folder under "
            "DBScripts, such as 'App1' or 'H01/App1'."
        )

    if not isinstance(definition, dict):
        raise ConsolidationDefinitionError(
            f"{where}: execution plan entry '{application}' must be a mapping."
        )

    schema = definition.get("schema")
    if not isinstance(schema, str) or not schema.strip():
        raise ConsolidationDefinitionError(
            f"{where}: schema is missing for application '{application}'."
        )

    calling_script = definition.get("calling_script")
    if not isinstance(calling_script, str) or not calling_script.strip():
        raise ConsolidationDefinitionError(
            f"{where}: calling script is missing for application '{application}'."
        )

    return Entry(
        release=release,
        source_application="/".join(parts),
        schema=str(schema).strip(),
        # sqlplus.generic finds a calling script by file name in its application's folder.
        calling_script=PurePosixPath(calling_script.strip()).name,
        extra={
            str(key): value
            for key, value in definition.items()
            if key not in ("schema", "calling_script")
        },
    )
