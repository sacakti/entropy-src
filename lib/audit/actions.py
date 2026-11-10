"""
Names for audited API calls, derived from the route template.

`POST /api/workflows/{name}/run`   -> workflows.run
`DELETE /api/tasks/{task_id}`      -> tasks.delete
`POST /api/tasks/{task_id}/comments` -> tasks.comments.create
`PUT /api/admin/users/{username}`  -> users.update

New routes are named the same way without a list to maintain.
"""

from __future__ import annotations

import re
from typing import Dict, Optional, Tuple

# Last path words that are verbs: POST /x/{id}/<verb> is "<verb>", not "create <verb>".
VERBS = {
    "activate",
    "answer",
    "apply",
    "approve",
    "archive",
    "assign",
    "attach",
    "backup",
    "bulk-delete",
    "bulk-download",
    "cancel",
    "change-password",
    "check",
    "clone",
    "commit",
    "copy",
    "deactivate",
    "disable",
    "download",
    "duplicate",
    "enable",
    "events",
    "execute",
    "export",
    "finish",
    "fire",
    "follow",
    "generate",
    "housekeeping",
    "import",
    "install",
    "keepalive",
    "link",
    "login",
    "logout",
    "move",
    "pause",
    "promote",
    "publish",
    "purge",
    "push",
    "rename",
    "reorder",
    "rerun",
    "reset",
    "restart",
    "restore",
    "resume",
    "reveal",
    "revoke",
    "rollback",
    "run",
    "save",
    "setup",
    "start",
    "stop",
    "switch",
    "sync",
    "test",
    "token",
    "tour",
    "trigger",
    "uninstall",
    "unlink",
    "upgrade",
    "upload",
    "validate",
    "verify",
}
METHOD_VERBS = {
    "POST": "create",
    "PUT": "update",
    "PATCH": "update",
    "DELETE": "delete",
    "GET": "view",
}
# /api/admin/<area>/... is filed under the area (users, groups, roles, settings, ...).
CONTAINERS = {"admin"}
PARAM = re.compile(r"^\{[^}]+\}$")


def describe(method: str, template: str) -> Tuple[str, str]:
    """(category, action) of an API call from its route template."""

    words = [part for part in template.strip("/").split("/") if part]
    if words and words[0] == "api":
        words = words[1:]
    static = [word for word in words if not PARAM.match(word)]
    while len(static) > 1 and static[0] in CONTAINERS:
        static = static[1:]
    if not static:
        return "api", METHOD_VERBS.get(method.upper(), method.lower())
    category, rest = static[0], [_clean(word) for word in static[1:]]
    reads = ("report", "content", "preview")
    if rest and (rest[-1] in VERBS or (method.upper() == "GET" and rest[-1] in reads)):
        verb = rest.pop()
    elif method.upper() == "GET" and words and words[-1].startswith("ent."):
        verb = "download"
    else:
        verb = METHOD_VERBS.get(method.upper(), method.lower())
    return category, ".".join([category, *rest, verb])


def target(path_params: Dict[str, object], body_name: Optional[str] = None) -> Optional[str]:
    """What was acted on: the route's identifiers (e.g. "deploy", "#42"), else the body's name."""

    parts = []
    for key, value in path_params.items():
        text = str(value)
        parts.append(f"#{text}" if key.endswith("id") and text.isdigit() else text)
    if body_name and body_name not in parts:
        parts.append(body_name)
    return " / ".join(parts) or None


def _clean(word: str) -> str:
    """`report.xlsx` -> `report`; `ent.pyz` -> `ent`."""

    return word.split(".")[0] or word
