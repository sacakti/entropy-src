"""The icon chosen for each plugin."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from core.web.routes import plugins as routes
from lib.database.connection import DatabaseConnection
from lib.plugins.icons import PluginIconError, PluginIconStore


@pytest.fixture()
def connection(tmp_path: Path) -> DatabaseConnection:
    return DatabaseConnection(tmp_path / "entropy.db")


@pytest.fixture()
def store(connection) -> PluginIconStore:
    return PluginIconStore(connection)


def test_choosing_replaces_and_none_goes_back_to_the_default(store) -> None:
    store.set("oc.audit", "rocket", "admin")
    store.set("oc.audit", "shield", "admin")
    store.set("oc.generic", "ship", "admin")

    assert store.all() == {"oc.audit": "shield", "oc.generic": "ship"}

    store.set("oc.audit", None, "admin")

    assert store.all() == {"oc.generic": "ship"}


@pytest.mark.parametrize("icon", ["", "Rocket", "a b", "<svg>", "x" * 61, "-dash", "../x"])
def test_badly_formed_icons_are_refused(store, icon) -> None:
    with pytest.raises(PluginIconError):
        store.set("oc.audit", icon, "admin")

    assert store.all() == {}


def test_a_choice_outlives_the_store_being_reopened(connection, store) -> None:
    store.set("oc.audit", "rocket", "admin")

    assert PluginIconStore(connection).all() == {"oc.audit": "rocket"}


# ----------------------------------------------------------------------
# Route
# ----------------------------------------------------------------------


def _call(connection, monkeypatch, name: str, icon, known=("oc.audit",), checked=None):
    plugins = [
        SimpleNamespace(namespace=item.split(".")[0], name=item.split(".")[1]) for item in known
    ]
    monkeypatch.setattr(
        routes, "_plugin_manager", lambda request: SimpleNamespace(list=lambda: plugins)
    )
    monkeypatch.setattr(routes, "_studio", lambda request: SimpleNamespace(drafts=lambda: []))
    monkeypatch.setattr(
        routes,
        "_require_permission",
        lambda request, user, permission: (checked if checked is not None else []).append(
            permission
        ),
    )
    context = SimpleNamespace(database_manager=SimpleNamespace(connection=connection))
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(entropy_context=context)))
    record = ("token", MagicMock(), SimpleNamespace(username="admin", id=1))
    return routes.set_plugin_icon(name, routes.PluginIconRequest(icon=icon), request, record)


def test_route_saves_and_needs_write_permission(connection, store, monkeypatch) -> None:
    checked = []

    result = _call(connection, monkeypatch, "oc.audit", "rocket", checked=checked)

    assert result == {"qualified_name": "oc.audit", "icon": "rocket"}
    assert checked == ["plugins.write"]
    assert store.all() == {"oc.audit": "rocket"}


def test_route_resets(connection, store, monkeypatch) -> None:
    store.set("oc.audit", "rocket", "admin")

    assert _call(connection, monkeypatch, "oc.audit", None)["icon"] is None
    assert store.all() == {}


def test_route_refuses_an_unknown_plugin(connection, store, monkeypatch) -> None:
    with pytest.raises(HTTPException) as caught:
        _call(connection, monkeypatch, "oc.missing", "rocket")

    assert caught.value.status_code == 404
    assert store.all() == {}


def test_route_refuses_a_bad_icon(connection, store, monkeypatch) -> None:
    with pytest.raises(HTTPException) as caught:
        _call(connection, monkeypatch, "oc.audit", "Not An Icon")

    assert caught.value.status_code == 422
