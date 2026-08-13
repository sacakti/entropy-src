# Shell Plugin — Release Notes

## Overview

The `builtin.shell` plugin allows workflows to execute shell commands and shell scripts directly on the system where Entropy is running.

It supports:

* Inline shell commands
* Shell scripts
* Multiple shell interpreters
* Command-line arguments
* Working directories
* Execution timeouts
* Environment variables
* Standard output and error output
* Exit-code and success status

The plugin is designed to be generic, so commands such as `grep`, `find`, `awk`, `sed`, `curl`, `jq`, `oc`, and other installed command-line tools can be used without requiring separate Entropy plugins.

---

## Basic Usage

A shell command can be executed using the `command` argument.

```json
{
    "name": "Execute Command",
    "plugin": "custom.shell",
    "enabled": true,
    "continue_on_error": false,
    "tags": [
        "shell"
    ],
    "arguments": {
        "command": "echo Hello Entropy"
    }
}
```

If no shell is specified, Entropy automatically selects an available shell.

---

## Selecting a Shell

The `shell` argument is optional.

When omitted, Entropy searches for an available shell in the following order:

```text
bash
sh
zsh
```

For example:

```json
{
    "arguments": {
        "command": "echo Hello"
    }
}
```

To explicitly select Bash:

```json
{
    "arguments": {
        "command": "echo Hello",
        "shell": "bash"
    }
}
```

To use another available shell:

```json
{
    "arguments": {
        "command": "echo Hello",
        "shell": "zsh"
    }
}
```

If an explicitly requested shell is not available, the step fails with an appropriate error.

---

## Passing Arguments

Arguments can be supplied through the `args` array.

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

This is useful when the same command needs to be executed with different values.

For example:

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

Use the `script` argument when executing a shell script.

```json
{
    "arguments": {
        "script": "/home/devops/scripts/deploy.sh"
    }
}
```

Arguments can also be passed to the script:

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

Entropy executes the script through the selected shell.

For example:

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

This means the script does not need to be directly executable or depend on its executable bit.

---

## Command or Script

A step must provide **exactly one** of:

```text
command
```

or:

```text
script
```

This is valid:

```json
{
    "arguments": {
        "command": "echo Hello"
    }
}
```

This is also valid:

```json
{
    "arguments": {
        "script": "/home/devops/test.sh"
    }
}
```

This is invalid:

```json
{
    "arguments": {
        "command": "echo Hello",
        "script": "/home/devops/test.sh"
    }
}
```

Entropy will reject the step because both were specified.

---

## Working Directory

Use `cwd` to control the working directory of the command or script.

```json
{
    "arguments": {
        "command": "ls -la",
        "cwd": "/home/devops/application"
    }
}
```

The command executes as though it were started from:

```text
/home/devops/application
```

---

## Execution Timeout

Use `timeout` to limit how long the command can run.

```json
{
    "arguments": {
        "command": "./long-running-task.sh",
        "timeout": 300
    }
}
```

The value is specified in seconds.

For example:

```text
timeout: 30
```

allows the command to run for up to 30 seconds.

---

## Environment Variables

Environment variables can be supplied through `env`.

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

Multiple environment variables can be supplied:

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

---

## Using Workflow Variables

ShellPlugin arguments can use workflow variables resolved by Entropy.

For example:

```json
{
    "variables": {
        "environment": "sit"
    },
    "steps": [
        {
            "name": "Show Environment",
            "plugin": "custom.shell",
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

The workflow engine resolves:

```text
${environment}
```

before the ShellPlugin executes.

The ShellPlugin itself does not need to know how the variable was obtained.

---

## Using Vault Values

Workflow variables can reference Entropy Vault entries using:

```text
${entv:key}
```

Example:

```json
{
    "variables": {
        "schema2": "${entv:schema2}"
    },
    "steps": [
        {
            "name": "Test Vault Value",
            "plugin": "custom.shell",
            "arguments": {
                "command": "echo \"$1\"",
                "args": [
                    "${schema2}"
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

This allows deployment scripts and command-line tools to consume Vault-managed values without the ShellPlugin directly accessing the Vault.

---

## Using Command-Line Tools

ShellPlugin is not limited to `echo` or simple commands.

Any command available on the target system can be used.

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

Shell features such as pipes can be used when supported by the selected shell:

```json
{
    "arguments": {
        "command": "cat application.log | grep -i error | tail -20"
    }
}
```

---

## Plugin Outputs

After execution, the plugin exposes the command result through workflow outputs.

Available values include:

```text
exit_code
success
stdout
stderr
duration
```

For example:

```text
exit_code
    0

success
    true

stdout
    command output

stderr
    error output

duration
    execution time in seconds
```

A successful command returns an exit code of `0`.

If the command exits with a non-zero status, the ShellPlugin reports the failure and the workflow follows the step's `continue_on_error` behavior.

---

## Complete Example

The following workflow demonstrates Vault variables, command arguments, shell selection, working directory, environment variables, and timeout.

```json
{
    "name": "Shell Plugin Example",
    "version": "1.0.0",
    "description": "Example workflow demonstrating custom.shell.",
    "variables": {
        "environment": "${entv:environment}"
    },
    "steps": [
        {
            "name": "Execute Shell Command",
            "plugin": "custom.shell",
            "enabled": true,
            "continue_on_error": false,
            "tags": [
                "shell"
            ],
            "arguments": {
                "command": "echo \"Environment: $1\" && echo \"Application: $APP_NAME\"",
                "shell": "bash",
                "args": [
                    "${environment}"
                ],
                "cwd": "/home/devops",
                "timeout": 30,
                "env": {
                    "APP_NAME": "entropy"
                }
            }
        }
    ]
}
```

---

## Argument Reference

| Argument  | Required                    | Description                                            |
| --------- | --------------------------- | ------------------------------------------------------ |
| `command` | One of `command` / `script` | Inline shell command                                   |
| `script`  | One of `command` / `script` | Path to a shell script                                 |
| `shell`   | No                          | Shell interpreter; automatically detected when omitted |
| `args`    | No                          | Positional arguments passed to the command or script   |
| `cwd`     | No                          | Working directory                                      |
| `timeout` | No                          | Maximum execution time in seconds                      |
| `env`     | No                          | Environment variables                                  |

### Minimal command

```json
{
    "arguments": {
        "command": "echo Hello"
    }
}
```

### Minimal script

```json
{
    "arguments": {
        "script": "/home/devops/test.sh"
    }
}
```

### Full configuration

```json
{
    "arguments": {
        "command": "echo \"$1\"",
        "shell": "bash",
        "args": [
            "Hello"
        ],
        "cwd": "/home/devops",
        "timeout": 60,
        "env": {
            "APP_ENV": "sit"
        }
    }
}
```

---

## Important Notes

1. `command` and `script` are mutually exclusive.
2. `shell` is optional.
3. `args` must be a list of strings.
4. `timeout` is specified in seconds.
5. The required shell or command-line utilities must exist on the target system.
6. Workflow and Vault variables are resolved before plugin execution.
7. ShellPlugin does not directly access Entropy Vault.
8. Commands execute with the permissions of the Entropy process.
9. Be careful when constructing commands from external or untrusted input.
10. The ShellPlugin is intended as a generic workflow execution primitive and can use any appropriate command-line utility available on the target host.

```
```
