"""
Plugin SDK catalog.

The catalog is built by introspecting the SDK classes plugins actually run
against, so editor completion and reference checks never drift from the code.
"""

from __future__ import annotations

import importlib
import inspect
from functools import lru_cache
from typing import Any

# Names that only exist under TYPE_CHECKING in the SDK modules.
_TYPE_LOCATIONS = {
    "LinuxExecutor": "lib.executor",
    "PluginContext": "lib.plugins.context",
    "PluginArguments": "lib.plugins.arguments",
    "PluginLog": "lib.plugins.context",
    "PluginMessage": "lib.plugins.message",
    "PluginMode": "lib.plugins.mode",
    "PluginUI": "lib.plugins.ui",
    "PluginResult": "lib.models.plugin",
    "Path": "pathlib",
}

# Types whose members are worth offering inside the editor.
_BUILTIN_TYPES: dict[str, type] = {
    "dict": dict,
    "str": str,
    "list": list,
}

# Importable symbols plugin modules commonly use.
_SYMBOLS = (
    ("lib.plugins.base", "BasePlugin"),
    ("lib.models.plugin", "PluginResult"),
    ("lib.plugins.exceptions", "PluginException"),
    ("lib.plugins.exceptions", "PluginValueError"),
    ("lib.plugins.exceptions", "PluginExecutionError"),
    ("lib.plugins.mode", "PluginMode"),
    ("pathlib", "Path"),
)

ROOT_TYPE = "BasePlugin"


def _summary(obj: Any) -> str:
    doc = inspect.getdoc(obj) or ""
    return doc.strip().split("\n\n", 1)[0].strip()


def _type_name(annotation: Any) -> str | None:
    """Return the bare type name of an annotation string such as 'dict[str, Any]'."""

    if not isinstance(annotation, str) or not annotation:
        return None

    name = annotation.split("[", 1)[0].split("|", 1)[0].strip()
    return name.rsplit(".", 1)[-1] or None


def _resolve(name: str | None) -> type | None:
    if not name:
        return None

    if name in _BUILTIN_TYPES:
        return _BUILTIN_TYPES[name]

    module_name = _TYPE_LOCATIONS.get(name)

    if module_name is None:
        return None

    try:
        value = getattr(importlib.import_module(module_name), name, None)
    except Exception:
        return None

    return value if inspect.isclass(value) else None


def _return_annotation(cls: type, name: str) -> str | None:
    attribute = inspect.getattr_static(cls, name, None)

    if isinstance(attribute, property) and attribute.fget is not None:
        # Some stdlib properties wrap callables without annotations
        # (e.g. operator.attrgetter on Python 3.9's pathlib).
        return getattr(attribute.fget, "__annotations__", {}).get("return")

    if callable(attribute):
        return getattr(attribute, "__annotations__", {}).get("return")

    return None


def _signature(function: Any) -> str:
    try:
        signature = inspect.signature(function)
    except (TypeError, ValueError):
        return "(...)"

    parameters = [
        parameter
        for parameter in signature.parameters.values()
        if parameter.name not in ("self", "cls")
    ]

    return str(signature.replace(parameters=parameters))


def _members(cls: type, fallback: type | None = None) -> list[dict[str, Any]]:
    members: list[dict[str, Any]] = []

    for name in sorted(dir(cls)):
        if name.startswith("_"):
            continue

        attribute = inspect.getattr_static(cls, name, None)

        if isinstance(attribute, property):
            annotation = _return_annotation(cls, name)

            if annotation is None and fallback is not None:
                annotation = _return_annotation(fallback, name)

            members.append(
                {
                    "name": name,
                    "kind": "property",
                    "type": _type_name(annotation),
                    "annotation": annotation,
                    "doc": _summary(attribute),
                }
            )
            continue

        if isinstance(attribute, (staticmethod, classmethod)):
            attribute = attribute.__func__

        if (
            inspect.isfunction(attribute)
            or inspect.ismethoddescriptor(attribute)
            or inspect.isbuiltin(attribute)
        ):
            members.append(
                {
                    "name": name,
                    "kind": "method",
                    "signature": _signature(getattr(cls, name)),
                    "type": _type_name(_return_annotation(cls, name)),
                    "doc": _summary(attribute),
                }
            )

    return members


def _describe(cls: type, fallback: type | None = None) -> dict[str, Any]:
    return {
        "name": cls.__name__,
        "module": cls.__module__,
        "doc": _summary(cls),
        "members": _members(cls, fallback),
    }


@lru_cache(maxsize=1)
def build_catalog() -> dict[str, Any]:
    """Return the SDK catalog: BasePlugin and every type reachable from its members."""

    from lib.plugins.base import BasePlugin
    from lib.plugins.context import PluginContext

    types: dict[str, dict[str, Any]] = {
        ROOT_TYPE: _describe(BasePlugin, PluginContext),
    }

    pending = [types[ROOT_TYPE]]

    while pending:
        current = pending.pop()

        for member in current["members"]:
            type_name = member.get("type")

            if not type_name or type_name in types:
                continue

            resolved = _resolve(type_name)

            if resolved is None:
                continue

            types[type_name] = _describe(resolved)

            # Builtins are leaves; SDK types may expose further SDK types.
            if type_name not in _BUILTIN_TYPES:
                pending.append(types[type_name])

    symbols = []

    for module_name, name in _SYMBOLS:
        try:
            value = getattr(importlib.import_module(module_name), name)
        except Exception:
            continue

        symbols.append(
            {
                "name": name,
                "module": module_name,
                "kind": "class" if inspect.isclass(value) else "function",
                "signature": _signature(value) if callable(value) else "",
                "doc": _summary(value),
            }
        )

    return {
        "root": ROOT_TYPE,
        "types": types,
        "symbols": symbols,
    }


def plugin_attributes() -> set[str]:
    """Attributes every BasePlugin instance has, including private runtime state."""

    from lib.plugins.base import BasePlugin

    return set(dir(BasePlugin)) | {"_context"}
