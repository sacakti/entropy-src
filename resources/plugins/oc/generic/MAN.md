Absolutely buddy. Based on the complete `GenericPlugin` implementation, this is the `man.md` for **`oc.generic`**. I’ve documented the actual supported operations, isolated per-environment kubeconfig behavior, resource-list support, raw commands, outputs, validation, and security behavior without adding functionality that isn't present in the code. 

````markdown
# oc_generic

------------------------------------------------------------------------

## Overview

`oc.generic` is a generic OpenShift CLI operations plugin for Entropy.

The plugin provides a controlled workflow interface for executing common
OpenShift operations through the `oc` command-line interface.

Supported operations are:

- `login`
- `logout`
- `project`
- `whoami`
- `get`
- `apply`
- `replace`
- `delete`
- `raw`

The plugin uses an environment-specific kubeconfig for every OpenShift
session. This isolates OpenShift credentials and session state between
different environments.

### Purpose

The plugin provides a common interface for OpenShift operations without
requiring individual workflow plugins for every supported `oc` command.

It can be used for:

- Establishing an OpenShift session.
- Removing an OpenShift session.
- Selecting an OpenShift project.
- Identifying the authenticated OpenShift user.
- Reading OpenShift resources.
- Applying YAML resources.
- Replacing YAML resources.
- Deleting resources.
- Executing supported arbitrary `oc` commands through the `raw`
  operation.

### Important Behavior

The plugin:

- Requires the OpenShift CLI (`oc`) to be installed.
- Executes `oc` as an external process.
- Uses an isolated kubeconfig for each environment.
- Does not use the user's default kubeconfig directly.
- Stores environment-specific kubeconfig files under the plugin session
  directory.
- Requires a successful `login` operation before operations that need an
  existing OpenShift session.
- Supports both a single resource path and a list of resource paths for
  resource operations.
- Processes multiple resource paths independently.
- Does not automatically retry failed OpenShift commands.
- Does not perform rollback when one resource succeeds and another fails.

------------------------------------------------------------------------

## Requirements

The plugin requires:

- Entropy runtime.
- OpenShift CLI (`oc`).
- An accessible OpenShift cluster for operations requiring cluster
  connectivity.
- Valid OpenShift credentials for `login`.
- Appropriate OpenShift permissions for the requested operation.
- A valid environment name.
- Appropriate filesystem permissions for the Entropy session directory.

### System Command

The following command must be available in `PATH`:

```bash
oc
````

The plugin fails when the command cannot be found.

### OpenShift Access

For cluster operations, the authenticated user must have sufficient
OpenShift permissions for the requested operation.

For example:

* `get` requires permission to read the requested resource.
* `apply` requires permission to create or update the requested resource.
* `replace` requires permission to replace the requested resource.
* `delete` requires permission to delete the requested resource.
* `project` requires permission to access or switch to the requested
  project.

---

## Arguments

The arguments depend on the selected operation.

| Argument                   | Required                         | Type                       | Default | Description                                                               |
| -------------------------- | -------------------------------- | -------------------------- | ------- | ------------------------------------------------------------------------- |
| `operation`                | Yes                              | `string`                   | ---     | OpenShift operation to execute.                                           |
| `environment`              | Yes                              | `string`                   | ---     | Logical OpenShift environment used to isolate the kubeconfig.             |
| `api_url`                  | Required for `login`             | `string`                   | ---     | OpenShift API server URL.                                                 |
| `username`                 | Required for `login`             | `string`                   | ---     | OpenShift username.                                                       |
| `password`                 | Required for `login`             | `string`                   | ---     | OpenShift password.                                                       |
| `insecure_skip_tls_verify` | No                               | `boolean`                  | `false` | Disables TLS certificate verification for login when enabled.             |
| `namespace`                | No for `project`                 | `string`                   | ---     | OpenShift project to switch to. If omitted, displays the current project. |
| `resource`                 | Required for resource operations | `string` or `list[string]` | ---     | Resource YAML path or list of resource YAML paths.                        |
| `arguments`                | No                               | `list[string]`             | `[]`    | Additional arguments appended to the OpenShift command.                   |
| `command`                  | Required for `raw`               | `string`                   | ---     | Raw `oc` subcommand to execute.                                           |

---

## Argument Details

### `operation`

Specifies the OpenShift operation.

Accepted values:

```text
login
logout
project
whoami
get
apply
replace
delete
raw
```

The value is:

1. Required.
2. Validated as a string.
3. Trimmed.
4. Converted to lowercase.
5. Checked against the supported operation list.

Example:

```json
{
    "operation": "apply"
}
```

Invalid example:

```json
{
    "operation": "invalid"
}
```

This results in an error similar to:

```text
Unsupported OpenShift operation 'invalid'.
```

---

### `environment`

Specifies the logical OpenShift environment.

The environment is used to create an isolated kubeconfig location.

Example:

```json
{
    "environment": "SIT"
}
```

Valid characters are:

* Letters.
* Numbers.
* `.`
* `_`
* `-`

The environment must begin with a letter or number.

Valid examples:

```text
SIT
UAT
PROD
prod-01
cluster_01
environment.test
```

Invalid examples include values containing unsupported characters.

The environment must not be empty.

---

### `api_url`

Used by the `login` operation.

Specifies the OpenShift API server URL.

Example:

```json
{
    "api_url": "https://api.example.com:6443"
}
```

The value is passed to:

```bash
oc login <api_url>
```

The plugin does not independently validate the URL format.

---

### `username`

Used by the `login` operation.

Specifies the OpenShift username.

Example:

```json
{
    "username": "admin"
}
```

The value is passed to `oc login` using:

```bash
--username
```

---

### `password`

Used by the `login` operation.

Specifies the OpenShift password.

The value is passed to:

```bash
oc login
```

using:

```bash
--password
```

Do not place credentials directly in workflow files when a more secure
Entropy variable or secret-management mechanism is available.

---

### `insecure_skip_tls_verify`

Used by the `login` operation.

Type:

```text
boolean
```

Default:

```text
false
```

When enabled, the plugin adds:

```bash
--insecure-skip-tls-verify
```

to the `oc login` command.

Example:

```json
{
    "insecure_skip_tls_verify": true
}
```

This disables TLS certificate verification for the login operation and
should only be used when explicitly required.

---

### `namespace`

Used by the `project` operation.

When supplied, the plugin switches to the specified OpenShift project.

Example:

```json
{
    "operation": "project",
    "environment": "SIT",
    "namespace": "my-project"
}
```

This executes:

```bash
oc project my-project
```

When `namespace` is omitted, the plugin executes:

```bash
oc project
```

to determine the current project.

An explicitly supplied `namespace` must be a non-empty string.

---

### `resource`

Used by:

* `get`
* `apply`
* `replace`
* `delete`

The argument supports either:

```text
string
```

or:

```text
list[string]
```

#### Single resource

```json
{
    "resource": "/opt/yamls/deployment.yaml"
}
```

The plugin executes:

```bash
oc apply -f /opt/yamls/deployment.yaml
```

when the operation is `apply`.

#### Multiple resources

```json
{
    "resource": [
        "/opt/yamls/app-1.yaml",
        "/opt/yamls/app-2.yaml"
    ]
}
```

Each resource is executed independently.

An empty resource string is rejected.

An empty resource list is rejected.

Every item in a resource list must be a non-empty string.

---

### `arguments`

Additional command-line arguments.

Type:

```text
list[string]
```

Default:

```json
[]
```

Every value must be a string.

For resource operations, the values are appended after the resource
argument.

Example:

```json
{
    "operation": "get",
    "environment": "SIT",
    "resource": "/opt/yamls/resource.yaml",
    "arguments": [
        "-o",
        "yaml"
    ]
}
```

The resulting command is equivalent to:

```bash
oc get -f /opt/yamls/resource.yaml -o yaml
```

---

### `command`

Used by the `raw` operation.

Specifies the `oc` subcommand to execute.

The plugin automatically adds the `oc` executable prefix.

Example:

```json
{
    "operation": "raw",
    "environment": "SIT",
    "command": "get",
    "arguments": [
        "pods"
    ]
}
```

The resulting command is:

```bash
oc get pods
```

The `command` value:

* Must be a string.
* Must not be empty.
* Is stripped of surrounding whitespace.

The command must not include the `oc` executable prefix.

Use:

```text
get
```

not:

```text
oc get
```

---

## Workflow Configuration

The plugin is executed through an Entropy workflow step.

### Basic Configuration

```json
{
    "name": "Execute OpenShift Operation",
    "plugin": "oc.generic",
    "enabled": true,
    "on_failure": "abort",
    "tags": [],
    "arguments": {
        "operation": "whoami",
        "environment": "SIT"
    }
}
```

The plugin identifier is:

```text
oc.generic
```

---

## Complete Workflow Example

```json
{
    "name": "OpenShift Workflow",
    "version": "1.0.0",
    "description": "Execute OpenShift operations.",
    "variables": {
        "environment": "SIT"
    },
    "steps": [
        {
            "name": "OpenShift Login",
            "plugin": "oc.generic",
            "enabled": true,
            "on_failure": "abort",
            "tags": [
                "openshift",
                "login"
            ],
            "arguments": {
                "operation": "login",
                "environment": "${environment}",
                "api_url": "https://api.example.com:6443",
                "username": "admin",
                "password": "${password}"
            }
        },
        {
            "name": "Check User",
            "plugin": "oc.generic",
            "enabled": true,
            "on_failure": "abort",
            "tags": [
                "openshift"
            ],
            "arguments": {
                "operation": "whoami",
                "environment": "${environment}"
            }
        },
        {
            "name": "Apply Deployment",
            "plugin": "oc.generic",
            "enabled": true,
            "on_failure": "abort",
            "tags": [
                "openshift",
                "deployment"
            ],
            "arguments": {
                "operation": "apply",
                "environment": "${environment}",
                "resource": "/opt/yamls/deployment.yaml"
            }
        }
    ]
}
```

---

## Workflow Variables

Workflow variables can be used for plugin arguments.

Example:

```json
{
    "variables": {
        "environment": "SIT",
        "namespace": "application"
    }
}
```

They can then be referenced:

```json
{
    "arguments": {
        "operation": "project",
        "environment": "${environment}",
        "namespace": "${namespace}"
    }
}
```

Workflow variables are resolved by the workflow engine before the plugin
receives its runtime arguments.

---

## Vault Variables

The plugin itself does not directly retrieve Vault values.

Vault-backed variables may be resolved by the Entropy workflow engine
before plugin execution.

Example:

```json
{
    "variables": {
        "password": "${entv:openshift_password}"
    }
}
```

The value can then be supplied to the login operation:

```json
{
    "arguments": {
        "operation": "login",
        "environment": "SIT",
        "api_url": "https://api.example.com:6443",
        "username": "admin",
        "password": "${password}"
    }
}
```

Do not place actual passwords, tokens, credentials, private keys, or
other sensitive values in this document.

---

## Execution

### General Execution

The plugin performs the following high-level stages:

1. Display the OpenShift operation start message.
2. Enter the `oc-generic` activity.
3. Validate the requested operation.
4. Dispatch to the corresponding operation handler.
5. Resolve and validate the OpenShift environment.
6. Resolve the environment-specific kubeconfig.
7. Construct the required `oc` command.
8. Execute the command through the Entropy shell service.
9. Capture command output, error output, exit code, and duration.
10. Publish operation-specific outputs.
11. Return a `PluginResult`.

### Login

The login operation:

1. Validates the environment.
2. Reads the API URL.
3. Reads username.
4. Reads password.
5. Reads `insecure_skip_tls_verify`.
6. Creates the environment-specific kubeconfig directory.
7. Executes `oc login`.
8. Removes the kubeconfig if login fails.
9. Publishes login information on success.

### Logout

The logout operation:

1. Validates the environment.
2. Locates the environment kubeconfig.
3. Requires an existing kubeconfig.
4. Executes:

```bash
oc logout
```

5. Removes the kubeconfig after successful logout.

### Project

The project operation has two execution paths.

#### Display current project

When `namespace` is omitted:

```bash
oc project
```

is executed.

#### Switch project

When `namespace` is supplied:

```bash
oc project <namespace>
```

is executed.

### Whoami

The plugin executes:

```bash
oc whoami
```

and publishes the returned username.

### Resource Operations

The resource operations are:

```text
get
apply
replace
delete
```

For each resource:

```bash
oc <operation> -f <resource>
```

is executed.

Additional arguments are appended after the resource path.

### Raw

The raw operation constructs:

```text
oc + command + arguments
```

For example:

```json
{
    "operation": "raw",
    "environment": "SIT",
    "command": "get",
    "arguments": [
        "pods",
        "-o",
        "wide"
    ]
}
```

executes:

```bash
oc get pods -o wide
```

---

## Kubeconfig Isolation

The plugin does not use a shared OpenShift kubeconfig for different
environments.

The kubeconfig is stored below:

```text
<Entropy session directory>/.kube/<environment>/config
```

The exact root is determined by the Entropy runtime's
`session_directory`.

For example, conceptually:

```text
<session_directory>
└── .kube
    ├── SIT
    │   └── config
    ├── UAT
    │   └── config
    └── PROD
        └── config
```

Each `oc` command receives:

```text
KUBECONFIG=<environment-specific-config>
```

through its execution environment.

This prevents the plugin from relying on the user's default kubeconfig
for these operations.

---

## Outputs

The exact outputs depend on the operation.

### Login Outputs

Successful login produces:

| Output        | Type      | Description                                  |
| ------------- | --------- | -------------------------------------------- |
| `operation`   | `string`  | `login`.                                     |
| `environment` | `string`  | OpenShift environment.                       |
| `api_url`     | `string`  | OpenShift API URL.                           |
| `success`     | `boolean` | Indicates login success.                     |
| `kubeconfig`  | `string`  | Path to the environment-specific kubeconfig. |
| `exit_code`   | `integer` | `oc` exit code.                              |

Example:

```text
outputs:

    operation = "login"
    environment = "SIT"
    api_url = "https://api.example.com:6443"
    success = true
    kubeconfig = "<session_directory>/.kube/SIT/config"
    exit_code = 0
```

---

### Logout Outputs

Successful logout produces:

```text
operation
environment
success
exit_code
```

Example:

```text
outputs:

    operation = "logout"
    environment = "SIT"
    success = true
    exit_code = 0
```

---

### Project Outputs

When querying the current project:

```text
operation
environment
success
exit_code
stdout
```

When switching projects:

```text
operation
environment
namespace
success
exit_code
```

---

### Whoami Outputs

The `whoami` operation produces:

```text
operation
environment
username
success
exit_code
```

Example:

```text
outputs:

    operation = "whoami"
    environment = "SIT"
    username = "developer"
    success = true
    exit_code = 0
```

---

### Resource Operation Outputs

The `get`, `apply`, `replace`, and `delete` operations produce:

```text
operation
environment
resources
results
success
```

`resources` is a list of processed resource paths.

Each entry in `results` contains:

```text
resource
exit_code
success
stdout
stderr
duration
```

Example:

```text
outputs:

    operation = "apply"

    environment = "SIT"

    resources =
        [
            "/opt/yamls/app-1.yaml",
            "/opt/yamls/app-2.yaml"
        ]

    results =
        [
            {
                "resource": "/opt/yamls/app-1.yaml",
                "exit_code": 0,
                "success": true,
                "stdout": "...",
                "stderr": "",
                "duration": 0.14
            }
        ]

    success = true
```

---

### Raw Outputs

The `raw` operation produces:

```text
operation
environment
command
exit_code
success
stdout
stderr
duration
```

Example:

```text
outputs:

    operation = "raw"
    environment = "SIT"
    command = "oc get pods"
    exit_code = 0
    success = true
    stdout = "..."
    stderr = ""
    duration = 0.12
```

---

## Artifacts

The plugin does not intentionally create workflow artifacts.

The standard plugin metadata contains an artifact mapping based on
artifacts registered by the surrounding Entropy runtime.

When no artifacts are registered, the metadata is effectively:

```json
{
    "artifacts": {}
}
```

OpenShift command output is exposed through workflow outputs rather than
as plugin artifacts.

---

## Examples

### Example 1 --- OpenShift Login

```json
{
    "arguments": {
        "operation": "login",
        "environment": "SIT",
        "api_url": "https://api.example.com:6443",
        "username": "admin",
        "password": "${password}"
    }
}
```

Equivalent command:

```bash
oc login https://api.example.com:6443 \
    --username admin \
    --password <password>
```

The command uses the environment-specific kubeconfig.

---

### Example 2 --- Login with TLS Verification Disabled

```json
{
    "arguments": {
        "operation": "login",
        "environment": "SIT",
        "api_url": "https://api.example.com:6443",
        "username": "admin",
        "password": "${password}",
        "insecure_skip_tls_verify": true
    }
}
```

The additional option becomes:

```bash
--insecure-skip-tls-verify
```

---

### Example 3 --- Check Authenticated User

```json
{
    "arguments": {
        "operation": "whoami",
        "environment": "SIT"
    }
}
```

Equivalent command:

```bash
oc whoami
```

---

### Example 4 --- Display Current Project

```json
{
    "arguments": {
        "operation": "project",
        "environment": "SIT"
    }
}
```

Equivalent command:

```bash
oc project
```

---

### Example 5 --- Switch Project

```json
{
    "arguments": {
        "operation": "project",
        "environment": "SIT",
        "namespace": "application"
    }
}
```

Equivalent command:

```bash
oc project application
```

---

### Example 6 --- Get a Resource

```json
{
    "arguments": {
        "operation": "get",
        "environment": "SIT",
        "resource": "/opt/yamls/deployment.yaml"
    }
}
```

Equivalent command:

```bash
oc get -f /opt/yamls/deployment.yaml
```

---

### Example 7 --- Apply a Resource

```json
{
    "arguments": {
        "operation": "apply",
        "environment": "SIT",
        "resource": "/opt/yamls/deployment.yaml"
    }
}
```

Equivalent command:

```bash
oc apply -f /opt/yamls/deployment.yaml
```

---

### Example 8 --- Apply Multiple Resources

```json
{
    "arguments": {
        "operation": "apply",
        "environment": "SIT",
        "resource": [
            "/opt/yamls/app-1.yaml",
            "/opt/yamls/app-2.yaml"
        ]
    }
}
```

The plugin executes the resources independently:

```bash
oc apply -f /opt/yamls/app-1.yaml
oc apply -f /opt/yamls/app-2.yaml
```

If one fails, the other resources are still processed.

---

### Example 9 --- Replace Resources

```json
{
    "arguments": {
        "operation": "replace",
        "environment": "SIT",
        "resource": [
            "/opt/yamls/configmap.yaml",
            "/opt/yamls/secret.yaml"
        ]
    }
}
```

Equivalent commands:

```bash
oc replace -f /opt/yamls/configmap.yaml
oc replace -f /opt/yamls/secret.yaml
```

---

### Example 10 --- Delete a Resource

```json
{
    "arguments": {
        "operation": "delete",
        "environment": "SIT",
        "resource": "/opt/yamls/deployment.yaml"
    }
}
```

Equivalent command:

```bash
oc delete -f /opt/yamls/deployment.yaml
```

---

### Example 11 --- Additional Arguments

```json
{
    "arguments": {
        "operation": "get",
        "environment": "SIT",
        "resource": "/opt/yamls/deployment.yaml",
        "arguments": [
            "-o",
            "yaml"
        ]
    }
}
```

Equivalent command:

```bash
oc get -f /opt/yamls/deployment.yaml -o yaml
```

---

### Example 12 --- Raw OpenShift Command

```json
{
    "arguments": {
        "operation": "raw",
        "environment": "SIT",
        "command": "get",
        "arguments": [
            "pods",
            "-o",
            "wide"
        ]
    }
}
```

Equivalent command:

```bash
oc get pods -o wide
```

The `oc` prefix is added automatically.

---

### Example 13 --- Using Workflow Variables

```json
{
    "variables": {
        "environment": "SIT",
        "namespace": "application",
        "resource": "/opt/yamls/deployment.yaml"
    },
    "steps": [
        {
            "name": "Switch Project",
            "plugin": "oc.generic",
            "enabled": true,
            "on_failure": "abort",
            "tags": [],
            "arguments": {
                "operation": "project",
                "environment": "${environment}",
                "namespace": "${namespace}"
            }
        },
        {
            "name": "Apply Deployment",
            "plugin": "oc.generic",
            "enabled": true,
            "on_failure": "abort",
            "tags": [],
            "arguments": {
                "operation": "apply",
                "environment": "${environment}",
                "resource": "${resource}"
            }
        }
    ]
}
```

---

### Example 14 --- Using Vault Variables

```json
{
    "variables": {
        "password": "${entv:openshift_password}"
    },
    "steps": [
        {
            "name": "OpenShift Login",
            "plugin": "oc.generic",
            "enabled": true,
            "on_failure": "abort",
            "tags": [],
            "arguments": {
                "operation": "login",
                "environment": "SIT",
                "api_url": "https://api.example.com:6443",
                "username": "admin",
                "password": "${password}"
            }
        }
    ]
}
```

The workflow engine resolves the Vault-backed variable before the plugin
receives the argument.

---

## Validation

The plugin validates the following.

### Operation

`operation`:

* Must be supplied.
* Must be a string.
* Must not be empty.
* Must match a supported operation.

### Environment

`environment`:

* Must be supplied.
* Must be a string.
* Must not be empty.
* May contain only letters, numbers, `.`, `_`, and `-`.
* Must begin with a letter or number.

### Namespace

When supplied to `project`:

* Must be a string.
* Must not be empty.

### Resource

For resource operations, `resource` must be:

```text
string
```

or:

```text
list[string]
```

A string must not be empty.

A list must not be empty.

Every list element must be a non-empty string.

### Additional Arguments

`arguments`:

* Must be a list.
* Every value must be a string.

### Raw Command

For `raw`:

* `command` must be a string.
* `command` must not be empty.
* `arguments` must be a list of strings.

### Kubeconfig

Operations that require an existing session validate that the
environment-specific kubeconfig exists.

---

## Validation Errors

Examples include:

```text
Argument 'operation' must be specified.
```

```text
Unsupported OpenShift operation 'invalid'.
```

```text
Argument 'environment' must be a non-empty string.
```

```text
Argument 'environment' contains invalid characters.
Use only letters, numbers, '.', '_' and '-'.
```

```text
Argument 'namespace' must be a non-empty string.
```

```text
Argument 'resource' must be a non-empty string.
```

```text
Argument 'resource' must not be empty.
```

```text
All values in 'resource' must be non-empty strings.
```

```text
Argument 'resource' must be a string or a list of strings.
```

```text
Argument 'arguments' must be a list.
```

```text
All values in 'arguments' must be strings.
```

```text
Argument 'command' must be a non-empty string.
```

```text
No OpenShift session exists for environment 'SIT'.
Run the login operation first.
```

---

## Error Handling

The plugin catches `GenericPluginException` at the main execution
boundary and returns a failed `PluginResult`.

### OpenShift Command Failures

When an `oc` command returns a failure:

* The command result is recorded.
* Standard error is used as the primary error message where available.
* The operation returns `success=false`.
* The workflow can apply its configured failure policy.

### Multiple Resource Failures

Resource operations process each resource independently.

For example:

```json
{
    "resource": [
        "/opt/yamls/app-1.yaml",
        "/opt/yamls/app-2.yaml"
    ]
}
```

results in separate `oc` executions.

If `app-1.yaml` succeeds and `app-2.yaml` fails:

* `app-1.yaml` remains successfully processed.
* `app-2.yaml` is recorded as failed.
* The overall operation returns failure.
* No automatic rollback is performed.

### Login Failure

If login fails, the plugin attempts to remove the newly created
environment-specific kubeconfig.

If kubeconfig cleanup itself fails, the cleanup error is logged as a
warning and the original login failure is returned.

### Missing `oc`

If the `oc` executable is unavailable, the plugin returns:

```text
OpenShift CLI 'oc' was not found. Please install the OpenShift CLI
and ensure it is available in PATH.
```

### Operating System Errors

Operating-system errors while executing `oc` are converted into plugin
errors.

---

## Security

The plugin performs OpenShift authentication and therefore handles
sensitive credentials.

### Password Handling

The login operation passes the supplied password to:

```bash
oc login
```

using:

```bash
--password
```

Workflows should avoid hard-coding passwords.

Prefer Entropy's variable and secret-management mechanisms where
available.

### Kubeconfig Isolation

Each environment has its own kubeconfig:

```text
<session_directory>/.kube/<environment>/config
```

This prevents the plugin from intentionally sharing one kubeconfig
between environments.

### Environment Isolation

The environment name forms part of the kubeconfig path.

Only validated environment names are accepted to prevent unsupported
path characters.

### TLS Verification

`insecure_skip_tls_verify` defaults to `false`.

When enabled, TLS verification is disabled for `oc login`.

This should be used only when necessary.

### Logging

The plugin logs executed OpenShift commands at debug level.

The implementation intentionally does not write credentials to the log
as part of `_log_result()`.

However, users should still avoid putting sensitive values into
arbitrary command arguments or workflow logging.

### Credentials

The plugin does not implement a separate credential store.

Credentials are supplied to the login operation by workflow arguments
and passed to `oc`.

---

## Filesystem

| Path                                             | Purpose                                           |
| ------------------------------------------------ | ------------------------------------------------- |
| `<session_directory>/.kube/<environment>/`       | Environment-specific OpenShift session directory. |
| `<session_directory>/.kube/<environment>/config` | Environment-specific kubeconfig.                  |
| `resource`                                       | User-supplied local resource YAML path(s).        |

### Kubeconfig Directory

The directory is created automatically during login.

Conceptually:

```text
<session_directory>/.kube/<environment>/
```

is created with parent directories when required.

### Kubeconfig File

The kubeconfig is:

* Created by successful/attempted login setup.
* Used for subsequent OpenShift commands.
* Removed during logout after successful `oc logout`.
* Removed when login fails, subject to cleanup success.

### Resource Files

Resource files supplied through `resource` are read by the external
`oc` command.

The plugin itself does not create, modify, or delete these resource
files.

---

## External Commands

The plugin executes the OpenShift CLI:

```bash
oc
```

All commands are constructed by the plugin and executed through the
Entropy shell service.

### Login

```bash
oc login <api_url> \
    --username <username> \
    --password <password>
```

When TLS verification is disabled:

```bash
oc login <api_url> \
    --username <username> \
    --password <password> \
    --insecure-skip-tls-verify
```

### Logout

```bash
oc logout
```

### Current Project

```bash
oc project
```

### Switch Project

```bash
oc project <namespace>
```

### Whoami

```bash
oc whoami
```

### Get

```bash
oc get -f <resource>
```

### Apply

```bash
oc apply -f <resource>
```

### Replace

```bash
oc replace -f <resource>
```

### Delete

```bash
oc delete -f <resource>
```

### Raw

```bash
oc <command> <arguments...>
```

The `raw` operation does not prepend another `oc` value because the
plugin itself adds the executable prefix.

---

## External Services

### OpenShift

The plugin communicates with an OpenShift cluster through the `oc`
command-line client.

Purpose:

* Authentication.
* Project management.
* Resource retrieval.
* Resource application.
* Resource replacement.
* Resource deletion.
* Other commands explicitly supplied through `raw`.

### Authentication

OpenShift authentication is performed through:

```bash
oc login
```

The resulting kubeconfig is used by later operations.

### Connectivity

Network connectivity to the configured OpenShift API server is required
for cluster operations.

---

## Side Effects

The plugin can produce the following side effects.

### Login

* Creates an environment-specific kubeconfig directory.
* Creates or updates the environment-specific kubeconfig through
  `oc login`.
* Establishes an OpenShift session.

### Logout

* Logs out through `oc`.
* Removes the environment-specific kubeconfig.

### Project

When a namespace is supplied:

* Changes the current OpenShift project associated with the session.

### Apply

May:

* Create resources.
* Update resources.
* Modify cluster state.

The exact effect is determined by OpenShift's `oc apply` behavior.

### Replace

May modify existing OpenShift resources.

### Delete

Deletes the specified OpenShift resources.

### Get

Reads information from OpenShift and does not intentionally modify
cluster state.

### Whoami

Reads the authenticated OpenShift identity.

### Raw

The side effects depend entirely on the supplied `oc` command and
arguments.

---

## Performance

Performance depends primarily on:

* OpenShift API response time.
* Network latency.
* Number of resources.
* Resource size.
* OpenShift cluster load.
* Execution time of the `oc` command.

Multiple resources are processed sequentially.

Each resource results in a separate `oc` invocation.

The plugin does not define its own retry or timeout mechanism in the
provided implementation.

---

## Limitations

### OpenShift CLI Dependency

The `oc` executable must be installed and available in `PATH`.

### OpenShift Dependency

Operations requiring cluster access depend on OpenShift connectivity.

### Session Requirement

Operations other than login require an existing environment-specific
kubeconfig.

### No Automatic Login

The plugin does not automatically log in when a kubeconfig is missing.

The workflow must explicitly execute:

```text
operation = login
```

first.

### No Automatic Project Selection

The plugin does not automatically select a project unless the workflow
explicitly executes the `project` operation with a namespace.

### No Retry

Failed `oc` commands are not automatically retried.

### No Rollback

The plugin does not roll back successfully executed resources if a
subsequent resource fails.

### Resource Operations

Resource operations accept resource paths, not arbitrary structured
resource objects.

### Raw Operation

The `raw` operation exposes generic `oc` command execution and should
therefore be used carefully.

---

## Troubleshooting

### Problem

```text
OpenShift CLI 'oc' was not found.
```

**Cause**

The OpenShift CLI is not installed or is not available in `PATH`.

**Solution**

Install the OpenShift CLI and verify:

```bash
oc version
```

is available from the same environment in which Entropy runs.

---

### Problem

```text
No OpenShift session exists for environment 'SIT'.
Run the login operation first.
```

**Cause**

The environment-specific kubeconfig does not exist.

**Solution**

Run the login operation first:

```json
{
    "operation": "login",
    "environment": "SIT",
    "api_url": "https://api.example.com:6443",
    "username": "admin",
    "password": "${password}"
}
```

Then execute the required OpenShift operation.

---

### Problem

```text
Argument 'environment' contains invalid characters.
```

**Cause**

The environment contains characters outside the supported set.

Allowed characters:

```text
A-Z
a-z
0-9
.
_
-
```

**Solution**

Use an environment name such as:

```text
SIT
UAT
PROD
prod-01
cluster_01
```

---

### Problem

```text
Argument 'resource' must not be empty.
```

**Cause**

The resource operation received an empty list.

**Solution**

Provide at least one resource:

```json
{
    "resource": [
        "/opt/yamls/deployment.yaml"
    ]
}
```

---

### Problem

```text
Argument 'resource' must be a string or a list of strings.
```

**Cause**

The `resource` argument is neither a string nor a list of strings.

**Solution**

Use either:

```json
{
    "resource": "/opt/yamls/deployment.yaml"
}
```

or:

```json
{
    "resource": [
        "/opt/yamls/app-1.yaml",
        "/opt/yamls/app-2.yaml"
    ]
}
```

---

### Problem

An OpenShift operation fails with an `oc` error.

**Cause**

The command was executed successfully from the plugin's perspective,
but OpenShift returned a non-zero exit code.

Possible causes include:

* Authentication failure.
* Authorization failure.
* Invalid resource.
* Missing resource.
* Invalid project.
* Cluster connectivity failure.
* Invalid command arguments.

**Solution**

Inspect the `stderr` value in the operation output.

For resource operations, inspect the corresponding entry under:

```text
outputs.results
```

---

### Problem

Login fails and a session does not remain available.

**Cause**

The plugin intentionally removes the environment-specific kubeconfig
when login fails.

**Solution**

Correct the login configuration or credentials and run the login
operation again.

---

### Problem

A raw command fails.

**Cause**

The supplied `command` or `arguments` may not form a valid `oc`
command.

**Solution**

Remember that the plugin automatically adds `oc`.

Use:

```json
{
    "command": "get",
    "arguments": [
        "pods"
    ]
}
```

not:

```json
{
    "command": "oc get",
    "arguments": [
        "pods"
    ]
}
```

---

## Notes

### Recommended Workflow Pattern

For operations that require authentication, use a workflow sequence such
as:

```text
OpenShift Login
       |
       v
Project Selection
       |
       v
OpenShift Operation
```

For example:

```text
oc.generic (login)
       |
       v
oc.generic (project)
       |
       v
oc.generic (apply)
```

### Deployment Workflow Integration

A deployment workflow may use `oc.generic` after another plugin has
modified Deployment YAML files.

For example:

```text
BuildReleaseContext
       |
       v
DeploymentYAMLUpdate
       |
       v
oc.generic (apply)
```

The Deployment update plugin modifies the local YAML repository, while
`oc.generic` performs the actual OpenShift operation.

### Resource List Processing

When a list of resources is supplied, each resource is executed
independently.

This allows a workflow to process multiple YAML files through one
plugin step.

However, the operation is not transactional.

### Environment-Specific Sessions

Always use a consistent environment value for all steps that belong to
the same OpenShift session.

For example:

```text
login   -> SIT
project -> SIT
apply   -> SIT
```

Using different environment names creates separate kubeconfig
locations and therefore separate sessions.

### Raw Operation

The `raw` operation should be reserved for OpenShift commands that are
not covered by the explicit operation handlers.

The plugin does not restrict the raw command to the named supported
operations after dispatching to `raw`.

Therefore, the workflow author is responsible for ensuring that the
supplied command and arguments are appropriate.

---

## Changelog

### 1.0.0

* Initial plugin release.
* Added OpenShift login support.
* Added OpenShift logout support.
* Added OpenShift project management.
* Added authenticated user lookup through `whoami`.
* Added generic `get` operation.
* Added generic `apply` operation.
* Added generic `replace` operation.
* Added generic `delete` operation.
* Added raw OpenShift command execution.
* Added environment-specific kubeconfig isolation.
* Added support for single resource paths.
* Added support for multiple resource paths.
* Added independent processing of multiple resources.
* Added command output and execution metadata.
* Added OpenShift command error handling.
* Added environment name validation.
* Added additional command argument validation.

```
```
