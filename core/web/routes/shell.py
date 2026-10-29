"""
The web shell: `ent` commands typed in the browser, without the `ent`.

Each command runs the remote `ent` client (lib/remote_cli) in a short-lived
subprocess, logged in with the caller's own session, against this server's
API. So the shell can do exactly what the person could do in the web UI.
Commands that would read files on the server, prompt, or never end are
refused with a hint.

The shell and the ent client share one command contract
(lib/remote_cli/contract.py). It works in the web page's current project
(the X-Entropy-Project header), and `project set` and `config set output`
change the page's own project and output preference: the browser keeps
them and sends them with each command.
"""

from __future__ import annotations

import json
import os
import shlex
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field

from core.web.projects import PROJECT_HEADER, projects, visible_projects
from core.web.routes.auth import SESSION_COOKIE, _current_session, bearer_token, verify_csrf
from lib.models.session import Session
from lib.models.users import User
from lib.remote_cli import contract

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
    {"command": "project list | current", "description": "Projects; the one you work in."},
    {"command": "project set <key>", "description": "Work in another project (also: use)."},
    {"command": "workflow list", "description": "This project's workflows (also: wf ls)."},
    {"command": "workflow get <name> [-o yaml]", "description": "A workflow (also: show)."},
    {"command": "workflow run <name> [--var K=V] [--node N]", "description": "Start a run."},
    {"command": "workflow delete <name> -y", "description": "Delete a workflow (also: rm)."},
    {"command": "workflow history <name>", "description": "Kept earlier versions."},
    {"command": "job list [--state failed]", "description": "Runs (also: runs ls)."},
    {"command": "job get <id>", "description": "A run and its steps."},
    {"command": "job logs <id>", "description": "A run's console output."},
    {"command": "job stop <id>", "description": "Stop a run."},
    {"command": "plugin list", "description": "Plugins."},
    {"command": "plugin run <name> [--arg K=V]", "description": "Run a plugin once."},
    {"command": "node list", "description": "Execution nodes."},
    {"command": "schedule list", "description": "Schedules."},
    {"command": "user | group | role list", "description": "Users, groups, roles."},
    {"command": "vault ns", "description": "Vault namespaces you can see."},
    {"command": "vault ls <namespace>", "description": "Keys in a namespace (never values)."},
    {"command": "notification list --unread", "description": "Your notifications."},
    {
        "command": "... -o detailed|table|wide|json|yaml|name",
        "description": "Output mode of one command.",
    },
    {"command": "config set output <mode>", "description": "Your default output mode."},
    {"command": "<command> -h", "description": "Every option of a command."},
    {"command": "clear | exit", "description": "Clear the screen; close the shell (also: quit)."},
]

# First words the client understands (for completion in the browser).
VOCABULARY = sorted(
    {"help", "whoami", "status", "version", "clear", "exit", "quit"}
    | {item.name for item in contract.RESOURCES}
    | {alias for item in contract.RESOURCES for alias in item.aliases}
)


class ShellRequest(BaseModel):
    command: str = Field(min_length=1, max_length=2000)
    # The browser's saved `config set output` preference.
    output: Optional[str] = Field(default=None, max_length=20)


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


def run(
    argv: List[str],
    token: str,
    server: str,
    project: Optional[str] = None,
    output: Optional[str] = None,
) -> Dict[str, Any]:
    """Run the client once in a subprocess, signed in with `token`, in `project`."""

    shell_context: Dict[str, Any] = {"server": server, "token": token, "verify_tls": True}
    if project:
        shell_context["project"] = project

    with tempfile.TemporaryDirectory(prefix="entropy-shell-") as directory:
        config = Path(directory) / "config.json"
        descriptor = os.open(str(config), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(
                {"current": "shell", "contexts": {"shell": shell_context}},
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
        if output:
            environment[contract.OUTPUT_ENV] = output
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


def _result(
    stdout: str = "", stderr: str = "", exit_code: int = 0, **effects: Any
) -> Dict[str, Any]:
    result: Dict[str, Any] = {"exit_code": exit_code, "stdout": stdout, "stderr": stderr}
    if effects:
        # What the browser changes: its current project or output preference.
        result["effects"] = effects
    return result


def browser_settings(
    request: Request, user: User, argv: List[str], output: Optional[str]
) -> Optional[Dict[str, Any]]:
    """
    `project set|remove` and `config ...`: these are the page's own settings,
    so they are answered here and applied by the browser. None otherwise.
    """

    noun = contract.resource(argv[0])
    if noun is None or noun.name not in ("project", "config") or len(argv) < 2:
        return None
    verb = contract.canonical_verb(noun.name, argv[1])
    rest = [arg for arg in argv[2:] if not arg.startswith("-")]

    if noun.name == "project":
        if verb == "remove":
            return _result(
                "Project selection cleared; the default project is used.\n", project=None
            )
        if verb != "set":
            return None
        if len(rest) != 1:
            return _result(stderr="usage: project set KEY", exit_code=2)
        found = projects(request).get(rest[0])
        visible = visible_projects(request, user)
        if found is None or (visible is not None and found["id"] not in visible):
            return _result(
                stderr=f"error: No project '{rest[0]}' that you can see. See: project list",
                exit_code=1,
            )
        return _result(
            f"Now using project '{found['key']}' ({found['name']}).\n", project=found["key"]
        )

    if verb == "view":
        try:
            saved = contract.check_output(output) if output else None
        except contract.OutputModeError:
            saved = None
        mode = saved or contract.DEFAULT_OUTPUT
        return _result(f"output: {mode} ({'saved' if saved else 'default'})\n")
    if not rest or rest[0] not in contract.CONFIG_KEYS:
        return _result(stderr=f"usage: config {verb} output [MODE]", exit_code=2)
    if verb == "unset":
        return _result(f"Forgot output; using {contract.DEFAULT_OUTPUT}.\n", output=None)
    if len(rest) != 2:
        return _result(
            stderr=f"usage: config set output {{{','.join(contract.OUTPUT_MODES)}}}", exit_code=2
        )
    try:
        mode = contract.check_output(rest[1], "config set output")
    except contract.OutputModeError as exc:
        return _result(stderr=f"error: {exc}", exit_code=2)
    return _result(f"output set to {mode}.\n", output=mode)


@router.get("")
def shell_info(
    response: Response,
    record: SessionRecord = Depends(_current_session),
) -> Dict[str, Any]:
    response.headers["Cache-Control"] = "no-store"
    return {
        "commands": COMMANDS,
        "vocabulary": VOCABULARY,
        "resources": contract.describe(),
        "output_modes": list(contract.OUTPUT_MODES),
        "timeout_seconds": TIMEOUT_SECONDS,
    }


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

    output = payload.output
    if output:
        try:
            output = contract.check_output(output)
        except contract.OutputModeError:
            output = None

    settings = browser_settings(request, record[2], argv, output)
    if settings is not None:
        return settings

    project = (request.headers.get(PROJECT_HEADER) or "").strip() or None
    return run(argv, _session_token(request), _server_url(), project, output)
