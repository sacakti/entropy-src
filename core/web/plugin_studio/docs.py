"""
A plugin's help page: what it does, its inputs and outputs, how to use it
in a workflow, its manual, and which workflows use it.

Manuals (MAN.md, README.md) are written by whoever can save plugins, so
they are rendered with raw HTML disabled and only http(s), mailto and
in-page links kept.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional
from xml.etree import ElementTree

from .contract import plugin_contract

MANUAL_FILES = ("MAN.md", "README.md")
MAX_MANUAL_BYTES = 512 * 1024
SAFE_URL = re.compile(r"^(https?:|mailto:|#)", re.IGNORECASE)


def render_markdown(text: str) -> str:
    """Markdown to HTML with raw HTML escaped and unsafe links removed."""

    import markdown
    from markdown.treeprocessors import Treeprocessor

    class SafeLinks(Treeprocessor):
        def run(self, root: ElementTree.Element) -> None:
            for element in root.iter():
                for attribute in ("href", "src"):
                    value = element.get(attribute)
                    if value is not None and not SAFE_URL.match(value.strip()):
                        del element.attrib[attribute]
                if element.tag == "a" and str(element.get("href", "")).lower().startswith("http"):
                    element.set("target", "_blank")
                    element.set("rel", "noopener noreferrer")

    renderer = markdown.Markdown(
        extensions=["fenced_code", "tables", "sane_lists", "toc"],
        extension_configs={"toc": {"permalink": False}},
        output_format="html",
    )
    # No raw HTML: it is shown as text.
    renderer.preprocessors.deregister("html_block")
    renderer.inlinePatterns.deregister("html")
    renderer.treeprocessors.register(SafeLinks(renderer), "entropy_safe_links", 0)
    return renderer.convert(text)


def _read(path: Path) -> Optional[str]:
    try:
        if path.is_file() and path.stat().st_size <= MAX_MANUAL_BYTES:
            return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    return None


def _metadata(directory: Path) -> Dict[str, Any]:
    try:
        data = json.loads((directory / "plugin.json").read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _example(directory: Path, qualified_name: str) -> Optional[Dict[str, Any]]:
    """The step from the plugin's own example workflow, if it ships one."""

    text = _read(directory / "workflow.json")
    if not text:
        return None
    try:
        workflow = json.loads(text)
    except ValueError:
        return None
    for step in workflow.get("steps") or []:
        if isinstance(step, dict) and step.get("plugin") == qualified_name:
            return step
    return None


def _value_example(argument: Dict[str, Any]) -> Any:
    if argument.get("default") is not None:
        return argument["default"]
    return {
        "integer": 1,
        "number": 1.0,
        "boolean": True,
        "list": [],
        "dict": {},
    }.get(str(argument.get("type")), f"<{argument['name']}>")


def usage_step(qualified_name: str, contract: Dict[str, Any], example: Optional[Dict[str, Any]]):
    """A workflow step using the plugin: its own example, else built from its contract."""

    if example:
        return example
    name = qualified_name.split(".", 1)[-1]
    return {
        "name": name,
        "plugin": qualified_name,
        "enabled": True,
        "on_failure": "abort",
        "arguments": {
            argument["name"]: _value_example(argument)
            for argument in contract.get("arguments", [])
            if argument.get("required") or argument.get("default") is None
        },
    }


def used_by(workflows: Any, qualified_name: str, limit: int = 50) -> List[Dict[str, Any]]:
    """Registered workflows with a step that uses the plugin."""

    found: List[Dict[str, Any]] = []
    try:
        # Every project's: names are only unique within a project.
        entries = [(item.name, item.project_id) for item in workflows.list_all()]
    except Exception:  # noqa: BLE001 - help still works without this list
        return found
    for name, project_id in entries:
        try:
            workflow = workflows.get(name, project_id=project_id)
        except Exception:  # noqa: BLE001 - skip unreadable workflows
            continue
        steps = [step.name for step in workflow.steps if step.plugin == qualified_name]
        if steps:
            found.append({"name": workflow.name, "version": workflow.version, "steps": steps})
            if len(found) >= limit:
                break
    return found


def plugin_docs(plugin: Any, workflows: Any) -> Dict[str, Any]:
    directory = Path(plugin.path)
    qualified_name = f"{plugin.namespace}.{plugin.name}"
    metadata = _metadata(directory)
    contract = (
        plugin_contract(directory)
        if directory.is_dir()
        else {"description": None, "arguments": [], "outputs": []}
    )

    manual = None
    for filename in MANUAL_FILES:
        text = _read(directory / filename)
        if text and text.strip():
            manual = {"file": filename, "html": render_markdown(text)}
            break

    example = _example(directory, qualified_name)
    return {
        "description": metadata.get("description") or contract.get("description"),
        "author": metadata.get("author"),
        "license": metadata.get("license"),
        "tags": [str(tag) for tag in metadata.get("tags") or []],
        "dependencies": [str(item) for item in metadata.get("dependencies") or []],
        "entropy": metadata.get("entropy"),
        "arguments": contract.get("arguments", []),
        "outputs": contract.get("outputs", []),
        "usage": usage_step(qualified_name, contract, example),
        "usage_from_example": example is not None,
        "manual": manual,
        "used_by": used_by(workflows, qualified_name) if workflows is not None else [],
    }
