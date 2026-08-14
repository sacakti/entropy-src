# ShellPlugin

{{ description or "Execute shell commands or shell scripts." }}

---

## Overview

The `builtin.shell` plugin executes shell commands and shell scripts on the system where Entropy is running.

It supports:

- Inline shell commands.
- Shell scripts.
- Explicit shell selection.
- Positional command/script arguments.
- Working directories.
- Execution timeouts.
- Environment variables.
- Standard output and standard error.
- Exit-code and success status.
- Workflow variable resolution.
- Entropy Vault-backed workflow variables.

The plugin is intentionally generic. It can execute command-line tools installed on the target system, including tools such as `grep`, `find`, `awk`, `sed`, `curl`, `jq`, `oc`, and similar utilities.

---

## Plugin Contract

The plugin inherits from `BasePlugin` and returns a `PluginResult` from `execute()`.

Workflow and Vault variable resolution are performed by the workflow engine before the plugin executes.

The plugin itself does not directly access the Entropy Vault.

---

## Arguments

| Argument | Required | Type | Default | Description |
|----------|:--------:|------|---------|-------------|
| `command` | One of `command` / `script` | string | — | Inline shell command to execute. |
| `script` | One of `command` / `script` | string | — | Path to a shell script to execute. |
| `shell` | No | string | Auto-detected | Shell interpreter. |
| `args` | No | list[string] | `[]` | Positional arguments passed to the command or script. |
| `cwd` | No | string | Runtime default | Working directory. |
| `timeout` | No | integer | Runtime default | Maximum execution time in seconds. |
| `env` | No | dict[string, string] | Runtime environment | Additional environment variables. |

Exactly one of `command` or `script` must be provided.

---

## Command Execution

A command can be executed using the `command` argument:

```json
{
    "arguments": {
        "command": "echo Hello Entropy"
    }
}
```

If no shell is specified, the plugin searches for an available shell in this order:

```text
bash
sh
zsh
```

---

## Shell Selection

The shell can be explicitly selected:

```json
{
    "arguments": {
        "command": "echo Hello",
        "shell": "bash"
    }
}
```

For example:

```json
{
    "arguments": {
        "command": "echo Hello",
        "shell": "zsh"
    }
}
```

If an explicitly requested shell cannot be found, the plugin raises a `PluginException`.

---

## Passing Arguments

Positional arguments are supplied through `args`.

```json
{
    "arguments": {
        "command": "echo Hello $1 from $2",
        "shell": "bash",
        "args": [
            "Entropy",
            "DevOps"
        ]
    }
}
```

The command receives:

```text
$1 = Entropy
$2 = DevOps
```

The arguments are passed separately to the shell process; they are not concatenated into the command string.

### Example

```json
{
    "arguments": {
        "command": "grep -i \"$1\" \"$2\"",
        "shell": "bash",
        "args": [
            "error",
            "/var/log/application.log"
        ]
    }
}
```

---

## Executing Shell Scripts

Use `script` to execute a shell script:

```json
{
    "arguments": {
        "script": "/home/devops/scripts/deploy.sh"
    }
}
```

Arguments can be passed to the script:

```json
{
    "arguments": {
        "script": "/home/devops/scripts/deploy.sh",
        "args": [
            "sit",
            "application"
        ]
    }
}
```

An explicit shell can also be selected:

```json
{
    "arguments": {
        "script": "/home/devops/scripts/deploy.sh",
        "shell": "bash",
        "args": [
            "sit"
        ]
    }
}
```

---

## Command or Script

Exactly one of these arguments must be supplied:

```text
command
```

or:

```text
script
```

### Valid

```json
{
    "arguments": {
        "command": "echo Hello"
    }
}
```

```json
{
    "arguments": {
        "script": "/home/devops/test.sh"
    }
}
```

### Invalid

```json
{
    "arguments": {
        "command": "echo Hello",
        "script": "/home/devops/test.sh"
    }
}
```

The plugin rejects a configuration containing both.

---

## Working Directory

Use `cwd` to specify the working directory:

```json
{
    "arguments": {
        "command": "ls -la",
        "cwd": "/home/devops/application"
    }
}
```

---

## Timeout

Use `timeout` to limit execution time.

The value is specified in seconds:

```json
{
    "arguments": {
        "command": "./long-running-task.sh",
        "timeout": 300
    }
}
```

The timeout must be a positive integer.

---

## Environment Variables

Environment variables can be supplied through `env`:

```json
{
    "arguments": {
        "command": "echo \"$APP_ENV\"",
        "env": {
            "APP_ENV": "sit"
        }
    }
}
```

Multiple values can be supplied:

```json
{
    "arguments": {
        "command": "./deploy.sh",
        "env": {
            "APP_ENV": "sit",
            "APP_NAME": "myapp"
        }
    }
}
```

Environment variable names and values must be strings.

---

## Workflow Variables

ShellPlugin arguments can consume workflow variables.

```json
{
    "variables": {
        "environment": "sit"
    },
    "steps": [
        {
            "name": "Show Environment",
            "plugin": "builtin.shell",
            "enabled": true,
            "on_failure": "abort",
            "arguments": {
                "command": "echo \"$1\"",
                "args": [
                    "${environment}"
                ]
            }
        }
    ]
}
```

The workflow engine resolves `${environment}` before the plugin executes.

---

## Entropy Vault Values

A workflow variable can reference an Entropy Vault entry:

```json
{
    "variables": {
        "name": "${entv:name}"
    },
    "steps": [
        {
            "name": "Test Vault Value",
            "plugin": "builtin.shell",
            "enabled": true,
            "on_failure": "abort",
            "arguments": {
                "command": "echo \"$1\"",
                "args": [
                    "${name}"
                ]
            }
        }
    ]
}
```

The resolution flow is:

```text
Entropy Vault
      ↓
Workflow Variable
      ↓
Step Argument
      ↓
ShellPlugin
      ↓
Shell Command
```

The ShellPlugin does not directly retrieve Vault values.

---

## Step Argument Overrides

Workflow step arguments can be overridden from the CLI using `--set`.

For example:

```bash
ent workflow run shell \
    --set 'Execute ShellPlugin.command="echo Hello $1"' \
    --type string
```

A list argument can be supplied with JSON and `--type list`:

```bash
ent workflow run shell \
    --set 'Execute ShellPlugin.args=["Pravin"]' \
    --type list
```

A dictionary can be supplied with `--type dict`:

```bash
ent workflow run shell \
    --set 'Execute ShellPlugin.env={"APP_ENV":"prod"}' \
    --type dict
```

Multiple step arguments can be supplied in one assignment expression using the configured assignment separator:

```bash
ent workflow run shell \
    --set 'Execute ShellPlugin.args=["Pravin"];Execute ShellPlugin.command="echo Hello $1"' \
    --type auto
```

---

## Workflow Variable Overrides

Workflow variables can be overridden with `-a` / `--arguments`.

For example:

```bash
ent workflow run shell \
    -a 'name=Pravin'
```

Multiple variables can be supplied using the default `;` separator:

```bash
ent workflow run shell \
    -a 'environment=prod;version=1.0.0'
```

The assignment separator can be customized when required.

---

## Outputs

After execution, the plugin publishes:

| Output | Type | Description |
|--------|------|-------------|
| `exit_code` | integer | Process exit code. |
| `success` | boolean | Whether the shell execution succeeded. |
| `stdout` | string | Standard output produced by the command or script. |
| `stderr` | string | Standard error produced by the command or script. |
| `duration` | number | Execution duration in seconds. |

Example:

```text
exit_code = 0
success   = true
stdout    = command output
stderr    = ""
duration  = 0.03
```

These values are available to subsequent workflow steps through step outputs.

---

## Failure Behavior

If the command or script exits with a non-zero exit code, the plugin raises an execution error after publishing the process result.

The workflow engine then applies the step's:

```json
"on_failure": "abort"
```

policy, or another configured failure policy.

A failed shell command does not become a successful `PluginResult`.

---

## Errors

The plugin uses `PluginException` for plugin argument and shell validation errors.

Examples include:

```text
Either 'command' or 'script' must be specified.
```

```text
Only one of 'command' or 'script' may be specified.
```

```text
Argument 'args' must be a list.
```

```text
All values in 'args' must be strings.
```

```text
Argument 'timeout' must be greater than zero.
```

```text
Shell 'bash' was not found on this system.
```

---

## Command-Line Tools

ShellPlugin can execute any appropriate command available on the target system.

### grep

```json
{
    "arguments": {
        "command": "grep -i \"$1\" /var/log/application.log",
        "args": [
            "error"
        ]
    }
}
```

### find

```json
{
    "arguments": {
        "command": "find /opt/application -type f"
    }
}
```

### jq

```json
{
    "arguments": {
        "command": "cat config.json | jq -r '.database.host'"
    }
}
```

### OpenShift

If `oc` is installed and configured:

```json
{
    "arguments": {
        "command": "oc get pods -n \"$1\"",
        "args": [
            "my-namespace"
        ]
    }
}
```

### Shell pipelines

Shell pipelines are supported by the selected shell:

```json
{
    "arguments": {
        "command": "cat application.log | grep -i error | tail -20"
    }
}
```

---

## Complete Workflow

The repository includes:

```text
workflow.json
```

The current example demonstrates a Vault-backed workflow variable and a positional shell argument:

```json
{
    "name": "shell",
    "version": "1.0.0",
    "description": "Example workflow for builtin.shell",
    "variables": {
        "name": "${entv:name}"
    },
    "steps": [
        {
            "name": "Execute ShellPlugin",
            "plugin": "builtin.shell",
            "enabled": true,
            "on_failure": "abort",
            "tags": [
                "shell"
            ],
            "arguments": {
                "command": "echo I am \"$1\"",
                "args": [
                    "${name}"
                ]
            }
        }
    ]
}
```

Run it with:

```bash
ent workflow run resources/plugins/builtin/shell/workflow.json
```

---

## Local Development

The plugin can be executed directly from its source directory without installation:

```bash
ent plugin run \
    --local resources/plugins/builtin/shell
```

For example:

```bash
ent plugin run \
    --local resources/plugins/builtin/shell \
    -a 'command=echo Hello'
```

---

## Installation

Install the plugin with:

```bash
ent plugin install resources/plugins/builtin/shell
```

List installed plugins:

```bash
ent plugin list
```

Uninstall it with:

```bash
ent plugin uninstall builtin.shell
```

---

## Security Considerations

ShellPlugin executes commands with the permissions of the Entropy process.

Care should therefore be taken when command strings, arguments, environment variables, script paths, or workflow variables originate from untrusted sources.

Do not treat ShellPlugin as a security boundary.

---

## Dependencies

ShellPlugin does not require external Python packages.

The commands and shell interpreters used by a workflow are external system dependencies and must be available on the target host.
