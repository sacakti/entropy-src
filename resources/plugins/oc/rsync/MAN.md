# oc_rsync

------------------------------------------------------------------------

## Overview

`oc.rsync` is an Entropy plugin for transferring local files or
directories into a running OpenShift pod using `oc rsync`.

The plugin consumes an `rsync_plan` generated or supplied by the
workflow. Each plan item identifies:

- The Deployment whose pod should receive the files.
- The destination path inside the pod.
- The local source path to transfer.

For every plan item, the plugin:

1. Resolves the Deployment's selector.
2. Finds pods matching that selector.
3. Selects a `Running` and `Ready` pod.
4. Executes `oc rsync` from the local source to the selected pod.
5. Publishes the result of each transfer.

### Important Behavior

The plugin deliberately does **not** perform OpenShift authentication
or project selection.

An existing environment-specific OpenShift session is required. The
session must already have been established by another workflow step,
such as `oc.generic` login.

The plugin uses the existing environment-specific kubeconfig:

```text
<session_directory>/.kube/<environment>/config
```

The plugin does not create, modify, or remove OpenShift sessions.

When multiple rsync operations are supplied, each operation is executed
independently. The plugin does not provide transactional rollback.

------------------------------------------------------------------------

## Requirements

The plugin requires:

- Entropy runtime.
- OpenShift CLI (`oc`) installed and available in `PATH`.
- An existing OpenShift session for the specified environment.
- Network connectivity to the OpenShift cluster.
- Permission to inspect the relevant Deployment and Pods.
- Permission to perform `oc rsync` into the selected pod.
- A valid local source path for every rsync plan item.
- A running and Ready pod belonging to each referenced Deployment.

### Required OpenShift CLI

The following command must be available:

```bash
oc
```

The plugin uses:

```bash
oc get deployment <deployment> -o json
oc get pods -l <selector> -o json
oc rsync <source> <pod>:<target>
```

### Authentication

Authentication is intentionally outside this plugin.

Before using `oc.rsync`, the workflow must establish an OpenShift
session for the same environment.

------------------------------------------------------------------------

## Arguments

| Argument | Required | Type | Default | Description |
|----------|----------|------|---------|-------------|
| `environment` | Yes | `string` | --- | OpenShift environment/session name. |
| `rsync_plan` | Yes | `list[object]` | --- | List of rsync operations to execute. |

Each `rsync_plan` item must contain:

| Field | Required | Type | Description |
|-------|----------|------|-------------|
| `deployment` | Yes | `string` | OpenShift Deployment name used to locate a pod. |
| `target` | Yes | `string` | Destination path inside the selected pod. |
| `source` | Yes | `string` | Local source file or directory to transfer. |

------------------------------------------------------------------------

## Argument Details

### `environment`

Specifies the OpenShift environment whose existing session should be
used.

Example:

```json
{
    "environment": "SIT"
}
```

The value:

- Must be a string.
- Must not be empty.
- Is stripped of surrounding whitespace.

The value is used to locate:

```text
<session_directory>/.kube/SIT/config
```

The plugin does not create the kubeconfig if it does not exist.

------------------------------------------------------------------------

### `rsync_plan`

Specifies the list of file-transfer operations.

Example:

```json
{
    "rsync_plan": [
        {
            "deployment": "app-1",
            "target": "/opt/app/jrxml",
            "source": "/opt/releases/common_path/jrxml"
        }
    ]
}
```

The value must be a list.

An empty list is valid. When the list is empty, the plugin completes
successfully without executing any OpenShift commands.

Each item must be an object containing non-empty string values for:

- `deployment`
- `target`
- `source`

The local `source` path must exist.

------------------------------------------------------------------------

### `rsync_plan.deployment`

Specifies the Deployment used to locate the destination pod.

The plugin does **not** assume that the Deployment name is the pod
name.

Instead, it:

1. Retrieves the Deployment.
2. Reads `spec.selector.matchLabels`.
3. Converts the labels into an OpenShift label selector.
4. Retrieves matching pods.
5. Selects one pod that is both `Running` and `Ready`.

Example:

```json
{
    "deployment": "trade-workitem-service"
}
```

------------------------------------------------------------------------

### `rsync_plan.target`

Specifies the destination path inside the selected pod.

Example:

```json
{
    "target": "/opt/app/jrxml"
}
```

The destination passed to `oc rsync` is constructed as:

```text
<pod>:<target>
```

For example:

```text
trade-workitem-service-abc123:/opt/app/jrxml
```

------------------------------------------------------------------------

### `rsync_plan.source`

Specifies the local source file or directory.

Example:

```json
{
    "source": "/opt/releases/common_path/jrxml"
}
```

The source must exist before execution.

The plugin validates source existence using the local filesystem.

------------------------------------------------------------------------

## Workflow Configuration

The plugin is executed through an Entropy workflow step.

### Basic Configuration

```json
{
    "name": "Rsync Common Paths",
    "plugin": "oc.rsync",
    "enabled": true,
    "on_failure": "abort",
    "tags": [],
    "arguments": {
        "environment": "SIT",
        "rsync_plan": [
            {
                "deployment": "app-1",
                "target": "/opt/app/jrxml",
                "source": "/opt/releases/common_path/jrxml"
            }
        ]
    }
}
```

Authentication and project selection should be performed separately.

For example:

```text
oc.generic (login)
        |
        v
oc.generic (project)
        |
        v
oc.rsync
```

------------------------------------------------------------------------

## Complete Workflow Example

```json
{
    "name": "OpenShift Rsync Workflow",
    "version": "1.0.0",
    "description": "Transfer common files into running application pods.",
    "variables": {
        "environment": "SIT",
        "source": "/opt/releases/common_path/jrxml"
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
                "username": "${username}",
                "password": "${password}"
            }
        },
        {
            "name": "Select Project",
            "plugin": "oc.generic",
            "enabled": true,
            "on_failure": "abort",
            "tags": [
                "openshift"
            ],
            "arguments": {
                "operation": "project",
                "environment": "${environment}",
                "namespace": "application"
            }
        },
        {
            "name": "Rsync Common Paths",
            "plugin": "oc.rsync",
            "enabled": true,
            "on_failure": "abort",
            "tags": [
                "openshift",
                "rsync"
            ],
            "arguments": {
                "environment": "${environment}",
                "rsync_plan": [
                    {
                        "deployment": "app-1",
                        "target": "/opt/app/jrxml",
                        "source": "${source}"
                    }
                ]
            }
        }
    ]
}
```

------------------------------------------------------------------------

## Workflow Variables

Workflow variables can be used for values supplied to plugin arguments.

Example:

```json
{
    "variables": {
        "environment": "SIT",
        "source": "/opt/releases/common_path/jrxml"
    }
}
```

They can be referenced from the plugin arguments:

```json
{
    "arguments": {
        "environment": "${environment}",
        "rsync_plan": [
            {
                "deployment": "app-1",
                "target": "/opt/app/jrxml",
                "source": "${source}"
            }
        ]
    }
}
```

Workflow variables are resolved by the workflow engine before the plugin
receives its runtime arguments.

------------------------------------------------------------------------

## Vault Variables

The plugin does not directly access Vault.

Vault-backed values may be resolved by the Entropy workflow engine before
the plugin receives its arguments.

For example, credentials used by a separate `oc.generic` login step may
be supplied through Vault-backed workflow variables:

```json
{
    "variables": {
        "username": "${entv:openshift_username}",
        "password": "${entv:openshift_password}"
    }
}
```

The `oc.rsync` plugin itself does not require username or password
arguments.

Do not place actual passwords, tokens, credentials, private keys, or
other sensitive values in this document.

------------------------------------------------------------------------

## Execution

The plugin executes the rsync plan in the following stages.

1. Validate `environment`.
2. Validate `rsync_plan`.
3. Return immediately if the plan is empty.
4. Resolve the existing environment-specific kubeconfig.
5. Process each rsync plan item.
6. Retrieve the referenced Deployment as JSON.
7. Read `spec.selector.matchLabels`.
8. Build an OpenShift label selector.
9. Retrieve matching Pods as JSON.
10. Filter Pods to those with `status.phase == "Running"`.
11. Filter Pods to those with a `Ready` condition whose status is
    `True`.
12. Sort eligible pod names.
13. Select the first eligible pod.
14. Build the destination as `<pod>:<target>`.
15. Execute `oc rsync <source> <pod>:<target>`.
16. Record the command result.
17. Continue processing the remaining plan items.
18. Publish aggregate outputs.
19. Return a successful or failed `PluginResult`.

### Empty Plan

An empty `rsync_plan` is valid.

The plugin returns:

```text
success = true
resources_processed = 0
resources_succeeded = 0
resources_failed = 0
changes = 0
results = []
```

No OpenShift command is executed.

------------------------------------------------------------------------

## Pod Selection

The plugin deliberately resolves a pod from the Deployment rather than
assuming the Deployment name is also a pod name.

For a Deployment such as:

```yaml
spec:
  selector:
    matchLabels:
      app: app-1
```

the plugin constructs:

```text
app=app-1
```

and executes:

```bash
oc get pods -l app=app-1 -o json
```

Only pods satisfying both conditions are eligible:

```text
status.phase == "Running"
```

and:

```text
status.conditions:
  type == "Ready"
  status == "True"
```

If multiple pods are eligible, their names are sorted and the first
name is selected.

------------------------------------------------------------------------

## Outputs

The plugin publishes aggregate execution information.

| Output | Type | Description |
|--------|------|-------------|
| `success` | `boolean` | Whether all rsync operations succeeded. |
| `environment` | `string` | OpenShift environment used. |
| `resources_processed` | `integer` | Number of rsync plan items processed. |
| `resources_succeeded` | `integer` | Number of successful rsync operations. |
| `resources_failed` | `integer` | Number of failed rsync operations. |
| `changes` | `integer` | Number of successful rsync operations. |
| `results` | `list[object]` | Detailed result for each rsync operation. |

### Result Fields

Each item in `results` contains:

| Field | Type | Description |
|-------|------|-------------|
| `deployment` | `string` | Deployment used for pod resolution. |
| `pod` | `string` | Selected pod. |
| `source` | `string` | Local source path. |
| `target` | `string` | Pod destination path. |
| `destination` | `string` | Combined `<pod>:<target>` destination. |
| `success` | `boolean` | Whether the rsync command succeeded. |
| `exit_code` | `integer` | `oc` exit code. |
| `stdout` | `string` | Standard output from `oc rsync`. |
| `stderr` | `string` | Standard error from `oc rsync`. |
| `duration` | `number` | Command execution duration. |

### Example

```text
outputs:

    success = true
    environment = "SIT"
    resources_processed = 1
    resources_succeeded = 1
    resources_failed = 0
    changes = 1

    results =
        [
            {
                "deployment": "app-1",
                "pod": "app-1-7d8f9c6d5b-abcde",
                "source": "/opt/releases/common_path/jrxml",
                "target": "/opt/app/jrxml",
                "destination": "app-1-7d8f9c6d5b-abcde:/opt/app/jrxml",
                "success": true,
                "exit_code": 0,
                "stdout": "...",
                "stderr": "",
                "duration": 0.52
            }
        ]
```

These outputs can be consumed by later workflow steps.

------------------------------------------------------------------------

## Artifacts

The plugin does not intentionally create workflow artifacts.

The returned metadata contains the artifacts registered by the Entropy
runtime.

When no artifacts are registered:

```json
{
    "artifacts": {}
}
```

Rsync output is exposed through workflow outputs rather than plugin
artifacts.

------------------------------------------------------------------------

## Examples

### Example 1 --- Basic Usage

```json
{
    "arguments": {
        "environment": "SIT",
        "rsync_plan": [
            {
                "deployment": "app-1",
                "target": "/opt/app/jrxml",
                "source": "/opt/releases/common_path/jrxml"
            }
        ]
    }
}
```

The plugin resolves a Running and Ready pod belonging to `app-1` and
executes:

```bash
oc rsync /opt/releases/common_path/jrxml <pod>:/opt/app/jrxml
```

------------------------------------------------------------------------

### Example 2 --- Multiple Deployments

```json
{
    "arguments": {
        "environment": "SIT",
        "rsync_plan": [
            {
                "deployment": "app-1",
                "target": "/opt/app/jrxml",
                "source": "/opt/releases/common_path/jrxml"
            },
            {
                "deployment": "app-2",
                "target": "/opt/app/reports",
                "source": "/opt/releases/common_path/reports"
            }
        ]
    }
}
```

Each operation is processed independently.

------------------------------------------------------------------------

### Example 3 --- Using Workflow Variables

```json
{
    "variables": {
        "environment": "SIT",
        "source": "/opt/releases/common_path/jrxml",
        "target": "/opt/app/jrxml"
    },
    "steps": [
        {
            "name": "Rsync Common Path",
            "plugin": "oc.rsync",
            "enabled": true,
            "on_failure": "abort",
            "tags": [],
            "arguments": {
                "environment": "${environment}",
                "rsync_plan": [
                    {
                        "deployment": "app-1",
                        "target": "${target}",
                        "source": "${source}"
                    }
                ]
            }
        }
    ]
}
```

------------------------------------------------------------------------

### Example 4 --- Context-Generated Rsync Plan

The plugin can consume an rsync plan produced by an earlier workflow
step.

For example, if a context-building step produces:

```json
{
    "common_paths": [
        {
            "deployment": "app-1",
            "target": "/opt/app/jrxml",
            "source": "/opt/releases/common_path/jrxml"
        }
    ]
}
```

the plan can be passed to the plugin:

```json
{
    "name": "Rsync Common Paths",
    "plugin": "oc.rsync",
    "enabled": true,
    "on_failure": "abort",
    "arguments": {
        "environment": "SIT",
        "rsync_plan": "${steps.BuildReleaseContext.outputs.common_paths}"
    }
}
```

This is the intended integration pattern when another plugin generates
the rsync execution plan.

------------------------------------------------------------------------

### Example 5 --- Empty Plan

```json
{
    "arguments": {
        "environment": "SIT",
        "rsync_plan": []
    }
}
```

The plugin succeeds without executing `oc`.

------------------------------------------------------------------------

## Validation

The plugin validates:

### `environment`

- Must be a string.
- Must not be empty.

### `rsync_plan`

- Must be a list.
- May be empty.
- Every item must be an object.
- Every item must contain a non-empty `deployment`.
- Every item must contain a non-empty `target`.
- Every item must contain a non-empty `source`.
- Every local source path must exist.

### Existing OpenShift Session

The environment-specific kubeconfig must exist:

```text
<session_directory>/.kube/<environment>/config
```

The plugin does not create this file.

### Deployment

The referenced Deployment must provide:

```text
spec.selector.matchLabels
```

and `matchLabels` must be a non-empty object.

### Deployment Selector

Every selector key must be a non-empty string.

Every selector value must be a non-empty string.

### Pod

At least one matching pod must satisfy:

```text
status.phase == "Running"
```

and contain:

```text
condition.type == "Ready"
condition.status == "True"
```

------------------------------------------------------------------------

## Validation Errors

Examples include:

```text
Argument 'environment' must be a non-empty string.
```

```text
Argument 'rsync_plan' must be a list.
```

```text
Rsync plan item 1 must be an object.
```

```text
Rsync plan item 1 must contain a non-empty 'deployment'.
```

```text
Rsync plan item 1 must contain a non-empty 'target'.
```

```text
Rsync plan item 1 must contain a non-empty 'source'.
```

```text
Rsync source '/opt/releases/common_path/jrxml' does not exist.
```

```text
No OpenShift session exists for environment 'SIT'.
Run the login operation first.
```

```text
Deployment/app-1 does not contain a valid spec.
```

```text
Deployment/app-1 does not contain a valid selector.
```

```text
Deployment/app-1 does not contain spec.selector.matchLabels.
```

```text
Deployment selector contains an invalid label key.
```

```text
Deployment selector label 'app' must have a non-empty value.
```

```text
Deployment selector cannot be empty.
```

```text
Unable to read pods for Deployment/app-1.
```

```text
No Running and Ready pods found for Deployment/app-1.
```

------------------------------------------------------------------------

## Error Handling

The plugin converts `RsyncPluginException` failures into a failed
`PluginResult`.

### Source Validation Failure

If a local source does not exist, execution fails before the rsync
operation is started.

### Missing OpenShift Session

If the environment-specific kubeconfig does not exist, execution
fails with:

```text
No OpenShift session exists for environment '<environment>'.
Run the login operation first.
```

### OpenShift Query Failure

If retrieving the Deployment or Pods fails, the plugin raises an error
and does not perform the corresponding rsync operation.

### Invalid JSON

Deployment and Pod queries must return valid JSON objects.

Invalid or unexpected JSON causes the operation to fail.

### No Ready Pod

If no matching pod is both Running and Ready, the operation fails.

No rsync command is attempted for that deployment.

### Rsync Command Failure

When `oc rsync` returns a failure:

- The command result is recorded.
- The operation is marked unsuccessful.
- The plugin continues with subsequent plan items.
- The failed operation is included in `results`.
- The overall plugin result is unsuccessful.

### Partial Operation Behavior

The plugin is not transactional.

For example, with:

```text
app-1 -> success
app-2 -> failure
app-3 -> success
```

the successful transfers remain completed.

The plugin does not roll them back.

The final result reports:

```text
success = false
resources_processed = 3
resources_succeeded = 2
resources_failed = 1
changes = 2
```

### Workflow Failure Policy

The workflow's `on_failure` behavior determines what happens after the
plugin returns a failure.

For example:

```json
{
    "on_failure": "abort"
}
```

causes the workflow to abort according to the workflow engine's failure
handling.

------------------------------------------------------------------------

## Security

### Authentication

The plugin does not authenticate to OpenShift.

It requires an existing environment-specific OpenShift session.

Authentication should be performed by a separate workflow step.

### Kubeconfig

The plugin reads the existing environment-specific kubeconfig:

```text
<session_directory>/.kube/<environment>/config
```

It does not create or modify the session.

### Credentials

No username or password arguments are accepted by this plugin.

Credentials should therefore be handled by the separate authentication
step.

### Logging

The plugin logs OpenShift command activity.

The plugin does not intentionally log authentication credentials because
authentication is outside this plugin.

Command output and error output may be logged as part of execution.

Users should avoid placing sensitive information in paths or other
values that may appear in command output.

### File Transfer

The plugin transfers the specified local source into a pod.

Users should ensure that the source contains only data that is
appropriate for the destination environment.

------------------------------------------------------------------------

## Filesystem

| Path | Purpose |
|------|---------|
| `<session_directory>/.kube/<environment>/config` | Existing OpenShift kubeconfig used for the environment. |
| `rsync_plan[].source` | Local file or directory transferred to the pod. |

### Kubeconfig

The kubeconfig:

- Must already exist.
- Is read by the OpenShift CLI.
- Is not created by this plugin.
- Is not modified by this plugin.
- Is not removed by this plugin.

### Source

The source:

- Must exist before execution.
- May represent a file or directory supported by `oc rsync`.
- Is transferred to the selected pod.

The plugin does not create or remove the source path.

------------------------------------------------------------------------

## External Commands

The plugin executes the OpenShift CLI.

### Deployment Lookup

For each plan item:

```bash
oc get deployment <deployment> -o json
```

Purpose:

- Retrieve the Deployment.
- Read its selector.

### Pod Lookup

The plugin converts Deployment `spec.selector.matchLabels` into a
comma-separated label selector.

Example:

```text
app=app-1,component=backend
```

It then executes:

```bash
oc get pods -l app=app-1,component=backend -o json
```

Purpose:

- Find pods belonging to the Deployment.
- Identify Running and Ready pods.

### Rsync

The transfer command is:

```bash
oc rsync <source> <pod>:<target>
```

Example:

```bash
oc rsync /opt/releases/common_path/jrxml \
    app-1-7d8f9c6d5b-abcde:/opt/app/jrxml
```

The command uses the environment-specific kubeconfig through:

```text
KUBECONFIG=<session_directory>/.kube/<environment>/config
```

------------------------------------------------------------------------

## External Services

### OpenShift

The plugin communicates with an OpenShift cluster through the `oc`
command-line client.

OpenShift is used for:

- Deployment lookup.
- Pod lookup.
- Pod readiness detection.
- File transfer into pods.

### Authentication Service

Authentication is not performed by this plugin.

An existing OpenShift session is required.

------------------------------------------------------------------------

## Side Effects

The plugin can produce the following side effects:

- Read Deployment information from OpenShift.
- Read Pod information from OpenShift.
- Transfer local files or directories into running pods.
- Modify files inside destination pods through `oc rsync`.

The plugin does not:

- Log in to OpenShift.
- Log out of OpenShift.
- Select an OpenShift project.
- Create kubeconfigs.
- Remove kubeconfigs.
- Modify Deployments.
- Modify Pod specifications.
- Delete Pods.

------------------------------------------------------------------------

## Performance

Performance depends on:

- Number of rsync plan items.
- Size of transferred files.
- Number of files in transferred directories.
- Network latency.
- OpenShift API response time.
- Pod availability.
- Cluster performance.
- `oc rsync` transfer performance.

For every plan item, the plugin performs:

1. One Deployment lookup.
2. One Pod lookup.
3. One rsync operation.

Operations are executed sequentially.

Large directories or files may require significant transfer time.

The plugin does not define an explicit retry or timeout mechanism in the
provided implementation.

------------------------------------------------------------------------

## Limitations

- Requires the OpenShift CLI.
- Requires an existing OpenShift session.
- Does not perform authentication.
- Does not perform project selection.
- Requires `spec.selector.matchLabels`.
- Requires at least one matching Running and Ready pod.
- Selects only one pod per Deployment.
- When multiple eligible pods exist, the lexicographically first pod
  name is selected.
- Does not provide transactional behavior.
- Does not roll back successful transfers after later failures.
- Processes plan items sequentially.
- Does not automatically retry failed commands.
- Source validation uses the local filesystem.
- The plugin relies on `oc rsync` for the actual transfer behavior.

------------------------------------------------------------------------

## Troubleshooting

### Problem

```text
No OpenShift session exists for environment 'SIT'.
Run the login operation first.
```

**Cause**

The environment-specific kubeconfig does not exist.

**Solution**

Run an OpenShift login operation for the same environment before
executing `oc.rsync`.

For example:

```text
oc.generic
    operation = login
    environment = SIT
```

Then execute:

```text
oc.rsync
    environment = SIT
```

------------------------------------------------------------------------

### Problem

```text
Rsync source '/opt/releases/common_path/jrxml' does not exist.
```

**Cause**

The local source path does not exist.

**Solution**

Verify the source path:

```bash
ls -ld /opt/releases/common_path/jrxml
```

Correct the workflow variable or generated rsync plan.

------------------------------------------------------------------------

### Problem

```text
Deployment/app-1 does not contain spec.selector.matchLabels.
```

**Cause**

The Deployment does not contain a usable `spec.selector.matchLabels`
mapping.

**Solution**

Ensure the Deployment contains a selector such as:

```yaml
spec:
  selector:
    matchLabels:
      app: app-1
```

------------------------------------------------------------------------

### Problem

```text
No Running and Ready pods found for Deployment/app-1.
```

**Cause**

No pod matching the Deployment selector is simultaneously:

```text
Running
```

and:

```text
Ready=True
```

**Solution**

Inspect the Deployment and Pods:

```bash
oc get deployment app-1 -o yaml
oc get pods -l app=app-1
```

Wait for a suitable pod to become Running and Ready, or correct the
Deployment selector if it is incorrect.

------------------------------------------------------------------------

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

is available from the environment running Entropy.

------------------------------------------------------------------------

### Problem

```text
OpenShift command failed: ...
```

**Cause**

An OpenShift lookup command returned a non-zero exit code.

Possible causes include:

- Invalid or expired session.
- Insufficient permissions.
- Incorrect project.
- Deployment does not exist.
- Pod lookup failure.
- OpenShift connectivity failure.

**Solution**

Inspect the reported OpenShift error and verify the existing session,
project, Deployment, and permissions.

------------------------------------------------------------------------

### Problem

`oc rsync` fails after a pod is successfully selected.

**Cause**

The selected pod was available, but the transfer command failed.

Possible causes include:

- Invalid destination path.
- Insufficient permissions inside the container.
- Source/target incompatibility.
- Pod state changed during transfer.
- OpenShift connectivity problems.
- `oc rsync` limitations.

**Solution**

Inspect the corresponding `results` entry:

```text
outputs.results
```

Pay particular attention to:

```text
success
exit_code
stdout
stderr
duration
```

------------------------------------------------------------------------

### Problem

The expected pod is not selected when multiple pods exist.

**Cause**

The plugin selects all matching Running and Ready pods, sorts their
names, and selects the first one.

**Solution**

Verify the Deployment selector and matching pods.

The plugin intentionally does not implement load balancing, random pod
selection, or pod affinity selection.

------------------------------------------------------------------------

## Notes

### Authentication and Project Selection

Authentication and project selection are intentionally outside the
plugin.

This keeps `oc.rsync` focused on its single responsibility: transferring
local content into a running pod.

A typical workflow should therefore separate responsibilities:

```text
Authentication
      |
      v
Project Selection
      |
      v
Rsync
```

### Deployment-Based Pod Resolution

Do not provide a pod name in the rsync plan.

The plan provides a Deployment name:

```json
{
    "deployment": "app-1"
}
```

The plugin discovers the appropriate pod dynamically from the
Deployment selector.

### Readiness Requirement

The plugin transfers files only to a pod that is both:

```text
Running
```

and:

```text
Ready=True
```

This avoids intentionally selecting pods that are not currently ready.

### Generated Plans

The preferred integration pattern is to generate the `rsync_plan` in an
earlier workflow step and pass it directly to `oc.rsync`.

For example:

```text
BuildReleaseContext
        |
        v
outputs.common_paths
        |
        v
oc.rsync
```

### Environment Consistency

The environment used by `oc.rsync` must match the environment for which
the OpenShift session was created.

For example:

```text
login   -> SIT
project -> SIT
rsync   -> SIT
```

Using a different environment name causes the plugin to look for a
different kubeconfig.

------------------------------------------------------------------------

## Changelog

### 1.0.0

- Initial plugin release.
- Added OpenShift rsync support.
- Added Deployment-based pod resolution.
- Added Deployment selector processing.
- Added Running and Ready pod filtering.
- Added deterministic pod selection.
- Added local source validation.
- Added environment-specific kubeconfig usage.
- Added support for multiple rsync operations.
- Added independent operation result reporting.
- Added aggregate success and failure reporting.
- Authentication intentionally kept outside the plugin.
- Project selection intentionally kept outside the plugin.
