---
paths:
  - "lib/plugins/**"
  - "resources/plugins/**"
  - "tests/plugins/**"
---

# Plugin rules

## Layout
- Plugin framework: `lib/plugins/` (`base.py` BasePlugin, `context.py` PluginContext,
  `manager.py`, `runner.py`, `loader.py`, `registry.py`, `discovery.py`, `contract.py`).
- Plugins: `resources/plugins/<namespace>/<name>/` with `plugin.json`
  (name, namespace, version, module, dependencies), `plugin.py`, optional
  `exceptions.py`, `README.md`, `MAN.md`, `workflow.json`, `requirements.txt`.
- Registration is via install/discovery (`PluginManager`, `PluginRepository`
  -> `PluginRegistry`), not imports. `contract.py` checks that `plugin.py` has a
  `BasePlugin` subclass with `execute()`, and checks declared arguments/outputs.
- Bump `version` in `plugin.json` when changing a plugin's behavior.

## Boundaries
- A plugin implements one unit of workflow behavior through the public SDK
  (`BasePlugin` properties). It does not touch runtime internals.
- Plugins must not import or call other plugins. Compose them in workflows instead.
- Filesystem, process, archive, and environment work goes through the executor
  facades: `self.filesystem`, `self.shell`, `self.archive`, `self.environment`,
  `self.information`, `self.path`. Do not use `os`/`shutil`/`subprocess` for things the
  executor supports. Check `lib/executor/` for an existing method first.
- Data comes from `self.arguments`, `self.variables`, `self.vault(...)`, and `self.ask(...)`.
  Results go to `self.outputs` and `self.artifacts`.

## Output and errors
- The executor returns `ExecutionResult`. It never prints or logs.
- Plugins report through `self.message`, `self.log`, and `self.ui`. Do not use `print`.
- `execute()` returns `PluginResult`. Expected failures raise the plugin's own
  exception (from `exceptions.py`), and `execute()` catches it and returns
  `PluginResult(success=False, errors=[...])`. `success=False` fails the step.
- Never log secrets (`ask(secret=True)` values, vault data).

## Tests
- Tests are in `tests/plugins/<plugin>/`. Plugin conftests add the namespace
  directory to `sys.path` (see `tests/plugins/docker_build/conftest.py`).
- Framework fixtures are in `tests/plugins/conftest.py` (mocked context, `DummyPlugin`).
- Mock the executor facades. Never run real docker/oc/sftp/sql commands in tests.
