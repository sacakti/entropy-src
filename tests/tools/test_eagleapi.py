"""EagleAPI: collections store, vault references, polling helpers and the sender."""

from __future__ import annotations

import base64
import datetime
import ipaddress
import json
import ssl
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Dict, Iterator, Optional

import pytest

from lib.database.connection import DatabaseConnection
from lib.tools.eagleapi import client, namespace_name
from lib.tools.eagleapi.client import EagleRequestError, execute, join_base, prepare
from lib.tools.eagleapi.polling import PollError, extract_poll_url, json_path, stop_state
from lib.tools.eagleapi.references import (
    MASK,
    EagleReferenceError,
    Resolver,
    VaultValue,
    environments,
)
from lib.tools.eagleapi.store import EagleStore, EagleStoreError, normalize_request

# ----------------------------------------------------------------------
# Store
# ----------------------------------------------------------------------


@pytest.fixture
def store(tmp_path) -> Iterator[EagleStore]:
    connection = DatabaseConnection(tmp_path / "entropy.db")
    connection.open()
    yield EagleStore(connection)
    connection.close()


def _tree(store: EagleStore, project: int) -> Dict[str, Any]:
    main = store.create(project, kind="folder", name="main")
    app1 = store.create(project, kind="folder", name="app1", parent_id=main["id"])
    app2 = store.create(project, kind="folder", name="app2", parent_id=main["id"])
    sub = store.create(project, kind="folder", name="subapp1", parent_id=app2["id"])
    sub1 = store.create(project, kind="folder", name="subapp1_1", parent_id=sub["id"])
    req = store.create(
        project,
        kind="request",
        name="REQ1",
        parent_id=app1["id"],
        data={"method": "get", "url": "/context/uri"},
    )
    return {"main": main, "app1": app1, "app2": app2, "sub": sub, "sub1": sub1, "req": req}


def test_store_keeps_a_nested_tree_per_project(store) -> None:
    items = _tree(store, 1)
    store.create(2, kind="folder", name="other")

    listed = store.list(1)
    assert len(listed) == 6
    request = store.get(1, items["req"]["id"])
    assert request["method"] == "GET"
    assert request["data"]["url"] == "/context/uri"
    assert request["data"]["polling"]["enabled"] is False
    # Other projects' items are invisible.
    assert [item["name"] for item in store.list(2)] == ["other"]
    with pytest.raises(LookupError):
        store.get(2, items["req"]["id"])


def test_store_refuses_bad_parents_and_cycles(store) -> None:
    items = _tree(store, 1)
    with pytest.raises(EagleStoreError, match="only be placed in folders"):
        store.create(1, kind="folder", name="x", parent_id=items["req"]["id"])
    with pytest.raises(EagleStoreError, match="into itself"):
        store.move(1, items["main"]["id"], parent_id=items["sub1"]["id"])
    with pytest.raises(EagleStoreError, match="name is required"):
        store.create(1, kind="folder", name="   ")


def test_store_move_rename_duplicate_delete(store) -> None:
    items = _tree(store, 1)
    moved = store.move(1, items["req"]["id"], parent_id=items["sub1"]["id"])
    assert moved["parent_id"] == items["sub1"]["id"]

    renamed = store.update(1, items["req"]["id"], name="  REQ  one ", data={"method": "POST"})
    assert renamed["name"] == "REQ one" and renamed["method"] == "POST"

    copy = store.duplicate(1, items["app2"]["id"])
    assert copy["name"] == "app2 copy"
    assert len(store.list(1)) == 6 + 4  # app2 copy, subapp1, subapp1_1, REQ one
    siblings = [item["name"] for item in store.list(1) if item["parent_id"] == items["main"]["id"]]
    assert siblings == ["app1", "app2", "app2 copy"]

    assert store.delete(1, items["main"]["id"]) == 10
    assert store.list(1) == []


def test_normalize_request_clamps_values() -> None:
    data = normalize_request(
        {"options": {"timeout": 9999}, "polling": {"interval": 0, "max_attempts": -3}}
    )
    assert data["options"]["timeout"] == 300
    assert data["polling"]["interval"] == 0.5
    assert data["polling"]["max_attempts"] == 1
    assert data["body"]["mode"] == "none"


# ----------------------------------------------------------------------
# References
# ----------------------------------------------------------------------

NS = namespace_name("default")


def _file(name: str, content: bytes) -> Dict[str, Any]:
    return {
        "filename": name,
        "content_type": "application/octet-stream",
        "size": len(content),
        "data": base64.b64encode(content).decode("ascii"),
    }


def _fetch(values: Dict[str, Any]):
    def fetch(namespace: str, key: str) -> VaultValue:
        if namespace != NS:
            raise EagleReferenceError(f"{namespace} is not in this project.")
        if key not in values:
            raise EagleReferenceError(f"{key}: no such key")
        value = values[key]
        kind = "file" if isinstance(value, dict) else "string"
        return VaultValue(value=value, type=kind, sensitive=not key.endswith("_URL"))

    return fetch


def test_resolver_replaces_env_and_references_and_masks() -> None:
    resolver = Resolver(_fetch({"SIT_CLIENT_ID": "client-abc", "SIT_URL": "http://h"}), "SIT")
    text = resolver.text("id=${entv:" + NS + "/{{ENV}}_CLIENT_ID} base=${entv:" + NS + "/SIT_URL}")
    assert text == "id=client-abc base=http://h"
    # Only sensitive values are secrets.
    assert resolver.secrets == {"client-abc"}
    assert resolver.mask("x?id=client-abc") == f"x?id={MASK}"
    assert resolver.mask_header("Authorization", "Bearer abc") == f"Bearer {MASK}"
    assert resolver.mask_header("X-Id", "client-abc") == MASK


def test_resolver_refuses_other_namespaces_and_missing_environment() -> None:
    resolver = Resolver(_fetch({}), None)
    with pytest.raises(EagleReferenceError, match="no environment"):
        resolver.text("{{ENV}}")
    with pytest.raises(EagleReferenceError, match="not in this project"):
        resolver.text("${entv:someone-else/KEY}")
    with pytest.raises(EagleReferenceError, match="not a valid environment"):
        Resolver(_fetch({}), "sit; drop")


def test_resolver_files() -> None:
    resolver = Resolver(_fetch({"CERT": _file("c.pem", b"PEM DATA")}), None)
    assert resolver.file("${entvfile:" + NS + "/CERT}") == b"PEM DATA"
    assert resolver.text("${entv:" + NS + "/CERT}") == "PEM DATA"
    assert resolver.file("  ") is None
    with pytest.raises(EagleReferenceError, match="vault file reference"):
        resolver.file("/etc/passwd")


def test_environments_from_keys() -> None:
    assert environments(["SIT_URL", "UAT_URL", "SIT_CLIENT_ID", "url", "X_URL_2"]) == [
        "SIT",
        "UAT",
    ]


# ----------------------------------------------------------------------
# Polling helpers
# ----------------------------------------------------------------------


def test_json_path() -> None:
    document = {"data": {"links": {"status": "/s/1"}}, "items": [{"href": "/a"}], "odd key": 1}
    assert json_path(document, "data.links.status") == "/s/1"
    assert json_path(document, "$.data.links.status") == "/s/1"
    assert json_path(document, "items[0].href") == "/a"
    assert json_path(document, "$['odd key']") == 1
    with pytest.raises(PollError):
        json_path(document, "items[3]")
    with pytest.raises(PollError):
        json_path(document, "data.nope")


def test_extract_poll_url() -> None:
    headers = [("Location", "/jobs/7")]
    body = json.dumps({"links": {"status": "/jobs/7/status"}})
    assert extract_poll_url({"source": "header", "expression": "location"}, headers, "") == (
        "/jobs/7"
    )
    assert extract_poll_url({"source": "json", "expression": "links.status"}, [], body) == (
        "/jobs/7/status"
    )
    assert (
        extract_poll_url({"source": "regex", "expression": r'"status": "([^"]+)"'}, [], body)
        == "/jobs/7/status"
    )
    with pytest.raises(PollError, match="no 'Location'"):
        extract_poll_url({"source": "header", "expression": "Location"}, [], "")


def test_stop_state() -> None:
    spec = {"stop": {"type": "json", "path": "status", "values": "COMPLETED, FAILED"}}
    assert stop_state(spec, 200, '{"status":"RUNNING"}')["done"] is False
    assert stop_state(spec, 200, '{"status":"completed"}')["done"] is True
    assert stop_state(spec, 500, "")["done"] is True
    status = {"stop": {"type": "status", "status": 202}}
    assert stop_state(status, 202, "")["done"] is False
    assert stop_state(status, 200, "")["done"] is True


# ----------------------------------------------------------------------
# Sending against a local server
# ----------------------------------------------------------------------


class _Handler(BaseHTTPRequestHandler):
    polls: Dict[str, int] = {}

    def log_message(self, *args: Any) -> None:  # quiet
        pass

    def _reply(self, status: int, payload: Any, headers: Optional[Dict[str, str]] = None) -> None:
        raw = payload if isinstance(payload, bytes) else json.dumps(payload).encode()
        self.send_response(status)
        content_type = "application/octet-stream" if isinstance(payload, bytes) else None
        self.send_header("Content-Type", content_type or "application/json")
        for key, value in (headers or {}).items():
            self.send_header(key, value)
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def _body(self) -> str:
        length = int(self.headers.get("Content-Length") or 0)
        return self.rfile.read(length).decode() if length else ""

    def do_GET(self) -> None:  # noqa: N802
        if self.path.startswith("/api/jobs/") and self.path.endswith("/status"):
            count = self.polls.get(self.path, 0) + 1
            self.polls[self.path] = count
            self._reply(200, {"status": "COMPLETED" if count >= 3 else "RUNNING"})
        elif self.path == "/redirect":
            self._reply(302, {}, {"Location": "/api/echo"})
        elif self.path == "/binary":
            self._reply(200, bytes(range(256)))
        elif self.path == "/big":
            self._reply(200, {"data": "x" * 5000})
        else:
            self._echo()

    def do_POST(self) -> None:  # noqa: N802
        if self.path == "/api/jobs":
            self._reply(202, {"links": {"status": "jobs/42/status"}}, {"Location": "/api/jobs/42"})
        elif self.path == "/token":
            body = self._body()
            ok = "client_secret=s3cr3t-value" in body or self.headers.get("Authorization")
            self._reply(200 if ok else 401, {"access_token": "tok-123456", "expires_in": 60})
        else:
            self._echo()

    do_PUT = do_PATCH = do_DELETE = do_POST  # noqa: N815

    def _echo(self) -> None:
        self._reply(
            200,
            {
                "method": self.command,
                "path": self.path,
                "headers": dict(self.headers.items()),
                "body": self._body(),
            },
        )


@pytest.fixture
def server() -> Iterator[str]:
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    _Handler.polls = {}
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}"
    httpd.shutdown()
    httpd.server_close()


def _resolver(base: str, environment: Optional[str] = "SIT", **extra: Any) -> Resolver:
    values = {"SIT_URL": base + "/api", "SIT_CLIENT_ID": "client-abc", **extra}
    return Resolver(_fetch(values), environment)


def test_send_uses_environment_base_url_params_headers_and_masks(server) -> None:
    definition = {
        "method": "POST",
        "url": "/echo",
        "params": [
            {"key": "q", "value": "a b"},
            {"key": "off", "value": "1", "enabled": False},
            {"key": "id", "value": "${entv:" + NS + "/SIT_CLIENT_ID}"},
        ],
        "headers": [{"key": "X-Client-Id", "value": "${entv:" + NS + "/{{ENV}}_CLIENT_ID}"}],
        "body": {"mode": "json", "json": '{"hello": "world"}'},
        "auth": {"type": "basic", "username": "u", "password": "p"},
    }
    result = execute(definition, _resolver(server), NS)

    assert result["status"] == 200
    echoed = json.loads(result["body"])
    assert echoed["path"] == "/api/echo?q=a+b&id=client-abc"
    assert echoed["headers"]["X-Client-Id"] == "client-abc"
    assert echoed["headers"]["Content-Type"] == "application/json"
    assert echoed["headers"]["Authorization"] == "Basic " + base64.b64encode(b"u:p").decode()
    assert echoed["body"] == '{"hello": "world"}'

    sent = result["request"]
    assert sent["url"].endswith(f"/api/echo?q=a+b&id={MASK}")
    assert dict(sent["headers"])["X-Client-Id"] == MASK
    assert dict(sent["headers"])["Authorization"] == f"Basic {MASK}"
    assert "client-abc" not in json.dumps(sent)


def test_send_form_body_and_absolute_url_without_environment(server) -> None:
    definition = {
        "method": "PUT",
        "url": server + "/form",
        "body": {"mode": "form", "form": [{"key": "a", "value": "1 2"}]},
    }
    result = execute(definition, _resolver(server, environment=None), NS)
    echoed = json.loads(result["body"])
    assert echoed["method"] == "PUT"
    assert echoed["body"] == "a=1+2"
    assert echoed["headers"]["Content-Type"] == "application/x-www-form-urlencoded"


def test_relative_url_needs_an_environment(server) -> None:
    with pytest.raises(EagleRequestError, match="Choose an environment"):
        prepare({"url": "/echo"}, _resolver(server, environment=None), NS)
    assert join_base("http://h/base/", "/x") == "http://h/base/x"
    assert join_base("http://h/base", "?a=1") == "http://h/base?a=1"


def test_oauth2_client_credentials(server) -> None:
    client._TOKENS.clear()
    definition = {
        "url": "/echo",
        "auth": {
            "type": "oauth2",
            "token_url": server + "/token",
            "client_id": "${entv:" + NS + "/SIT_CLIENT_ID}",
            "client_secret": "${entv:" + NS + "/SIT_SECRET}",
        },
    }
    result = execute(definition, _resolver(server, SIT_SECRET="s3cr3t-value"), NS)
    echoed = json.loads(result["body"])
    assert echoed["headers"]["Authorization"] == "Bearer tok-123456"
    assert dict(result["request"]["headers"])["Authorization"] == f"Bearer {MASK}"


def test_polling_flow(server) -> None:
    definition = {
        "method": "POST",
        "url": "/jobs",
        "polling": {
            "enabled": True,
            "extract": {"source": "json", "expression": "$.links.status"},
            "stop": {"type": "json", "path": "status", "values": "COMPLETED,FAILED"},
        },
    }
    first = execute(definition, _resolver(server), NS)
    assert first["status"] == 202
    poll_url = first["poll"]["url"]
    assert poll_url == "jobs/42/status"

    states = []
    for _ in range(5):
        result = execute(definition, _resolver(server), NS, poll_url=poll_url)
        assert json.loads(result["body"])["status"] in ("RUNNING", "COMPLETED")
        # Relative to the request URL (…/api/jobs).
        assert result["request"]["url"] == server + "/api/jobs/42/status"
        states.append(result["poll"]["done"])
        if result["poll"]["done"]:
            break
    assert states == [False, False, True]


def test_polling_reports_a_missing_poll_url(server) -> None:
    definition = {
        "url": "/echo",
        "polling": {"enabled": True, "extract": {"source": "header", "expression": "Location"}},
    }
    result = execute(definition, _resolver(server), NS)
    assert "no 'Location' header" in result["poll"]["error"]


def test_redirects_binary_truncation_and_errors(server, monkeypatch) -> None:
    resolver = _resolver(server, environment=None)
    followed = execute({"url": server + "/redirect"}, resolver, NS)
    assert followed["status"] == 200 and json.loads(followed["body"])["path"] == "/api/echo"

    kept = execute(
        {"url": server + "/redirect", "options": {"follow_redirects": False}}, resolver, NS
    )
    assert kept["status"] == 302
    assert dict(kept["headers"])["Location"] == "/api/echo"

    binary = execute({"url": server + "/binary"}, resolver, NS)
    assert binary["is_base64"] is True
    assert base64.b64decode(binary["body"]) == bytes(range(256))

    monkeypatch.setattr(client, "MAX_BODY_BYTES", 100)
    monkeypatch.setattr(client.send, "__defaults__", (100,))
    big = execute({"url": server + "/big"}, resolver, NS)
    assert big["truncated"] is True and big["size"] == 100

    refused = execute({"url": "http://127.0.0.1:9/"}, resolver, NS)
    assert refused["error"].startswith("Connection failed")

    with pytest.raises(EagleRequestError, match="Only http"):
        prepare({"url": "file:///etc/passwd"}, resolver, NS)


# ----------------------------------------------------------------------
# TLS: CA bundle, client certificates (PEM and PFX)
# ----------------------------------------------------------------------


def _certificates() -> Dict[str, bytes]:
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.hazmat.primitives.serialization import pkcs12
    from cryptography.x509.oid import NameOID

    now = datetime.datetime.now(datetime.timezone.utc)

    def build(subject: str, key, issuer_name, issuer_key, *, ca=False, server=False):
        builder = (
            x509.CertificateBuilder()
            .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, subject)]))
            .issuer_name(issuer_name)
            .public_key(key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(now - datetime.timedelta(minutes=5))
            .not_valid_after(now + datetime.timedelta(days=1))
            .add_extension(x509.BasicConstraints(ca=ca, path_length=None), critical=True)
        )
        if server:
            builder = builder.add_extension(
                x509.SubjectAlternativeName([x509.IPAddress(ipaddress.ip_address("127.0.0.1"))]),
                critical=False,
            )
        return builder.sign(issuer_key, hashes.SHA256())

    ca_key = ec.generate_private_key(ec.SECP256R1())
    ca_name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Eagle Test CA")])
    ca = build("Eagle Test CA", ca_key, ca_name, ca_key, ca=True)
    server_key = ec.generate_private_key(ec.SECP256R1())
    server_cert = build("127.0.0.1", server_key, ca_name, ca_key, server=True)
    client_key = ec.generate_private_key(ec.SECP256R1())
    client_cert = build("eagle-client", client_key, ca_name, ca_key)

    def pem_key(key) -> bytes:
        return key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )

    pem = serialization.Encoding.PEM
    return {
        "ca": ca.public_bytes(pem),
        "server_cert": server_cert.public_bytes(pem),
        "server_key": pem_key(server_key),
        "client_cert": client_cert.public_bytes(pem),
        "client_key": pem_key(client_key),
        "client_pfx": pkcs12.serialize_key_and_certificates(
            b"client",
            client_key,
            client_cert,
            None,
            serialization.BestAvailableEncryption(b"pfx-pass"),
        ),
    }


@pytest.fixture(scope="module")
def tls_server(tmp_path_factory) -> Iterator[Dict[str, Any]]:
    material = _certificates()
    folder = tmp_path_factory.mktemp("tls")
    for name in ("ca", "server_cert", "server_key"):
        (folder / f"{name}.pem").write_bytes(material[name])
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(folder / "server_cert.pem", folder / "server_key.pem")
    context.load_verify_locations(folder / "ca.pem")
    context.verify_mode = ssl.CERT_REQUIRED

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    httpd.socket = context.wrap_socket(httpd.socket, server_side=True)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield {"url": f"https://127.0.0.1:{httpd.server_address[1]}", **material}
    httpd.shutdown()
    httpd.server_close()


def _tls_resolver(material: Dict[str, Any]) -> Resolver:
    values = {
        "CA": _file("ca.pem", material["ca"]),
        "CERT": _file("client.crt", material["client_cert"]),
        "KEY": _file("client.key", material["client_key"]),
        "PFX": _file("client.pfx", material["client_pfx"]),
        "PFX_PASSWORD": "pfx-pass",
    }
    return Resolver(_fetch(values), None)


def _ref(key: str, kind: str = "entvfile") -> str:
    return "${" + kind + ":" + NS + "/" + key + "}"


def test_tls_with_pem_client_certificate(tls_server) -> None:
    definition = {
        "url": tls_server["url"] + "/echo",
        "tls": {
            "ca_bundle": _ref("CA"),
            "client_cert": "pem",
            "cert": _ref("CERT"),
            "key": _ref("KEY"),
        },
    }
    result = execute(definition, _tls_resolver(tls_server), NS)
    assert result.get("error") is None, result.get("error")
    assert result["status"] == 200


def test_tls_with_pfx_client_certificate(tls_server) -> None:
    definition = {
        "url": tls_server["url"] + "/echo",
        "tls": {
            "ca_bundle": _ref("CA"),
            "client_cert": "pfx",
            "pfx": _ref("PFX"),
            "password": _ref("PFX_PASSWORD", "entv"),
        },
    }
    result = execute(definition, _tls_resolver(tls_server), NS)
    assert result.get("error") is None, result.get("error")
    assert result["status"] == 200


def test_tls_failures(tls_server) -> None:
    resolver = _tls_resolver(tls_server)
    # Unknown CA: verification fails.
    untrusted = execute({"url": tls_server["url"] + "/echo"}, resolver, NS)
    assert untrusted["error"].startswith("TLS error")
    # Trusted, but the server wants a client certificate.
    without_cert = execute(
        {"url": tls_server["url"] + "/echo", "tls": {"ca_bundle": _ref("CA")}}, resolver, NS
    )
    assert without_cert.get("error")
    with pytest.raises(EagleRequestError, match="PFX/P12 keystore could not be opened"):
        execute(
            {
                "url": tls_server["url"] + "/echo",
                "tls": {"client_cert": "pfx", "pfx": _ref("PFX"), "password": "wrong"},
            },
            resolver,
            NS,
        )


# ----------------------------------------------------------------------
# TLS profiles (project settings)
# ----------------------------------------------------------------------


def test_tls_modes_and_profiles() -> None:
    from lib.tools.eagleapi.store import (
        EagleStoreError,
        effective_tls,
        normalize_request,
        normalize_settings,
    )

    settings = normalize_settings(
        {
            "tls_profiles": [
                {"id": "sit", "name": "SIT mTLS", "client_cert": "pfx", "pfx": "${entvfile:e/P}"},
                {"id": "lab", "name": "Lab", "verify": False},
            ],
            "default_tls": "sit",
        }
    )
    # New requests inherit the project default.
    plain = normalize_request({})
    assert plain["tls"]["mode"] == "inherit"
    tls, source = effective_tls(plain, settings)
    assert tls["pfx"] == "${entvfile:e/P}" and source == "default SIT mTLS"

    chosen = normalize_request({"tls": {"mode": "profile", "profile": "lab"}})
    tls, source = effective_tls(chosen, settings)
    assert tls["verify"] is False and source == "profile Lab"

    own = normalize_request({"tls": {"mode": "custom", "verify": False}})
    tls, source = effective_tls(own, settings)
    assert tls["verify"] is False and source == "request"

    # Requests saved before profiles existed keep their own settings.
    legacy = normalize_request({"tls": {"client_cert": "pem", "cert": "${entvfile:e/C}"}})
    assert legacy["tls"]["mode"] == "custom"

    # No default: nothing special (verify on, no client certificate).
    tls, source = effective_tls(plain, {**settings, "default_tls": ""})
    assert tls["verify"] is True and tls["client_cert"] == "none" and source == "none"

    with pytest.raises(EagleStoreError, match="no longer exists"):
        effective_tls(normalize_request({"tls": {"mode": "profile", "profile": "gone"}}), settings)
    with pytest.raises(EagleStoreError, match="two TLS profiles"):
        normalize_settings({"tls_profiles": [{"name": "A"}, {"name": "a"}]})
