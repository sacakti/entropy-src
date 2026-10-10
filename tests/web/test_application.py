"""Tests for the Entropy web application foundation."""

from fastapi.testclient import TestClient

from core.web.application import create_app


class FakeContextFactory:
    """Provide a lightweight factory for web lifecycle tests."""

    def __init__(self, interactive: bool = False) -> None:
        self.interactive = interactive
        self.discovered = False

    def build(self) -> object:
        return object()

    def discover(self) -> None:
        self.discovered = True


def test_health_reports_initialized_context() -> None:
    factory = FakeContextFactory()
    app = create_app(factory)  # type: ignore[arg-type]

    with TestClient(app) as client:
        response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "application": "entropy",
        "initialized": True,
    }
    assert factory.discovered


def test_health_reports_uninitialized_context_without_startup() -> None:
    app = create_app(FakeContextFactory())  # type: ignore[arg-type]

    response = TestClient(app, raise_server_exceptions=False).get("/api/health")

    assert response.status_code == 200
    assert response.json()["initialized"] is False
