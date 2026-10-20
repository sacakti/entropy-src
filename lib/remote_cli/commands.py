"""
The `ent` commands for a remote Entropy server.

    ent login https://entropy.example.com
    ent workflow list
    ent workflow run deploy --var env=uat --follow
    ent job logs 42 -f
"""

from __future__ import annotations

import argparse
import contextlib
import getpass
import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from . import client_version
from .api import ApiError, Client, path
from .config import Config, ConfigError, context_name, normalize_server
from .output import emit_json, table, when

TERMINAL = ("completed", "failed", "cancelled")
STATE_EXIT = {"completed": 0, "failed": 1, "cancelled": 130}


class CommandError(Exception):
    """A user-facing failure; printed without a traceback."""


# ----------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------


def _client(args: argparse.Namespace) -> Client:
    context = Config.load().current(getattr(args, "context", None))
    if not context.get("token"):
        raise CommandError(f"Not logged in to {context['server']}. Run: ent login")
    return Client.for_context(context)


def _values(pairs: Optional[List[str]], what: str) -> Dict[str, Any]:
    """KEY=VALUE pairs; values are JSON when they parse as JSON, else text."""

    values: Dict[str, Any] = {}
    for pair in pairs or []:
        key, separator, value = pair.partition("=")
        if not separator or not key.strip():
            raise CommandError(f"{what} must look like KEY=VALUE, not '{pair}'.")
        try:
            values[key.strip()] = json.loads(value)
        except ValueError:
            values[key.strip()] = value
    return values


def _definition(file: str) -> Dict[str, str]:
    source = Path(file).expanduser()
    if not source.is_file():
        raise CommandError(f"No such file: {file}")
    suffix = source.suffix.lower()
    format_name = {".json": "json", ".yaml": "yaml", ".yml": "yaml"}.get(suffix)
    if format_name is None:
        raise CommandError("Workflow files must end in .json, .yaml or .yml.")
    return {"definition": source.read_text(encoding="utf-8"), "format": format_name}


def _confirm(question: str, assume_yes: bool) -> None:
    if assume_yes:
        return
    if not sys.stdin.isatty():
        raise CommandError(f"{question} Add --yes to confirm when not running interactively.")
    if input(f"{question} [y/N]: ").strip().lower() not in ("y", "yes"):
        raise CommandError("Cancelled.")


def _follow(client: Client, job_id: int, quiet: bool = False) -> int:
    """Print a run's console output until it ends; return its exit status."""

    offset = 0
    state = "queued"
    idle_after_end = 0
    while True:
        chunk = client.get(path("runs", job_id, "log"), offset=offset)
        if chunk and chunk.get("text"):
            if not quiet:
                sys.stdout.write(chunk["text"])
                sys.stdout.flush()
            offset = chunk["offset"]
        state = client.get(path("runs", job_id))["run"]["state"]
        if state in TERMINAL:
            # Let the last lines arrive (remote nodes forward them in batches).
            if not chunk or not chunk.get("text"):
                idle_after_end += 1
            if idle_after_end >= 2:
                break
        time.sleep(1.0)
    print(f"\nRun #{job_id} {state}.", file=sys.stderr)
    return STATE_EXIT.get(state, 1)


# ----------------------------------------------------------------------
# Session
# ----------------------------------------------------------------------


def cmd_login(args: argparse.Namespace) -> int:
    config = Config.load()
    existing: Dict[str, Any] = {}
    if args.server:
        server = normalize_server(args.server)
        name = args.name or config.find_server(server) or context_name(server)
        existing = dict(config.contexts.get(name, {}))
    else:
        try:
            existing = config.current(getattr(args, "context", None))
        except ConfigError:
            raise CommandError(
                "Give the server URL: ent login https://entropy.example.com"
            ) from None
        server, name = existing["server"], args.name or existing["name"]

    verify_tls = not args.insecure_skip_tls_verify and existing.get("verify_tls", True)
    ca_file = args.certificate_authority or existing.get("ca_file")
    if ca_file:
        ca_file = str(Path(ca_file).expanduser().resolve())
    client = Client(server, verify_tls=verify_tls, ca_file=ca_file)

    if args.token:
        client.token = args.token.strip()
        me = client.get("/auth/me")
        user, expires = me["user"], me.get("expires_at")
        token = client.token
    else:
        username = args.username or os.environ.get("ENT_USERNAME")
        if not username:
            default = existing.get("username") or ""
            username = input(f"Username{f' [{default}]' if default else ''}: ").strip() or default
        if args.password_stdin:
            password = sys.stdin.readline().rstrip("\n")
        else:
            password = os.environ.get("ENT_PASSWORD") or getpass.getpass("Password: ")
        if not username or not password:
            raise CommandError("A username and password are needed.")
        result = client.post("/auth/token", {"username": username, "password": password})
        user, expires, token = result["user"], result.get("expires_at"), result["token"]

    config.upsert(
        name,
        {
            "server": server,
            "token": token,
            "username": user["username"],
            "verify_tls": verify_tls,
            "ca_file": ca_file,
            "expires_at": expires,
        },
    )
    config.save()

    if server.startswith("http://") and not any(
        local in server for local in ("://localhost", "://127.", "://[::1]")
    ):
        print(
            "Warning: this server uses plain HTTP; your token travels unencrypted.", file=sys.stderr
        )
    print(f"Logged in to {server} as {user['username']} (context '{name}').")
    if expires:
        print(f"The session lasts until {when(expires)}.")
    return 0


def cmd_logout(args: argparse.Namespace) -> int:
    config = Config.load()
    context = config.current(getattr(args, "context", None))
    if context.get("token"):
        # Expired or unreachable: forget it locally anyway.
        with contextlib.suppress(ApiError):
            Client.for_context(context).delete("/auth/token")
    config.contexts[context["name"]].pop("token", None)
    config.contexts[context["name"]].pop("expires_at", None)
    config.save()
    print(f"Logged out of {context['server']}.")
    return 0


def cmd_whoami(args: argparse.Namespace) -> int:
    me = _client(args).get("/auth/me")
    if args.output == "json":
        emit_json(me)
        return 0
    user = me["user"]
    print(user["username"] + (f" ({user['full_name']})" if user.get("full_name") else ""))
    if args.verbose:
        print("Permissions:")
        for permission in sorted(me.get("permissions", [])):
            print(f"  {permission}")
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    config = Config.load()
    context = config.current(getattr(args, "context", None))
    client = Client.for_context(context)
    server_version = client.get("/version").get("version", "?")
    print(f"Context:  {context['name']}")
    print(f"Server:   {context['server']} (Entropy {server_version})")
    print(f"Client:   ent {client_version()}")
    if not context.get("token"):
        print("User:     not logged in (run: ent login)")
        return 1
    try:
        me = client.get("/auth/me")
    except ApiError as error:
        print(f"User:     {error}")
        return 1
    print(f"User:     {me['user']['username']}")
    print(f"Session:  until {when(me.get('expires_at'))}")
    return 0


def cmd_version(args: argparse.Namespace) -> int:
    print(f"Client: ent {client_version()}")
    try:
        context = Config.load().current(getattr(args, "context", None))
        server = Client.for_context(context).get("/version")
        print(f"Server: Entropy {server.get('version')} ({context['server']})")
    except (ConfigError, ApiError) as error:
        print(f"Server: unknown ({error})")
    return 0


def cmd_context(args: argparse.Namespace) -> int:
    config = Config.load()
    if args.action == "list":
        rows = []
        for name, context in sorted(config.contexts.items()):
            rows.append(
                (
                    "*" if name == config.current_name else "",
                    name,
                    context.get("server"),
                    context.get("username") if context.get("token") else "(logged out)",
                )
            )
        table(("current", "name", "server", "user"), rows)
        return 0
    if not args.name:
        raise CommandError(f"Give the context name: ent context {args.action} NAME")
    if args.name not in config.contexts:
        raise CommandError(f"No context named '{args.name}'.")
    if args.action == "use":
        config.data["current"] = args.name
        print(f"Using context '{args.name}' ({config.contexts[args.name]['server']}).")
    else:
        del config.contexts[args.name]
        if config.current_name == args.name:
            config.data["current"] = next(iter(config.contexts), None)
        print(f"Deleted context '{args.name}'.")
    config.save()
    return 0


# ----------------------------------------------------------------------
# Workflows
# ----------------------------------------------------------------------


def cmd_workflow_list(args: argparse.Namespace) -> int:
    items = _client(args).get("/workflows")["items"]
    if args.output == "json":
        emit_json(items)
        return 0
    table(
        ("name", "version", "updated", "description"),
        ((w["name"], w["version"], when(w.get("updated_at")), w.get("description")) for w in items),
    )
    return 0


def cmd_workflow_get(args: argparse.Namespace) -> int:
    detail = _client(args).get(path("workflows", args.name), format=args.output)
    print(detail["definition"].rstrip("\n"))
    return 0


def cmd_workflow_validate(args: argparse.Namespace) -> int:
    result = _client(args).post("/workflows/validate", _definition(args.file))["workflow"]
    print(
        f"Valid: {result['name']} {result['version']} with "
        f"{result['step_count']} step{'' if result['step_count'] == 1 else 's'}."
    )
    return 0


def cmd_workflow_apply(args: argparse.Namespace) -> int:
    client = _client(args)
    body = _definition(args.file)
    name = client.post("/workflows/validate", body)["workflow"]["name"]
    try:
        client.get(path("workflows", name))
        exists = True
    except ApiError as error:
        if error.status != 404:
            raise
        exists = False
    if exists:
        result = client.put(path("workflows", name), body)
        print(f"Workflow '{name}' updated (version {result['version']}).")
    else:
        result = client.post("/workflows", body)
        print(f"Workflow '{name}' created (version {result['version']}).")
    return 0


def cmd_workflow_delete(args: argparse.Namespace) -> int:
    _confirm(f"Delete workflow '{args.name}'?", args.yes)
    _client(args).delete(path("workflows", args.name))
    print(f"Workflow '{args.name}' deleted.")
    return 0


def cmd_workflow_run(args: argparse.Namespace) -> int:
    client = _client(args)
    body: Dict[str, Any] = {"node": args.node, "variables": _values(args.var, "--var")}
    if args.tag:
        body["tags"] = args.tag
    if args.step:
        body["steps"] = args.step
    if args.step_node:
        body["step_nodes"] = {
            key: str(value) for key, value in _values(args.step_node, "--step-node").items()
        }
    run = client.post(path("workflows", args.name, "run"), body)["run"]
    print(f"Run #{run['id']} started on {run['node']}.", file=sys.stderr)
    if args.follow:
        return _follow(client, run["id"])
    print(run["id"])
    return 0


def cmd_workflow_history(args: argparse.Namespace) -> int:
    history = _client(args).get(path("workflows", args.name, "history"))
    if args.output == "json":
        emit_json(history)
        return 0
    print(f"Current version: {history['current_version']}")
    table(
        ("id", "version", "kept", "by", "reason"),
        (
            (i["id"], i["version"], when(i["created_at"]), i.get("created_by"), i["reason"])
            for i in history["items"]
        ),
    )
    return 0


def cmd_workflow_restore(args: argparse.Namespace) -> int:
    _confirm(f"Restore version #{args.id} of '{args.name}'?", args.yes)
    result = _client(args).post(path("workflows", args.name, "history", args.id, "restore"))
    print(f"Restored {result['restored_from']} as version {result['version']}.")
    return 0


# ----------------------------------------------------------------------
# Jobs (runs)
# ----------------------------------------------------------------------


def cmd_job_list(args: argparse.Namespace) -> int:
    result = _client(args).get(
        "/runs", tab=args.state, search=args.workflow or "", limit=args.limit
    )
    if args.output == "json":
        emit_json(result["items"])
        return 0
    table(
        ("id", "target", "state", "node", "by", "started", "trigger"),
        (
            (
                run["id"],
                run["target"],
                run["state"],
                ",".join((run.get("options") or {}).get("nodes") or [run["node"]]),
                run.get("username"),
                when(run.get("started_at") or run.get("created_at")),
                run.get("trigger"),
            )
            for run in result["items"]
        ),
    )
    return 0


def cmd_job_get(args: argparse.Namespace) -> int:
    detail = _client(args).get(path("runs", args.id))
    if args.output == "json":
        emit_json(detail)
        return 0
    run = detail["run"]
    print(f"Run #{run['id']}  {run['target']}  {run['state']}")
    print(
        f"  Node:     {run['node']}    Trigger: {run.get('trigger')}    By: {run.get('username')}"
    )
    print(f"  Started:  {when(run.get('started_at'))}    Finished: {when(run.get('finished_at'))}")
    options = run.get("options") or {}
    if options.get("tags"):
        print(f"  Tags:     {', '.join(options['tags'])}")
    if options.get("skipped"):
        print(f"  Skipped:  {', '.join(options['skipped'])}")
    status = {step["name"]: step for step in detail.get("steps", [])}
    rows = []
    for step in detail.get("plan", []):
        if not step.get("selected", step.get("enabled", True)):
            continue
        seen = status.get(step["name"], {})
        rows.append(
            (
                step["name"],
                step.get("plugin"),
                step.get("node") or run["node"],
                seen.get("status", "pending"),
                f"{seen['duration_ms'] / 1000:.1f}s" if seen.get("duration_ms") else "",
            )
        )
    if rows:
        print()
        table(("step", "plugin", "node", "status", "duration"), rows)
    return 0


def cmd_job_logs(args: argparse.Namespace) -> int:
    client = _client(args)
    if args.events:
        cursor = None
        while True:
            batch = client.get(path("runs", args.id, "events"), after=cursor)
            for event in batch["events"]:
                level = (event.get("level") or "").upper()[:5]
                text = event.get("message") or event["type"]
                where = f"[{event['node_name']}] " if event.get("node_name") else ""
                print(f"{when(event.get('created_at'))}  {level:5}  {where}{text}")
            cursor = batch.get("cursor", cursor)
            if not args.follow or batch["run"]["state"] in TERMINAL and not batch["events"]:
                return STATE_EXIT.get(batch["run"]["state"], 0) if args.follow else 0
            time.sleep(1.0)
    if args.follow:
        return _follow(client, args.id)
    sys.stdout.write(client.get(path("runs", args.id, "log"), offset=0)["text"])
    return 0


def cmd_job_stop(args: argparse.Namespace) -> int:
    run = _client(args).post(path("runs", args.id, "stop"))["run"]
    print(f"Run #{run['id']}: {run['state']}.")
    return 0


def cmd_job_wait(args: argparse.Namespace) -> int:
    return _follow(_client(args), args.id, quiet=True)


# ----------------------------------------------------------------------
# Plugins, nodes, schedules
# ----------------------------------------------------------------------


def cmd_plugin_list(args: argparse.Namespace) -> int:
    client = _client(args)
    items: List[Dict[str, Any]] = []
    page = 1
    while True:
        result = client.get("/plugins", page=page, page_size=10)
        items.extend(result["items"])
        if page >= result["pagination"]["total_pages"]:
            break
        page += 1
    if args.output == "json":
        emit_json(items)
        return 0
    table(
        ("name", "version", "status"),
        (
            (
                p["qualified_name"],
                p["version"],
                "draft" if p.get("draft") else "enabled" if p["enabled"] else "disabled",
            )
            for p in items
        ),
    )
    return 0


def cmd_plugin_run(args: argparse.Namespace) -> int:
    client = _client(args)
    run = client.post(
        path("plugins", args.name, "run"),
        {"node": args.node, "arguments": _values(args.arg, "--arg")},
    )["run"]
    print(f"Run #{run['id']} started on {run['node']}.", file=sys.stderr)
    if args.follow:
        return _follow(client, run["id"])
    print(run["id"])
    return 0


def cmd_node_list(args: argparse.Namespace) -> int:
    items = _client(args).get("/nodes")["items"]
    if args.output == "json":
        emit_json(items)
        return 0
    table(
        ("name", "kind", "host", "status", "running", "last seen"),
        (
            (
                n["name"],
                n["kind"],
                n.get("host"),
                ("ready" if n.get("agent_up") else "unreachable") if n["enabled"] else "disabled",
                n.get("running_jobs", 0),
                when(n.get("last_seen_at")) if n["kind"] != "local" else "-",
            )
            for n in items
        ),
    )
    return 0


def cmd_schedule_list(args: argparse.Namespace) -> int:
    items = _client(args).get("/schedules")["items"]
    if args.output == "json":
        emit_json(items)
        return 0
    table(
        ("id", "name", "target", "cron", "node", "enabled"),
        (
            (s["id"], s["name"], f"{s['kind']}:{s['target']}", s["cron"], s["node"], s["enabled"])
            for s in items
        ),
    )
    return 0


# ----------------------------------------------------------------------
# Parser
# ----------------------------------------------------------------------


def _output(parser: argparse.ArgumentParser, choices=("table", "json"), default="table") -> None:
    parser.add_argument("-o", "--output", choices=choices, default=default, help="Output format.")


def _login_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("server", nargs="?", help="Server URL, e.g. https://entropy.example.com")
    parser.add_argument("-u", "--username", help="Username (prompted when omitted).")
    parser.add_argument(
        "--password-stdin", action="store_true", help="Read the password from stdin."
    )
    parser.add_argument("--token", help="Log in with a token (Copy login command in the web UI).")
    parser.add_argument("--name", help="Context name (default: the server's host:port).")
    parser.add_argument(
        "--insecure-skip-tls-verify",
        action="store_true",
        help="Do not verify the server's certificate.",
    )
    parser.add_argument("--certificate-authority", metavar="FILE", help="CA certificate to trust.")
    parser.set_defaults(func=cmd_login)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ent",
        description="Entropy command line for remote servers. Start with: ent login <server-url>",
    )
    parser.add_argument("--context", help="Use this saved server instead of the current one.")
    parser.add_argument("--version", action="store_true", help="Show client and server versions.")
    commands = parser.add_subparsers(dest="command", metavar="COMMAND")

    _login_options(commands.add_parser("login", help="Log in to an Entropy server."))
    commands.add_parser("logout", help="Log out and revoke the token.").set_defaults(
        func=cmd_logout
    )
    whoami = commands.add_parser("whoami", help="Show the logged-in user.")
    whoami.add_argument("-v", "--verbose", action="store_true", help="Also list permissions.")
    _output(whoami)
    whoami.set_defaults(func=cmd_whoami)
    commands.add_parser("status", help="Server, user and session.").set_defaults(func=cmd_status)
    commands.add_parser("version", help="Client and server versions.").set_defaults(
        func=cmd_version
    )

    # ent auth login|logout|whoami|status: the same, grouped like the local CLI.
    auth = commands.add_parser("auth", help="Log in, log out, who am I.").add_subparsers(
        dest="auth_command", metavar="ACTION"
    )
    _login_options(auth.add_parser("login", help="Log in to an Entropy server."))
    auth.add_parser("logout", help="Log out.").set_defaults(func=cmd_logout)
    auth_whoami = auth.add_parser("whoami", help="Show the logged-in user.")
    auth_whoami.add_argument("-v", "--verbose", action="store_true")
    _output(auth_whoami)
    auth_whoami.set_defaults(func=cmd_whoami)
    auth.add_parser("status", help="Server, user and session.").set_defaults(func=cmd_status)

    context = commands.add_parser("context", aliases=["ctx"], help="Saved servers.")
    context.add_argument("action", choices=("list", "use", "delete"), nargs="?", default="list")
    context.add_argument("name", nargs="?")
    context.set_defaults(func=cmd_context)

    # Workflows
    workflow = commands.add_parser("workflow", aliases=["workflows", "wf"], help="Workflows.")
    wf = workflow.add_subparsers(dest="workflow_command", metavar="ACTION")
    item = wf.add_parser("list", aliases=["ls"], help="List workflows.")
    _output(item)
    item.set_defaults(func=cmd_workflow_list)
    item = wf.add_parser("get", help="Print a workflow definition.")
    item.add_argument("name")
    _output(item, ("yaml", "json"), "yaml")
    item.set_defaults(func=cmd_workflow_get)
    item = wf.add_parser("validate", help="Check a definition file without saving it.")
    item.add_argument("-f", "--file", required=True)
    item.set_defaults(func=cmd_workflow_validate)
    item = wf.add_parser("apply", help="Create or update a workflow from a file.")
    item.add_argument("-f", "--file", required=True)
    item.set_defaults(func=cmd_workflow_apply)
    item = wf.add_parser("delete", aliases=["rm"], help="Delete a workflow.")
    item.add_argument("name")
    item.add_argument("-y", "--yes", action="store_true")
    item.set_defaults(func=cmd_workflow_delete)
    item = wf.add_parser("run", aliases=["start"], help="Run a workflow.")
    item.add_argument("name")
    item.add_argument("--node", default="local", help="Node to run on (default local).")
    item.add_argument("--var", action="append", metavar="KEY=VALUE", help="Input variable.")
    item.add_argument("--tag", action="append", help="Only steps with this tag (repeatable).")
    item.add_argument("--step", action="append", help="Only these steps (repeatable).")
    item.add_argument(
        "--step-node", action="append", metavar="STEP=NODE", help="Run a step on another node."
    )
    item.add_argument("-F", "--follow", action="store_true", help="Stream output until it ends.")
    item.set_defaults(func=cmd_workflow_run)
    item = wf.add_parser("history", help="Kept earlier versions.")
    item.add_argument("name")
    _output(item)
    item.set_defaults(func=cmd_workflow_history)
    item = wf.add_parser("restore", help="Restore a kept version.")
    item.add_argument("name")
    item.add_argument("id", type=int)
    item.add_argument("-y", "--yes", action="store_true")
    item.set_defaults(func=cmd_workflow_restore)

    # Jobs
    job = commands.add_parser("job", aliases=["jobs", "run", "runs"], help="Runs (jobs).")
    jb = job.add_subparsers(dest="job_command", metavar="ACTION")
    item = jb.add_parser("list", aliases=["ls"], help="List runs.")
    item.add_argument(
        "--state", choices=("active", "completed", "failed", "cancelled", "all"), default="all"
    )
    item.add_argument("--workflow", help="Only runs of this workflow or plugin.")
    item.add_argument("--limit", type=int, default=20)
    _output(item)
    item.set_defaults(func=cmd_job_list)
    item = jb.add_parser("get", aliases=["show"], help="A run and its steps.")
    item.add_argument("id", type=int)
    _output(item)
    item.set_defaults(func=cmd_job_get)
    item = jb.add_parser("logs", aliases=["log"], help="Console output (or --events).")
    item.add_argument("id", type=int)
    item.add_argument("-f", "--follow", action="store_true", help="Keep printing until it ends.")
    item.add_argument(
        "--events", action="store_true", help="Step events instead of console output."
    )
    item.set_defaults(func=cmd_job_logs)
    item = jb.add_parser("stop", help="Stop a run.")
    item.add_argument("id", type=int)
    item.set_defaults(func=cmd_job_stop)
    item = jb.add_parser("wait", help="Wait for a run; exit 0 if it completed.")
    item.add_argument("id", type=int)
    item.set_defaults(func=cmd_job_wait)

    # Plugins, nodes, schedules
    plugin = commands.add_parser("plugin", aliases=["plugins", "pl"], help="Plugins.")
    pl = plugin.add_subparsers(dest="plugin_command", metavar="ACTION")
    item = pl.add_parser("list", aliases=["ls"], help="List plugins.")
    _output(item)
    item.set_defaults(func=cmd_plugin_list)
    item = pl.add_parser("run", help="Run a plugin once.")
    item.add_argument("name")
    item.add_argument("--node", default="local")
    item.add_argument("--arg", action="append", metavar="KEY=VALUE")
    item.add_argument("-F", "--follow", action="store_true")
    item.set_defaults(func=cmd_plugin_run)

    node = commands.add_parser("node", aliases=["nodes"], help="Execution nodes.")
    nd = node.add_subparsers(dest="node_command", metavar="ACTION")
    item = nd.add_parser("list", aliases=["ls"], help="List nodes.")
    _output(item)
    item.set_defaults(func=cmd_node_list)

    schedule = commands.add_parser("schedule", aliases=["schedules"], help="Schedules.")
    sc = schedule.add_subparsers(dest="schedule_command", metavar="ACTION")
    item = sc.add_parser("list", aliases=["ls"], help="List schedules.")
    _output(item)
    item.set_defaults(func=cmd_schedule_list)

    return parser


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.version:
        return cmd_version(args)

    handler: Optional[Callable[[argparse.Namespace], int]] = getattr(args, "func", None)
    if handler is None:
        # A group without an action: show that group's help.
        parser.parse_args((argv or sys.argv[1:]) + ["-h"])
        return 2

    try:
        return int(handler(args) or 0)
    except (CommandError, ConfigError, ApiError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("", file=sys.stderr)
        return 130
