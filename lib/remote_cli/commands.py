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
from .contract import (
    CONFIG_KEYS,
    OUTPUT_ENV,
    OUTPUT_MODES,
    PROJECT_ENV,
    OutputModeError,
    resolve_output,
    resource,
)
from .output import Column, render, table, when

TERMINAL = ("completed", "failed", "cancelled")
STATE_EXIT = {"completed": 0, "failed": 1, "cancelled": 130}


class CommandError(Exception):
    """A user-facing failure; printed without a traceback."""


# ----------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------


def _project(args: argparse.Namespace, context: Dict[str, Any]) -> Optional[str]:
    """--project, else $ENT_PROJECT, else the context's saved project."""

    return (
        getattr(args, "project", None)
        or os.environ.get(PROJECT_ENV, "").strip()
        or context.get("project")
        or None
    )


def _client(args: argparse.Namespace) -> Client:
    context = Config.load().current(getattr(args, "context", None))
    if not context.get("token"):
        raise CommandError(f"Not logged in to {context['server']}. Run: ent login")
    return Client.for_context(context, _project(args, context))


def _mode(args: argparse.Namespace) -> str:
    """-o, else $ENT_OUTPUT, else `ent config set output`, else detailed."""

    return resolve_output(getattr(args, "output", None), Config.load().preference("output"))


def _emit(
    args: argparse.Namespace,
    items: List[Any],
    columns: List[Column],
    *,
    title: str,
    kind: str,
    **options: Any,
) -> int:
    text = render(_mode(args), items, columns, title=title, kind=kind, **options)
    if text:
        print(text)
    return 0


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
    if _mode(args) in ("json", "yaml"):
        return _emit(args, [], [], title="", kind="user", data=me)
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
    client = Client.for_context(context, _project(args, context))
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
    print(f"Project:  {client.project or '(server default)'}")
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
# Project and preferences
# ----------------------------------------------------------------------


def cmd_project(args: argparse.Namespace) -> int:
    config = Config.load()
    context = config.current(getattr(args, "context", None))
    stored = config.contexts[context["name"]]
    action = args.action

    if action in ("set", "use"):
        if not args.key:
            raise CommandError("Give the project key: ent project set KEY")
        result = _client(args).get("/projects")
        keys = {item["key"]: item for item in result["items"]}
        if args.key not in keys:
            raise CommandError(f"No project '{args.key}' that you can see. See: ent project list")
        stored["project"] = args.key
        config.save()
        print(f"Now using project '{args.key}' ({keys[args.key]['name']}) on {context['server']}.")
        return 0
    if action in ("remove", "unset"):
        stored.pop("project", None)
        config.save()
        print("Project selection cleared; the server's default project is used.")
        return 0

    result = _client(args).get("/projects")
    current = result.get("current")
    if action == "current":
        project = next((p for p in result["items"] if p["key"] == current), None)
        if _mode(args) in ("json", "yaml", "name"):
            return _emit(
                args,
                [project] if project else [],
                [("key", lambda p: p["key"], False)],
                title="Project",
                kind="project",
                data=project,
            )
        print(f"{current} — {project['name']}" if project else str(current or "-"))
        return 0
    return _emit(
        args,
        result["items"],
        [
            ("current", lambda p: "*" if p["key"] == current else "", False),
            ("key", lambda p: p["key"], False),
            ("name", lambda p: p["name"], False),
            ("roles", lambda p: ", ".join(p.get("my_roles") or []), True),
            ("description", lambda p: p.get("description"), True),
        ],
        title="Projects",
        kind="project",
        name=lambda p: p["key"],
    )


def cmd_config(args: argparse.Namespace) -> int:
    config = Config.load()
    if args.action in ("view", "get"):
        keys = [args.key] if args.key else sorted(CONFIG_KEYS)
        for key in keys:
            if key not in CONFIG_KEYS:
                raise CommandError(f"Unknown setting '{key}'. Settings: {', '.join(CONFIG_KEYS)}.")
        saved = config.preference("output")
        effective = resolve_output(None, saved)
        source = OUTPUT_ENV if os.environ.get(OUTPUT_ENV) else "saved" if saved else "default"
        print(f"output: {effective} ({source})")
        return 0
    if not args.key or args.key not in CONFIG_KEYS:
        raise CommandError(f"Give a setting: {', '.join(CONFIG_KEYS)}.")
    if args.action == "unset":
        config.preferences.pop(args.key, None)
        config.save()
        print(f"Forgot {args.key}; using {resolve_output(None, None)}.")
        return 0
    if not args.value:
        raise CommandError(
            f"Give a value: ent config set {args.key} {{{','.join(CONFIG_KEYS[args.key])}}}"
        )
    try:
        value = resolve_output(args.value)
    except OutputModeError as error:
        raise CommandError(str(error)) from None
    config.preferences[args.key] = value
    config.save()
    print(f"{args.key} set to {value}.")
    return 0


# ----------------------------------------------------------------------
# Workflows
# ----------------------------------------------------------------------


def cmd_workflow_list(args: argparse.Namespace) -> int:
    items = _client(args).get("/workflows")["items"]
    return _emit(
        args,
        items,
        [
            ("name", lambda w: w["name"], False),
            ("version", lambda w: w["version"], False),
            ("updated", lambda w: when(w.get("updated_at")), False),
            ("created", lambda w: when(w.get("created_at")), True),
            ("description", lambda w: w.get("description"), False),
        ],
        title="Workflows",
        kind="workflow",
    )


def cmd_workflow_get(args: argparse.Namespace) -> int:
    mode = _mode(args)
    client = _client(args)
    if mode in ("yaml", "json"):
        detail = client.get(path("workflows", args.name), format=mode)
        print(detail["definition"].rstrip("\n"))
        return 0
    detail = client.get(path("workflows", args.name), format="json")
    if mode != "detailed":
        return _emit(
            args,
            [detail],
            [
                ("name", lambda w: w["name"], False),
                ("version", lambda w: w["version"], False),
                ("steps", lambda w: w["step_count"], False),
                ("description", lambda w: w.get("description"), True),
            ],
            title="Workflow",
            kind="workflow",
        )
    definition = json.loads(detail["definition"])
    print(f"Workflow:     {detail['name']}")
    print(f"Version:      {detail['version']}")
    print(f"Description:  {detail.get('description') or '-'}")
    variables = definition.get("variables") or {}
    if variables:
        print("Variables:")
        for key, value in variables.items():
            print(f"  {key}: {json.dumps(value, default=str)}")
    print()
    return _emit(
        args,
        definition.get("steps") or [],
        [
            ("name", lambda s: s.get("name"), False),
            ("plugin", lambda s: s.get("plugin"), False),
            ("enabled", lambda s: "yes" if s.get("enabled", True) else "no", False),
            ("tags", lambda s: ", ".join(s.get("tags") or []), False),
            ("on failure", lambda s: s.get("on_failure"), False),
        ],
        title="Steps",
        kind="step",
    )


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
    if _mode(args) == "detailed":
        print(f"Current version: {history['current_version']}")
    return _emit(
        args,
        history["items"],
        [
            ("id", lambda i: i["id"], False),
            ("version", lambda i: i["version"], False),
            ("kept", lambda i: when(i["created_at"]), False),
            ("by", lambda i: i.get("created_by"), False),
            ("reason", lambda i: i["reason"], False),
        ],
        title=f"History of {args.name}",
        kind="version",
        name=lambda i: i["id"],
        data=history,
    )


def cmd_workflow_restore(args: argparse.Namespace) -> int:
    _confirm(f"Restore version #{args.id} of '{args.name}'?", args.yes)
    result = _client(args).post(path("workflows", args.name, "history", args.id, "restore"))
    print(f"Restored {result['restored_from']} as version {result['version']}.")
    return 0


# ----------------------------------------------------------------------
# Jobs (runs)
# ----------------------------------------------------------------------


def _nodes(run: Dict[str, Any]) -> str:
    return ",".join((run.get("options") or {}).get("nodes") or [run["node"]])


def cmd_job_list(args: argparse.Namespace) -> int:
    result = _client(args).get(
        "/runs", tab=args.state, search=args.workflow or "", limit=args.limit
    )
    return _emit(
        args,
        result["items"],
        [
            ("id", lambda r: r["id"], False),
            ("target", lambda r: r["target"], False),
            ("state", lambda r: r["state"], False),
            ("node", _nodes, False),
            ("by", lambda r: r.get("username"), True),
            ("started", lambda r: when(r.get("started_at") or r.get("created_at")), False),
            ("finished", lambda r: when(r.get("finished_at")), True),
            ("trigger", lambda r: r.get("trigger"), True),
        ],
        title="Runs",
        kind="job",
        name=lambda r: r["id"],
    )


def cmd_job_get(args: argparse.Namespace) -> int:
    detail = _client(args).get(path("runs", args.id))
    run = detail["run"]
    mode = _mode(args)
    if mode != "detailed":
        return _emit(
            args,
            [run],
            [
                ("id", lambda r: r["id"], False),
                ("target", lambda r: r["target"], False),
                ("state", lambda r: r["state"], False),
                ("node", _nodes, False),
                ("by", lambda r: r.get("username"), True),
                ("started", lambda r: when(r.get("started_at")), False),
                ("finished", lambda r: when(r.get("finished_at")), True),
            ],
            title="Run",
            kind="job",
            name=lambda r: r["id"],
            data=detail,
        )
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
    steps = [
        step for step in detail.get("plan", []) if step.get("selected", step.get("enabled", True))
    ]
    if not steps:
        return 0
    print()
    return _emit(
        args,
        steps,
        [
            ("step", lambda s: s["name"], False),
            ("plugin", lambda s: s.get("plugin"), False),
            ("node", lambda s: s.get("node") or run["node"], False),
            ("status", lambda s: status.get(s["name"], {}).get("status", "pending"), False),
            (
                "duration",
                lambda s: (
                    f"{status[s['name']]['duration_ms'] / 1000:.1f}s"
                    if status.get(s["name"], {}).get("duration_ms")
                    else ""
                ),
                False,
            ),
        ],
        title="Steps",
        kind="step",
    )


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
    return _emit(
        args,
        items,
        [
            ("name", lambda p: p["qualified_name"], False),
            ("version", lambda p: p["version"], False),
            (
                "status",
                lambda p: "draft" if p.get("draft") else "enabled" if p["enabled"] else "disabled",
                False,
            ),
            ("description", lambda p: p.get("description"), True),
        ],
        title="Plugins",
        kind="plugin",
    )


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
    return _emit(
        args,
        items,
        [
            ("name", lambda n: n["name"], False),
            ("kind", lambda n: n["kind"], False),
            ("host", lambda n: n.get("host"), False),
            (
                "status",
                lambda n: (
                    ("ready" if n.get("agent_up") else "unreachable")
                    if n["enabled"]
                    else "disabled"
                ),
                False,
            ),
            ("running", lambda n: n.get("running_jobs", 0), False),
            (
                "last seen",
                lambda n: when(n.get("last_seen_at")) if n["kind"] != "local" else "-",
                True,
            ),
        ],
        title="Nodes",
        kind="node",
    )


def cmd_schedule_list(args: argparse.Namespace) -> int:
    items = _client(args).get("/schedules")["items"]
    return _emit(
        args,
        items,
        [
            ("id", lambda s: s["id"], False),
            ("name", lambda s: s["name"], False),
            ("target", lambda s: f"{s['kind']}:{s['target']}", False),
            ("cron", lambda s: s["cron"], False),
            ("node", lambda s: s["node"], True),
            ("enabled", lambda s: s["enabled"], False),
        ],
        title="Schedules",
        kind="schedule",
        name=lambda s: s["name"],
    )


def cmd_user_list(args: argparse.Namespace) -> int:
    items = _client(args).get("/admin/users")["items"]
    return _emit(
        args,
        items,
        [
            ("username", lambda u: u["username"], False),
            ("name", lambda u: u.get("full_name"), False),
            ("email", lambda u: u.get("email"), True),
            ("active", lambda u: "yes" if u.get("is_active") else "no", False),
            ("roles", lambda u: ", ".join(u.get("roles") or []), True),
            ("groups", lambda u: ", ".join(u.get("groups") or []), True),
        ],
        title="Users",
        kind="user",
    )


def cmd_group_list(args: argparse.Namespace) -> int:
    items = _client(args).get("/admin/groups")["items"]
    return _emit(
        args,
        items,
        [
            ("name", lambda g: g["name"], False),
            ("description", lambda g: g.get("description"), True),
            ("members", lambda g: len(g.get("members") or g.get("users") or []), False),
            ("roles", lambda g: ", ".join(g.get("roles") or []), False),
        ],
        title="Groups",
        kind="group",
    )


def cmd_role_list(args: argparse.Namespace) -> int:
    items = _client(args).get("/admin/roles")["items"]
    return _emit(
        args,
        items,
        [
            ("name", lambda r: r["name"], False),
            ("built-in", lambda r: "yes" if r.get("is_builtin") else "no", False),
            ("permissions", lambda r: len(r.get("permissions") or []), False),
            ("description", lambda r: r.get("description"), True),
        ],
        title="Roles",
        kind="role",
    )


def cmd_vault_namespaces(args: argparse.Namespace) -> int:
    items = _client(args).get("/vault/namespaces")["items"]
    return _emit(
        args,
        items,
        [
            ("namespace", lambda n: n["name"], False),
            ("visibility", lambda n: n.get("visibility"), False),
            ("your access", lambda n: n.get("access") or "read", False),
            ("created", lambda n: when(n.get("created_at")), True),
        ],
        title="Vault namespaces",
        kind="namespace",
    )


def cmd_vault_list(args: argparse.Namespace) -> int:
    """Keys of a namespace; values are never shown here."""

    items = _client(args).get(path("vault", "namespaces", args.namespace, "entries"))["items"]
    return _emit(
        args,
        items,
        [
            ("key", lambda e: e["key"], False),
            ("type", lambda e: e.get("type"), False),
            ("sensitive", lambda e: "yes" if e.get("sensitive") else "no", False),
            ("updated", lambda e: when(e.get("updated_at")), True),
        ],
        title=f"Vault keys in {args.namespace}",
        kind="key",
    )


def cmd_notification_list(args: argparse.Namespace) -> int:
    items = _client(args).get("/notifications", limit=args.limit)["items"]
    if args.unread:
        items = [n for n in items if not n.get("read")]
    return _emit(
        args,
        items,
        [
            ("when", lambda n: when(n.get("created_at")), False),
            ("level", lambda n: n["level"], False),
            ("title", lambda n: n["title"], False),
            ("message", lambda n: n.get("message"), True),
        ],
        title="Notifications",
        kind="notification",
        name=lambda n: n.get("id"),
    )


# ----------------------------------------------------------------------
# Parser
# ----------------------------------------------------------------------


def _output(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "-o",
        "--output",
        choices=OUTPUT_MODES,
        help=f"Output mode (default: ${OUTPUT_ENV}, then `ent config set output`, then detailed).",
    )


def _resource(commands: Any, name: str) -> Any:
    """A resource's parser and its verbs, named as in the contract."""

    item = resource(name)
    assert item is not None, name
    parser = commands.add_parser(item.name, aliases=list(item.aliases), help=item.help)
    return parser.add_subparsers(dest=f"{item.name}_command", metavar="ACTION")


def _verb(actions: Any, resource_name: str, name: str) -> argparse.ArgumentParser:
    item = resource(resource_name)
    verb = item.verb(name) if item else None
    assert verb is not None and verb.remote, f"{resource_name} {name}"
    parser: argparse.ArgumentParser = actions.add_parser(
        verb.name, aliases=list(verb.aliases), help=verb.help
    )
    return parser


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


def _run_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--node", default="local", help="Node to run on (default local).")
    parser.add_argument(
        "--var",
        "-a",
        "--arguments",
        dest="var",
        action="append",
        metavar="KEY=VALUE",
        help="Input variable.",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ent",
        description="Entropy command line for remote servers. Start with: ent login <server-url>",
    )
    parser.add_argument("--context", help="Use this saved server instead of the current one.")
    parser.add_argument(
        "-p",
        "--project",
        help=f"Work in this project for one command (also ${PROJECT_ENV}).",
    )
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
    commands.add_parser("status", help="Server, user, project and session.").set_defaults(
        func=cmd_status
    )
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

    # Project and preferences
    actions = _resource(commands, "project")
    for name in ("list", "current", "set", "remove"):
        item = _verb(actions, "project", name)
        if name == "set":
            item.add_argument("key", help="Project key.")
        else:
            item.set_defaults(key=None)
        if name in ("list", "current"):
            _output(item)
        item.set_defaults(func=cmd_project, action=name)

    actions = _resource(commands, "config")
    for name in ("view", "set", "unset"):
        item = _verb(actions, "config", name)
        item.add_argument("key", nargs="?" if name == "view" else None, help="Setting: output.")
        if name == "set":
            item.add_argument("value", help=f"One of: {', '.join(OUTPUT_MODES)}.")
        else:
            item.set_defaults(value=None)
        item.set_defaults(func=cmd_config, action=name)

    # Workflows
    wf = _resource(commands, "workflow")
    item = _verb(wf, "workflow", "list")
    _output(item)
    item.set_defaults(func=cmd_workflow_list)
    item = _verb(wf, "workflow", "get")
    item.add_argument("name")
    _output(item)
    item.set_defaults(func=cmd_workflow_get)
    item = _verb(wf, "workflow", "validate")
    item.add_argument("-f", "--file", "--from-file", dest="file", required=True)
    item.set_defaults(func=cmd_workflow_validate)
    item = _verb(wf, "workflow", "apply")
    item.add_argument("-f", "--file", "--from-file", dest="file", required=True)
    item.set_defaults(func=cmd_workflow_apply)
    item = _verb(wf, "workflow", "delete")
    item.add_argument("name")
    item.add_argument("-y", "--yes", action="store_true")
    item.set_defaults(func=cmd_workflow_delete)
    item = _verb(wf, "workflow", "run")
    item.add_argument("name")
    _run_options(item)
    item.add_argument("--tag", action="append", help="Only steps with this tag (repeatable).")
    item.add_argument("--step", action="append", help="Only these steps (repeatable).")
    item.add_argument(
        "--step-node", action="append", metavar="STEP=NODE", help="Run a step on another node."
    )
    item.add_argument("-F", "--follow", action="store_true", help="Stream output until it ends.")
    item.set_defaults(func=cmd_workflow_run)
    item = _verb(wf, "workflow", "history")
    item.add_argument("name")
    _output(item)
    item.set_defaults(func=cmd_workflow_history)
    item = _verb(wf, "workflow", "restore")
    item.add_argument("name")
    item.add_argument("id", type=int)
    item.add_argument("-y", "--yes", action="store_true")
    item.set_defaults(func=cmd_workflow_restore)

    # Jobs
    jb = _resource(commands, "job")
    item = _verb(jb, "job", "list")
    item.add_argument(
        "--state", choices=("active", "completed", "failed", "cancelled", "all"), default="all"
    )
    item.add_argument("--workflow", help="Only runs of this workflow or plugin.")
    item.add_argument("--limit", type=int, default=20)
    _output(item)
    item.set_defaults(func=cmd_job_list)
    item = _verb(jb, "job", "get")
    item.add_argument("id", type=int)
    _output(item)
    item.set_defaults(func=cmd_job_get)
    item = _verb(jb, "job", "logs")
    item.add_argument("id", type=int)
    item.add_argument("-f", "--follow", action="store_true", help="Keep printing until it ends.")
    item.add_argument(
        "--events", action="store_true", help="Step events instead of console output."
    )
    item.set_defaults(func=cmd_job_logs)
    item = _verb(jb, "job", "stop")
    item.add_argument("id", type=int)
    item.set_defaults(func=cmd_job_stop)
    item = _verb(jb, "job", "wait")
    item.add_argument("id", type=int)
    item.set_defaults(func=cmd_job_wait)

    # Plugins, nodes, schedules
    pl = _resource(commands, "plugin")
    item = _verb(pl, "plugin", "list")
    _output(item)
    item.set_defaults(func=cmd_plugin_list)
    item = _verb(pl, "plugin", "run")
    item.add_argument("name")
    item.add_argument("--node", default="local")
    item.add_argument("--arg", action="append", metavar="KEY=VALUE")
    item.add_argument("-F", "--follow", action="store_true")
    item.set_defaults(func=cmd_plugin_run)

    # Read only here; manage them in the web UI (or the ent on the server).
    for noun, handler in (
        ("node", cmd_node_list),
        ("schedule", cmd_schedule_list),
        ("user", cmd_user_list),
        ("group", cmd_group_list),
        ("role", cmd_role_list),
    ):
        item = _verb(_resource(commands, noun), noun, "list")
        _output(item)
        item.set_defaults(func=handler)

    va = _resource(commands, "vault")
    item = _verb(va, "vault", "namespaces")
    _output(item)
    item.set_defaults(func=cmd_vault_namespaces)
    item = _verb(va, "vault", "list")
    item.add_argument("namespace")
    _output(item)
    item.set_defaults(func=cmd_vault_list)

    item = _verb(_resource(commands, "notification"), "notification", "list")
    item.add_argument("--unread", action="store_true", help="Only unread ones.")
    item.add_argument("--limit", type=int, default=20)
    _output(item)
    item.set_defaults(func=cmd_notification_list)

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
    except (CommandError, ConfigError, ApiError, OutputModeError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("", file=sys.stderr)
        return 130
