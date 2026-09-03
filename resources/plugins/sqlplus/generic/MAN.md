# sqlplus.generic

---

## Overview

The `sqlplus.generic` plugin executes Oracle SQL scripts using the
`sqlplus` command-line client.

The plugin supports two execution modes:

- `plan` — execute database scripts using the database execution plan
  produced by the `release.context_builder` plugin.
- `direct` — execute explicitly supplied database execution definitions.

The plugin is designed for release and deployment workflows where
multiple applications may have independent database schemas.

For each execution, the plugin:

1. Resolves the database connection and schema credentials.
2. Resolves the SQL script associated with the application.
3. Builds the SQLPlus connection command.
4. Detects an existing SQLPlus `SPOOL` command when present.
5. Applies the configured spool policy.
6. Executes SQLPlus with the script directory as the working directory.
7. Captures stdout, stderr, exit code, and duration.
8. Detects process-level and SQLPlus/Oracle-level failures.
9. Applies the configured `on_error` policy.
10. Publishes structured workflow outputs, changes, errors, and artifacts.

Each application/schema execution is independent. A failure in one
application does not necessarily stop execution of subsequent
applications. The behavior is controlled by the `on_error` argument.

---

## Requirements

### Operating System

The plugin uses Entropy's operating-system process execution
infrastructure and therefore requires an operating system supported by
Entropy.

### SQLPlus

The Oracle SQLPlus command-line client must be installed.

The `sqlplus` executable must be available in the process `PATH`.

The plugin executes SQLPlus using:

```text
sqlplus
```

If the executable cannot be found, the plugin reports a structured
execution failure.

Example:

```text
SQLPlus executable was not found. Ensure 'sqlplus' is installed and available on PATH.
```

### Oracle Connectivity

The execution environment must be able to connect to the target Oracle
database using the supplied:

- IP/host
- port
- SID/service identifier
- username
- password

### Files

Every SQL script supplied to the plugin must:

- exist before execution
- be readable by the Entropy process
- be a valid SQLPlus script
- be accessible from the execution environment

---

## Arguments

| Argument | Required | Type | Default | Description |
| --- | --- | --- | --- | --- |
| `mode` | Yes | `string` | — | SQLPlus execution mode: `plan` or `direct`. |
| `on_error` | No | `string` | `abort` | Determines whether execution stops or continues after an individual execution failure. |
| `connection` | Yes for `plan` | `object` | — | Common Oracle connection information. |
| `schemas` | Yes for `plan` | `object` | — | Schema-specific credentials. |
| `execution` | Yes for `plan` | `object` | — | Database execution context, normally supplied by `release.context_builder`. |
| `executions` | Yes for `direct` | `array` | — | Explicit SQLPlus executions. |
| `execution_path` | No | `string` | First script's parent when spool is enabled | Base directory used for generated spool paths. |
| `release` | No | `string` | `release` | Release value used by spool filename placeholders. |
| `spool` | No | `object` | Disabled | Controls spool detection, validation, override, and generated spool files. |

---

## Argument Details

### `mode`

Accepted values:

```text
plan
direct
```

#### `plan`

Uses:

- `connection`
- `schemas`
- `execution`

The `execution` object normally comes from:

```text
steps.BuildReleaseContext.outputs.database
```

The plugin extracts:

```text
execution.execution_plan
execution.scripts
```

and resolves them against the supplied connection and schema
credentials.

#### `direct`

Does not use a release execution plan.

The caller directly supplies the complete list of executions through
`executions`.

---

### `on_error`

Controls behavior when an individual application/schema execution
fails.

Accepted values:

```text
abort
continue
```

Default:

```text
abort
```

#### `abort`

Stops execution after the first failed application.

```text
APP1 → SUCCESS
APP2 → FAILURE
APP3 → SKIPPED
APP4 → SKIPPED
```

#### `continue`

Continues executing subsequent applications after a failure.

```text
APP1 → SUCCESS
APP2 → FAILURE
APP3 → SUCCESS
APP4 → SUCCESS
```

A `continue` policy does not make the overall plugin successful.

If any execution fails:

```text
success = false
```

---

### `connection`

Defines common Oracle connection information used by all schemas in
plan mode.

Example:

```json
{
    "IP": "localhost",
    "PORT": 1521,
    "SID": "orcl"
}
```

The connection contains environment-specific information and does not
contain schema usernames or passwords.

---

### `schemas`

Contains schema-specific credentials.

Example:

```json
{
    "APP1": {
        "username": "app1",
        "password": "1234"
    },
    "APP2": {
        "username": "app2",
        "password": "1234"
    }
}
```

Credentials should normally be supplied through Entropy Vault
interpolation rather than being written directly in workflow files.

---

### `execution`

Contains the database execution context.

Recommended source:

```text
${steps.BuildReleaseContext.outputs.database}
```

Example:

```json
{
    "scripts": [
        {
            "application": "App1",
            "script": "/path/to/App1_calling_script.sql"
        }
    ],
    "execution_plan": {
        "applications": {
            "App1": {
                "schema": "APP1",
                "calling_script": "App1_calling_script.sql"
            }
        }
    }
}
```

The plugin uses:

```text
execution.scripts
execution.execution_plan
```

to construct actual SQLPlus executions.

---

### `executions`

Used by `direct` mode.

Each execution defines one independent database operation.

Example:

```json
[
    {
        "ip": "localhost",
        "port": 1521,
        "sid": "orcl",
        "schema": "APP1",
        "username": "app1",
        "password": "1234",
        "script": "/path/to/App1_calling_script.sql"
    }
]
```

---

## Spool Subsystem

The spool subsystem provides reliable SQLPlus execution tracing without
requiring every calling script to contain a valid `SPOOL` command.

The configuration is:

```json
"spool": {
    "enabled": true,
    "override": false,
    "create_if_not_exists": true,
    "name_placeholder": "%execution_path/%release_%schema_%date.log",
    "wrappers_before": [
        "SET ECHO ON",
        "SET FEEDBACK ON",
        "SET HEADING ON",
        "SET SERVEROUTPUT ON"
    ],
    "wrappers_after": [
        "SPOOL OFF",
        "EXIT"
    ]
}
```

### `spool.enabled`

Controls whether Entropy manages spool behavior.

```text
enabled = false
```

The SQLPlus script is executed normally. If the script itself contains
a `SPOOL` command, SQLPlus uses it. Entropy does not replace or create a
spool file.

If no spool is available, the captured stdout is written to the Entropy
execution log in a concise form so that execution output is not lost.

```text
enabled = true
```

Entropy detects the script's existing spool configuration and ensures
that a usable execution spool is available.

### `spool.override`

Controls whether an existing active spool target should be replaced by
the configured spool target.

```text
override = false
```

Behavior:

- valid existing spool → use it unchanged
- invalid existing spool → generate a replacement execution copy using
  the configured spool path
- no existing spool → generate a wrapper execution script

```text
override = true
```

An existing active spool target is replaced with the configured spool
target in an Entropy-generated execution copy.

The original user SQL script is not modified.

`override` therefore acts as the input spool replacement mechanism; a
separate `infile_replace` setting is not required.

### Existing Spool Detection

When `spool.enabled` is true, the plugin scans the calling script for an
active SQLPlus spool command.

Example:

```sql
SPOOL /opt/oracle/prod/customer.log;

@test.sql;

SPOOL OFF;
```

The active spool target is:

```text
/opt/oracle/prod/customer.log
```

`SPOOL OFF` is not considered an active spool target.

Relative spool paths are resolved relative to the directory containing
the calling script.

For example:

```sql
SPOOL logs/customer.log;
```

with:

```text
/db/releases/H004/DBScripts/App1/App1_calling_script.sql
```

resolves to:

```text
/db/releases/H004/DBScripts/App1/logs/customer.log
```

### Spool Path Validation

An existing spool target is considered usable when:

- an existing target is a writable file, or
- the target does not exist but its existing parent directory is
  writable.

The plugin also validates that the target is not an invalid filesystem
object such as a directory where a file is expected.

This allows deployment environments to contain hardcoded spool paths
from another environment without forcing SQLPlus to use an unusable
location.

### Automatic Path Replacement

If an existing spool path is invalid and `spool.enabled` is true, the
plugin may use the configured spool target instead.

Example:

```text
existing:
    /opt/oracle/prod/customer.log

configured:
    /release/H004/APP1_2026-09-01.log
```

The execution result records why the configured path was selected.

Example:

```json
{
    "enabled": true,
    "detected": true,
    "existing": "/opt/oracle/prod/customer.log",
    "used": "/release/H004/APP1_2026-09-01.log",
    "overridden": true,
    "reason": "existing_spool_invalid"
}
```

Other reasons may include:

```text
spool_created
override_requested
existing_spool
```

The exact reason describes the spool decision made for that execution.

### Generated Execution Scripts

The plugin never modifies the original calling script.

When a wrapper or replacement is required, Entropy creates an execution
copy under:

```text
<execution_path>/.entropy/sqlplus/
```

Examples:

```text
App1_calling_script_spool.sql
```

The generated script is then passed to SQLPlus instead of the original
calling script.

### Spool Filename Placeholders

The default spool filename is:

```text
%execution_path/%release_%schema_%date.log
```

Supported placeholders:

| Placeholder | Meaning |
| --- | --- |
| `%execution_path` | Resolved execution directory. |
| `%release` | Workflow `release` value. |
| `%schema` | Current database schema. |
| `%date` | Current date in `YYYY-MM-DD` format. |

Example:

```text
%execution_path/%release_%schema_%date.log
```

can resolve to:

```text
/release/H004/APP1_2026-09-01.log
```

### `spool.create_if_not_exists`

Controls creation of the parent directory for a configured spool path.

When enabled, missing parent directories are created before SQLPlus
execution.

### `spool.wrappers_before`

Commands inserted before the generated `SPOOL` command.

Example:

```json
"wrappers_before": [
    "SET ECHO ON",
    "SET FEEDBACK ON",
    "SET HEADING ON",
    "SET SERVEROUTPUT ON"
]
```

### `spool.wrappers_after`

Commands inserted after the calling script.

Example:

```json
"wrappers_after": [
    "SPOOL OFF",
    "EXIT"
]
```

These settings are primarily used when Entropy creates a wrapper for a
script that does not already contain a spool command.

---

## Spool Result Information

When spool processing is enabled, each execution result can contain:

```json
"spool": {
    "enabled": true,
    "detected": true,
    "existing": "/opt/oracle/prod/customer.log",
    "used": "/release/H004/APP1_2026-09-01.log",
    "overridden": true,
    "reason": "override_requested"
}
```

Fields:

| Field | Description |
| --- | --- |
| `enabled` | Whether Entropy spool management was enabled. |
| `detected` | Whether an active spool command was detected in the calling script. |
| `existing` | Resolved existing spool target, if detected. |
| `used` | Spool path selected for this execution, if Entropy manages a spool. |
| `overridden` | Whether the existing spool target was replaced. |
| `reason` | Explanation for the spool decision. |

When spool management is disabled and no Entropy-managed spool is
created, `spool` remains `null`.

---

## Execution Logging Without Spool

Spool is optional.

When:

```json
"spool": {
    "enabled": false
}
```

SQLPlus executes normally.

If the calling script has its own `SPOOL` command, SQLPlus continues to
use that command.

If there is no spool, Entropy still retains execution output by
capturing SQLPlus stdout.

The UI-facing output is intentionally summarized rather than displaying
large SQLPlus output in full.

Example:

```text
SQLPlus output:
...
...
... (stdout is large; see execution log)
```

The structured result contains a concise stdout representation with:

```json
{
    "preview": "...",
    "lines": 120,
    "truncated": true
}
```

This prevents large SQL result sets from overwhelming workflow output
while retaining an execution trace in the Entropy log.

---

## Workflow Configuration

Basic configuration:

```json
{
    "name": "Execute SQLPlus",
    "plugin": "sqlplus.generic",
    "enabled": true,
    "on_failure": "abort",
    "tags": [
        "sqlplus"
    ],
    "arguments": {
        "mode": "direct",
        "on_error": "abort",
        "executions": []
    }
}
```

### Workflow `on_failure` vs Plugin `on_error`

These are different controls.

`on_failure` belongs to the Entropy workflow engine and determines what
the workflow does when the SQLPlus plugin itself returns:

```text
success = false
```

`on_error` belongs to the SQLPlus plugin and determines whether SQLPlus
continues with subsequent database executions after an individual
execution fails.

---

## Complete Direct Example With Spool

```json
{
    "name": "SQLPlus Direct Test",
    "version": "1.0.0",
    "description": "Execute SQLPlus scripts directly with managed spooling.",
    "variables": {},
    "steps": [
        {
            "name": "SQLPlus Direct",
            "plugin": "sqlplus.generic",
            "enabled": true,
            "on_failure": "abort",
            "tags": [
                "sqlplus",
                "direct"
            ],
            "arguments": {
                "mode": "direct",
                "on_error": "abort",
                "executions": [
                    {
                        "ip": "localhost",
                        "port": 1521,
                        "sid": "orcl",
                        "schema": "APP1",
                        "username": "app1",
                        "password": "1234",
                        "script": "/db/App1/App1_calling_script.sql"
                    }
                ],
                "spool": {
                    "enabled": true,
                    "override": true,
                    "create_if_not_exists": true,
                    "name_placeholder": "%execution_path/%release_%schema_%date.log",
                    "wrappers_before": [
                        "SET ECHO ON",
                        "SET FEEDBACK ON",
                        "SET HEADING ON",
                        "SET SERVEROUTPUT ON"
                    ],
                    "wrappers_after": [
                        "SPOOL OFF",
                        "EXIT"
                    ]
                }
            }
        }
    ]
}
```

---

## Plan Mode Example

```json
{
    "name": "SQLPlus Workflow",
    "version": "1.0.0",
    "description": "Execute database release scripts using SQLPlus.",
    "steps": [
        {
            "name": "BuildReleaseContext",
            "plugin": "release.context_builder",
            "enabled": true,
            "on_failure": "abort",
            "arguments": {}
        },
        {
            "name": "SQLPlus",
            "plugin": "sqlplus.generic",
            "enabled": true,
            "on_failure": "abort",
            "arguments": {
                "mode": "plan",
                "on_error": "continue",
                "connection": {
                    "IP": "localhost",
                    "PORT": 1521,
                    "SID": "orcl"
                },
                "schemas": {
                    "APP1": {
                        "username": "app1",
                        "password": "1234"
                    },
                    "APP2": {
                        "username": "app2",
                        "password": "1234"
                    }
                },
                "execution": "${steps.BuildReleaseContext.outputs.database}",
                "spool": {
                    "enabled": true,
                    "override": false,
                    "create_if_not_exists": true,
                    "name_placeholder": "%execution_path/%release_%schema_%date.log"
                }
            }
        }
    ]
}
```

In production, credentials should be supplied through Entropy Vault.

---

## Execution

The plugin execution consists of the following stages:

1. Validate `mode`.
2. Validate `on_error`.
3. Resolve database executions.
4. In `plan` mode, resolve the database execution plan and scripts.
5. In `direct` mode, resolve explicitly supplied executions.
6. Detect an existing SQLPlus spool command.
7. Validate the detected spool path when spool management is enabled.
8. Determine whether the existing spool can be used or must be replaced.
9. Generate an execution wrapper/replacement when required.
10. Build the SQLPlus command.
11. Execute SQLPlus using Entropy's shell abstraction.
12. Capture exit code, stdout, stderr, and duration.
13. Detect SQLPlus/Oracle failures.
14. Record spool decision information.
15. Apply the `on_error` policy.
16. Publish workflow outputs.
17. Publish changes, errors, and spool artifacts.

---

## SQLPlus Execution

The plugin invokes SQLPlus using:

```text
sqlplus username/password@//host:port/sid @script
```

The actual password is supplied to the process, while the command
representation exposed by Entropy is sanitized.

The SQL script is executed with its containing directory as the process
working directory.

For example:

```text
Script:
/releases/H004/DBScripts/App1/App1_calling_script.sql

Working directory:
/releases/H004/DBScripts/App1
```

This allows calling scripts to resolve relative files from their own
location.

---

## Outputs

The plugin produces:

| Output | Type | Description |
| --- | --- | --- |
| `success` | `boolean` | Overall SQLPlus execution status. |
| `mode` | `string` | Execution mode. |
| `on_error` | `string` | Error policy used. |
| `executions` | `integer` | Number of resolved executions. |
| `succeeded` | `integer` | Number of successful executions. |
| `failed` | `integer` | Number of failed executions. |
| `skipped` | `integer` | Number skipped because of `abort`. |
| `results` | `array` | Detailed results for attempted executions. |

### Result Fields

A result can contain:

```json
{
    "schema": "APP1",
    "script": "/path/to/App1_calling_script.sql",
    "success": true,
    "exit_code": 0,
    "stdout": {
        "preview": "...",
        "lines": 10,
        "truncated": false
    },
    "stderr": "",
    "duration": 0.42,
    "spool": {
        "enabled": true,
        "detected": false,
        "existing": null,
        "used": "/release/H004/APP1_2026-09-01.log",
        "overridden": false,
        "reason": "spool_created"
    },
    "error_type": null,
    "error_message": null
}
```

Sensitive credentials are not included.

### Stdout

The plugin does not expose potentially huge stdout directly in the UI
result.

Instead it publishes:

```json
{
    "preview": "...",
    "lines": 120,
    "truncated": true
}
```

When stdout is large, the preview ends with an indication that the
execution log should be checked.

---

## Failure Information

SQLPlus failures can include:

- process startup failures
- timeout failures
- operating-system errors
- Oracle `ORA-*` errors
- SQLPlus `SP2-*` errors
- PL/SQL `PLS-*` errors
- non-zero SQLPlus exit codes

The plugin records structured error information when available.

Example:

```json
{
    "schema": "APP1",
    "script": "/path/to/App1_calling_script.sql",
    "exit_code": 1,
    "type": "ORA",
    "message": "Oracle error detected",
    "stderr": "...",
    "spool": "/release/H004/APP1_2026-09-01.log"
}
```

When an execution fails, the spool log should be checked for the full
SQLPlus execution trace.

---

## Plugin Result

The plugin publishes:

```text
PluginResult

├── success
├── changed
├── outputs
├── changes
├── errors
├── warnings
└── metadata
```

### `changed`

`changed` is true when at least one SQLPlus execution completed
successfully.

```text
No successful executions → changed = false

At least one successful execution → changed = true
```

---

## Changes

`changes` contains structured execution events.

Example:

```json
[
    {
        "schema": "APP1",
        "script": "/path/to/App1_calling_script.sql",
        "action": "execute",
        "status": "executed"
    }
]
```

For a failed execution:

```json
[
    {
        "schema": "APP1",
        "script": "/path/to/App1_calling_script.sql",
        "action": "execute",
        "status": "failed"
    }
]
```

---

## Errors

`errors` contains structured failures.

Example:

```json
[
    {
        "schema": "APP1",
        "script": "/path/to/App1_calling_script.sql",
        "exit_code": 1,
        "type": "ORA",
        "message": "Oracle error detected",
        "stderr": "...",
        "spool": "/release/H004/APP1_2026-09-01.log"
    }
]
```

The full execution trace should be inspected in the spool artifact when
one is available.

---

## Artifacts

When Entropy-managed spooling is used, the generated spool log is
published as a plugin artifact.

The artifact name identifies the schema and calling script:

```text
sqlplus_<schema>_<script>_spool
```

Example:

```text
sqlplus_APP1_App1_calling_script_spool
```

The artifact value is the spool log path.

Example:

```text
{
    "artifacts": {
        "sqlplus_APP1_App1_calling_script_spool":
            "/release/H004/APP1_2026-09-01.log"
    }
}
```

These spool logs are intended to provide the full execution trace for
later analysis or reporting plugins.

A future reporting plugin can consume these artifacts to identify
invalid objects, SQL errors, execution failures, and other deployment
information.

---

## Validation

The plugin validates:

### Mode

```text
plan
direct
```

### Error Policy

```text
abort
continue
```

### Spool Configuration

When provided, `spool` must be an object.

The following fields are validated:

- `enabled` → boolean
- `override` → boolean
- `create_if_not_exists` → boolean
- `name_placeholder` → non-empty string
- `wrappers_before` → list of strings
- `wrappers_after` → list of strings

### Execution Path

If supplied:

```text
execution_path
```

must be a non-empty string.

When spool management is enabled and no execution path is supplied, the
plugin can derive the execution path from the first resolved SQL script.

### Direct Mode

Each execution must contain valid connection, schema, credential, and
script information.

---

## Error Handling

### Configuration Failures

Invalid arguments are rejected during resolution.

Examples:

- missing mode
- unsupported mode
- invalid error policy
- invalid spool configuration
- invalid execution plan
- invalid direct execution definitions

### Process Failures

Operating-system failures are converted into structured SQLPlus
execution failures.

Examples:

- `sqlplus` executable not found
- permission errors
- process execution errors
- timeout failures

### SQLPlus/Oracle Failures

The plugin evaluates:

1. process exit code
2. SQLPlus/Oracle error output

Recognized error patterns include:

```text
ORA-xxxxx
SP2-xxxxx
PLS-xxxxx
```

A detected SQLPlus/Oracle error causes the execution to be marked as
failed.

### Partial Execution

With:

```text
on_error = continue
```

a failed application does not prevent subsequent applications from
executing.

With:

```text
on_error = abort
```

execution stops after the first failure.

---

## Security

SQLPlus credentials are sensitive information.

Credentials should be stored in Entropy Vault rather than hardcoded in
workflow files.

The actual SQLPlus process requires credentials, but the displayed
command representation masks the password.

Example displayed command:

```text
app1/****@//localhost:1521/orcl
```

Passwords must not be placed in:

- workflow files
- documentation
- source code
- test fixtures
- custom log messages

The plugin does not intentionally include database passwords in
structured outputs, changes, or errors.

---

## Filesystem

The plugin reads SQL scripts supplied by the resolver.

The original SQL scripts are not modified or deleted.

When spool management requires a generated execution script, the
generated copy is stored under:

```text
<execution_path>/.entropy/sqlplus/
```

The original calling script remains unchanged.

### Working Directory

SQLPlus runs with:

```text
cwd = script.parent
```

This is important for calling scripts that reference other files using
relative paths.

### Generated Spool Logs

When configured, spool directories are created when
`create_if_not_exists` is enabled and the filesystem permits creation.

The target directory/file must be writable for the spool to be usable.

---

## External Commands

The plugin executes:

```bash
sqlplus username/password@//host:port/sid @script
```

The `sqlplus` executable must be available in `PATH`.

---

## External Services

### Oracle Database

The plugin connects to Oracle databases using SQLPlus.

Connection information consists of:

```text
IP
PORT
SID
```

Authentication consists of:

```text
username
password
```

Each schema may have independent credentials.

---

## Side Effects

SQL scripts may:

- create database objects
- alter database objects
- insert data
- update data
- delete data
- execute stored procedures
- perform other database operations

The plugin starts the SQLPlus process for each execution and can create
Entropy-generated spool directories, wrapper scripts, and spool log
files when spool management is enabled.

The original SQL scripts are not modified or deleted.

---

## Performance

Executions are performed sequentially.

For multiple schemas:

```text
APP1
  ↓
APP2
  ↓
APP3
```

The plugin does not execute schemas concurrently.

Database execution time depends primarily on:

- SQL script complexity
- database performance
- network latency
- number of applications
- number of SQL statements
- database locks
- external database dependencies

---

## Limitations

- Requires SQLPlus to be installed.
- Requires `sqlplus` to be available in `PATH`.
- Requires Oracle database connectivity.
- Requires valid schema credentials.
- Executes database operations sequentially.
- Does not provide database transaction management across independent
  applications.
- Cannot automatically roll back changes already committed by a
  previously successful application.
- `on_error = continue` does not make a failed execution successful.
- SQL scripts are responsible for their own transaction semantics.
- SQLPlus/Oracle errors are detected from exit status and recognized
  output patterns.
- Spool path validation cannot guarantee that the Oracle SQLPlus process
  will ultimately have sufficient permissions in every runtime
  environment.

---

## Troubleshooting

### SQLPlus executable was not found

Check:

```bash
which sqlplus
```

Then:

```bash
sqlplus -v
```

Ensure the Entropy execution environment has the same `PATH` used to
locate SQLPlus.

### Existing spool path is replaced

Check the execution result:

```json
"spool": {
    "enabled": true,
    "detected": true,
    "existing": "/opt/oracle/prod/customer.log",
    "used": "/release/H004/APP1_2026-09-01.log",
    "overridden": true,
    "reason": "existing_spool_invalid"
}
```

Possible reasons include:

- the original spool file does not exist and its parent directory is
  unavailable
- the parent directory is not writable
- the existing target is not a file
- `override` was explicitly requested

### Existing spool is used

With:

```text
enabled = true
override = false
```

a valid existing spool target is preserved.

The result identifies it through:

```text
detected = true
existing = <path>
used = <path>
overridden = false
```

### No spool command exists

With:

```text
enabled = true
```

Entropy generates an execution wrapper containing the configured spool
command.

The original SQL script remains unchanged.

### Large stdout appears truncated

This is intentional.

The structured output uses a preview to prevent large SQL query results
from overwhelming the workflow UI.

Check the Entropy execution log when spool is disabled, or the generated
spool artifact when spool is enabled.

### Oracle/SQLPlus execution failed

Check:

1. `error_type`
2. `error_message`
3. `stderr`
4. `spool.used`
5. the generated spool artifact

The spool log is the preferred source for detailed execution analysis
when available.

---

## Recommended Architecture

```text
BuildReleaseContext
        │
        ▼
database execution context
        │
        ▼
SQLPlus
        │
        ├── connection
        ├── schema credentials
        ├── execution plan
        │
        └── spool subsystem
                │
                ├── detect existing spool
                ├── validate path
                ├── preserve valid spool
                ├── override invalid/existing spool when configured
                └── generate spool when absent
                        │
                        ▼
                SQLPlus execution trace
                        │
                        ▼
                spool artifact
                        │
                        ▼
                future analysis/reporting plugin
```

The spool subsystem is deliberately separated from database execution
resolution so that future plugins can consume the resulting execution
logs without needing to execute SQL again.

---

## Examples

### Basic Direct Usage

```json
{
    "name": "SQLPlus Direct",
    "plugin": "sqlplus.generic",
    "enabled": true,
    "on_failure": "abort",
    "arguments": {
        "mode": "direct",
        "on_error": "abort",
        "executions": [
            {
                "ip": "localhost",
                "port": 1521,
                "sid": "orcl",
                "schema": "APP1",
                "username": "app1",
                "password": "1234",
                "script": "/db/App1/App1_calling_script.sql"
            }
        ]
    }
}
```

### Managed Spool Without Override

```json
{
    "mode": "direct",
    "on_error": "continue",
    "executions": [],
    "spool": {
        "enabled": true,
        "override": false,
        "create_if_not_exists": true,
        "name_placeholder": "%execution_path/%release_%schema_%date.log"
    }
}
```

A valid existing spool is preserved. An invalid spool is replaced by an
Entropy-generated execution copy.

### Managed Spool With Override

```json
{
    "mode": "direct",
    "on_error": "abort",
    "executions": [],
    "spool": {
        "enabled": true,
        "override": true,
        "create_if_not_exists": true,
        "name_placeholder": "%execution_path/%release_%schema_%date.log",
        "wrappers_before": [
            "SET ECHO ON",
            "SET FEEDBACK ON",
            "SET HEADING ON",
            "SET SERVEROUTPUT ON"
        ],
        "wrappers_after": [
            "SPOOL OFF",
            "EXIT"
        ]
    }
}
```

The existing active spool target is replaced in the generated execution
copy.

### Spool Disabled

```json
{
    "mode": "direct",
    "on_error": "abort",
    "executions": [],
    "spool": {
        "enabled": false
    }
}
```

The calling script is executed normally.

If the script contains its own spool command, SQLPlus uses it.

If no spool is available, Entropy captures stdout and writes a concise
execution trace to the Entropy log.

---

## Notes

The SQLPlus plugin is intended primarily for release/deployment
workflows.

Use `plan` mode when SQL executions originate from a release execution
plan.

Use `direct` mode when the caller already has complete SQLPlus execution
definitions.

Keep common connection information and schema-specific credentials
separate.

Store credentials in Entropy Vault.

For production deployments, select `on_error` deliberately according to
the independence and failure-isolation requirements of the applications.

Spool logs are intended to become the durable execution evidence for
future analysis and reporting plugins.

---

## Changelog

### Current

- Added SQLPlus spool subsystem.
- Added active spool detection.
- Added relative spool path resolution.
- Added spool path validation.
- Added writable file/directory checks.
- Added configurable spool filename placeholders.
- Added automatic spool creation when no active spool exists.
- Added configurable spool wrapper commands.
- Added `spool.override`.
- Added safe generated execution copies instead of modifying original SQL
  scripts.
- Added automatic replacement of invalid existing spool paths.
- Added structured spool decision metadata:
  `enabled`, `detected`, `existing`, `used`, `overridden`, and `reason`.
- Added spool log artifacts to `PluginResult.metadata`.
- Added concise stdout previews for large SQLPlus output.
- Added Entropy execution-log fallback when spool is disabled or
  unavailable.
- Added structured SQLPlus/Oracle failure information.
- Preserved `plan` and `direct` execution modes.
- Preserved schema-level sequential execution and `on_error` handling.

### 1.0.0

- Initial SQLPlus plugin release.
- Added `plan` execution mode.
- Added `direct` execution mode.
- Added multiple schema execution support.
- Added configurable `on_error` policy.
- Added SQLPlus command execution through Entropy shell infrastructure.
- Added script-directory working-directory support.
- Added credential-safe command representation.
- Added SQLPlus/Oracle error detection.
- Added structured execution results.
- Added structured changes and errors.
- Added Vault-compatible credential configuration.
- Added integration with database execution plans produced by
  `release.context_builder`.
