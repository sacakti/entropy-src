"""The web server serves the built UI next to the API."""

from fastapi.testclient import TestClient

from core.web.application import create_app
from tests.web.test_application import FakeContextFactory


def _client(tmp_path, monkeypatch) -> TestClient:
    (tmp_path / "assets").mkdir()
    (tmp_path / "index.html").write_text("<html>entropy</html>", encoding="utf-8")
    (tmp_path / "assets" / "app-1234.js").write_text("console.log(1)", encoding="utf-8")
    (tmp_path / "logo.svg").write_text("<svg/>", encoding="utf-8")
    monkeypatch.setenv("ENTROPY_WEB_DIST", str(tmp_path))
    return TestClient(create_app(FakeContextFactory()))  # type: ignore[arg-type]


def test_index_and_spa_routes_serve_the_ui(tmp_path, monkeypatch) -> None:
    client = _client(tmp_path, monkeypatch)

    for path in ("/", "/runs", "/admin/system"):
        response = client.get(path)
        assert response.status_code == 200
        assert "entropy" in response.text
        assert response.headers["cache-control"] == "no-cache"


def test_hashed_assets_are_cached(tmp_path, monkeypatch) -> None:
    client = _client(tmp_path, monkeypatch)

    response = client.get("/assets/app-1234.js")
    assert response.status_code == 200
    assert "immutable" in response.headers["cache-control"]
    assert client.head("/assets/app-1234.js").status_code == 200
    assert client.get("/logo.svg").headers["cache-control"] == "no-cache"


def test_api_paths_are_not_swallowed(tmp_path, monkeypatch) -> None:
    client = _client(tmp_path, monkeypatch)

    assert client.get("/api/health").json()["application"] == "entropy"
    assert client.get("/api/does-not-exist").status_code == 404


def test_paths_outside_the_build_fall_back_to_index(tmp_path, monkeypatch) -> None:
    secret = tmp_path.parent / "secret.txt"
    secret.write_text("secret", encoding="utf-8")
    client = _client(tmp_path, monkeypatch)

    response = client.get("/..%2Fsecret.txt")
    assert "secret" not in response.text


def test_no_build_means_no_ui(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("ENTROPY_WEB_DIST", str(tmp_path / "missing"))
    client = TestClient(create_app(FakeContextFactory()))  # type: ignore[arg-type]

    assert client.get("/").status_code == 404
