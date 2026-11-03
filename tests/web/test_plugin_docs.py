"""Plugin help pages: safe manuals and usage examples."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

import pytest

from core.web.plugin_studio.docs import render_markdown, usage_step


def test_manual_html_is_escaped_and_links_are_safe() -> None:
    html = render_markdown(
        "<script>alert(1)</script>\n\n[bad](javascript:alert(1)) [good](https://example.com)"
    )

    assert "<script>" not in html and "&lt;script&gt;" in html
    assert "javascript:" not in html
    assert 'href="https://example.com"' in html and 'rel="noopener noreferrer"' in html


def test_manual_keeps_tables_and_code() -> None:
    html = render_markdown("| a |\n|---|\n| 1 |\n\n```yaml\nx: <y>\n```")

    assert "<table>" in html
    assert "x: &lt;y&gt;" in html


def test_usage_step_from_contract() -> None:
    contract = {
        "arguments": [
            {"name": "url", "type": "string", "required": True, "default": None},
            {"name": "retries", "type": "integer", "required": False, "default": 3},
            {"name": "token", "type": "string", "required": False, "default": None},
        ]
    }

    step = usage_step("acme.fetch", contract, None)

    assert step["plugin"] == "acme.fetch" and step["name"] == "fetch"
    # Required and default-less arguments are shown; defaults may be omitted.
    assert step["arguments"] == {"url": "<url>", "token": "<token>"}


def test_usage_step_prefers_the_plugins_example() -> None:
    example = {"name": "Hello", "plugin": "builtin.hello", "arguments": {}}

    assert usage_step("builtin.hello", {"arguments": []}, example) is example


# ----------------------------------------------------------------------
# Plugin list dependencies
# ----------------------------------------------------------------------


def test_list_dependencies_read_from_manifest(tmp_path: Path) -> None:
    from core.web.routes.plugins import _manifest_dependencies

    (tmp_path / "plugin.json").write_text(
        json.dumps(
            {
                "dependencies": [{"name": "paramiko", "version": "3.0"}, "requests", {}],
                "required_plugins": [{"name": "oc.sync_yamls"}],
            },
        ),
        encoding="utf-8",
    )

    assert _manifest_dependencies(tmp_path) == {
        "extensions": [{"name": "paramiko", "version": "3.0"}, {"name": "requests"}],
        "plugins": [{"name": "oc.sync_yamls"}],
        "tools": [],
    }


@pytest.mark.parametrize("content", [None, "not json", "[]"])
def test_list_dependencies_tolerate_missing_or_bad_manifest(
    tmp_path: Path, content: Optional[str]
) -> None:
    from core.web.routes.plugins import _manifest_dependencies

    if content is not None:
        (tmp_path / "plugin.json").write_text(content, encoding="utf-8")

    assert _manifest_dependencies(tmp_path) == {"extensions": [], "plugins": [], "tools": []}
    assert _manifest_dependencies(None) == {"extensions": [], "plugins": [], "tools": []}
