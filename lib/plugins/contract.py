"""
Plugin contracts: the arguments a plugin takes and the outputs it publishes.

Every plugin declares them in plugin.json:

    "arguments": [
        {"name": "host", "type": "string", "required": true,
         "description": "Server to connect to"},
        {"name": "port", "type": "integer", "default": 22,
         "minimum": 1, "maximum": 65535},
        {"name": "password", "type": "string", "secret": true},
        {"name": "operation", "type": "string", "choices": ["upload", "download"]},
        {"name": "source", "type": "path", "path": "file"},
        {"name": "files", "type": "list"},
        {"name": "options", "type": "dictionary"},
        {"name": "dry_run", "type": "boolean", "default": false}
    ],
    "outputs": [
        {"name": "files_transferred", "type": "integer", "description": "..."}
    ]

Types: string, boolean, integer, number, path, list, dictionary, any.
Required arguments have no default. Paths say whether they are a "file",
a "directory" or "any" (the web UI offers a file browser).

The contract is checked when a plugin is installed (well formed, and the
source reads and publishes nothing undeclared), before it runs (required
arguments present, types and ranges, no unknown arguments) and when it
finishes (published outputs are declared). Plugins installed before
contracts existed keep working with a contract inferred from their source.
"""

from __future__ import annotations

import ast
import json
import re
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


# ----------------------------------------------------------------------
# Declared contracts
# ----------------------------------------------------------------------

TYPES = ("string", "boolean", "integer", "number", "path", "list", "dictionary", "any")
PATH_KINDS = ("file", "directory", "any")
NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
ARGUMENT_KEYS = {
    "name",
    "type",
    "required",
    "default",
    "description",
    "secret",
    "choices",
    "minimum",
    "maximum",
    "path",
    "label",
    "example",
    # Asked for at run time when an interactive run does not give it.
    "prompt",
}
OUTPUT_KEYS = {"name", "type", "description"}

# What a lifecycle may look like: hooks a plugin may define, in run order.
LIFECYCLE = ("validate", "prepare", "execute", "cleanup")


class ContractError(ValueError):
    """A contract that is not well formed, or values that break it."""

    def __init__(self, problems: list[str]) -> None:
        super().__init__("; ".join(problems))
        self.problems = problems


def _type_ok(kind: str, value: Any) -> bool:
    if value is None or kind == "any":
        return True
    if kind in ("string", "path"):
        return isinstance(value, str)
    if kind == "boolean":
        return isinstance(value, bool)
    if kind == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if kind == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if kind == "list":
        return isinstance(value, list)
    if kind == "dictionary":
        return isinstance(value, dict)
    return False


def normalize(data: Any) -> dict[str, Any]:
    """A well-formed contract from plugin.json's "arguments" and "outputs"."""

    problems: list[str] = []
    data = data if isinstance(data, dict) else {}
    raw_arguments = data.get("arguments")
    raw_outputs = data.get("outputs")
    if not isinstance(raw_arguments, list):
        problems.append('"arguments" must be a list (empty when the plugin takes none)')
        raw_arguments = []
    if not isinstance(raw_outputs, list):
        problems.append('"outputs" must be a list (empty when the plugin publishes none)')
        raw_outputs = []

    arguments: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, item in enumerate(raw_arguments):
        where = f"argument {index + 1}"
        if not isinstance(item, dict):
            problems.append(f"{where} must be an object")
            continue
        name = item.get("name")
        if not isinstance(name, str) or not NAME.match(name):
            problems.append(f"{where}: 'name' must be a Python-style identifier")
            continue
        where = f"argument '{name}'"
        if name in seen:
            problems.append(f"{where} is declared twice")
        seen.add(name)
        unknown = set(item) - ARGUMENT_KEYS
        if unknown:
            problems.append(f"{where}: unknown keys {', '.join(sorted(unknown))}")
        kind = item.get("type", "string")
        if kind not in TYPES:
            problems.append(f"{where}: type must be one of {', '.join(TYPES)}")
            kind = "any"
        required = item.get("required", False)
        if not isinstance(required, bool):
            problems.append(f"{where}: 'required' is true or false")
            required = False
        entry: dict[str, Any] = {
            "name": name,
            "type": kind,
            "required": required,
            "default": item.get("default"),
            "description": str(item.get("description") or ""),
            "secret": item.get("secret") is True,
            "prompt": item.get("prompt") is True,
        }
        if required and item.get("default") is not None:
            problems.append(f"{where}: a required argument has no default")
        if not _type_ok(kind, entry["default"]):
            problems.append(f"{where}: the default is not a {kind}")
        if "choices" in item:
            choices = item["choices"]
            if not isinstance(choices, list) or not choices:
                problems.append(f"{where}: 'choices' is a non-empty list")
            else:
                entry["choices"] = choices
        for bound in ("minimum", "maximum"):
            if bound in item:
                if kind not in ("integer", "number") or not _type_ok("number", item[bound]):
                    problems.append(f"{where}: '{bound}' is a number, for integer or number")
                else:
                    entry[bound] = item[bound]
        if kind == "path":
            path_kind = item.get("path", "any")
            if path_kind not in PATH_KINDS:
                problems.append(f"{where}: 'path' is file, directory or any")
            entry["path"] = path_kind if path_kind in PATH_KINDS else "any"
        for extra in ("label", "example"):
            if extra in item:
                entry[extra] = item[extra]
        arguments.append(entry)

    outputs: list[dict[str, Any]] = []
    seen = set()
    for index, item in enumerate(raw_outputs):
        if isinstance(item, str):
            item = {"name": item}
        if not isinstance(item, dict) or not isinstance(item.get("name"), str):
            problems.append(f"output {index + 1} needs a name")
            continue
        name = item["name"]
        if not NAME.match(name):
            problems.append(f"output '{name}': the name must be a Python-style identifier")
        if name in seen:
            problems.append(f"output '{name}' is declared twice")
        seen.add(name)
        unknown = set(item) - OUTPUT_KEYS
        if unknown:
            problems.append(f"output '{name}': unknown keys {', '.join(sorted(unknown))}")
        kind = item.get("type", "any")
        if kind not in TYPES:
            problems.append(f"output '{name}': type must be one of {', '.join(TYPES)}")
            kind = "any"
        outputs.append(
            {"name": name, "type": kind, "description": str(item.get("description") or "")}
        )

    if problems:
        raise ContractError(problems)
    return {"arguments": arguments, "outputs": outputs}


def declared(manifest: dict[str, Any]) -> dict[str, Any] | None:
    """The plugin.json contract, or None when the plugin predates contracts."""

    if "arguments" not in manifest and "outputs" not in manifest:
        return None
    return normalize(manifest)


def read_manifest(directory: Path) -> dict[str, Any]:
    try:
        data = json.loads((directory / "plugin.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def inferred(directory: Path) -> dict[str, Any]:
    """Arguments and outputs found in the plugin source."""

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
    return {
        "arguments": sorted(
            arguments.values(), key=lambda item: (not item["required"], item["name"])
        ),
        "outputs": [
            {"name": name, "type": "any", "description": ""} for name in sorted(set(outputs))
        ],
    }


def check_source(directory: Path, contract: dict[str, Any]) -> list[str]:
    """
    What the source does outside its contract: arguments read by name that
    are not declared, outputs published that are not declared, and a missing
    plugin class with execute().
    """

    problems = []
    found = inferred(directory)
    names = {item["name"] for item in contract["arguments"]}
    for item in found["arguments"]:
        if item["name"] not in names:
            problems.append(f"the source reads argument '{item['name']}', which is not declared")
    outputs = {item["name"] for item in contract["outputs"]}
    for item in found["outputs"]:
        if item["name"] not in outputs:
            problems.append(f"the source publishes output '{item['name']}', which is not declared")

    module = directory / "plugin.py"
    try:
        tree = ast.parse(module.read_text(encoding="utf-8"))
    except (OSError, SyntaxError, UnicodeDecodeError) as exc:
        return problems + [f"plugin.py cannot be read: {exc}"]
    classes = [
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef)
        and any(
            (isinstance(base, ast.Name) and base.id == "BasePlugin")
            or (isinstance(base, ast.Attribute) and base.attr == "BasePlugin")
            for base in node.bases
        )
    ]
    if not classes:
        problems.append("plugin.py has no class based on BasePlugin")
    elif not any(
        isinstance(item, ast.FunctionDef) and item.name == "execute"
        for cls in classes
        for item in cls.body
    ):
        problems.append("the plugin class has no execute() method")
    return problems


def check_arguments(contract: dict[str, Any], values: dict[str, Any]) -> dict[str, Any]:
    """
    Arguments for a run, checked against the contract: required ones given,
    no unknown ones, types, choices and ranges right; defaults filled in.
    Raises ContractError with every problem.
    """

    problems = []
    declared_names = {item["name"] for item in contract["arguments"]}
    unknown = sorted(set(values) - declared_names)
    if unknown:
        problems.append(
            f"unknown argument{'s' if len(unknown) > 1 else ''} {', '.join(unknown)} "
            f"(the plugin takes {', '.join(sorted(declared_names)) or 'none'})"
        )
    result: dict[str, Any] = {}
    for item in contract["arguments"]:
        name = item["name"]
        value = values.get(name)
        if value is None or value == "":
            if item["required"]:
                problems.append(f"'{name}' is required")
                continue
            if item["default"] is not None:
                result[name] = item["default"]
            elif name in values:
                result[name] = value
            continue
        kind = item["type"]
        # Values typed into a form arrive as text; numbers and flags are read.
        if isinstance(value, str) and kind in ("integer", "number", "boolean"):
            text = value.strip()
            try:
                if kind == "integer":
                    value = int(text)
                elif kind == "number":
                    value = float(text)
                elif text.lower() in ("true", "yes", "1", "false", "no", "0"):
                    value = text.lower() in ("true", "yes", "1")
            except ValueError:
                pass
        # Workflow references are resolved before the plugin runs.
        if not _type_ok(kind, value) and not (isinstance(value, str) and "${" in value):
            problems.append(f"'{name}' must be a {kind}")
            continue
        if "choices" in item and value not in item["choices"] and isinstance(value, str):
            # Plugins compare choices without case; "TAG" is "tag".
            folded = [
                choice
                for choice in item["choices"]
                if isinstance(choice, str) and choice.casefold() == value.casefold()
            ]
            value = folded[0] if folded else value
        if "choices" in item and value not in item["choices"]:
            problems.append(f"'{name}' must be one of {', '.join(map(str, item['choices']))}")
        for bound, compare in (("minimum", lambda a, b: a < b), ("maximum", lambda a, b: a > b)):
            if bound in item and isinstance(value, (int, float)) and compare(value, item[bound]):
                limit = "at least" if bound == "minimum" else "at most"
                problems.append(f"'{name}' must be {limit} {item[bound]}")
        result[name] = value
    if problems:
        raise ContractError(problems)
    return result


def check_outputs(contract: dict[str, Any], outputs: dict[str, Any]) -> list[str]:
    declared_names = {item["name"] for item in contract["outputs"]}
    return [
        f"output '{name}' is not declared in plugin.json"
        for name in sorted(outputs)
        if name not in declared_names
    ]


def plugin_contract(directory: Path) -> dict[str, Any]:
    """
    The plugin's contract for the web UI: the declared one, else (plugins
    installed before contracts) the one inferred from the source.
    """

    manifest = read_manifest(directory)
    try:
        contract = declared(manifest)
    except ContractError:
        contract = None
    source = "declared"
    if contract is None:
        contract, source = inferred(directory), "inferred"
    return {
        "description": manifest.get("description") or None,
        "contract": source,
        "arguments": sorted(
            contract["arguments"], key=lambda item: (not item["required"], item["name"])
        ),
        "outputs": [item["name"] for item in contract["outputs"]],
        "output_details": contract["outputs"],
    }
