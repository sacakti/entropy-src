"""
The command contract shared by every `ent` surface.

The local `ent` on the Entropy server, the remote `ent` client (ent.pyz) and
the browser shell (the remote client without the `ent`) all take their
resource names, verbs, aliases and output modes from here, kubectl/oc
style: `ent <resource> <verb> [name] [-o MODE]`.

Standard library only: this module ships inside ent.pyz.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Dict, Optional, Tuple

# ----------------------------------------------------------------------
# Output modes
# ----------------------------------------------------------------------

# detailed: titled, boxed tables with every column (the default).
# table:    plain columns like `oc get` / `kubectl get`.
# wide:     plain columns with the extra ones (`-o wide`).
# json / yaml: machine readable.  name: `resource/name` per line.
OUTPUT_MODES = ("detailed", "table", "wide", "json", "yaml", "name")
DEFAULT_OUTPUT = "detailed"
OUTPUT_ENV = "ENT_OUTPUT"

# The current project for one command, over the saved one.
PROJECT_ENV = "ENT_PROJECT"
PROJECT_HEADER = "X-Entropy-Project"

# Settings `ent config set KEY VALUE` keeps.
CONFIG_KEYS = {"output": OUTPUT_MODES}


class OutputModeError(ValueError):
    """An unknown output mode was asked for."""


def check_output(mode: str, origin: str = "-o") -> str:
    value = mode.strip().lower()
    if value not in OUTPUT_MODES:
        raise OutputModeError(
            f"{origin}: unknown output mode '{mode}'. Use one of: {', '.join(OUTPUT_MODES)}."
        )
    return value


def resolve_output(flag: Optional[str] = None, saved: Optional[str] = None) -> str:
    """The output mode: -o, else $ENT_OUTPUT, else the saved preference, else detailed."""

    if flag:
        return check_output(flag)
    environment = os.environ.get(OUTPUT_ENV, "").strip()
    if environment:
        return check_output(environment, OUTPUT_ENV)
    if saved:
        return check_output(saved, "ent config output")
    return DEFAULT_OUTPUT


# ----------------------------------------------------------------------
# Resources and verbs
# ----------------------------------------------------------------------


@dataclass(frozen=True)
class Verb:
    name: str
    help: str
    aliases: Tuple[str, ...] = ()
    # Where it exists: the local CLI on the server, and the remote client
    # (which the browser shell runs).
    local: bool = True
    remote: bool = True


@dataclass(frozen=True)
class Resource:
    name: str
    help: str
    aliases: Tuple[str, ...] = ()
    verbs: Tuple[Verb, ...] = field(default_factory=tuple)

    def verb(self, word: str) -> Optional[Verb]:
        for verb in self.verbs:
            if word == verb.name or word in verb.aliases:
                return verb
        return None


RESOURCES: Tuple[Resource, ...] = (
    Resource(
        "project",
        "The project commands work in.",
        ("projects", "proj"),
        (
            Verb("list", "Projects you can see.", ("ls",)),
            Verb("current", "The current project."),
            Verb("set", "Work in this project.", ("use",)),
            Verb("remove", "Back to the default project.", ("unset",)),
        ),
    ),
    Resource(
        "config",
        "Command line preferences (output).",
        (),
        (
            Verb("view", "Show the preferences in effect.", ("get",)),
            Verb("set", "Save a preference: config set output table."),
            Verb("unset", "Forget a preference."),
        ),
    ),
    Resource(
        "workflow",
        "Workflows of the current project.",
        ("workflows", "wf"),
        (
            Verb("list", "List workflows.", ("ls",)),
            Verb("get", "A workflow's definition (-o yaml|json).", ("show", "describe")),
            Verb("apply", "Create or update a workflow from a file (-f).", ("add", "replace")),
            Verb("validate", "Check a definition file without saving it."),
            Verb("delete", "Delete a workflow.", ("remove", "rm")),
            Verb("run", "Run a workflow.", ("start",)),
            Verb("history", "Kept earlier versions.", local=False),
            Verb("restore", "Restore a kept version.", local=False),
            Verb("edit", "Edit a workflow in $EDITOR.", remote=False),
        ),
    ),
    Resource(
        "job",
        "Runs of the current project.",
        ("jobs", "run", "runs"),
        (
            Verb("list", "List runs.", ("ls",)),
            Verb("get", "A run and its steps.", ("show", "describe")),
            Verb("logs", "Console output (-f to follow).", ("log",)),
            Verb("stop", "Stop a run."),
            Verb("wait", "Wait for a run; exit 0 if it completed."),
        ),
    ),
    Resource(
        "plugin",
        "Plugins.",
        ("plugins", "pl"),
        (
            Verb("list", "List plugins.", ("ls",)),
            Verb("run", "Run a plugin once."),
        ),
    ),
    Resource(
        "node", "Execution nodes.", ("nodes",), (Verb("list", "List nodes.", ("ls",), local=False),)
    ),
    Resource(
        "schedule",
        "Schedules.",
        ("schedules",),
        (Verb("list", "List schedules.", ("ls",), local=False),),
    ),
    Resource("user", "Users.", ("users",), (Verb("list", "List users.", ("ls",)),)),
    Resource("group", "Groups.", ("groups",), (Verb("list", "List groups.", ("ls",)),)),
    Resource("role", "Roles.", ("roles",), (Verb("list", "List roles.", ("ls",)),)),
    Resource(
        "vault",
        "Vault namespaces and keys (never values).",
        (),
        (
            Verb("namespaces", "Namespaces you can see.", ("ns",), local=False),
            Verb("list", "Keys in a namespace.", ("ls",)),
        ),
    ),
    Resource(
        "notification",
        "Your notifications.",
        ("notifications",),
        (Verb("list", "Recent notifications.", ("ls",), local=False),),
    ),
)


def resource(word: str) -> Optional[Resource]:
    """The resource a first word names (its name or an alias)."""

    for item in RESOURCES:
        if word == item.name or word in item.aliases:
            return item
    return None


def canonical_verb(resource_name: str, word: str) -> str:
    """The canonical verb for `word` (an alias or the name itself)."""

    item = resource(resource_name)
    verb = item.verb(word) if item else None
    return verb.name if verb else word


def describe() -> Dict[str, Dict[str, object]]:
    """The contract as data (served to the browser shell for completion)."""

    return {
        item.name: {
            "help": item.help,
            "aliases": list(item.aliases),
            "verbs": {
                verb.name: {"help": verb.help, "aliases": list(verb.aliases)}
                for verb in item.verbs
                if verb.remote
            },
        }
        for item in RESOURCES
    }
