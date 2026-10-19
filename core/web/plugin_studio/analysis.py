"""
Static checks for plugin sources edited in the browser.

Python files are checked for syntax, undefined names, Plugin SDK references
made through ``self``, and symbols imported from sibling plugin modules or
Entropy packages. JSON files are parsed, and the staged plugin manifest is run
through the same reader and validator the installer uses.
"""

from __future__ import annotations

import ast
import builtins
import importlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Callable, Union

from core.web.plugin_studio.sdk import ROOT_TYPE, build_catalog, plugin_attributes

MODULE_NAMES = {
    "__file__",
    "__name__",
    "__doc__",
    "__package__",
    "__spec__",
    "__loader__",
    "__path__",
    "__builtins__",
    "__annotations__",
}

BUILTIN_NAMES = set(dir(builtins)) | MODULE_NAMES

# Absolute imports from these packages are resolved against the running Entropy.
CHECKED_PACKAGES = ("lib", "core")


@dataclass(frozen=True)
class Diagnostic:
    path: str
    severity: str
    message: str
    line: int = 1
    column: int = 1
    end_line: int | None = None
    end_column: int | None = None
    source: str = "entropy"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _at(path: str, severity: str, message: str, node: ast.AST, source: str) -> Diagnostic:
    line = getattr(node, "lineno", 1) or 1
    column = (getattr(node, "col_offset", 0) or 0) + 1
    end_column = getattr(node, "end_col_offset", None)

    return Diagnostic(
        path=path,
        severity=severity,
        message=message,
        line=line,
        column=column,
        end_line=getattr(node, "end_lineno", None),
        end_column=end_column + 1 if end_column is not None else None,
        source=source,
    )


# ----------------------------------------------------------------------
# Python
# ----------------------------------------------------------------------


Scope = Union[ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda, ast.ClassDef]

# Pattern-matching nodes exist from Python 3.10; on 3.9 sources cannot contain them.
_NAMED_CAPTURES: tuple[type, ...] = tuple(
    getattr(ast, name) for name in ("MatchAs", "MatchStar") if hasattr(ast, name)
)
_MAPPING_PATTERN: tuple[type, ...] = tuple(
    getattr(ast, name) for name in ("MatchMapping",) if hasattr(ast, name)
)


def _body(scope: Scope) -> list[ast.AST]:
    return [scope.body] if isinstance(scope, ast.Lambda) else list(scope.body)


def _bindings(scope: Scope) -> set[str]:
    """Names a scope binds, without looking inside nested function or class bodies."""

    names: set[str] = set()

    if isinstance(scope, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
        names.update(
            argument.arg for argument in ast.walk(scope.args) if isinstance(argument, ast.arg)
        )

    pending = _body(scope)

    while pending:
        node = pending.pop()

        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(node.name)
            # Decorators, defaults and bases evaluate in this scope.
            pending.extend(node.decorator_list)
            if isinstance(node, ast.ClassDef):
                pending.extend(node.bases)
            else:
                pending.extend(node.args.defaults + [d for d in node.args.kw_defaults if d])
            continue

        if isinstance(node, ast.Lambda):
            continue

        if isinstance(node, ast.Name) and isinstance(node.ctx, (ast.Store, ast.Del)):
            names.add(node.id)
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            names.update((alias.asname or alias.name).split(".", 1)[0] for alias in node.names)
        elif isinstance(node, (ast.Global, ast.Nonlocal)):
            names.update(node.names)
        elif isinstance(node, (ast.ExceptHandler, *_NAMED_CAPTURES)) and node.name:
            names.add(node.name)
        elif isinstance(node, _MAPPING_PATTERN) and node.rest:
            names.add(node.rest)

        pending.extend(ast.iter_child_nodes(node))

    return names


def _module_names(source: str) -> set[str]:
    """Names bound at module scope."""

    return _bindings(ast.parse(source))


class _NameResolver(ast.NodeVisitor):
    """Report loads of names no enclosing scope, the module, or builtins binds."""

    def __init__(self, path: str, module: ast.Module) -> None:
        self.path = path
        self.diagnostics: list[Diagnostic] = []
        self._scopes: list[tuple[ast.AST, set[str]]] = [(module, _bindings(module) | BUILTIN_NAMES)]

    def _resolves(self, name: str) -> bool:
        innermost = len(self._scopes) - 1

        for index in range(innermost, -1, -1):
            scope, names = self._scopes[index]

            # Class bodies are not visible from functions nested inside them.
            if isinstance(scope, ast.ClassDef) and index != innermost:
                continue

            if name in names:
                return True

        return False

    def _enter(self, node: Scope) -> None:
        self._scopes.append((node, _bindings(node)))

        for child in _body(node):
            self.visit(child)

        self._scopes.pop()

    def visit_FunctionDef(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        for item in (
            node.decorator_list + node.args.defaults + [d for d in node.args.kw_defaults if d]
        ):
            self.visit(item)

        for argument in ast.walk(node.args):
            if isinstance(argument, ast.arg) and argument.annotation:
                self.visit(argument.annotation)

        if node.returns:
            self.visit(node.returns)

        self._enter(node)

    visit_AsyncFunctionDef = visit_FunctionDef  # noqa: N815

    def visit_Lambda(self, node: ast.Lambda) -> None:
        for item in node.args.defaults + [d for d in node.args.kw_defaults if d]:
            self.visit(item)

        self._enter(node)

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        for item in node.decorator_list + node.bases + [keyword.value for keyword in node.keywords]:
            self.visit(item)

        self._enter(node)

    def visit_Name(self, node: ast.Name) -> None:
        if isinstance(node.ctx, ast.Load) and not self._resolves(node.id):
            self.diagnostics.append(
                _at(self.path, "error", f"Undefined name '{node.id}'.", node, "reference")
            )


def _undefined_names(path: str, tree: ast.Module) -> list[Diagnostic]:
    resolver = _NameResolver(path, tree)

    for statement in tree.body:
        resolver.visit(statement)

    return resolver.diagnostics


def _top_level_names(source: str) -> set[str] | None:
    try:
        return _module_names(source)
    except SyntaxError:
        return None


def _relative_target(path: str, level: int, module: str) -> str | None:
    """Return the dotted plugin-relative module an import refers to."""

    package = path.split("/")[:-1]

    if level - 1 > len(package):
        return None

    base = package[: len(package) - (level - 1)]
    return ".".join(base + ([module] if module else []))


def _imports(
    path: str,
    tree: ast.Module,
    module_names: Callable[[str], set[str] | None],
) -> list[Diagnostic]:
    diagnostics: list[Diagnostic] = []

    for node in ast.walk(tree):
        if not isinstance(node, ast.ImportFrom):
            continue

        module = node.module or ""
        imported = [alias.name for alias in node.names if alias.name != "*"]

        if node.level > 0:
            target = _relative_target(path, node.level, module)

            # Imports that climb out of the plugin reach sibling plugins,
            # which the installer resolves through plugin.json requirements.
            if target is None:
                continue

            names = module_names(target)
            label = target or "."

            if names is None:
                diagnostics.append(
                    _at(path, "error", f"Plugin module '{label}' was not found.", node, "import")
                )
                continue

            for name in imported:
                submodule = f"{target}.{name}" if target else name

                if name not in names and module_names(submodule) is None:
                    diagnostics.append(
                        _at(
                            path,
                            "error",
                            f"'{name}' is not defined in plugin module '{label}'.",
                            node,
                            "import",
                        )
                    )
            continue

        if module.split(".", 1)[0] not in CHECKED_PACKAGES:
            continue

        try:
            loaded = importlib.import_module(module)
        except Exception:
            diagnostics.append(
                _at(path, "error", f"Entropy module '{module}' cannot be imported.", node, "import")
            )
            continue

        for name in imported:
            if not hasattr(loaded, name):
                diagnostics.append(
                    _at(path, "error", f"'{name}' is not exported by '{module}'.", node, "import")
                )

    return diagnostics


def _plugin_classes(tree: ast.Module) -> list[ast.ClassDef]:
    """Classes deriving only from BasePlugin, where every attribute is knowable."""

    classes = []

    for node in tree.body:
        if not isinstance(node, ast.ClassDef) or len(node.bases) != 1:
            continue

        base = node.bases[0]
        base_name = base.id if isinstance(base, ast.Name) else getattr(base, "attr", None)

        if base_name == ROOT_TYPE:
            classes.append(node)

    return classes


def _class_attributes(cls: ast.ClassDef) -> set[str]:
    names: set[str] = set()

    for node in cls.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(node.name)
        elif isinstance(node, ast.Assign):
            names.update(target.id for target in node.targets if isinstance(target, ast.Name))
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            names.add(node.target.id)

    for child in ast.walk(cls):
        if (
            isinstance(child, ast.Attribute)
            and isinstance(child.ctx, (ast.Store, ast.Del))
            and isinstance(child.value, ast.Name)
            and child.value.id == "self"
        ):
            names.add(child.attr)

    return names


def _sdk_references(path: str, tree: ast.Module) -> list[Diagnostic]:
    catalog = build_catalog()
    types = catalog["types"]
    root_members = {member["name"]: member for member in types[ROOT_TYPE]["members"]}
    inherited = plugin_attributes()
    diagnostics: list[Diagnostic] = []

    for cls in _plugin_classes(tree):
        known = inherited | _class_attributes(cls)

        for node in ast.walk(cls):
            if not (
                isinstance(node, ast.Attribute)
                and isinstance(node.ctx, ast.Load)
                and isinstance(node.value, ast.Attribute)
                and isinstance(node.value.value, ast.Name)
                and node.value.value.id == "self"
            ):
                continue

            # self.<sdk>.<member>
            member = root_members.get(node.value.attr)
            type_name = member.get("type") if member else None

            if type_name not in types or type_name in ("dict", "str", "list"):
                continue

            names = {item["name"] for item in types[type_name]["members"]}

            if node.attr not in names:
                diagnostics.append(
                    _at(
                        path,
                        "error",
                        f"'{node.attr}' is not a member of self.{node.value.attr} ({type_name}).",
                        node,
                        "sdk",
                    )
                )

        for node in ast.walk(cls):
            if (
                isinstance(node, ast.Attribute)
                and isinstance(node.ctx, ast.Load)
                and isinstance(node.value, ast.Name)
                and node.value.id == "self"
                and node.attr not in known
            ):
                diagnostics.append(
                    _at(
                        path,
                        "error",
                        f"'{node.attr}' is not defined on {cls.name} or the Plugin SDK.",
                        node,
                        "sdk",
                    )
                )

    return diagnostics


def check_python(
    path: str,
    source: str,
    module_names: Callable[[str], set[str] | None],
) -> list[Diagnostic]:
    try:
        tree = ast.parse(source, filename=path)
    except SyntaxError as exc:
        return [
            Diagnostic(
                path=path,
                severity="error",
                message=f"Syntax error: {exc.msg}.",
                line=exc.lineno or 1,
                column=exc.offset or 1,
                # end_lineno/end_offset exist on SyntaxError from Python 3.10.
                end_line=getattr(exc, "end_lineno", None),
                end_column=getattr(exc, "end_offset", None),
                source="syntax",
            )
        ]

    return (
        _undefined_names(path, tree)
        + _imports(path, tree, module_names)
        + _sdk_references(path, tree)
    )


# ----------------------------------------------------------------------
# JSON
# ----------------------------------------------------------------------


def check_json(path: str, source: str) -> list[Diagnostic]:
    try:
        json.loads(source)
    except json.JSONDecodeError as exc:
        return [
            Diagnostic(
                path=path,
                severity="error",
                message=f"Invalid JSON: {exc.msg}.",
                line=exc.lineno,
                column=exc.colno,
                source="json",
            )
        ]

    return []


def check_manifest(
    directory: Path,
    namespace: str,
    name: str,
    reader: Any,
    validator: Any,
) -> list[Diagnostic]:
    """Run the installer's manifest reader and validator against a staged plugin."""

    try:
        manifest = reader.read(directory)
        validator.validate(manifest)
    except Exception as exc:
        return [
            Diagnostic(path="plugin.json", severity="error", message=str(exc), source="manifest")
        ]

    if (manifest.namespace, manifest.name) != (namespace, name):
        return [
            Diagnostic(
                path="plugin.json",
                severity="error",
                message=(
                    f"Manifest identifies '{manifest.namespace}.{manifest.name}'; "
                    f"it must remain '{namespace}.{name}'."
                ),
                source="manifest",
            )
        ]

    return []


def check_files(files: dict[str, str]) -> list[Diagnostic]:
    """Check every Python and JSON file in a plugin's file map."""

    cache: dict[str, set[str] | None] = {}

    def module_names(module: str) -> set[str] | None:
        """Top-level names of a plugin module or package; None when absent."""

        if module not in cache:
            stem = module.replace(".", "/")
            source = files.get(f"{stem}.py") if stem else None

            if source is None:
                source = files.get(f"{stem}/__init__.py" if stem else "__init__.py")

            cache[module] = None if source is None else (_top_level_names(source) or set())

        return cache[module]

    diagnostics: list[Diagnostic] = []

    for path, source in sorted(files.items()):
        if path.endswith(".py"):
            diagnostics.extend(check_python(path, source, module_names))
        elif path.endswith(".json"):
            diagnostics.extend(check_json(path, source))

    return diagnostics
