# sqlplus.generic

------------------------------------------------------------------------

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
4. Executes SQLPlus with the script directory as the working directory.
5. Captures the SQLPlus execution result.
6. Detects process-level and SQLPlus/Oracle-level failures.
7. Applies the configured `on_error` policy.
8. Publishes structured workflow outputs, changes, and errors.

Each application/schema execution is independent.

A failure in one application does not necessarily stop execution of
subsequent applications. The behavior is controlled by the `on_error`
argument.

------------------------------------------------------------------------

## Requirements

The following requirements must be satisfied before using this plugin.

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
````

If the executable cannot be found, the plugin reports a structured
execution failure.

Example error:

```text
SQLPlus executable was not found. Ensure 'sqlplus' is installed and available on PATH.
```

### Oracle Connectivity

The execution environment must be able to connect to the target Oracle
database using the supplied:

* IP/host
* port
* SID/service identifier
* username
* password

### Entropy

The plugin requires the Entropy plugin execution infrastructure,
including:

* `BasePlugin`
* `PluginResult`
* Entropy shell/process execution through `self.shell`

### Files

Every SQL script supplied to the plugin must:

* exist before execution
* be readable by the Entropy process
* be a valid SQLPlus script
* be accessible from the execution environment

---

## Arguments

The plugin accepts the following arguments.

| Argument     | Required         | Type     | Default | Description                                                                   |
| ------------ | ---------------- | -------- | ------- | ----------------------------------------------------------------------------- |
| `mode`       | Yes              | `string` | ---     | SQLPlus execution mode.                                                       |
| `on_error`   | No               | `string` | `abort` | Determines whether execution stops or continues after an application failure. |
| `connection` | Yes for `plan`   | `object` | ---     | Common Oracle connection information.                                         |
| `schemas`    | Yes for `plan`   | `object` | ---     | Schema-specific credentials.                                                  |
| `execution`  | Yes for `plan`   | `object` | ---     | Database execution context, normally supplied by `BuildReleaseContext`.       |
| `executions` | Yes for `direct` | `array`  | ---     | Explicit SQLPlus executions.                                                  |

---

## Argument Details

### `mode`

Defines how database executions are resolved.

Accepted values:

```text
plan
direct
```

#### `plan`

Uses:

* `connection`
* `schemas`
* `execution`

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
the `executions` argument.

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

Example:

```text
APP1 → SUCCESS
APP2 → FAILURE
APP3 → SKIPPED
APP4 → SKIPPED
```

#### `continue`

Continues executing subsequent applications after a failure.

Example:

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

Defines the common Oracle connection information used by all schemas
in plan mode.

Example:

```json
{
    "IP": "localhost",
    "PORT": 1521,
    "SID": "orcl"
}
```

The connection contains environment-specific information.

It is intended to be common to all database schemas in the execution.

The connection does not contain schema usernames or passwords.

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

The schema key must correspond to the schema referenced by the
execution plan.

For example:

```json
{
    "schema": "APP1"
}
```

must resolve against:

```json
{
    "APP1": {
        "username": "...",
        "password": "..."
    }
}
```

Credentials should normally be supplied through Entropy Vault
interpolation rather than being written directly in workflow files.

---

### `execution`

Contains the database execution context.

The recommended source is:

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

to construct the actual SQLPlus executions.

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
    },
    {
        "ip": "localhost",
        "port": 1521,
        "sid": "orcl",
        "schema": "APP2",
        "username": "app2",
        "password": "1234",
        "script": "/path/to/App2_calling_script.sql"
    }
]
```

Each execution is independent.

---

## Workflow Configuration

The plugin is executed through a workflow step.

### Basic Configuration

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

`on_failure` belongs to the Entropy workflow engine.

Example:

```json
{
    "on_failure": "abort"
}
```

It determines what the workflow does when the SQLPlus plugin itself
returns:

```text
success = false
```

`on_error` belongs to the SQLPlus plugin.

Example:

```json
{
    "on_error": "continue"
}
```

It determines whether SQLPlus continues with subsequent database
applications after an individual database execution fails.

For example:

```text
SQLPlus plugin
    │
    ├── APP1 → success
    ├── APP2 → failure
    └── APP3 → success
```

with:

```text
on_error = continue
```

causes APP3 to execute.

The final plugin result is still:

```text
success = false
```

because APP2 failed.

---

## Complete Workflow Example

### Plan Mode

The recommended deployment configuration is to use the database
execution context generated by `BuildReleaseContext`.

```json
{
    "name": "SQLPlus Workflow",
    "version": "1.0.0",
    "description": "Execute database release scripts using SQLPlus.",

    "variables": {
        "release": "/path/to/release.zip",
        "docker_repository": "/path/to/repository",
        "yaml_repository": "/path/to/yamls",
        "image_tag": "1.1.10"
    },

    "steps": [
        {
            "name": "BuildReleaseContext",
            "plugin": "release.context_builder",
            "enabled": true,
            "on_failure": "abort",
            "tags": [
                "release",
                "context_builder"
            ],
            "arguments": {
                "release": "${release}",
                "docker_repository": "${docker_repository}",
                "yaml_repository": "${yaml_repository}",
                "image_tag": "${image_tag}"
            }
        },
        {
            "name": "SQLPlus",
            "plugin": "sqlplus.generic",
            "enabled": true,
            "on_failure": "abort",
            "tags": [
                "release",
                "sqlplus"
            ],
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
                "execution": "${steps.BuildReleaseContext.outputs.database}"
            }
        }
    ]
}
```

In production, credentials should not be hardcoded as shown above.
Use Vault variables instead.

---

## Workflow Variables

Workflow variables can be used to supply plugin arguments.

Example:

```json
{
    "variables": {
        "oracle_connection": {
            "IP": "localhost",
            "PORT": 1521,
            "SID": "orcl"
        }
    }
}
```

The variable can then be referenced where supported:

```json
{
    "arguments": {
        "connection": "${oracle_connection}"
    }
}
```

Workflow variables are resolved by the workflow engine before the plugin
receives its runtime arguments.

---

## Vault Variables

Database credentials should be stored in Entropy Vault rather than
hardcoded in workflow files.

A recommended environment structure is:

```text
SIT_CONNECTION
SIT_SCHEMA_APP1
SIT_SCHEMA_APP2
```

For example, the connection Vault value can contain:

```json
{
    "IP": "localhost",
    "PORT": 1521,
    "SID": "orcl"
}
```

A schema Vault value can contain:

```json
{
    "username": "app1",
    "password": "..."
}
```

The workflow can reference these values through Entropy Vault
interpolation.

Example:

```json
{
    "variables": {
        "SIT": {
            "connection": "${entv:SIT_CONNECTION}",
            "schemas": "${entv:SIT_SCHEMA_*}"
        }
    }
}
```

These variables can then be passed to the SQLPlus plugin according to
the workflow variable interpolation rules.

Actual passwords must never be placed in this manual.

---

## Execution

The plugin execution consists of the following stages.

1. Validate the `mode` argument.

2. Validate the `on_error` policy.

3. Resolve database executions.

4. In `plan` mode:

   * Read the database execution context.
   * Resolve the execution plan.
   * Resolve the corresponding SQL scripts.
   * Resolve schema credentials.

5. In `direct` mode:

   * Validate the explicitly supplied execution definitions.

6. Build the SQLPlus command for each execution.

7. Execute SQLPlus using Entropy's shell abstraction.

8. Set the SQL script's parent directory as the process working
   directory.

9. Capture:

   * exit code
   * stdout
   * stderr
   * execution duration

10. Detect SQLPlus/Oracle failures.

11. Apply the `on_error` policy.

12. Publish workflow outputs.

13. Publish structured changes and errors.

---

## SQLPlus Execution

The plugin invokes SQLPlus using the following connection format:

```text
sqlplus username/password@//host:port/sid @script
```

Example:

```bash
sqlplus app1/****@//localhost:1521/orcl @App1_calling_script.sql
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

The plugin produces the following outputs.

| Output       | Type      | Description                                                    |
| ------------ | --------- | -------------------------------------------------------------- |
| `success`    | `boolean` | Overall SQLPlus execution status.                              |
| `mode`       | `string`  | Execution mode used by the plugin.                             |
| `on_error`   | `string`  | Error policy used during execution.                            |
| `executions` | `integer` | Number of executions requested.                                |
| `succeeded`  | `integer` | Number of executions that completed successfully.              |
| `failed`     | `integer` | Number of executions that failed.                              |
| `skipped`    | `integer` | Number of executions skipped because of `abort`.               |
| `results`    | `array`   | Detailed result of each execution that was actually attempted. |

### `success`

`true` only when all requested executions completed successfully.

Example:

```text
success = true
```

If any execution fails:

```text
success = false
```

If `on_error` is `continue`, subsequent applications may still execute,
but the overall result remains failed.

### `executions`

The total number of execution definitions resolved by the plugin.

Example:

```text
executions = 3
```

### `succeeded`

Number of executions that completed successfully.

### `failed`

Number of executions that failed.

### `skipped`

Number of executions that were not attempted because:

```text
on_error = abort
```

Example:

```text
APP1 → success
APP2 → failure
APP3 → skipped

executions = 3
succeeded = 1
failed = 1
skipped = 1
```

### `results`

Contains detailed information for each execution that was attempted.

Example:

```json
{
    "schema": "APP1",
    "script": "/path/to/App1_calling_script.sql",
    "success": true,
    "exit_code": 0,
    "stdout": "...",
    "stderr": "",
    "duration": 0.42
}
```

Sensitive connection credentials are not included.

---

## Example Output

```text
outputs:
    success = false
    mode = "plan"
    on_error = "continue"
    executions = 2
    succeeded = 1
    failed = 1
    skipped = 0

    results:
        APP1:
            success = true
            exit_code = 0

        APP2:
            success = false
            exit_code = 1
```

---

## Plugin Result

The plugin publishes the following top-level result structure:

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

`changed` indicates whether at least one SQLPlus execution completed
successfully.

Therefore:

```text
No successful executions → changed = false
At least one successful execution → changed = true
```

Examples:

```text
APP1 → failure
changed = false
```

```text
APP1 → success
APP2 → failure
changed = true
```

A failed execution by itself does not make `changed` true.

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

Changes are published at the top level of `PluginResult`.

They are not duplicated inside `outputs`.

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
        "stderr": "..."
    }
]
```

Errors are published at the top level of `PluginResult`.

They are not duplicated inside `outputs`.

---

## Artifacts

The SQLPlus plugin does not create deployment artifacts.

The plugin may expose artifacts inherited through the Entropy plugin
framework, but SQLPlus does not create or persist SQL execution output
as an Entropy artifact.

SQLPlus stdout and stderr are available through the execution results.

---

## Examples

### Example 1 --- Basic Direct Usage

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

Do not use plaintext credentials in production workflows.

---

### Example 2 --- Multiple Schemas

```json
{
    "name": "SQLPlus Multiple Schemas",
    "plugin": "sqlplus.generic",
    "enabled": true,
    "on_failure": "abort",
    "arguments": {
        "mode": "direct",
        "on_error": "continue",
        "executions": [
            {
                "ip": "localhost",
                "port": 1521,
                "sid": "orcl",
                "schema": "APP1",
                "username": "app1",
                "password": "1234",
                "script": "/db/App1/App1_calling_script.sql"
            },
            {
                "ip": "localhost",
                "port": 1521,
                "sid": "orcl",
                "schema": "APP2",
                "username": "app2",
                "password": "1234",
                "script": "/db/App2/App2_calling_script.sql"
            }
        ]
    }
}
```

With:

```text
on_error = continue
```

APP2 is executed even if APP1 fails.

---

### Example 3 --- Plan Mode

```json
{
    "name": "SQLPlus Plan",
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
        "execution": "${steps.BuildReleaseContext.outputs.database}"
    }
}
```

The database execution context is obtained from the
`release.context_builder` step.

---

### Example 4 --- Using Workflow Variables

```json
{
    "variables": {
        "connection": {
            "IP": "localhost",
            "PORT": 1521,
            "SID": "orcl"
        }
    },

    "steps": [
        {
            "name": "SQLPlus",
            "plugin": "sqlplus.generic",
            "enabled": true,
            "on_failure": "abort",
            "arguments": {
                "mode": "plan",
                "on_error": "continue",
                "connection": "${connection}",
                "execution": "${steps.BuildReleaseContext.outputs.database}"
            }
        }
    ]
}
```

---

### Example 5 --- Using Vault Variables

```json
{
    "variables": {
        "SIT": {
            "connection": "${entv:SIT_CONNECTION}",
            "schemas": "${entv:SIT_SCHEMA_*}"
        }
    },

    "steps": [
        {
            "name": "SQLPlus",
            "plugin": "sqlplus.generic",
            "enabled": true,
            "on_failure": "abort",
            "tags": [
                "release",
                "sqlplus"
            ],
            "arguments": {
                "mode": "plan",
                "on_error": "continue",
                "connection": "${SIT.connection}",
                "schemas": "${SIT.schemas}",
                "execution": "${steps.BuildReleaseContext.outputs.database}"
            }
        }
    ]
}
```

Vault values are resolved by the workflow engine before the SQLPlus
plugin receives its arguments.

Do not place actual credentials in workflow files or documentation.

---

## Validation

The plugin validates the following.

### Mode

`mode` is required.

Allowed values:

```text
plan
direct
```

### Error Policy

`on_error` must be one of:

```text
abort
continue
```

### Plan Mode

Plan mode requires:

```text
connection
schemas
execution
```

The `execution` object must contain the database execution information
required by the resolver.

The plugin extracts:

```text
execution.execution_plan
execution.scripts
```

### Direct Mode

Direct mode requires:

```text
executions
```

Each execution must contain the required database connection,
credentials, schema, and script information.

### Script Validation

Scripts must resolve to valid filesystem paths and must be accessible
for execution.

### Runtime Validation

The SQLPlus executable must be available when execution begins.

---

## Validation Errors

Examples include:

```text
'mode' is required.
```

```text
'execution' must be an object in plan mode.
```

```text
Unsupported SQLPlus mode: 'example'.
```

```text
'on_error' must be either 'abort' or 'continue'.
```

Resolver validation errors are returned through the plugin/workflow
error handling mechanism.

---

## Error Handling

The plugin handles failures at multiple levels.

### Configuration Failures

Invalid arguments are rejected during resolution.

Examples:

* missing mode
* unsupported mode
* invalid error policy
* invalid execution plan
* missing execution information
* invalid direct execution definitions

### Process Failures

Operating-system failures are converted into structured SQLPlus
execution failures.

Examples:

* `sqlplus` executable not found
* permission errors
* process execution errors
* timeout failures

A process failure does not result in an uncaught Python traceback from
the SQLPlus execution layer.

### SQLPlus/Oracle Failures

The plugin evaluates the SQLPlus execution result using:

1. Process exit code.
2. SQLPlus/Oracle error output.

Recognized SQLPlus/Oracle error patterns include errors such as:

```text
ORA-xxxxx
SP2-xxxxx
PLS-xxxxx
```

A detected SQLPlus/Oracle error causes the individual execution to be
marked as failed.

### Partial Execution

Applications are independent.

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

### Overall Success

The overall plugin result is unsuccessful if any requested execution
fails or is skipped because the `abort` policy stopped the batch.

Example:

```text
APP1 → SUCCESS
APP2 → FAILURE
APP3 → SUCCESS

on_error = continue

success = false
changed = true
```

### Cleanup

The plugin does not modify or delete SQL scripts.

---

## Security

SQLPlus credentials are sensitive information.

### Credential Storage

Credentials should be stored in Entropy Vault.

Recommended structure:

```text
SIT_CONNECTION
SIT_SCHEMA_APP1
SIT_SCHEMA_APP2
```

The workflow should resolve these values through Vault interpolation.

### Password Exposure

The actual SQLPlus process requires the database credentials.

The plugin therefore constructs the SQLPlus authentication argument
internally.

The displayed command representation is sanitized so that the
password is not exposed as part of the recorded command.

For example, the actual process command may contain:

```text
app1/<password>@//localhost:1521/orcl
```

while the displayed representation uses:

```text
app1/****@//localhost:1521/orcl
```

### Plugin Outputs

The plugin does not include:

* database passwords
* complete database connection credentials
* authentication secrets

in its structured `outputs`, `changes`, or `errors`.

### Logs

Do not manually log the SQLPlus connection string or credentials from
custom workflow components.

### Documentation

Never store real credentials in workflow examples, plugin
documentation, source code, or test fixtures.

---

## Filesystem

The plugin reads SQL scripts supplied by the resolver.

Example:

```text
/releases/H004/DBScripts/App1/App1_calling_script.sql
```

The script:

* must already exist
* must be readable
* is not modified by the plugin
* is not deleted by the plugin

### Working Directory

SQLPlus is executed with:

```text
cwd = script.parent
```

For:

```text
/releases/H004/DBScripts/App1/App1_calling_script.sql
```

the working directory is:

```text
/releases/H004/DBScripts/App1
```

This is important when SQL scripts reference other files using relative
paths.

---

## External Commands

The plugin executes:

```bash
sqlplus username/password@//host:port/sid @script
```

Example:

```bash
sqlplus app1/****@//localhost:1521/orcl @App1_calling_script.sql
```

### Purpose

SQLPlus is used to execute Oracle database calling scripts.

### Required Availability

The `sqlplus` executable must be available in `PATH`.

### Working Directory

The SQLPlus process runs from the directory containing the SQL script.

### Failure Conditions

The plugin reports failure when:

* SQLPlus cannot be started.
* SQLPlus returns a non-zero exit code.
* SQLPlus/Oracle error patterns are detected.
* The process times out.
* An operating-system process error occurs.

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

### Connectivity

The execution environment must have network connectivity to the
configured Oracle database.

### Authentication

Each schema may have independent credentials.

For example:

```text
APP1 → app1 credentials
APP2 → app2 credentials
```

A schema failure does not automatically imply that another schema will
fail.

---

## Side Effects

The plugin can cause significant external state changes.

### Database Changes

SQL scripts may:

* create database objects
* alter database objects
* insert data
* update data
* delete data
* execute stored procedures
* perform other database operations

The exact database changes are determined by the SQL scripts.

### External Process

The plugin starts the SQLPlus process for each execution.

### Filesystem

The plugin reads SQL scripts but does not modify or delete them.

### Remote Systems

The plugin connects to the configured Oracle database.

---

## Performance

Database execution time depends primarily on:

* SQL script complexity
* database performance
* network latency
* number of applications
* number of SQL statements
* database locks
* external database dependencies

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

This ensures deterministic execution order and makes the `abort`
behavior predictable.

---

## Limitations

The plugin currently has the following operational constraints.

* Requires SQLPlus to be installed.
* Requires `sqlplus` to be available in `PATH`.
* Requires Oracle database connectivity.
* Requires valid schema credentials.
* Executes database operations sequentially.
* Does not provide database transaction management across independent
  applications.
* Cannot automatically roll back changes already committed by a
  previously successful application.
* `on_error = continue` does not make a failed execution successful.
* SQL scripts are responsible for their own database transaction
  semantics.
* The plugin does not modify SQL scripts to add SQLPlus error handling.
* SQLPlus/Oracle errors are detected from exit status and recognized
  output patterns.

---

## Troubleshooting

### Problem

```text
SQLPlus executable was not found.
```

### Cause

The `sqlplus` executable is not installed or is not available in the
process `PATH`.

### Solution

Install the Oracle SQLPlus client and ensure:

```bash
which sqlplus
```

resolves to the executable.

Then verify:

```bash
sqlplus -v
```

---

### Problem

```text
'execution' must be an object in plan mode.
```

### Cause

The `execution` argument is missing or is not an object.

### Solution

Use:

```json
{
    "mode": "plan",
    "execution": "${steps.BuildReleaseContext.outputs.database}"
}
```

The supplied value must contain the database execution context.

---

### Problem

```text
Unsupported SQLPlus mode
```

### Cause

An unsupported value was supplied for `mode`.

### Solution

Use one of:

```text
plan
direct
```

---

### Problem

One application fails and subsequent applications do not execute.

### Cause

The plugin is configured with:

```text
on_error = abort
```

### Solution

Use:

```json
{
    "on_error": "continue"
}
```

if independent applications should continue executing after a failure.

---

### Problem

The plugin reports failure even though subsequent applications
completed successfully.

### Cause

One or more applications failed.

With:

```text
on_error = continue
```

the plugin continues execution but the overall result remains:

```text
success = false
```

This is expected behavior.

---

### Problem

`changed` is `false` even though a database execution was attempted.

### Cause

`changed` represents successful execution, not attempted execution.

For example:

```text
APP1 → SQLPlus executable missing
```

results in:

```text
success = false
changed = false
```

If at least one application successfully executes:

```text
changed = true
```

---

### Problem

A SQL script reports an Oracle error but SQLPlus appears to continue.

### Cause

SQLPlus script behavior depends on the SQL script's error handling and
SQLPlus settings.

The plugin also examines recognized SQLPlus/Oracle error output, but
scripts should be designed with appropriate SQLPlus error handling.

---

## Notes

The SQLPlus plugin is intended primarily for release/deployment
workflows.

The recommended architecture is:

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
        └── execution plan
                │
                ▼
        SQLPlus executions
                │
                ▼
        Oracle database
```

For environment-specific deployment, keep common connection
information and schema-specific credentials separate.

A recommended model is:

```text
Environment
│
├── Connection
│     ├── IP
│     ├── PORT
│     └── SID
│
└── Schemas
      ├── APP1
      │     ├── username
      │     └── password
      │
      └── APP2
            ├── username
            └── password
```

Store these values in Entropy Vault and resolve them through workflow
variables.

Use `plan` mode when the SQL executions originate from a release
execution plan.

Use `direct` mode when the caller already has the complete SQLPlus
execution definitions.

For production deployments, `on_error` should be selected deliberately
based on the independence and failure-isolation requirements of the
applications being deployed.

---

## Changelog

### 1.0.0

* Initial SQLPlus plugin release.
* Added `plan` execution mode.
* Added `direct` execution mode.
* Added multiple schema execution support.
* Added configurable `on_error` policy.
* Added `abort` execution behavior.
* Added `continue` execution behavior.
* Added SQLPlus command execution through Entropy shell infrastructure.
* Added script-directory working-directory support.
* Added credential-safe command representation.
* Added SQLPlus/Oracle error detection.
* Added structured execution results.
* Added structured changes and errors.
* Added Vault-compatible credential configuration.
* Added integration with database execution plans produced by
  `release.context_builder`.

```
```
