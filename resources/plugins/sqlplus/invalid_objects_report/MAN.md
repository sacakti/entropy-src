# invalid_objects_report



------------------------------------------------------------------------

## Overview

Describe what this plugin does.

Explain:

-   The purpose of the plugin.
-   The problem it solves.
-   When it should be used.
-   Important behavior users should understand.

------------------------------------------------------------------------

## Requirements

Document the requirements for using this plugin.

Examples:

-   Required operating system.
-   Required system commands.
-   Required permissions.
-   Required environment configuration.
-   Required files or directories.
-   Required Entropy services.
-   External dependencies.

------------------------------------------------------------------------

## Arguments

| Argument | Required | Type | Default | Description |
|---|---|---|---|---|
| `connection` | Yes | `dictionary` | — | Oracle connection: `IP`, `PORT`, `SID`. |
| `schemas` | Yes | `dictionary` | — | Credentials of the schemas that may be checked, e.g. `${entv:sit/schemas_*}`. |
| `execution` | No | `dictionary` | — | A release's database context: check only the schemas it changes. |
| `only_schemas` | No | `list` | — | Schemas to check by name or pattern (`APP*`), added to those from `execution`. |
| `report` | No | `dictionary` | — | Text added to the report file name. |
| `sqlhome` | No | `path` | PATH | Oracle home whose `bin/sqlplus` is used. |

### Choosing schemas

`schemas` is the pool of credentials, so it can stay one Vault pattern for the whole
environment (`${entv:sit/schemas_*}`). Which of them are checked:

| Given | Checked |
|---|---|
| Neither `execution` nor `only_schemas` | Every schema in `schemas` (as before 1.4.0). |
| `execution` | The schemas the release changes: the context's `schemas` list, else every `schema` of its execution plan's applications, in plan order. |
| `only_schemas` | Those names, and the schemas matching those patterns. |
| Both | The release's schemas, then the named ones. |

Names and patterns are compared without case. A release that changes no schema
(no execution plan) checks none, and the step still succeeds with an empty report.
A schema to be checked that has no credentials in `schemas` is listed in the report
as an error, so the step fails rather than skipping it silently. A pattern that
matches nothing is a warning.

After a release, check only what it touched:

``` json
{
    "name": "Invalid objects",
    "plugin": "sqlplus.invalid_objects_report",
    "arguments": {
        "connection": "${connection}",
        "schemas": "${entv:sit/schemas_*}",
        "execution": "${steps.BuildReleaseContext.outputs.database}",
        "only_schemas": ["COMMON"]
    }
}
```

`release.context_builder` (1.2.0 and later) puts the release's schemas in
`database.schemas`; an older context, or `consolidate.db_scripts`' `database`
output, works too, through its execution plan.

Document:

-   Accepted values.
-   Expected format.
-   Validation rules.
-   Default behavior.
-   Special behavior.
-   Restrictions.

------------------------------------------------------------------------

## Workflow Configuration

The plugin is executed through a workflow step.

### Basic Configuration

``` json
{
    "name": "Execute invalid_objects_report",
    "plugin": "",
    "enabled": true,
    "continue_on_error": false,
    "tags": [],
    "arguments": {}
}
```

------------------------------------------------------------------------

## Complete Workflow Example

``` json
{
    "name": "invalid_objects_report Workflow",
    "version": "1.0.0",
    "description": "",
    "variables": {},
    "steps": [
        {
            "name": "Execute invalid_objects_report",
            "plugin": "",
            "enabled": true,
            "continue_on_error": false,
            "tags": [],
            "arguments": {}
        }
    ]
}
```

------------------------------------------------------------------------

## Workflow Variables

Document workflow variables consumed by this plugin.

### Example

``` json
{
    "variables": {
        "example": "value"
    }
}
```

The variable can then be referenced by plugin arguments where supported.

### Example

``` json
{
    "arguments": {
        "example": "${example}"
    }
}
```

Document any variable-specific requirements or restrictions here.

------------------------------------------------------------------------

## Vault Variables

Document any Vault values that may be consumed by this plugin.

### Example

``` json
{
    "variables": {
        "password": "${entv:database_password}"
    }
}
```

Vault values are resolved by the workflow engine before the plugin
receives its runtime variables.

Do not place actual passwords, tokens, credentials, private keys, or
other sensitive values in this document.

------------------------------------------------------------------------

## Execution

Describe how the plugin executes.

Document the major execution stages.

For example:

1.  Validate the supplied arguments.
2.  Prepare required resources.
3.  Execute the requested operation.
4.  Publish workflow outputs.
5.  Publish workflow artifacts.
6.  Complete the plugin execution.

Document any conditional execution paths.

------------------------------------------------------------------------

## Outputs

Document the outputs produced by the plugin.

  Output      Type       Description
  ----------- ---------- ----------------------
  `example`   `string`   Describe the output.

### Example

``` text
outputs:
    example = "value"
```

Document whether each output is:

-   Always available.
-   Available only on success.
-   Available only under certain conditions.
-   Intended for consumption by later workflow steps.

------------------------------------------------------------------------

## Artifacts

Document workflow artifacts produced by the plugin.

  Artifact    Description
  ----------- ------------------------
  `example`   Describe the artifact.

For each artifact, document:

-   What it represents.
-   Where it points.
-   When it is created.
-   Whether it is always available.
-   Whether it can be consumed by subsequent workflow steps.

------------------------------------------------------------------------

## Examples

### Example 1 --- Basic Usage

Describe the most common usage scenario.

``` json
{
    "arguments": {}
}
```

### Example 2 --- Advanced Usage

Describe an advanced usage scenario.

``` json
{
    "arguments": {}
}
```

### Example 3 --- Using Workflow Variables

``` json
{
    "variables": {
        "example": "value"
    },
    "steps": [
        {
            "name": "Execute invalid_objects_report",
            "plugin": "",
            "enabled": true,
            "continue_on_error": false,
            "tags": [],
            "arguments": {
                "example": "${example}"
            }
        }
    ]
}
```

### Example 4 --- Using Vault Variables

``` json
{
    "variables": {
        "secret": "${entv:example_secret}"
    },
    "steps": [
        {
            "name": "Execute invalid_objects_report",
            "plugin": "",
            "enabled": true,
            "continue_on_error": false,
            "tags": [],
            "arguments": {
                "secret": "${secret}"
            }
        }
    ]
}
```

------------------------------------------------------------------------

## Validation

Document all validation performed by the plugin.

Examples:

-   Required arguments.
-   Argument types.
-   Allowed values.
-   Mutually exclusive arguments.
-   File validation.
-   Directory validation.
-   Configuration validation.
-   Runtime prerequisites.

### Validation Errors

Document the conditions under which plugin execution fails.

Example:

``` text
Argument 'example' is required.
```

------------------------------------------------------------------------

## Error Handling

Describe how errors are handled.

Document:

-   Validation failures.
-   Runtime failures.
-   External command failures.
-   File operation failures.
-   Network failures.
-   Partial-operation behavior.
-   Cleanup behavior after failure.
-   Whether the plugin raises an error.
-   Whether `continue_on_error` can be used at the workflow level.

------------------------------------------------------------------------

## Security

Document security-related behavior.

Examples:

-   Sensitive values.
-   Credentials.
-   Authentication.
-   Authorization.
-   File permissions.
-   Temporary files.
-   External command execution.
-   Secret handling.
-   Data persistence.

Never include real credentials, passwords, tokens, private keys, or
other sensitive values in this document.

------------------------------------------------------------------------

## Filesystem

Document files and directories used by the plugin.

  Path              Purpose
  ----------------- --------------------
  `/path/example`   Describe the path.

Document whether paths:

-   Must already exist.
-   Are created automatically.
-   Are modified.
-   Are deleted.
-   Are temporary.
-   Must be writable.
-   Must be readable.

------------------------------------------------------------------------

## External Commands

If the plugin executes operating-system commands, document them here.

### Example

``` bash
command --option value
```

Document:

-   Why the command is executed.
-   Required command availability.
-   Important arguments.
-   Expected behavior.
-   Failure conditions.
-   Required permissions.

------------------------------------------------------------------------

## External Services

Document external services accessed by the plugin.

Examples:

-   Docker.
-   OpenShift.
-   Kubernetes.
-   Git.
-   HTTP/HTTPS services.
-   Cloud services.
-   Databases.

For each service, document:

-   Purpose.
-   Required authentication.
-   Required configuration.
-   Expected connectivity.
-   Failure behavior.

------------------------------------------------------------------------

## Side Effects

Document operations that modify external state.

Examples:

-   Files created.
-   Files modified.
-   Files deleted.
-   Directories created.
-   Containers created.
-   Images pulled.
-   Images pushed.
-   Remote systems contacted.
-   Database changes.
-   External commands executed.

------------------------------------------------------------------------

## Performance

Document any relevant performance considerations.

Examples:

-   Large file processing.
-   Network operations.
-   Docker image transfers.
-   Long-running commands.
-   Storage requirements.
-   Timeout behavior.

------------------------------------------------------------------------

## Limitations

Document known limitations.

Examples:

-   Unsupported operating systems.
-   Unsupported file formats.
-   Unsupported argument combinations.
-   Maximum supported values.
-   External tool limitations.
-   Known operational constraints.

------------------------------------------------------------------------

## Troubleshooting

Document common problems and their solutions.

### Problem

Describe the problem.

### Cause

Describe the cause.

### Solution

Describe the solution.

Example:

``` text
Command not found.
```

**Cause**

The required external command is not available.

**Solution**

Install the required command and ensure it is available in `PATH`.

------------------------------------------------------------------------

## Notes

Document important operational considerations that users should know
before using the plugin.

Include any warnings, recommendations, compatibility notes, or special
usage instructions.

------------------------------------------------------------------------

## Changelog

### 1.4.0

-   `execution` checks only the schemas a release changes; `only_schemas` names
    schemas or patterns. Without them every schema is checked, as before.
-   New output `checked_schemas`.

### 1.0.0

-   Initial plugin release.
