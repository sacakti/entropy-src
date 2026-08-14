# ShellPlugin

## 1. NAME

`builtin.shell` — execute shell commands or shell scripts.

---

## 2. DESCRIPTION

ShellPlugin is a generic Entropy workflow plugin for executing shell commands and shell scripts on the target system.

It supports:

- Inline commands.
- Shell scripts.
- Shell selection.
- Positional arguments.
- Working directories.
- Execution timeouts.
- Environment variables.
- Standard output and standard error.
- Exit-code and success status.
- Workflow variable resolution.
- Entropy Vault-backed workflow variables.

The plugin relies on the Entropy Plugin SDK and does not directly resolve workflow variables or Vault entries.

---

## 3. PLUGIN CONTRACT

The plugin:

- Inherits from `BasePlugin`.
- Implements `execute()`.
- Returns a `PluginResult`.
- Publishes execution values through `self.outputs`.
- Uses the SDK message and activity APIs.
- Raises `PluginException` for plugin validation errors.

---

## 4. ARGUMENTS

### 4.1 `command`

**Type:** `string`

**Required:** One of `command` or `script`.

Inline shell command to execute.

Example:

```json
{
    "command": "echo Hello Entropy"
}
```

---

### 4.2 `script`

**Type:** `string`

**Required:** One of `command` or `script`.

Path to the shell script to execute.

Example:

```json
{
    "script": "/home/devops/scripts/deploy.sh"
}
```

---

### 4.3 `shell`

**Type:** `string`

**Required:** No.

**Default:** Automatically detected.

Explicit shell interpreter.

When omitted, the plugin searches in this order:

```text
bash
sh
zsh
```

Example:

```json
{
    "shell": "bash"
}
```

---

### 4.4 `args`

**Type:** `list[string]`

**Required:** No.

**Default:** `[]`

Positional arguments passed to the command or script.

Example:

```json
{
    "command": "echo \"$1\"",
    "args": [
        "Pravin"
    ]
}
```

All values must be strings.

---

### 4.5 `cwd`

**Type:** `string`

**Required:** No.

Working directory for the process.

Example:

```json
{
    "command": "pwd",
    "cwd": "/home/devops"
}
```

---

### 4.6 `timeout`

**Type:** `integer`

**Required:** No.

Positive execution timeout in seconds.

Example:

```json
{
    "command": "./deploy.sh",
    "timeout": 300
}
```

---

### 4.7 `env`

**Type:** `dict[string, string]`

**Required:** No.

Environment variables supplied to the process.

Example:

```json
{
    "command": "./deploy.sh",
    "env": {
        "APP_ENV": "prod"
    }
}
```

All environment variable names and values must be strings.

---

## 5. VALIDATION

The following rules are enforced:

1. Exactly one of `command` and `script` must be specified.
2. `command` must be a non-empty string.
3. `script` must be a non-empty string.
4. `shell`, when supplied, must be a string.
5. `args` must be a list.
6. Every value in `args` must be a string.
7. `cwd`, when supplied, must be a string.
8. `timeout`, when supplied, must be a positive integer.
9. `env`, when supplied, must be a dictionary.
10. All environment variable names and values must be strings.

---

## 6. SHELL RESOLUTION

If `shell` is explicitly supplied, the plugin resolves it using the system `PATH`.

If no shell is supplied, the plugin searches:

```text
bash
sh
zsh
```

The first available interpreter is selected.

If no supported shell is available, execution fails.

---

## 7. COMMAND EXECUTION

For an inline command, the plugin invokes the selected shell using the equivalent process structure:

```text
<shell> -c <command> -- <args...>
```

This allows the command to use positional parameters such as:

```text
$1
$2
```

Example:

```json
{
    "command": "echo \"Environment: $1\"",
    "args": [
        "prod"
    ]
}
```

---

## 8. SCRIPT EXECUTION

For a script, the plugin invokes the selected shell with the script path and positional arguments.

Conceptually:

```text
<shell> <script> <args...>
```

Example:

```json
{
    "script": "/home/devops/scripts/deploy.sh",
    "shell": "bash",
    "args": [
        "prod"
    ]
}
```

---

## 9. OUTPUTS

The plugin publishes the following outputs:

| Output | Type | Description |
|--------|------|-------------|
| `exit_code` | integer | Process exit code. |
| `success` | boolean | Whether execution succeeded. |
| `stdout` | string | Standard output. |
| `stderr` | string | Standard error. |
| `duration` | number | Execution duration in seconds. |

These values are stored in `self.outputs` and returned through `PluginResult`.

---

## 10. FAILURE HANDLING

If the process reports failure, the plugin raises an execution error containing the exit code.

The workflow engine determines the final workflow behavior according to the step's `on_failure` policy.

Example:

```json
{
    "on_failure": "abort"
}
```

The plugin does not convert a failed process into a successful result.

---

## 11. WORKFLOW VARIABLES

Workflow variables are resolved before ShellPlugin execution.

Example:

```json
{
    "variables": {
        "environment": "prod"
    },
    "steps": [
        {
            "name": "Show Environment",
            "plugin": "builtin.shell",
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

The plugin receives the resolved value rather than resolving `${environment}` itself.

---

## 12. VAULT VALUES

Vault-backed workflow variables can be used:

```json
{
    "variables": {
        "name": "${entv:name}"
    },
    "steps": [
        {
            "name": "Show Name",
            "plugin": "builtin.shell",
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

Resolution occurs before plugin execution:

```text
Vault
  ↓
Workflow variable
  ↓
Step argument
  ↓
ShellPlugin
  ↓
Shell process
```

---

## 13. CLI VARIABLE OVERRIDES

Workflow variables can be overridden using:

```text
-a
--arguments
```

Example:

```bash
ent workflow run shell \
    -a 'name=Pravin'
```

Multiple assignments use the configured assignment separator.

Default separator:

```text
;
```

Example:

```bash
ent workflow run deployment \
    -a 'environment=prod;version=1.0.0'
```

---

## 14. CLI STEP OVERRIDES

Step arguments can be overridden using:

```text
--set
```

Example:

```bash
ent workflow run shell \
    --set 'Execute ShellPlugin.command="echo Hello"'
```

Typed values are supported through:

```text
--type
```

### String

```bash
--set 'Execute ShellPlugin.command="echo Hello"' \
--type string
```

### List

```bash
--set 'Execute ShellPlugin.args=["Pravin"]' \
--type list
```

### Dictionary

```bash
--set 'Execute ShellPlugin.env={"APP_ENV":"prod"}' \
--type dict
```

Multiple step assignments can be combined using the configured assignment separator:

```bash
--set 'Execute ShellPlugin.args=["Pravin"];Execute ShellPlugin.command="echo Hello $1"' \
--type auto
```

---

## 15. EXAMPLES

### Minimal command

```json
{
    "plugin": "builtin.shell",
    "arguments": {
        "command": "echo Hello"
    }
}
```

### Command with arguments

```json
{
    "plugin": "builtin.shell",
    "arguments": {
        "command": "echo Hello $1",
        "args": [
            "Entropy"
        ]
    }
}
```

### Script

```json
{
    "plugin": "builtin.shell",
    "arguments": {
        "script": "/home/devops/scripts/deploy.sh"
    }
}
```

### Full configuration

```json
{
    "plugin": "builtin.shell",
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

## 16. WORKFLOW EXAMPLE

The included `workflow.json` demonstrates a Vault-backed workflow variable:

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

Run:

```bash
ent workflow run resources/plugins/builtin/shell/workflow.json
```

---

## 17. LOCAL EXECUTION

The plugin can be executed directly from its source directory:

```bash
ent plugin run \
    --local resources/plugins/builtin/shell
```

Example:

```bash
ent plugin run \
    --local resources/plugins/builtin/shell \
    -a 'command=echo Hello'
```

---

## 18. DEPENDENCIES

ShellPlugin has no external Python package dependencies.

The selected shell and any command-line utilities used by a workflow are system-level dependencies.

---

## 19. SECURITY

ShellPlugin executes processes using the permissions of the Entropy process.

Commands, scripts, arguments, environment variables, and paths should therefore be treated as executable input.

Do not use ShellPlugin as a security boundary or execute untrusted command content without appropriate validation and authorization.

---

## 20. FAILURE POLICY

Workflow behavior after a ShellPlugin failure is controlled by the workflow step:

```json
"on_failure": "abort"
```

or the other failure policies supported by the workflow engine.

The plugin itself is responsible for reporting the process result and raising execution failures; the workflow engine owns workflow-level failure handling.
