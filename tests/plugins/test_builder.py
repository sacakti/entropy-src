"""Visual plugin builder: models become contract-abiding plugin source."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from lib.plugins import contract
from lib.plugins.builder import BuilderError, generate, starter

MODEL = {
    "class_name": "DeployPlugin",
    "inputs": [
        {"name": "environment", "type": "string", "required": True, "choices": ["dev", "prod"]},
        {"name": "replicas", "type": "integer", "default": 0},
        {"name": "token", "type": "string", "secret": True, "prompt": True},
    ],
    "outputs": [{"name": "summary", "type": "string"}, {"name": "count", "type": "integer"}],
    "dependencies": {
        "extensions": [{"name": "paramiko", "version": ">=3"}],
        "plugins": [{"name": "builtin.shell"}],
    },
    "methods": [
        {
            "name": "validate",
            "blocks": [
                {
                    "type": "if",
                    "condition": "replicas < 0",
                    "then": [
                        {"type": "fail", "message": "replicas must be positive, not {replicas}"}
                    ],
                }
            ],
        },
        {
            "name": "execute",
            "blocks": [
                {"type": "set_var", "name": "total", "value": "0"},
                {
                    "type": "loop",
                    "variable": "host",
                    "over": "['a', 'b'] if environment == 'prod' else ['a']",
                    "body": [
                        {"type": "print", "level": "info", "text": "Deploying to {host}"},
                        {"type": "set_var", "name": "total", "value": "total + 1"},
                    ],
                },
                {
                    "type": "switch",
                    "value": "environment",
                    "cases": [
                        {"match": "'prod'", "body": [{"type": "call", "method": "notify"}]},
                        {
                            "match": "'dev'",
                            "body": [{"type": "print", "level": "debug", "text": "dev"}],
                        },
                    ],
                    "default": [{"type": "fail", "message": "unknown {environment}"}],
                },
                {"type": "ask", "variable": "confirm", "label": "Go?", "choices": ["yes", "no"]},
                {
                    "type": "run",
                    "variable": "uptime",
                    "command": "echo {environment}",
                    "check": True,
                },
                {"type": "set_output", "output": "summary", "value": "uptime['stdout'].strip()"},
                {"type": "set_output", "output": "count", "value": "total"},
            ],
        },
        {"name": "notify", "blocks": [{"type": "print", "level": "success", "text": "Live"}]},
    ],
}


def test_a_model_becomes_a_plugin_that_keeps_its_contract(tmp_path: Path) -> None:
    files = generate(MODEL, {"name": "deploy", "namespace": "demo", "version": "1.0.0"})
    source = files["plugin.py"]
    compile(source, "plugin.py", "exec")
    for expected in (
        "class DeployPlugin(BasePlugin):",
        "def validate(self) -> None:",
        "if self.inputs['replicas'] < 0:",
        "self.vars['total'] = self.vars['total'] + 1",
        "elif value_",
        "self.vars['confirm'] = self.ask(self._text('Go?'), name='confirm', choices=['yes', 'no'])",
        "result = self.shell.run(self._text('echo {environment}'), shell=True)",
        "self.outputs['summary'] = self.vars['uptime']['stdout'].strip()",
        "self.notify()",
    ):
        assert expected in source, expected

    manifest = json.loads(files["plugin.json"])
    assert manifest["dependencies"] == [{"name": "paramiko", "version": ">=3"}]
    assert manifest["required_plugins"] == [{"name": "builtin.shell"}]
    replicas = next(item for item in manifest["arguments"] if item["name"] == "replicas")
    assert replicas["default"] == 0  # a falsy default is kept
    assert json.loads(files["builder.json"])["class_name"] == "DeployPlugin"

    for name, content in files.items():
        (tmp_path / name).write_text(content, encoding="utf-8")
    declared = contract.declared(manifest)
    assert contract.check_source(tmp_path, declared) == []


@pytest.mark.parametrize(
    ("change", "problem"),
    [
        ({"methods": [{"name": "run", "blocks": []}]}, "needs an 'execute' method"),
        (
            {"methods": [{"name": "shell", "blocks": []}, {"name": "execute", "blocks": []}]},
            "taken by the plugin SDK",
        ),
        (
            {
                "methods": [
                    {
                        "name": "execute",
                        "blocks": [{"type": "set_var", "name": "x", "value": "__import__('os')"}],
                    }
                ]
            },
            "not available",
        ),
        (
            {
                "methods": [
                    {
                        "name": "execute",
                        "blocks": [
                            {"type": "set_var", "name": "x", "value": "open('/etc/passwd')"}
                        ],
                    }
                ]
            },
            "'open()' is not available",
        ),
        (
            {
                "methods": [
                    {
                        "name": "execute",
                        "blocks": [{"type": "set_var", "name": "x", "value": "y.__class__"}],
                    }
                ]
            },
            "may not be used",
        ),
        (
            {"methods": [{"name": "execute", "blocks": [{"type": "print", "text": "{missing}"}]}]},
            "unknown placeholder",
        ),
        (
            {
                "methods": [
                    {
                        "name": "execute",
                        "blocks": [{"type": "set_output", "output": "nope", "value": "1"}],
                    }
                ]
            },
            "not one of the plugin's outputs",
        ),
        (
            {
                "methods": [
                    {
                        "name": "execute",
                        "blocks": [{"type": "set_var", "name": "name", "value": "1"}],
                    }
                ]
            },
            "both an input and a variable",
        ),
    ],
)
def test_models_are_checked(change, problem) -> None:
    with pytest.raises(BuilderError) as caught:
        generate({**starter(), **change})
    assert any(problem in item for item in caught.value.problems), caught.value.problems
