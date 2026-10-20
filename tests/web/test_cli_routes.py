"""Bearer tokens for the command line and the CLI download endpoints."""

from __future__ import annotations

from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from core.web.routes import cli
from core.web.routes.auth import bearer_token, verify_csrf


def _app() -> FastAPI:
    app = FastAPI()
    app.include_router(cli.router)

    @app.post("/guarded", dependencies=[Depends(verify_csrf)])
    def guarded() -> dict:
        return {"ok": True}

    return app


def test_bearer_token_parsing() -> None:
    class Fake:
        def __init__(self, value: str) -> None:
            self.headers = {"authorization": value} if value else {}

    assert bearer_token(Fake("Bearer abc")) == "abc"  # type: ignore[arg-type]
    assert bearer_token(Fake("bearer  abc ")) == "abc"  # type: ignore[arg-type]
    assert bearer_token(Fake("Basic abc")) is None  # type: ignore[arg-type]
    assert bearer_token(Fake("Bearer ")) is None  # type: ignore[arg-type]
    assert bearer_token(Fake("")) is None  # type: ignore[arg-type]


def test_bearer_requests_need_no_csrf_token() -> None:
    client = TestClient(_app())

    assert client.post("/guarded").status_code == 403
    response = client.post("/guarded", headers={"Authorization": "Bearer t"})
    assert response.status_code == 200


def test_cli_info_and_installers_name_this_server() -> None:
    client = TestClient(_app(), base_url="http://entropy.test:8000")

    info = client.get("/api/cli").json()
    assert info["server"] == "http://entropy.test:8000"
    assert info["install"]["posix"] == "curl -fsSL http://entropy.test:8000/api/cli/install.sh | sh"
    assert info["login"] == "ent login http://entropy.test:8000"

    script = client.get("/api/cli/install.sh").text
    assert 'SERVER="http://entropy.test:8000"' in script
    assert "__SERVER__" not in script
    assert (
        "irm http://entropy.test:8000/api/cli/install.ps1"
        in client.get("/api/cli/install.ps1").text
    )


def test_server_url_honours_proxy_and_rejects_junk() -> None:
    client = TestClient(_app())

    proxied = client.get(
        "/api/cli", headers={"X-Forwarded-Proto": "https", "X-Forwarded-Host": "ent.example.com"}
    ).json()
    assert proxied["server"] == "https://ent.example.com"

    junk = client.get("/api/cli", headers={"X-Forwarded-Host": 'evil"; rm -rf /'}).json()
    assert junk["server"] == ""


def test_pyz_download_is_a_zipapp() -> None:
    response = TestClient(_app()).get("/api/cli/ent.pyz")

    assert response.status_code == 200
    assert response.content.startswith(b"#!/usr/bin/env python3\n")
    assert b"ent_cli/commands.py" in response.content
