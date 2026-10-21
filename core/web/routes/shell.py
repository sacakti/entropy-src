"""
The web shell: `ent` commands typed in the browser, without the `ent`.

Each command runs the remote `ent` client (lib/remote_cli) in a short-lived
subprocess, logged in with the caller's own session, against this server's
API. So the shell can do exactly what the person could do in the web UI.
Commands that would read files on the server, prompt, or never end are
refused with a hint.
"""

from __future__ import annotations

import json
import os
import shlex
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Tuple

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field

from core.web.routes.auth import SESSION_COOKIE, _current_session, bearer_token, verify_csrf
from lib.models.session import Session
from lib.models.users import User

router = APIRouter(prefix="/api/shell", tags=["shell"])

SessionRecord = Tuple[Session, str, User]

PROJECT_ROOT = Path(__file__).resolve().parents[3]
TIMEOUT_SECONDS = 30
MAX_OUTPUT = 200_000

# The shell is already signed in, and these manage the client's own login.
SESSION_COMMANDS = {"login", "logout", "auth", "context", "ctx"}
# Flags and actions that wait for a run to end: open the run instead.
FOLLOW_FLAGS = {"-f", "-F", "--follow"}
FILE_FLAGS = {"--file", "--certificate-authority"}

COMMANDS = [
    {"command": "whoami", "description": "Who you are signed in as."},
    {"command": "workflow list", "description": "Workflows (also: wf ls)."},
    {"command": "workflow get <name> -o yaml", "description": "A workflow's definition."},
    {"command": "workflow run <name> [--var K=V] [--node N]", "description": "Start a run."},
    {"command": "workflow history <name>", "description": "Kept earlier versions."},
    {"command": "job list [--state failed]", "description": "Runs (also: runs ls)."},
    {"command": "job get <id>", "description": "A run and its steps."},
    {"command": "job logs <id>", "description": "A run's console output."},
    {"command": "job stop <id>", "description": "Stop a run."},
    {"command": "plugin list", "description": "Plugins."},
    {"command": "plugin run <name> [--arg K=V]", "description": "Run a plugin once."},
    {"command": "node list", "description": "Execution nodes."},
    {"command": "schedule list", "description": "Schedules."},
    {"command": "user list", "description": "Users (administrators)."},
    {"command": "group list", "description": "Groups."},
    {"command": "role list", "description": "Roles."},
    {"command": "vault ns", "description": "Vault namespaces you can see."},
    {"command": "vault ls <namespace>", "description": "Keys in a namespace (never values)."},
    {"command": "notification list --unread", "description": "Your notifications."},
    {"command": "<command> -h", "description": "Every option of a command."},
]

# First words the client understands (for completion in the browser).
VOCABULARY = sorted(
    {
        "help",
        "whoami",
        "status",
        "version",
        "workflow",
        "wf",
        "workflows",
        "job",
        "jobs",
        "run",
        "runs",
        "plugin",
        "plugins",
        "pl",
        "node",
        "nodes",
        "schedule",
        "schedules",
        "user",
        "users",
        "group",
        "groups",
        "role",
        "roles",
        "vault",
        "notification",
        "notifications",
        "clear",
    }
)


class ShellRequest(BaseModel):
    command: str = Field(min_length=1, max_length=2000)


def _session_token(request: Request) -> str:
    token = bearer_token(request) or request.cookies.get(SESSION_COOKIE)
    if not token:
        raise HTTPException(status_code=401, detail="Authentication required.")
    return token


def _server_url() -> str:
    """This server as seen from itself."""

    from lib.nodes.reach import ALL_INTERFACES, bind_address, is_loopback

    host, port = bind_address()
    if host in ALL_INTERFACES or is_loopback(host):
        host = "127.0.0.1"
    shown = f"[{host}]" if ":" in host else host
    return f"http://{shown}:{port}"


def parse(command: str) -> List[str]:
    """The client's arguments, or ValueError with what to do instead."""

    try:
        argv = shlex.split(command)
    except ValueError as exc:
        raise ValueError(f"Cannot parse the command: {exc}.") from None
    if argv and argv[0] == "ent":
        argv = argv[1:]
    if not argv:
        raise ValueError("Type a command, e.g. workflow list. Type help for more.")

    first = argv[0]
    if first in SESSION_COMMANDS:
        raise ValueError(
            "The shell is signed in as you; sign in as someone else from the web page."
        )
    if first not in VOCABULARY and not first.startswith("-"):
        raise ValueError(f"Unknown command '{first}'. Type help to see the commands.")
    if any(arg in FILE_FLAGS or arg.startswith("--file=") for arg in argv) or (
        len(argv) > 1 and argv[1] in ("apply", "validate")
    ):
        raise ValueError(
            "Commands that read files are not available in the web shell. Use the workflow "
            "builder or Import, or the ent command line on your computer."
        )
    if any(arg in FOLLOW_FLAGS for arg in argv) or (len(argv) > 1 and argv[1] == "wait"):
        raise ValueError(
            "The shell does not wait for runs to end. Start the run, then open it in Runs "
            "(or run: job logs <id>)."
        )
    return argv


def run(argv: List[str], token: str, server: str) -> Dict[str, Any]:
    """Run the client once in a subprocess, signed in with `token`."""

    with tempfile.TemporaryDirectory(prefix="entropy-shell-") as directory:
        config = Path(directory) / "config.json"
        descriptor = os.open(str(config), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(
                {
                    "current": "shell",
                    "contexts": {"shell": {"server": server, "token": token, "verify_tls": True}},
                },
                handle,
            )
        environment = {
            "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
            "HOME": directory,
            "ENT_CONFIG": str(config),
            "PYTHONPATH": str(PROJECT_ROOT),
            "PYTHONIOENCODING": "utf-8",
            "COLUMNS": "160",
            "LANG": "C.UTF-8",
        }
        try:
            completed = subprocess.run(
                [sys.executable, "-m", "lib.remote_cli", *argv],
                cwd=directory,
                env=environment,
                stdin=subprocess.DEVNULL,
                capture_output=True,
                timeout=TIMEOUT_SECONDS,
            )
        except subprocess.TimeoutExpired as exc:
            output = (exc.stdout or b"").decode("utf-8", "replace")
            return {
                "exit_code": 124,
                "stdout": output[-MAX_OUTPUT:],
                "stderr": f"Stopped after {TIMEOUT_SECONDS} seconds.",
            }

    stdout = completed.stdout.decode("utf-8", "replace")
    stderr = completed.stderr.decode("utf-8", "replace")
    # argparse names the program after the module; the shell needs no prefix.
    for before, after in (
        ("usage: __main__.py", "usage:"),
        ("usage: ent", "usage:"),
        ("ent: error:", "error:"),
    ):
        stdout = stdout.replace(before, after)
        stderr = stderr.replace(before, after)
    return {
        "exit_code": completed.returncode,
        "stdout": stdout[:MAX_OUTPUT],
        "stderr": stderr[:MAX_OUTPUT],
    }


@router.get("")
def shell_info(
    response: Response,
    record: SessionRecord = Depends(_current_session),
) -> Dict[str, Any]:
    response.headers["Cache-Control"] = "no-store"
    return {"commands": COMMANDS, "vocabulary": VOCABULARY, "timeout_seconds": TIMEOUT_SECONDS}


@router.post("/exec", dependencies=[Depends(verify_csrf)])
def execute(
    payload: ShellRequest,
    request: Request,
    response: Response,
    record: SessionRecord = Depends(_current_session),
) -> Dict[str, Any]:
    response.headers["Cache-Control"] = "no-store"
    command = payload.command.strip()
    try:
        argv = parse(command)
    except ValueError as exc:
        return {"exit_code": 2, "stdout": "", "stderr": str(exc)}

    if argv[0] == "help":
        width = max(len(item["command"]) for item in COMMANDS)
        lines = [f"  {item['command'].ljust(width)}   {item['description']}" for item in COMMANDS]
        text = "Commands (type them without 'ent'):\n" + "\n".join(lines) + "\n"
        return {"exit_code": 0, "stdout": text, "stderr": ""}

    return run(argv, _session_token(request), _server_url())
