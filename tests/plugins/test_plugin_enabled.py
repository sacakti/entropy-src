"""Turning a plugin on or off from the web, and what a disabled plugin then does."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from core.web.routes import plugins as routes
from lib.plugins.exceptions import InvalidPluginNameError, PluginNotFoundError

CSS = Path(__file__).resolve().parents[2] / "frontend" / "src" / "styles" / "plugins.css"
RECORD = ("token", MagicMock(), SimpleNamespace(username="admin", id=1))


def _call(monkeypatch, manager, name: str, enabled: bool, checked=None):
    monkeypatch.setattr(routes, "_plugin_manager", lambda request: manager)
    monkeypatch.setattr(
        routes,
        "_require_permission",
        lambda request, user, permission: (checked if checked is not None else []).append(
            permission
        ),
    )
    return routes.set_plugin_enabled(
        name, routes.PluginEnabledRequest(enabled=enabled), MagicMock(), RECORD
    )


def test_disabling_and_enabling_reach_the_manager(monkeypatch) -> None:
    manager = MagicMock()
    checked = []

    result = _call(monkeypatch, manager, "oc.audit", False, checked)

    assert result == {"qualified_name": "oc.audit", "enabled": False}
    manager.disable.assert_called_once_with("oc.audit")
    manager.enable.assert_not_called()
    assert checked == ["plugins.write"]

    assert _call(monkeypatch, manager, "oc.audit", True)["enabled"] is True
    manager.enable.assert_called_once_with("oc.audit")


def test_no_permission_changes_nothing(monkeypatch) -> None:
    manager = MagicMock()
    monkeypatch.setattr(routes, "_plugin_manager", lambda request: manager)

    def refuse(*arguments):
        raise HTTPException(status_code=403, detail="Forbidden")

    monkeypatch.setattr(routes, "_require_permission", refuse)

    with pytest.raises(HTTPException) as caught:
        routes.set_plugin_enabled(
            "oc.audit", routes.PluginEnabledRequest(enabled=False), MagicMock(), RECORD
        )

    assert caught.value.status_code == 403
    manager.disable.assert_not_called()


@pytest.mark.parametrize(
    ("error", "status"),
    [(PluginNotFoundError("oc.none"), 404), (InvalidPluginNameError("bad"), 422)],
)
def test_an_unknown_or_bad_name_is_reported(monkeypatch, error, status) -> None:
    manager = MagicMock()
    manager.disable.side_effect = error

    with pytest.raises(HTTPException) as caught:
        _call(monkeypatch, manager, "oc.none", False)

    assert caught.value.status_code == status


def _rules_outside_comments() -> str:
    import re

    return re.sub(r"/\*.*?\*/", "", CSS.read_text(encoding="utf-8"), flags=re.S)


def test_status_colours_are_real_rules_not_swallowed_by_a_comment() -> None:
    rules = _rules_outside_comments()

    assert ".entropy-app .list-status-enabled" in rules
    assert ".entropy-app .list-status-disabled" in rules
    assert ".entropy-app .list-loading" in rules


def test_enabled_is_green_and_disabled_is_not_grey() -> None:
    import re

    rules = _rules_outside_comments()

    def colour(name: str) -> str:
        return re.search(rf"\.{name}\s*\{{\s*color:\s*([^;]+);", rules).group(1)

    assert colour("list-status-enabled") == "var(--app-success)"
    assert colour("list-status-disabled") not in ("var(--app-muted)", "var(--app-success)")


def test_the_stylesheet_has_no_comment_hiding_rules() -> None:
    import re

    text = CSS.read_text(encoding="utf-8")

    assert text.count("/*") == text.count("*/")
    assert not [item for item in re.findall(r"/\*.*?\*/", text, flags=re.S) if "}" in item]
