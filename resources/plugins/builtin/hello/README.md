# HelloPlugin

Demonstrates the Entropy Plugin SDK."

---

## Overview

The `builtin.hello` plugin is a demonstration plugin for the Entropy Plugin SDK.

It demonstrates:

- Plugin execution through `BasePlugin`.
- Runtime messages.
- Execution activities.
- Filesystem operations.
- Shell command execution.
- Workflow outputs.
- Workflow artifacts.
- Rich UI output through panels and tables.

The plugin creates a sample file in the Entropy workspace and executes:

```bash
uname -a
```

to demonstrate the shell SDK.

---

## Requirements

The plugin requires:

- A valid Entropy runtime environment.
- A writable Entropy workspace.
- `uname` available on the system `PATH`.

No external Python dependencies are required by the plugin.

---

## Arguments

The Hello plugin does not require any plugin arguments.

| Argument | Required | Type | Default | Description |
|----------|:--------:|------|---------|-------------|
| None | No | --- | --- | This plugin does not accept runtime arguments. |

---

## Workflow Configuration

The plugin is executed through a workflow step.

### Basic Configuration

```json
{
    "name": "Execute HelloPlugin",
    "plugin": "builtin.hello",
    "enabled": true,
    "on_failure": "abort",
    "tags": [
        "hello"
    ],
    "arguments": {}
}
```

---

## Complete Workflow Example

```json
{
    "name": "HelloPlugin Workflow",
    "version": "1.0.0",
    "description": "Example workflow for builtin.hello.",
    "variables": {},
    "steps": [
        {
            "name": "Execute HelloPlugin",
            "plugin": "builtin.hello",
            "enabled": true,
            "on_failure": "abort",
            "tags": [
                "hello"
            ],
            "arguments": {}
        }
    ]
}
```

The example workflow is included in:

```text
workflow.json
```

---

## Workflow Variables

The Hello plugin does not consume workflow variables.

The workflow may still define variables for other steps, but they are not required by this plugin.

---

## Step Argument Overrides

The Hello plugin does not define step arguments, so there are no plugin-specific `--set` overrides.

---

## Execution

The plugin performs the following operations:

1. Displays a greeting.
2. Displays the current Entropy workspace.
3. Displays the current user.
4. Creates `hello.txt` in the workspace.
5. Records the generated file as an artifact.
6. Publishes a `message` workflow output.
7. Executes `uname -a`.
8. Displays the command output in a UI panel.
9. Displays an execution summary in a UI table.
10. Returns a successful `PluginResult`.

---

## Outputs

The plugin produces the following workflow output:

| Output | Type | Description |
|--------|------|-------------|
| `message` | `string` | Contains the value `Hello`. |

Example result:

```python
{
    "message": "Hello"
}
```

The output can be consumed by a later workflow step:

```text
${steps.Execute HelloPlugin.outputs.message}
```

Use the actual workflow step name when referencing the output.

---

## Artifacts

The plugin produces one artifact:

| Artifact | Description |
|----------|-------------|
| `hello` | Path to the generated `hello.txt` file. |

The file contains:

```text
Hello from Entropy!
```

The artifact is registered with:

```python
self.artifacts["hello"] = output
```

---

## Runtime Messages

The plugin demonstrates the Entropy message API.

It uses:

```python
self.message.info(...)
self.message.success(...)
```

It also uses execution activities:

```python
with self.activity(
    "Create sample file",
):
    ...
```

and:

```python
with self.activity(
    "Execute uname -a",
):
    ...
```

The plugin does not duplicate exception rendering with `message.error()` followed by `raise`.

---

## Filesystem

The plugin creates:

```text
<entropy-workspace>/hello.txt
```

The file contains:

```text
Hello from Entropy!
```

The workspace path is obtained from:

```python
self.workspace
```

The file is written through the Entropy filesystem SDK:

```python
self.filesystem.write_text(
    output,
    "Hello from Entropy!",
)
```

---

## External Commands

The plugin executes:

```bash
uname -a
```

The command is executed through the Entropy shell SDK:

```python
result = self.shell.run(
    [
        "uname",
        "-a",
    ]
)
```

The command's standard output is displayed through the plugin UI.

The command must be available on the system.

---

## UI

The plugin demonstrates two UI components.

### System Information Panel

The output of `uname -a` is displayed using:

```python
self.ui.panel(
    "System Information",
    [
        result.stdout,
    ],
)
```

### Execution Summary

The plugin displays:

- Current user.
- Entropy workspace.
- Generated artifact name.

using:

```python
self.ui.table(...)
```

---

## Plugin Result

The plugin returns:

```python
PluginResult(
    success=True,
    changed=True,
    outputs=dict(
        self.outputs,
    ),
    metadata={
        "artifacts": {
            name: str(path)
            for name, path in self.artifacts.items()
        },
    },
)
```

The plugin reports `changed=True` because it creates the `hello.txt` file.

---

## Error Handling

The plugin relies on the Entropy runtime to handle raised exceptions.

Potential failures include:

- Workspace filesystem errors.
- Failure to create `hello.txt`.
- `uname` not being available.
- Shell execution failures.

The workflow step uses:

```json
"on_failure": "abort"
```

so a failure of the Hello plugin aborts the workflow according to the workflow failure policy.

---

## Local Plugin Development

The plugin can be executed directly from its source directory:

```bash
ent plugin run \
    --local resources/plugins/builtin/hello
```

The plugin does not require installation for local development.

---

## Plugin Installation

The plugin can also be installed normally:

```bash
ent plugin install resources/plugins/builtin/hello
```

List installed plugins:

```bash
ent plugin list
```

---

## Example

Run the plugin directly:

```bash
ent plugin run \
    --local resources/plugins/builtin/hello
```

Run the example workflow:

```bash
ent workflow run \
    resources/plugins/builtin/hello/workflow.json
```

---

## Limitations

This plugin is intended as an SDK demonstration.

It is not intended to perform a production operation.

The generated `hello.txt` file and `uname -a` execution are demonstration behavior.

---

## Changelog

### 1.0.0

- Initial plugin release.
