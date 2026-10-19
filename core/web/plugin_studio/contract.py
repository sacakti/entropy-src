"""
Plugin contracts: the arguments a plugin reads and the outputs it publishes.

Plugins do not declare these in plugin.json; they read arguments through the
SDK (``self.arguments.string("name", default, required=True)``) and publish
outputs through ``self.outputs``. The contract is recovered from the plugin
source so the workflow builder can offer typed argument fields and
``${steps.<step>.outputs.<key>}`` references.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path
from typing import Any

# PluginArguments method -> argument type shown in the builder.
ARGUMENT_TYPES = {
    "string": "string",
    "boolean": "boolean",
    "integer": "integer",
    "number": "number",
    "path": "path",
    "list": "list",
    "dictionary": "dictionary",
    "get": "any",
    "required": "any",
}

_UNKNOWN = object()


def _literal(node: ast.AST | None) -> Any:
    if node is None:
        return None

    try:
        value = ast.literal_eval(node)
    except (ValueError, SyntaxError, TypeError):
        return _UNKNOWN

    # Paths and other objects are not representable in a workflow definition.
    return value if isinstance(value, (str, int, float, bool, list, dict, type(None))) else _UNKNOWN


def _is_arguments(node: ast.AST, aliases: set[str]) -> bool:
    """True for ``self.arguments``, ``<anything>.arguments`` or an alias of them."""

    if isinstance(node, ast.Attribute):
        return node.attr == "arguments"

    return isinstance(node, ast.Name) and node.id in aliases


def _is_outputs(node: ast.AST) -> bool:
    return isinstance(node, ast.Attribute) and node.attr == "outputs"


def _string_keys(node: ast.AST) -> list[str]:
    if isinstance(node, ast.Dict):
        return [
            key.value
            for key in node.keys
            if isinstance(key, ast.Constant) and isinstance(key.value, str)
        ]

    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "dict":
        return [keyword.arg for keyword in node.keywords if keyword.arg]

    return []


def _scan(tree: ast.Module, arguments: dict[str, dict[str, Any]], outputs: list[str]) -> None:
    aliases = {
        target.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Assign) and _is_arguments(node.value, set())
        for target in node.targets
        if isinstance(target, ast.Name)
    }

    for node in ast.walk(tree):
        # arguments.<method>("name", default, required=...)
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr in ARGUMENT_TYPES
            and _is_arguments(node.func.value, aliases)
            and node.args
            and isinstance(node.args[0], ast.Constant)
            and isinstance(node.args[0].value, str)
        ):
            method = node.func.attr
            name = node.args[0].value
            keywords = {keyword.arg: keyword.value for keyword in node.keywords if keyword.arg}

            default_node = node.args[1] if len(node.args) > 1 else keywords.get("default")
            default = _literal(default_node)
            required = method == "required" or _literal(keywords.get("required")) is True

            entry = arguments.setdefault(
                name,
                {
                    "name": name,
                    "type": ARGUMENT_TYPES[method],
                    "required": False,
                    "default": None,
                },
            )

            # Prefer the most specific type and any concrete default seen.
            if entry["type"] == "any":
                entry["type"] = ARGUMENT_TYPES[method]
            entry["required"] = entry["required"] or required
            if default is not _UNKNOWN and default is not None and entry["default"] is None:
                entry["default"] = default

            for bound in ("minimum", "maximum"):
                value = _literal(keywords.get(bound))
                if isinstance(value, (int, float)) and not isinstance(value, bool):
                    entry[bound] = value
            continue

        # self.outputs["key"] = ...
        if isinstance(node, (ast.Assign, ast.AugAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]

            for target in targets:
                if (
                    isinstance(target, ast.Subscript)
                    and _is_outputs(target.value)
                    and isinstance(target.slice, ast.Constant)
                    and isinstance(target.slice.value, str)
                ):
                    outputs.append(target.slice.value)
            continue

        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            # self.outputs.update({...}) / self.outputs.update(key=...)
            if node.func.attr == "update" and _is_outputs(node.func.value):
                for argument in node.args:
                    outputs.extend(_string_keys(argument))
                outputs.extend(keyword.arg for keyword in node.keywords if keyword.arg)

            # self.outputs.setdefault("key", ...)
            if (
                node.func.attr == "setdefault"
                and _is_outputs(node.func.value)
                and node.args
                and isinstance(node.args[0], ast.Constant)
                and isinstance(node.args[0].value, str)
            ):
                outputs.append(node.args[0].value)

        # PluginResult(outputs={...})
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "PluginResult"
        ):
            for keyword in node.keywords:
                if keyword.arg == "outputs":
                    outputs.extend(_string_keys(keyword.value))


def plugin_contract(directory: Path) -> dict[str, Any]:
    """Return the arguments and outputs used by the plugin in ``directory``."""

    arguments: dict[str, dict[str, Any]] = {}
    outputs: list[str] = []

    for path in sorted(directory.rglob("*.py")):
        if "__pycache__" in path.parts or "tests" in path.relative_to(directory).parts:
            continue

        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except (SyntaxError, UnicodeDecodeError):
            continue

        _scan(tree, arguments, outputs)

    description = None
    manifest = directory / "plugin.json"

    if manifest.is_file():
        try:
            description = (
                json.loads(manifest.read_text(encoding="utf-8")).get("description") or None
            )
        except (json.JSONDecodeError, UnicodeDecodeError, AttributeError):
            description = None

    return {
        "description": description,
        "arguments": sorted(
            arguments.values(), key=lambda item: (not item["required"], item["name"])
        ),
        "outputs": sorted(set(outputs)),
    }
