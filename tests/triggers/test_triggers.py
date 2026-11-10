"""Webhook and queue triggers: definitions, tokens, payloads, firing, the hook and STOMP."""

from __future__ import annotations

import asyncio
import json
import threading
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict, List

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from core.web.audit import redact_query
from core.web.routes import hooks
from lib.database.connection import DatabaseConnection
from lib.triggers import fire as fire_module
from lib.triggers.fire import parameters_for, parse_payload
from lib.triggers.stomp import FrameReader, StompListener, frame
from lib.triggers.store import TriggerError, TriggerStore, token_hash

WEBHOOK = {
    "name": "Deploy orders",
    "source": "webhook",
    "kind": "workflow",
    "target": "deploy",
    "parameters": {"env": "SIT", "version": "1.0"},
}
QUEUE = {**WEBHOOK, "name": "Orders queue", "source": "queue", "destination": "/queue/orders"}


@pytest.fixture()
def store(tmp_path: Path) -> TriggerStore:
    return TriggerStore(DatabaseConnection(tmp_path / "entropy.db"))


# ----------------------------------------------------------------------
# Definitions and tokens
# ----------------------------------------------------------------------


def test_a_webhook_gets_a_token_shown_once_and_kept_hashed(store: TriggerStore) -> None:
    created = store.create(WEBHOOK, 1, "ada", project_id=1)
    trigger, token = created["trigger"], created["token"]

    assert token and len(token) >= 40 and trigger["token_hint"] == token[-4:]
    assert trigger["has_token"] and "token" not in trigger and "token_hash" not in trigger
    row = store.connection.fetchone(
        "SELECT token_hash FROM triggers WHERE id = ?", (trigger["id"],)
    )
    assert row["token_hash"] == token_hash(token) != token
    assert store.check_token(trigger["id"], token)
    assert not store.check_token(trigger["id"], token[:-1] + "x")
    assert not store.check_token(trigger["id"], "")
    assert store.by_hook_key(trigger["hook_key"])["id"] == trigger["id"]

    fresh = store.new_token(trigger["id"])
    assert fresh != token and store.check_token(trigger["id"], fresh)
    assert not store.check_token(trigger["id"], token)


def test_queue_triggers_need_a_destination_and_have_no_token(store: TriggerStore) -> None:
    with pytest.raises(TriggerError, match="destination"):
        store.create({**QUEUE, "destination": "orders"}, 1, "ada", project_id=1)
    created = store.create(QUEUE, 1, "ada", project_id=1)
    assert created["token"] is None and not created["trigger"]["has_token"]
    assert store.by_hook_key(created["trigger"]["hook_key"]) is None
    assert [item["id"] for item in store.enabled_queue_triggers()] == [created["trigger"]["id"]]

    # Turned into a webhook it gets a token; a webhook keeps no destination.
    updated = store.update(created["trigger"]["id"], {"source": "webhook"})
    assert updated["token"] and updated["trigger"]["destination"] is None
    assert store.enabled_queue_triggers() == []


def test_names_are_unique_per_project_and_deleting_removes_the_history(
    store: TriggerStore,
) -> None:
    first = store.create(WEBHOOK, 1, "ada", project_id=1)["trigger"]
    with pytest.raises(TriggerError) as caught:
        store.create({**WEBHOOK, "name": "deploy ORDERS"}, 1, "ada", project_id=1)
    assert caught.value.status == 409
    store.create(WEBHOOK, 1, "ada", project_id=2)
    store.add_run(first["id"], source="webhook", job_id=None, error="x", payload="{}", caller=None)
    assert store.list(1)[0]["fired"] == 1 and store.list(1)[0]["failed_to_start"] == 1

    assert store.delete([first["id"]]) == 1
    assert store.get(first["id"]) is None and store.runs(first["id"]) == []


def test_the_listener_status_round_trips(store: TriggerStore) -> None:
    assert store.listener_status()["state"] == "off"
    store.set_listener_status("listening", "Listening on 1 destination(s).")
    assert store.listener_status()["state"] == "listening"


# ----------------------------------------------------------------------
# Payloads
# ----------------------------------------------------------------------


def test_payload_fields_override_workflow_variables_and_the_payload_is_passed_whole() -> None:
    trigger = {**WEBHOOK, "use_payload": True, "kind": "workflow"}
    payload = parse_payload('{"version": "2.0", "ticket": "OPS-1"}')

    values, ignored = parameters_for(None, trigger, payload)

    assert values["env"] == "SIT" and values["version"] == "2.0" and values["ticket"] == "OPS-1"
    assert values["trigger_payload"] == payload and values["trigger_source"] == "webhook"
    assert ignored == []
    assert parse_payload("plain text") == "plain text" and parse_payload("  ") is None

    kept, _ = parameters_for(None, {**trigger, "use_payload": False}, payload)
    assert kept["version"] == "1.0" and kept["trigger_payload"] == payload


def test_plugins_take_only_the_arguments_they_declare(monkeypatch) -> None:
    monkeypatch.setattr(fire_module, "_plugin_arguments", lambda context, name: ["version"])
    trigger = {**WEBHOOK, "use_payload": True, "kind": "plugin", "target": "oc.deploy"}

    values, ignored = parameters_for(None, trigger, {"version": "2.0", "rogue": 1})

    assert values == {"env": "SIT", "version": "2.0"} and ignored == ["rogue"]


# ----------------------------------------------------------------------
# Firing
# ----------------------------------------------------------------------


class FakeService:
    started: List[Dict[str, Any]] = []
    marked: List[tuple] = []

    def __init__(self, context: Any) -> None:
        self.store = SimpleNamespace(mark_triggered=lambda *args: FakeService.marked.append(args))

    def start_workflow(self, user: Any, name: str, **options: Any) -> Dict[str, Any]:
        FakeService.started.append({"user": user.username, "name": name, **options})
        return {"id": 42}

    start_plugin = start_workflow


def _context(allowed: bool) -> Any:
    return SimpleNamespace(
        authorization=SimpleNamespace(has_permission=lambda *args: allowed),
        database_manager=None,
    )


def test_firing_runs_as_the_owner_in_the_project_and_records_it(store, monkeypatch) -> None:
    FakeService.started, FakeService.marked = [], []
    monkeypatch.setattr(fire_module, "RunService", FakeService)
    monkeypatch.setattr(
        fire_module,
        "schedule_owner",
        lambda connection, user_id: SimpleNamespace(id=1, username="ada"),
    )
    trigger = store.create(WEBHOOK, 1, "ada", project_id=7)["trigger"]

    run = fire_module.fire_trigger(
        _context(True),
        store,
        trigger,
        payload_text='{"version": "3"}',
        source="webhook",
        caller="x",
    )

    assert run["job_id"] == 42 and run["error"] is None and run["payload"] == '{"version": "3"}'
    [started] = FakeService.started
    assert (
        started["user"] == "ada" and started["project_id"] == 7 and started["trigger"] == "manual"
    )
    assert started["variables"]["version"] == "3"
    assert FakeService.marked == [(42, "webhook", trigger["id"], "Deploy orders")]
    assert store.get(trigger["id"])["last_fired_at"]


def test_an_owner_without_permission_is_recorded_not_raised(store, monkeypatch) -> None:
    FakeService.started = []
    monkeypatch.setattr(fire_module, "RunService", FakeService)
    monkeypatch.setattr(
        fire_module,
        "schedule_owner",
        lambda connection, user_id: SimpleNamespace(id=1, username="ada"),
    )
    trigger = store.create(WEBHOOK, 1, "ada", project_id=7)["trigger"]

    run = fire_module.fire_trigger(
        _context(False), store, trigger, payload_text="", source="queue", caller=None
    )

    assert run["job_id"] is None and "not allowed" in run["error"]
    assert FakeService.started == []
    assert store.runs(trigger["id"])[0]["state"] == "error"


# ----------------------------------------------------------------------
# The webhook
# ----------------------------------------------------------------------


def _request(connection: Any, path: str, body: bytes, headers: Dict[str, str], query: str = ""):
    app = SimpleNamespace(
        state=SimpleNamespace(
            entropy_context=SimpleNamespace(database_manager=SimpleNamespace(connection=connection))
        )
    )
    sent = {"done": False}

    async def receive() -> Dict[str, Any]:
        if sent["done"]:
            return {"type": "http.disconnect"}
        sent["done"] = True
        return {"type": "http.request", "body": body, "more_body": False}

    scope = {
        "type": "http",
        "method": "POST",
        "path": path,
        "headers": [(key.lower().encode(), value.encode()) for key, value in headers.items()],
        "query_string": query.encode(),
        "app": app,
        "client": ("10.0.0.5", 5000),
    }
    return Request(scope, receive)


def _call(store: TriggerStore, key: str, body: bytes, headers: Dict[str, str], token=None):
    request = _request(store.connection, f"/api/hooks/{key}", body, headers)
    return asyncio.run(hooks.call_hook(key, request, token=token))


def test_the_hook_fires_with_the_token_and_refuses_without_it(store, monkeypatch) -> None:
    fired: List[Dict[str, Any]] = []

    def fake_fire(context, store, trigger, **options):
        fired.append(options)
        return {"id": 1, "job_id": 9, "error": None}

    monkeypatch.setattr(hooks, "fire_trigger", fake_fire)
    created = store.create(WEBHOOK, 1, "ada", project_id=1)
    key, token = created["trigger"]["hook_key"], created["token"]

    response = _call(store, key, b'{"version": "2"}', {"X-Entropy-Token": token})
    assert response.status_code == 202
    assert json.loads(response.body) == {"accepted": True, "run_id": 9, "firing_id": 1}
    assert fired[0]["payload_text"] == '{"version": "2"}' and fired[0]["source"] == "webhook"
    assert "10.0.0.5" in fired[0]["caller"]

    assert _call(store, key, b"", {}, token=token).status_code == 202
    for headers, query in (({}, None), ({"X-Entropy-Token": "wrong"}, None)):
        with pytest.raises(HTTPException) as refused:
            _call(store, key, b"", headers, token=query)
        assert refused.value.status_code == 401
    # An unknown hook is refused the same way: nothing says which hooks exist.
    with pytest.raises(HTTPException) as unknown:
        _call(store, "nope", b"", {"X-Entropy-Token": token})
    assert unknown.value.status_code == 401 and unknown.value.detail == hooks.REFUSED

    store.update(created["trigger"]["id"], {"enabled": False})
    with pytest.raises(HTTPException) as paused:
        _call(store, key, b"", {"X-Entropy-Token": token})
    assert paused.value.status_code == 409
    with pytest.raises(HTTPException) as large:
        _call(store, key, b"", {"X-Entropy-Token": token, "Content-Length": str(2 * 1024 * 1024)})
    assert large.value.status_code == 413
    assert len(fired) == 2


def test_a_failed_start_answers_422_with_the_reason(store, monkeypatch) -> None:
    monkeypatch.setattr(
        hooks, "fire_trigger", lambda *args, **kwargs: {"id": 3, "job_id": None, "error": "No node"}
    )
    created = store.create(WEBHOOK, 1, "ada", project_id=1)

    response = _call(
        store, created["trigger"]["hook_key"], b"", {"X-Entropy-Token": created["token"]}
    )

    assert response.status_code == 422 and json.loads(response.body)["detail"] == "No node"


def test_tokens_in_the_query_are_not_written_to_the_audit_log() -> None:
    assert redact_query("token=s3cret&project=shop") == "token=%2A%2A%2A&project=shop"
    assert redact_query("project=shop") == "project=shop"


# ----------------------------------------------------------------------
# STOMP
# ----------------------------------------------------------------------


def test_frames_are_read_across_chunks_with_heartbeats_and_escapes() -> None:
    reader = FrameReader()
    data = (
        b"\n\nMESSAGE\ndestination:/queue/a\\cb\nsubscription:t3\nmessage-id:7\n"
        b"content-length:5\n\na\0b{c\0\nERROR\nmessage:boom\n\n\0"
    )
    first = reader.feed(data[:20])
    rest = reader.feed(data[20:])
    assert first == []
    [(command, headers, body), (error, error_headers, _)] = rest
    assert command == "MESSAGE" and headers["destination"] == "/queue/a:b" and body == b"a\0b{c"
    assert error == "ERROR" and error_headers["message"] == "boom"
    assert frame("ACK", {"id": "a:b"}) == b"ACK\nid:a\\cb\n\n\0"


class FakeSocket:
    """A broker: answers CONNECT, then sends one message, then stops the listener."""

    def __init__(self, stop: threading.Event, version: str = "1.2") -> None:
        self.sent: List[bytes] = []
        self.stop = stop
        self.replies = [
            f"CONNECTED\nversion:{version}\nheart-beat:20000,0\n\n\0".encode(),
            b"MESSAGE\nsubscription:t5\nmessage-id:m-1\nack:a-1\ndestination:/queue/orders\n"
            b'content-length:16\n\n{"version": "4"}\0',
        ]

    def settimeout(self, value: float) -> None:
        pass

    def sendall(self, data: bytes) -> None:
        self.sent.append(data)

    def recv(self, size: int) -> bytes:
        if self.replies:
            return self.replies.pop(0)
        self.stop.set()
        raise TimeoutError()

    def close(self) -> None:
        pass


@pytest.mark.parametrize(
    ("version", "ack"),
    [("1.2", b"ACK\nid:a-1\n\n\0"), ("1.1", b"ACK\nsubscription:t5\nmessage-id:m-1\n\n\0")],
)
def test_a_session_subscribes_fires_and_acknowledges(version: str, ack: bytes) -> None:
    stop = threading.Event()
    sock = FakeSocket(stop, version)
    listener = StompListener(SimpleNamespace(), stop, connect=lambda values, tls: sock)
    delivered: List[tuple] = []
    listener.deliver = lambda trigger_id, headers, body: delivered.append((trigger_id, body))
    listener._status = lambda state, detail: None
    values = {"host": "mq", "port": 61613, "username": "ent", "password": "pw"}

    listener.session(values, {"t5": "/queue/orders"})

    connect, subscribe = sock.sent[0].decode(), sock.sent[1].decode()
    assert connect.startswith("CONNECT\n") and "login:ent" in connect and "passcode:pw" in connect
    assert subscribe.startswith("SUBSCRIBE\n") and "destination:/queue/orders" in subscribe
    assert "ack:client-individual" in subscribe and "id:t5" in subscribe
    assert delivered == [(5, b'{"version": "4"}')]
    assert ack in sock.sent and sock.sent[-1].startswith(b"DISCONNECT")


def test_a_refused_connection_is_reported() -> None:
    stop = threading.Event()
    sock = FakeSocket(stop)
    sock.replies = [b"ERROR\nmessage:Bad credentials\n\n\0"]
    listener = StompListener(SimpleNamespace(), stop, connect=lambda values, tls: sock)

    with pytest.raises(RuntimeError, match="Bad credentials"):
        listener.session({"host": "mq", "port": 61613}, {"t1": "/queue/a"})


def test_messages_for_a_paused_trigger_are_dropped(store, monkeypatch) -> None:
    fired: List[Any] = []
    monkeypatch.setattr(fire_module, "fire_trigger", lambda *args, **kwargs: fired.append(kwargs))
    created = store.create(QUEUE, 1, "ada", project_id=1)["trigger"]
    context = SimpleNamespace(database_manager=SimpleNamespace(connection=store.connection))
    listener = StompListener(context, threading.Event(), connect=lambda values, tls: None)

    listener.deliver(created["id"], {"message-id": "1"}, b"{}")
    store.update(created["id"], {"enabled": False})
    listener.deliver(created["id"], {"message-id": "2"}, b"{}")
    listener.deliver(None, {}, b"{}")

    assert len(fired) == 1 and fired[0]["source"] == "queue"
    assert "/queue/orders" in fired[0]["caller"]
