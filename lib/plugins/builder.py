"""
Visual (no-code) plugin development.

A plugin made in the builder is described by `builder.json`: its inputs,
outputs and dependencies, and methods made of blocks (print, set, if,
loop, switch, ask, run a command, call, fail). `generate()` turns that
model into `plugin.py` (readable Python, following the plugin contract and
lifecycle) and the matching `plugin.json`.

Expressions in blocks are small Python expressions over the plugin's inputs
and variables (`count > 3`, `name.upper()`, `items[0]`); texts take
`{name}` placeholders. Both are checked here, so the generated source only
does what the blocks say.
"""

from __future__ import annotations

import ast
import json
import keyword
import re
from typing import Any, Dict, List, Optional, Set, Tuple

from lib.plugins.contract import ContractError, normalize

BUILDER_FILE = "builder.json"
MODEL_VERSION = 1

NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
PLACEHOLDER = re.compile(r"\{([A-Za-z_][A-Za-z0-9_]*)\}")
LEVELS = ("info", "success", "warning", "error", "debug")
LIFECYCLE = ("validate", "prepare", "execute", "cleanup")
SAFE_CALLS = {
    "abs", "all", "any", "bool", "dict", "enumerate", "float", "int", "len", "list",
    "max", "min", "range", "round", "set", "sorted", "str", "sum", "tuple", "zip",
}  # fmt: skip
SAFE_METHODS = {
    "count", "endswith", "find", "format", "get", "index", "items", "join", "keys",
    "lower", "lstrip", "replace", "rstrip", "split", "splitlines", "startswith",
    "strip", "title", "upper", "values",
}  # fmt: skip
# Names the generated class must not shadow.
RESERVED = {
    "arguments", "artifacts", "ask", "archive", "configuration", "context", "environment",
    "filesystem", "information", "inputs", "log", "message", "mode", "outputs", "path",
    "repositories", "shell", "ui", "variables", "vars", "workspace", "interactive", "automated",
}  # fmt: skip


class BuilderError(ValueError):
    """A model that cannot become a plugin; `problems` says where and why."""

    def __init__(self, problems: List[str]) -> None:
        super().__init__("; ".join(problems))
        self.problems = problems


def starter(class_name: str = "MyPlugin") -> Dict[str, Any]:
    """The model a new visual plugin starts from."""

    return {
        "version": MODEL_VERSION,
        "class_name": class_name,
        "inputs": [
            {"name": "name", "type": "string", "default": "world", "description": "Who to greet"}
        ],
        "outputs": [{"name": "greeting", "type": "string", "description": "What was said"}],
        "dependencies": {"extensions": [], "plugins": []},
        "methods": [
            {
                "name": "execute",
                "blocks": [
                    {"type": "print", "level": "info", "text": "Hello {name}!"},
                    {"type": "set_output", "output": "greeting", "value": "'Hello ' + name"},
                ],
            }
        ],
    }


# ----------------------------------------------------------------------
# Expressions
# ----------------------------------------------------------------------


class _Names(ast.NodeTransformer):
    """Checks an expression and points its names at inputs and variables."""

    def __init__(self, inputs: Set[str], variables: Set[str], where: str) -> None:
        self.inputs = inputs
        self.variables = variables
        self.where = where
        self.problems: List[str] = []

    def _lookup(self, name: str, node: ast.AST) -> ast.AST:
        target = "vars" if name in self.variables else "inputs"
        return ast.copy_location(
            ast.Subscript(
                value=ast.Attribute(
                    value=ast.Name(id="self", ctx=ast.Load()), attr=target, ctx=ast.Load()
                ),
                slice=ast.Constant(value=name),
                ctx=ast.Load(),
            ),
            node,
        )

    def visit_Name(self, node: ast.Name) -> ast.AST:
        if node.id in ("True", "False", "None"):
            return node
        if node.id in self.variables or node.id in self.inputs:
            return self._lookup(node.id, node)
        if node.id in SAFE_CALLS:
            return node
        self.problems.append(f"{self.where}: unknown name '{node.id}'")
        return node

    def visit_Attribute(self, node: ast.Attribute) -> ast.AST:
        if node.attr.startswith("_"):
            self.problems.append(f"{self.where}: '{node.attr}' may not be used")
        self.generic_visit(node)
        return node

    def visit_Call(self, node: ast.Call) -> ast.AST:
        func = node.func
        allowed = (isinstance(func, ast.Name) and func.id in SAFE_CALLS) or (
            isinstance(func, ast.Attribute) and func.attr in SAFE_METHODS
        )
        if not allowed:
            label = func.id if isinstance(func, ast.Name) else getattr(func, "attr", "?")
            self.problems.append(f"{self.where}: '{label}()' is not available in blocks")
        if isinstance(func, ast.Name):
            # The function name itself is checked above.
            node.args = [self.visit(item) for item in node.args]
            node.keywords = [self.visit(item) for item in node.keywords]
            return node
        self.generic_visit(node)
        return node

    def generic_visit(self, node: ast.AST) -> ast.AST:
        banned = (ast.Lambda, ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp,
                  ast.Await, ast.Yield, ast.YieldFrom, ast.NamedExpr, ast.Starred)  # fmt: skip
        if isinstance(node, banned):
            self.problems.append(f"{self.where}: {type(node).__name__} is not available in blocks")
            return node
        return super().generic_visit(node)


def _expression(
    text: Any, inputs: Set[str], variables: Set[str], where: str, problems: List[str]
) -> str:
    source = str(text if text is not None else "").strip()
    if not source:
        problems.append(f"{where}: a value is needed")
        return "None"
    try:
        tree = ast.parse(source, mode="eval")
    except SyntaxError as exc:
        problems.append(f"{where}: {exc.msg}")
        return "None"
    names = _Names(inputs, variables, where)
    tree = names.visit(tree)
    problems.extend(names.problems)
    return ast.unparse(ast.fix_missing_locations(tree))


def _text(text: Any, inputs: Set[str], variables: Set[str], where: str, problems: List[str]) -> str:
    value = str(text or "")
    for name in PLACEHOLDER.findall(value):
        if name not in inputs and name not in variables:
            problems.append(f"{where}: unknown placeholder '{{{name}}}'")
    return f"self._text({value!r})"


# ----------------------------------------------------------------------
# Generation
# ----------------------------------------------------------------------


def _collect_variables(blocks: Any, found: Set[str]) -> None:
    for block in blocks if isinstance(blocks, list) else []:
        if not isinstance(block, dict):
            continue
        kind = block.get("type")
        if kind in ("set_var", "ask", "run", "vault") and block.get(
            "variable" if kind != "set_var" else "name"
        ):
            found.add(str(block.get("variable" if kind != "set_var" else "name")))
        if kind == "loop" and block.get("variable"):
            found.add(str(block["variable"]))
        for key in ("then", "else", "body", "default"):
            _collect_variables(block.get(key), found)
        for case in block.get("cases") or []:
            if isinstance(case, dict):
                _collect_variables(case.get("body"), found)


class _Writer:
    def __init__(self, model: Dict[str, Any]) -> None:
        self.model = model
        self.problems: List[str] = []
        self.lines: List[str] = []
        self.counter = 0
        self.inputs = {item["name"] for item in model.get("inputs") or [] if isinstance(item, dict)}
        self.outputs = {
            item["name"] for item in model.get("outputs") or [] if isinstance(item, dict)
        }
        self.methods = {
            item.get("name") for item in model.get("methods") or [] if isinstance(item, dict)
        }
        self.variables: Set[str] = set()
        for method in model.get("methods") or []:
            if isinstance(method, dict):
                _collect_variables(method.get("blocks"), self.variables)

    def emit(self, depth: int, line: str) -> None:
        self.lines.append("    " * depth + line)

    def expr(self, value: Any, where: str) -> str:
        return _expression(value, self.inputs, self.variables, where, self.problems)

    def text(self, value: Any, where: str) -> str:
        return _text(value, self.inputs, self.variables, where, self.problems)

    def name(self, value: Any, where: str, kind: str = "name") -> str:
        text = str(value or "")
        if not NAME.match(text) or keyword.iskeyword(text):
            self.problems.append(f"{where}: '{text}' is not a valid {kind}")
        return text

    def blocks(self, blocks: Any, depth: int, where: str) -> None:
        items = blocks if isinstance(blocks, list) else []
        if not items:
            self.emit(depth, "pass")
            return
        for index, block in enumerate(items):
            self.block(block, depth, f"{where} › block {index + 1}")

    def block(
        self, block: Any, depth: int, where: str
    ) -> None:  # noqa: C901 - one branch per block type
        if not isinstance(block, dict):
            self.problems.append(f"{where}: not a block")
            return
        kind = block.get("type")
        where = f"{where} ({kind})"
        if kind == "print":
            level = block.get("level") or "info"
            if level not in LEVELS:
                self.problems.append(f"{where}: level is one of {', '.join(LEVELS)}")
                level = "info"
            self.emit(depth, f"self.message.{level}({self.text(block.get('text'), where)})")
        elif kind == "set_output":
            output = block.get("output")
            if output not in self.outputs:
                self.problems.append(f"{where}: '{output}' is not one of the plugin's outputs")
            self.emit(
                depth, f"self.outputs[{str(output)!r}] = {self.expr(block.get('value'), where)}"
            )
        elif kind == "set_var":
            name = self.name(block.get("name"), where, "variable name")
            self.emit(depth, f"self.vars[{name!r}] = {self.expr(block.get('value'), where)}")
        elif kind == "if":
            self.emit(depth, f"if {self.expr(block.get('condition'), where)}:")
            self.blocks(block.get("then"), depth + 1, f"{where} › then")
            if block.get("else"):
                self.emit(depth, "else:")
                self.blocks(block.get("else"), depth + 1, f"{where} › else")
        elif kind == "loop":
            name = self.name(block.get("variable"), where, "variable name")
            self.counter += 1
            item = f"item_{self.counter}"
            self.emit(depth, f"for {item} in {self.expr(block.get('over'), where)}:")
            self.emit(depth + 1, f"self.vars[{name!r}] = {item}")
            self.blocks(block.get("body"), depth + 1, f"{where} › body")
        elif kind == "switch":
            self.counter += 1
            value = f"value_{self.counter}"
            self.emit(depth, f"{value} = {self.expr(block.get('value'), where)}")
            cases = [case for case in block.get("cases") or [] if isinstance(case, dict)]
            for index, case in enumerate(cases):
                keyword_ = "if" if index == 0 else "elif"
                match = self.expr(case.get("match"), f"{where} › case {index + 1}")
                self.emit(depth, f"{keyword_} {value} == {match}:")
                self.blocks(case.get("body"), depth + 1, f"{where} › case {index + 1}")
            if cases and block.get("default"):
                self.emit(depth, "else:")
                self.blocks(block.get("default"), depth + 1, f"{where} › default")
            elif not cases:
                self.blocks(block.get("default"), depth, f"{where} › default")
        elif kind == "ask":
            name = self.name(block.get("variable"), where, "variable name")
            arguments = [self.text(block.get("label") or name, where), f"name={name!r}"]
            if block.get("secret"):
                arguments.append("secret=True")
            if block.get("default") not in (None, ""):
                arguments.append(f"default={str(block['default'])!r}")
            choices = [str(choice) for choice in block.get("choices") or [] if str(choice)]
            if choices:
                arguments.append(f"choices={choices!r}")
            self.emit(depth, f"self.vars[{name!r}] = self.ask({', '.join(arguments)})")
        elif kind == "run":
            name = self.name(block.get("variable") or "command", where, "variable name")
            self.emit(
                depth,
                f"result = self.shell.run({self.text(block.get('command'), where)}, shell=True)",
            )
            self.emit(depth, f"self.vars[{name!r}] = {{")
            for field in ("success", "exit_code", "stdout", "stderr"):
                self.emit(depth + 1, f"{field!r}: result.{field},")
            self.emit(depth, "}")
            if block.get("check", True):
                self.emit(depth, "if not result.success:")
                self.emit(
                    depth + 1,
                    'raise PluginException(f"Command failed ({result.exit_code}): '
                    '{result.stderr.strip() or result.stdout.strip()}")',
                )
        elif kind == "vault":
            name = self.name(block.get("variable"), where, "variable name")
            key = str(block.get("key") or "").strip()
            if "/" not in key or key.startswith("/") or key.endswith("/"):
                self.problems.append(f"{where}: the vault entry is 'namespace/key'")
            self.emit(depth, f"self.vars[{name!r}] = self.vault({key!r})")
        elif kind == "call":
            method = block.get("method")
            if method not in self.methods or method in LIFECYCLE:
                self.problems.append(f"{where}: '{method}' is not one of the plugin's own methods")
            self.emit(depth, f"self.{method}()")
        elif kind == "fail":
            self.emit(depth, f"raise PluginException({self.text(block.get('message'), where)})")
        else:
            self.problems.append(f"{where}: unknown block type")


def _check_model(model: Any) -> Tuple[Dict[str, Any], List[str]]:
    problems: List[str] = []
    if not isinstance(model, dict):
        return {}, ["The builder model must be an object."]
    if not NAME.match(str(model.get("class_name") or "")):
        problems.append("The class name must be a Python name, like MyPlugin.")
    methods = [item for item in model.get("methods") or [] if isinstance(item, dict)]
    names = [str(item.get("name") or "") for item in methods]
    if "execute" not in names:
        problems.append("The plugin needs an 'execute' method.")
    seen: Set[str] = set()
    for name in names:
        if not NAME.match(name) or keyword.iskeyword(name) or name.startswith("_"):
            problems.append(f"Method '{name}': use a Python name that does not start with '_'.")
        elif name in RESERVED:
            problems.append(f"Method '{name}': the name is taken by the plugin SDK.")
        if name in seen:
            problems.append(f"Method '{name}' is defined twice.")
        seen.add(name)
    inputs = {item.get("name") for item in model.get("inputs") or [] if isinstance(item, dict)}
    variables: Set[str] = set()
    for method in methods:
        _collect_variables(method.get("blocks"), variables)
    for name in sorted(inputs & variables):
        problems.append(f"'{name}' is both an input and a variable; rename one.")
    return model, problems


def _compact(item: Dict[str, Any]) -> Dict[str, Any]:
    """An argument as plugin.json keeps it: unset options left out."""

    result = {}
    for key, value in item.items():
        if key in ("secret", "prompt") and value is False:
            continue
        if key == "default" and value is None:
            continue
        if key == "description" and not value:
            continue
        result[key] = value
    return result


def generate(model: Any, manifest: Optional[Dict[str, Any]] = None) -> Dict[str, str]:
    """
    plugin.py, plugin.json and builder.json for the model; raises
    BuilderError listing every problem.
    """

    model, problems = _check_model(model)
    try:
        contract = normalize(
            {"arguments": model.get("inputs") or [], "outputs": model.get("outputs") or []}
        )
    except ContractError as exc:
        problems.extend(f"Inputs/outputs: {item}" for item in exc.problems)
        contract = {"arguments": [], "outputs": []}
    if problems:
        raise BuilderError(problems)

    writer = _Writer(model)
    description = str((manifest or {}).get("description") or "").strip()
    header = [
        '"""',
        *(description.splitlines() or ["Plugin made in the Entropy visual builder."]),
        "",
        f"Generated from {BUILDER_FILE} by the visual builder: change it there. Edits made",
        "here are replaced when the builder saves.",
        '"""',
        "",
        "from __future__ import annotations",
        "",
        "from typing import Any",
        "",
        "from lib.models.plugin import PluginResult",
        "from lib.plugins.base import BasePlugin",
        "from lib.plugins.exceptions import PluginException",
        "",
        "",
        "class _Values(dict):",
        '    """Placeholders without a value stay as they are."""',
        "",
        "    def __missing__(self, key: str) -> str:",
        '        return "{" + key + "}"',
        "",
        "",
        "class _Variables(dict):",
        '    """Variables set by the blocks; reading one not set yet says so."""',
        "",
        "    def __missing__(self, key: str) -> Any:",
        "        raise PluginException(",
        "            f\"Variable '{key}' has no value yet: \"",
        '            "a block must set it before it is used."',
        "        )",
        "",
        "",
    ]
    writer.lines.extend(header)
    class_name = str(model["class_name"])
    writer.emit(0, f"class {class_name}(BasePlugin):")
    writer.emit(1, "def __init__(self, context: Any) -> None:")
    writer.emit(2, "super().__init__(context)")
    if contract["arguments"]:
        writer.emit(2, "self.inputs = {")
        for item in contract["arguments"]:
            writer.emit(3, f"{item['name']!r}: self.arguments.get({item['name']!r}),")
        writer.emit(2, "}")
    else:
        writer.emit(2, "self.inputs = {}")
    writer.emit(2, "self.vars = _Variables()")

    methods = [item for item in model.get("methods") or [] if isinstance(item, dict)]
    ordered = sorted(
        methods,
        key=lambda item: (LIFECYCLE.index(item["name"]) if item["name"] in LIFECYCLE else 9, 0),
    )
    for method in ordered:
        name = str(method["name"])
        writer.lines.append("")
        if name == "execute":
            writer.emit(1, "def execute(self) -> PluginResult:")
            if method.get("blocks"):
                writer.blocks(method.get("blocks"), 2, "execute")
            writer.emit(2, "return PluginResult(success=True, outputs=dict(self.outputs))")
        else:
            writer.emit(1, f"def {name}(self) -> None:")
            if method.get("description"):
                writer.emit(2, f'"""{str(method["description"]).strip()}"""')
            writer.blocks(method.get("blocks"), 2, name)

    writer.lines.append("")
    writer.emit(1, "def _text(self, template: str) -> str:")
    writer.emit(2, "return template.format_map(_Values({**self.inputs, **self.vars}))")
    if writer.problems:
        raise BuilderError(writer.problems)

    source = "\n".join(writer.lines) + "\n"
    try:
        compile(source, "plugin.py", "exec")
    except SyntaxError as exc:  # pragma: no cover - a generator bug
        raise BuilderError([f"The generated source does not compile: {exc}"]) from exc

    merged = dict(manifest or {})
    merged["arguments"] = [_compact(item) for item in contract["arguments"]]
    merged["outputs"] = contract["outputs"]
    dependencies = model.get("dependencies") or {}
    merged["dependencies"] = [
        {key: item[key] for key in ("name", "version") if item.get(key)}
        for item in dependencies.get("extensions") or []
        if isinstance(item, dict) and item.get("name")
    ]
    merged["required_plugins"] = [
        {key: item[key] for key in ("name", "version") if item.get(key)}
        for item in dependencies.get("plugins") or []
        if isinstance(item, dict) and item.get("name")
    ]
    stored = {**model, "version": MODEL_VERSION}
    return {
        "plugin.py": source,
        "plugin.json": json.dumps(merged, indent=4, ensure_ascii=False) + "\n",
        BUILDER_FILE: json.dumps(stored, indent=4, ensure_ascii=False) + "\n",
    }
