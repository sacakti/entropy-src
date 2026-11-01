"""Audit log: action names, the store, and the middleware that records API calls."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import Request, Response

from core.web.audit import _body_name, audit_middleware, should_audit
from lib.audit.actions import describe, target
from lib.audit.store import AuditStore
from lib.database.connection import DatabaseConnection


@pytest.fixture
def connection(tmp_path: Path) -> DatabaseConnection:
    return DatabaseConnection(tmp_path / "entropy.db")


@pytest.mark.parametrize(
    ("method", "template", "expected"),
    [
        ("POST", "/api/workflows/{name}/run", ("workflows", "workflows.run")),
        ("DELETE", "/api/tasks/{task_id}", ("tasks", "tasks.delete")),
        ("POST", "/api/tasks/{task_id}/comments", ("tasks", "tasks.comments.create")),
        ("PUT", "/api/admin/users/{username}", ("users", "users.update")),
        (
            "POST",
            "/api/vault/namespaces/{n}/entries/{key}/reveal",
            ("vault", "vault.namespaces.entries.reveal"),
        ),
        ("GET", "/api/artifacts/{artifact_id}/download", ("artifacts", "artifacts.download")),
        ("GET", "/api/releases/report.xlsx", ("releases", "releases.report")),
        ("POST", "/api/auth/logout", ("auth", "auth.logout")),
    ],
)
def test_actions_are_named_from_the_route(method, template, expected) -> None:
    assert describe(method, template) == expected


def test_targets_use_route_identifiers_then_the_body_name() -> None:
    assert target({"job_id": 42}) == "#42"
    assert target({"name": "deploy"}, "deploy") == "deploy"
    assert target({}, "payments") == "payments"
    assert target({}) is None


def test_what_is_audited() -> None:
    assert should_audit("POST", "/api/workflows/deploy/run")
    assert should_audit("DELETE", "/api/tasks/3")
    assert should_audit("GET", "/api/artifacts/3/download")
    assert should_audit("GET", "/api/audit/export.csv")
    assert not should_audit("GET", "/api/runs/3/events")  # polling
    assert not should_audit("POST", "/api/auth/keepalive")
    assert not should_audit(
        "POST", "/api/auth/login"
    )  # recorded by the route, with the username tried
    assert not should_audit("POST", "/api/notifications/7/read")
    assert not should_audit("POST", "/api/agent/heartbeat")
    assert not should_audit("PUT", "/api/preferences/dashboard")  # layout autosave
    assert not should_audit("DELETE", "/api/preferences/dashboard")
    assert should_audit("PATCH", "/api/profile")  # name and e-mail changes stay audited
    assert not should_audit("POST", "/assets/app.js")


def test_bodies_give_only_a_name_never_secrets() -> None:
    raw = json.dumps({"username": "bob", "password": "S3cret!"}).encode()
    assert _body_name(raw, "application/json") == "bob"
    assert _body_name(json.dumps({"password": "x"}).encode(), "application/json") is None
    assert _body_name(b"name=x", "application/x-www-form-urlencoded") is None


def test_store_searches_filters_sorts_and_purges(connection) -> None:
    store = AuditStore(connection)
    store.record(category="workflows", action="workflows.run", username="alice", target="deploy")
    store.record(
        category="users", action="users.delete", username="bob", outcome="denied", status=403
    )
    store.record(category="auth", action="auth.login", username="mallory", outcome="denied")

    items, total = store.search()
    assert total == 3 and items[0]["username"] == "mallory"  # newest first
    assert store.search(outcome="denied")[1] == 2
    assert [item["username"] for item in store.search(search="deploy")[0]] == ["alice"]
    assert [item["username"] for item in store.search(sort="user", order="asc")[0]] == [
        "alice",
        "bob",
        "mallory",
    ]
    assert store.facets()["categories"] == ["auth", "users", "workflows"]

    old = (datetime.now(timezone.utc) - timedelta(days=400)).isoformat()
    connection.execute("UPDATE audit_log SET created_at = ? WHERE username = 'alice'", (old,))
    assert store.purge(365) == 1
    assert store.search()[1] == 2


def _request(connection, method: str, path: str, body: dict, user=("alice", 7)) -> Request:
    session = SimpleNamespace(username=user[0], user_id=user[1]) if user else None
    app = SimpleNamespace(
        state=SimpleNamespace(
            web_session_store=SimpleNamespace(
                get=lambda token: (session, "csrf", None) if session else None
            ),
            entropy_context=SimpleNamespace(
                database_manager=SimpleNamespace(connection=connection)
            ),
        )
    )
    raw = json.dumps(body).encode()
    scope = {
        "type": "http",
        "method": method,
        "path": path,
        "raw_path": path.encode(),
        "query_string": b"",
        "headers": [
            (b"content-type", b"application/json"),
            (b"cookie", b"entropy_session=" + b"a" * 64),
            (b"x-entropy-project", b"app1"),
            (b"user-agent", b"pytest"),
        ],
        "client": ("10.0.0.9", 50000),
        "app": app,
    }
    sent = {"done": False}

    async def receive() -> dict:
        if sent["done"]:
            return {"type": "http.disconnect"}
        sent["done"] = True
        return {"type": "http.request", "body": raw, "more_body": False}

    return Request(scope, receive)


def test_middleware_records_the_call(connection) -> None:
    request = _request(connection, "POST", "/api/workflows", {"name": "deploy", "definition": "{}"})

    async def route(incoming: Request) -> Response:
        assert await incoming.body()  # the route still reads the body
        incoming.scope["route"] = SimpleNamespace(path="/api/workflows")
        return Response(status_code=201)

    response = asyncio.run(audit_middleware(request, route))

    assert response.status_code == 201
    [entry] = AuditStore(connection).search()[0]
    assert entry["action"] == "workflows.create" and entry["target"] == "deploy"
    assert entry["username"] == "alice" and entry["user_id"] == 7
    assert entry["outcome"] == "success" and entry["status"] == 201
    assert entry["project"] == "app1" and entry["address"] == "10.0.0.9"
    assert entry["details"]["route"] == "POST /api/workflows"
    assert "definition" not in json.dumps(entry)  # no request bodies


def test_middleware_records_refusals_and_skips_reads(connection) -> None:
    async def forbidden(incoming: Request) -> Response:
        incoming.scope["route"] = SimpleNamespace(path="/api/admin/users/{username}")
        incoming.scope["path_params"] = {"username": "bob"}
        return Response(status_code=403)

    asyncio.run(
        audit_middleware(_request(connection, "DELETE", "/api/admin/users/bob", {}), forbidden)
    )

    async def ok(incoming: Request) -> Response:
        return Response(status_code=200)

    asyncio.run(audit_middleware(_request(connection, "GET", "/api/workflows", {}), ok))

    [entry] = AuditStore(connection).search()[0]
    assert (entry["action"], entry["target"], entry["outcome"]) == ("users.delete", "bob", "denied")
