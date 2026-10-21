"""Plugin help pages: safe manuals and usage examples."""

from __future__ import annotations

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
