# deployment

------------------------------------------------------------------------

## Overview

`oc.deployment` updates OpenShift Deployment YAML resources in a local
repository.

The plugin supports two execution modes:

- `folder`
- `deployments`

The primary purpose of the plugin is to update Deployment YAML
definitions, particularly container image references, as part of a
release deployment workflow.

The plugin operates only on YAML files stored in the filesystem. It
does not communicate directly with an OpenShift cluster and does not
execute `oc` commands.

### Problem Solved

During a release deployment, a new container image may need to be
referenced by an existing Deployment YAML.

For example, a Deployment may currently contain:

```yaml
image: quay.io/project1/app-1:1.1.6
````

and the release context may determine that it must be changed to:

```yaml
image: quay.io/project1/app-1:1.1.10
```

The `oc.deployment` plugin locates the appropriate Deployment and
container and updates the image reference in the YAML file.

### When to Use

Use this plugin when:

* Deployment YAML files need to be updated before deployment.
* A release context provides Deployment image changes.
* Deployment YAML files are maintained in a local repository.
* The workflow needs to update image references without directly
  interacting with OpenShift.

A common workflow sequence is:

```text
BuildReleaseContext
        |
        v
DeploymentYAMLUpdate
        |
        v
ApplyDeployments
```

`BuildReleaseContext` determines the Deployment changes, while
`DeploymentYAMLUpdate` applies those changes to the repository YAML.

### Important Behavior

The plugin:

* Supports multiple Deployment resources.
* Supports YAML files containing multiple documents.
* Locates Deployments by `metadata.name`.
* Updates the requested container image.
* Preserves other YAML documents in the same file.
* Writes the modified YAML file back to its original location.
* Reports resource-level errors without stopping processing of later
  resources in the same execution.
* Does not create a missing Deployment.
* Does not directly deploy the modified YAML to OpenShift.

---

## Requirements

The plugin requires:

* Entropy runtime.
* A valid workflow execution.
* Read access to Deployment YAML files.
* Write access to Deployment YAML files.
* A valid Deployment YAML repository.
* Valid YAML documents.
* Deployment resources containing `metadata.name`.
* Deployment resources containing the container specified by the
  update definition.

The plugin does not require:

* `oc` CLI.
* An OpenShift login session.
* Kubernetes API access.
* Docker.
* Git.
* An OpenShift network connection.

### Entropy Requirements

The plugin uses Entropy runtime services for:

* Argument handling.
* Filesystem operations.
* YAML parsing.
* YAML serialization.
* Workflow outputs.
* Workflow messages.
* Plugin activity tracking.

---

## Arguments

The plugin accepts different arguments depending on the selected
execution mode.

| Argument      | Required               | Type     | Default  | Description                                                |
| ------------- | ---------------------- | -------- | -------- | ---------------------------------------------------------- |
| `mode`        | No                     | `string` | `folder` | Selects the execution mode.                                |
| `source`      | Yes for `folder`       | `path`   | ---      | Source directory containing Deployment update definitions. |
| `target`      | Yes for `folder`       | `path`   | ---      | Target directory containing Deployment YAML files.         |
| `repository`  | Yes for `deployments`  | `path`   | ---      | Deployment YAML repository.                                |
| `deployments` | Yes for `deployments`* | `list`   | `[]`     | Deployment resources obtained from release context.        |

* The `deployments` argument defaults to an empty list. An empty list
causes the plugin to report that no Deployment resources require
updates.

---

## Argument Details

### `mode`

Selects the execution mode.

Accepted values:

```text
folder
deployments
```

The value is stripped of surrounding whitespace and converted to
lowercase.

Default:

```text
folder
```

### `folder`

Folder mode uses:

```text
source
target
```

The plugin loads Deployment update definitions from `source` and finds
matching Deployment resources in `target`.

### `deployments`

Deployment context mode uses:

```text
repository
deployments
```

The `deployments` list normally comes from a previous
`release.context_builder` workflow step.

Example:

```json
{
    "deployments": "${steps.BuildReleaseContext.outputs.deployment.resources.deployments}"
}
```

---

### `source`

Used by `folder` mode.

The source directory contains Deployment update definitions.

The path:

* Must exist.
* Must be a directory.
* Must be readable.
* Is not modified by this plugin.

Example:

```json
{
    "source": "/opt/releases/deployments"
}
```

---

### `target`

Used by `folder` mode.

The target directory contains Deployment YAML files.

The path:

* Must exist.
* Must be a directory.
* Must be readable.
* Must be writable because Deployment files may be modified.

Example:

```json
{
    "target": "/opt/repository/deployments"
}
```

Unlike the target directory in some other Entropy plugins, this plugin
does not create a missing target directory.

---

### `repository`

Used by `deployments` mode.

Specifies the root directory containing Deployment YAML resources.

The repository:

* Must be supplied.
* Must not be empty.
* Must exist.
* Must be a directory.

Example:

```json
{
    "repository": "/opt/repository/yamls"
}
```

The file specified by each Deployment context resource is resolved
relative to this directory.

For example:

```json
{
    "file": "deployments/app-1.yaml"
}
```

results in:

```text
/opt/repository/yamls/deployments/app-1.yaml
```

---

### `deployments`

Used by `deployments` mode.

Contains Deployment resources that require updates.

Each resource must contain:

```text
name
file
container
target_image
```

Example:

```json
[
    {
        "name": "app-1",
        "file": "deployments/app-1.yaml",
        "container": "app-1",
        "current_image": "quay.io/project1/app-1:1.1.6",
        "target_image": "quay.io/project1/app-1:1.1.10"
    }
]
```

### Resource fields

| Field           | Type     | Description                                      |
| --------------- | -------- | ------------------------------------------------ |
| `name`          | `string` | Deployment resource name.                        |
| `file`          | `string` | Deployment YAML path relative to the repository. |
| `container`     | `string` | Container whose image should be updated.         |
| `current_image` | `string` | Current image identified by release context.     |
| `target_image`  | `string` | Image that should be written to the Deployment.  |

The plugin validates:

```text
name
file
container
target_image
```

`current_image` is part of the release context but is not required by
the plugin's `_validate_context_resource()` method.

---

## Workflow Configuration

The plugin is executed through a workflow step.

### Basic Configuration

```json
{
    "name": "DeploymentYAMLUpdate",
    "plugin": "oc.deployment",
    "enabled": true,
    "on_failure": "abort",
    "tags": [],
    "arguments": {
        "mode": "deployments",
        "repository": "/opt/repository/yamls",
        "deployments": "${steps.BuildReleaseContext.outputs.deployment.resources.deployments}"
    }
}
```

The plugin identifier is:

```text
oc.deployment
```

---

## Complete Workflow Example

```json
{
    "name": "DeploymentUpdateWorkflow",
    "version": "1.0.0",
    "description": "Update Deployment images.",
    "variables": {
        "repository": "/opt/repository/yamls"
    },
    "steps": [
        {
            "name": "BuildReleaseContext",
            "plugin": "release.context_builder",
            "enabled": true,
            "on_failure": "abort",
            "arguments": {
                "release": "/opt/releases/TC01.zip",
                "docker_repository": "/opt/repository/docker",
                "yaml_repository": "${repository}",
                "image_tag": "1.1.10"
            }
        },
        {
            "name": "DeploymentYAMLUpdate",
            "plugin": "oc.deployment",
            "enabled": true,
            "on_failure": "abort",
            "arguments": {
                "mode": "deployments",
                "repository": "${repository}",
                "deployments": "${steps.BuildReleaseContext.outputs.deployment.resources.deployments}"
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
        "repository": "/opt/repository/yamls"
    }
}
```

The variable can then be referenced:

```json
{
    "arguments": {
        "repository": "${repository}"
    }
}
```

Workflow variables are resolved by the workflow engine before the plugin
receives the runtime argument.

### Release Context Variables

The recommended `deployments` input is the output of the release
context builder:

```text
${steps.BuildReleaseContext.outputs.deployment.resources.deployments}
```

Example:

```json
{
    "arguments": {
        "mode": "deployments",
        "repository": "/opt/repository/yamls",
        "deployments": "${steps.BuildReleaseContext.outputs.deployment.resources.deployments}"
    }
}
```

The resulting list contains Deployment information such as:

```json
[
    {
        "name": "trade-workitem-service",
        "file": "deployments/trade-workitem-service.yaml",
        "container": "trade-workitem-service",
        "current_image": "quay.io/project1/trade-workitem-service:1.1.6",
        "target_image": "quay.io/project1/trade-workitem-service:1.1.10"
    }
]
```

---

## Vault Variables

The plugin does not directly access Vault.

Vault-backed variables may be resolved by the workflow engine before the
plugin executes.

Example:

```json
{
    "variables": {
        "repository": "${entv:deployment_repository}"
    }
}
```

The resolved value can then be used as a plugin argument:

```json
{
    "arguments": {
        "repository": "${repository}"
    }
}
```

Do not place real passwords, tokens, credentials, private keys, or
other sensitive values in this document.

---

## Execution

### General Execution

The plugin performs the following high-level operations:

1. Display the start message.
2. Resolve the `mode` argument.
3. Select the appropriate execution path.
4. Validate required arguments.
5. Load Deployment definitions.
6. Locate target Deployment resources.
7. Apply Deployment update operations.
8. Serialize the modified YAML documents.
9. Write the target YAML files.
10. Calculate the number of effective changes.
11. Publish workflow outputs.
12. Return the final `PluginResult`.

### Folder Mode

Folder mode performs:

1. Resolve `source`.
2. Resolve `target`.
3. Validate that `source` exists and is a directory.
4. Validate that `target` exists and is a directory.
5. Load Deployment update definitions from `source`.
6. Load Deployment resources from YAML files under `target`.
7. Match definitions against target Deployment names.
8. Apply the corresponding update operations.
9. Write modified YAML files.
10. Report resource-level failures.
11. Return the execution result.

### Deployments Mode

Deployments mode performs:

1. Read the `deployments` argument.
2. Log the received Deployment resource list.
3. Validate that `deployments` is a list.
4. Validate `repository`.
5. Validate that the repository exists.
6. Return immediately if no Deployment resources are supplied.
7. Process each Deployment resource.
8. Validate:

   * `name`
   * `file`
   * `container`
   * `target_image`
9. Resolve the Deployment YAML path.
10. Load the YAML file.
11. Find the Deployment by `metadata.name`.
12. Build a Deployment update definition from the context resource.
13. Apply the requested update using `target_image`.
14. Write the modified YAML file.
15. Count effective changes.
16. Continue with the next resource if an individual resource fails.
17. Publish final outputs.

---

## Deployment Target Resolution

In `deployments` mode, the target file is constructed as:

```text
repository / resource["file"]
```

For example:

```text
repository:
    /opt/repository/yamls

file:
    deployments/app-1.yaml
```

produces:

```text
/opt/repository/yamls/deployments/app-1.yaml
```

The target YAML loader reads all documents in the file.

Only documents with:

```yaml
kind: Deployment
```

are considered Deployment resources.

The plugin then searches for a Deployment whose:

```yaml
metadata:
  name: <resource name>
```

matches the context resource's `name`.

---

## Container Image Update

The deployment context identifies:

```text
container
target_image
```

For example:

```json
{
    "name": "app-1",
    "file": "deployments/app-1.yaml",
    "container": "app-1",
    "target_image": "quay.io/project1/app-1:1.1.10"
}
```

The update definition generated from this context is applied to the
matching Deployment.

The plugin therefore updates the image associated with the specified
container.

The plugin does not independently discover which image should be used.
The `target_image` supplied in the deployment context is the value that
is applied.

---

## Outputs

The plugin produces the following workflow outputs.

| Output                | Type      | Description                                                     |
| --------------------- | --------- | --------------------------------------------------------------- |
| `success`             | `boolean` | Indicates whether all processed Deployment resources succeeded. |
| `resources_processed` | `integer` | Number of Deployment resources processed.                       |
| `resources_succeeded` | `integer` | Number of successfully processed Deployment resources.          |
| `resources_failed`    | `integer` | Number of failed Deployment resources.                          |
| `changes`             | `integer` | Number of effective changes applied.                            |
| `errors`              | `list`    | Detailed errors encountered while processing resources.         |

### Example

```text
outputs:

    success = true

    resources_processed = 2

    resources_succeeded = 2

    resources_failed = 0

    changes = 2

    errors = []
```

### `success`

Boolean indicating overall plugin success.

Example:

```json
true
```

The value is `false` when one or more resources fail.

### `resources_processed`

Number of Deployment resources processed.

Example:

```json
2
```

### `resources_succeeded`

Number of resources successfully updated.

Example:

```json
2
```

### `resources_failed`

Number of resources that failed.

Example:

```json
0
```

### `changes`

Number of effective changes.

Changes whose status is:

```text
unchanged
```

are not included in the change count.

Example:

```json
2
```

### `errors`

List containing details for failed resources.

Example:

```json
[
    {
        "kind": "Deployment",
        "name": "app-1",
        "path": "deployments/app-1.yaml",
        "message": "Target Deployment 'app-1' not found."
    }
]
```

---

## Example Output

A successful deployment update can produce:

```text
{
    "success": true,
    "resources_processed": 2,
    "resources_succeeded": 2,
    "resources_failed": 0,
    "changes": 2,
    "errors": []
}
```

A partial failure can produce:

```text
{
    "success": false,
    "resources_processed": 2,
    "resources_succeeded": 1,
    "resources_failed": 1,
    "changes": 1,
    "errors": [
        {
            "kind": "Deployment",
            "name": "app-2",
            "path": "deployments/app-2.yaml",
            "message": "Target Deployment 'app-2' not found."
        }
    ]
}
```

---

## Artifacts

The plugin does not intentionally create workflow artifacts.

The standard metadata contains an artifact mapping:

```json
{
    "artifacts": {}
}
```

unless artifacts have been registered by the surrounding plugin runtime.

The modified Deployment YAML files are filesystem outputs and are not
treated as plugin artifacts.

---

## Examples

### Example 1 --- Basic Folder Usage

```json
{
    "arguments": {
        "mode": "folder",
        "source": "/opt/release/deployments",
        "target": "/opt/repository/deployments"
    }
}
```

This loads Deployment update definitions from the source directory and
applies them to matching Deployment YAML files in the target directory.

---

### Example 2 --- Deployment Context Usage

```json
{
    "arguments": {
        "mode": "deployments",
        "repository": "/opt/repository/yamls",
        "deployments": [
            {
                "name": "app-1",
                "file": "deployments/app-1.yaml",
                "container": "app-1",
                "current_image": "quay.io/project1/app-1:1.1.6",
                "target_image": "quay.io/project1/app-1:1.1.10"
            }
        ]
    }
}
```

The plugin locates:

```text
/opt/repository/yamls/deployments/app-1.yaml
```

finds:

```yaml
kind: Deployment
metadata:
  name: app-1
```

and updates the specified container image.

---

### Example 3 --- Multiple Deployments

```json
{
    "arguments": {
        "mode": "deployments",
        "repository": "/opt/repository/yamls",
        "deployments": [
            {
                "name": "app-1",
                "file": "deployments/app-1.yaml",
                "container": "app-1",
                "current_image": "quay.io/project1/app-1:1.1.6",
                "target_image": "quay.io/project1/app-1:1.1.10"
            },
            {
                "name": "app-2",
                "file": "deployments/app-2.yaml",
                "container": "app-2",
                "current_image": "quay.io/project1/app-2:1.1.6",
                "target_image": "quay.io/project1/app-2:1.1.10"
            }
        ]
    }
}
```

Both Deployment resources are processed independently.

---

### Example 4 --- Using Workflow Variables

```json
{
    "variables": {
        "repository": "/opt/repository/yamls"
    },
    "steps": [
        {
            "name": "DeploymentYAMLUpdate",
            "plugin": "oc.deployment",
            "enabled": true,
            "on_failure": "abort",
            "tags": [],
            "arguments": {
                "mode": "deployments",
                "repository": "${repository}",
                "deployments": "${steps.BuildReleaseContext.outputs.deployment.resources.deployments}"
            }
        }
    ]
}
```

---

### Example 5 --- Complete Release Workflow

```json
{
    "name": "ReleaseDeployment",
    "version": "1.0.0",
    "description": "Build release context and update Deployment YAML.",
    "variables": {
        "release": "/opt/releases/TC01.zip",
        "docker_repository": "/opt/repository/docker",
        "yaml_repository": "/opt/repository/yamls",
        "image_tag": "1.1.10"
    },
    "steps": [
        {
            "name": "BuildReleaseContext",
            "plugin": "release.context_builder",
            "enabled": true,
            "on_failure": "abort",
            "arguments": {
                "release": "${release}",
                "docker_repository": "${docker_repository}",
                "yaml_repository": "${yaml_repository}",
                "image_tag": "${image_tag}"
            }
        },
        {
            "name": "DeploymentYAMLUpdate",
            "plugin": "oc.deployment",
            "enabled": true,
            "on_failure": "abort",
            "arguments": {
                "mode": "deployments",
                "repository": "${yaml_repository}",
                "deployments": "${steps.BuildReleaseContext.outputs.deployment.resources.deployments}"
            }
        }
    ]
}
```

---

## Validation

The plugin performs the following validation.

### Mode

The mode must be one of:

```text
folder
deployments
```

Otherwise the plugin fails with:

```text
Unsupported mode 'invalid'. Expected 'folder' or 'deployments'.
```

### Folder Mode

The plugin validates:

* `source` is present.
* `target` is present.
* `source` exists.
* `source` is a directory.
* `target` exists.
* `target` is a directory.

### Deployments Mode

The plugin validates:

* `deployments` is a list.
* `repository` is supplied.
* `repository` is non-empty.
* `repository` exists.
* Each Deployment resource is an object.
* Each Deployment resource contains:

  * `name`
  * `file`
  * `container`
  * `target_image`

### Target YAML

The target YAML loader validates:

* The target file exists.
* The target path is a file.
* YAML can be parsed.
* YAML documents are valid mappings when present.
* Deployment documents contain `metadata.name`.

### Target Deployment

The requested Deployment must exist in the specified target YAML file.

The Deployment is matched using:

```text
metadata.name
```

---

## Validation Errors

Examples include:

```text
Argument 'source' must be a non-empty path.
```

```text
Argument 'target' must be a non-empty path.
```

```text
Source directory '/path' does not exist.
```

```text
Source path '/path' is not a directory.
```

```text
Target directory '/path' does not exist.
```

```text
Target path '/path' is not a directory.
```

```text
Argument 'deployments' must be a list.
```

```text
Argument 'repository' must be a non-empty path.
```

```text
Deployment repository '/path' does not exist.
```

```text
Deployment resource must be an object.
```

```text
Deployment resource requires 'name'.
```

```text
Deployment resource requires 'file'.
```

```text
Deployment resource requires 'container'.
```

```text
Deployment resource requires 'target_image'.
```

```text
Target Deployment 'app-1' not found in '/path/deployments/app-1.yaml'.
```

---

## Error Handling

The plugin catches `DeploymentUpdateException` and general exceptions
at the top-level execution boundary and returns a failed
`PluginResult`.

### Resource-level failures

In both folder and deployment-context processing, individual resources
are handled independently.

If a resource fails:

1. The error is recorded.
2. The resource is counted as failed.
3. Processing continues with the next resource.
4. The final result reports `success=false`.

### Partial Operation Behavior

The plugin does not provide transactional rollback across multiple
Deployment resources.

For example, if two resources are processed and the first succeeds
while the second fails:

```text
resources_processed = 2
resources_succeeded = 1
resources_failed = 1
success = false
```

The successful first resource remains modified.

### Workflow Failure Policy

The workflow controls what happens after the plugin returns a failed
result.

For example:

```json
{
    "on_failure": "abort"
}
```

causes the workflow to stop according to the workflow engine's failure
policy.

The plugin itself does not implement workflow-level continuation.

---

## Security

The plugin operates on local Deployment YAML files.

### Credentials

The plugin does not authenticate to OpenShift and does not manage
OpenShift credentials.

### Sensitive Values

Deployment YAML files may contain sensitive configuration depending on
the application.

The plugin should therefore be executed with appropriate filesystem
permissions.

### Authentication

No OpenShift authentication is performed.

No OpenShift session is required.

### Authorization

Filesystem permissions determine whether the plugin can:

* Read the Deployment repository.
* Read Deployment YAML files.
* Write modified Deployment YAML files.

### External Command Execution

The plugin does not execute external operating-system commands.

---

## Filesystem

| Path              | Purpose                                                            |
| ----------------- | ------------------------------------------------------------------ |
| `source`          | Source directory for Deployment update definitions in folder mode. |
| `target`          | Target directory containing Deployment YAML files in folder mode.  |
| `repository`      | Root Deployment YAML repository in deployments mode.               |
| `repository/file` | Individual Deployment YAML file selected by deployment context.    |

### Source Directory

The source directory:

* Must already exist.
* Must be a directory.
* Must be readable.
* Is not modified.

### Target Directory

The target directory:

* Must already exist.
* Must be a directory.
* Must be readable.
* Must be writable.

The plugin does not create the target directory.

### Deployment YAML Files

Existing Deployment YAML files:

* Are read.
* Are parsed.
* Are modified when applicable.
* Are serialized.
* Are written back to the same path.

### Multi-document YAML

The target loader supports YAML files containing multiple documents.

For example:

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: app-1
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: app-2
```

The plugin can locate the requested Deployment document and writes all
documents back to the file.

---

## External Commands

The plugin does not execute external operating-system commands.

In particular, it does not execute:

```bash
oc apply
```

or:

```bash
oc replace
```

Applying the resulting YAML to OpenShift is the responsibility of
another workflow step.

---

## External Services

The plugin does not directly access external services.

It does not directly communicate with:

* OpenShift.
* Kubernetes API.
* Docker.
* Git.
* Vault.
* Databases.
* HTTP/HTTPS services.

It operates entirely on local filesystem resources.

---

## Side Effects

The plugin modifies Deployment YAML files.

Possible side effects include:

* Modification of Deployment container image references.
* Serialization of YAML documents.
* Writing modified Deployment files to disk.

The plugin does not:

* Create Deployments in OpenShift.
* Delete Deployments.
* Apply Deployments to OpenShift.
* Restart Pods directly.
* Modify live cluster resources.
* Execute `oc`.

---

## Performance

Performance is primarily affected by:

* Number of Deployment resources.
* Number and size of YAML files.
* Number of YAML documents in each file.
* Filesystem performance.

Deployment resources are processed sequentially.

Each target file is loaded and serialized when its corresponding
Deployment is processed.

The plugin performs no network operations.

---

## Limitations

### OpenShift API

The plugin does not communicate with the OpenShift API.

### Deployment Creation

The plugin does not create missing Deployments.

If the requested Deployment cannot be found in the specified YAML file,
the resource fails.

### YAML Format

The plugin requires valid YAML input.

### Resource Type

Only Kubernetes/OpenShift:

```text
Deployment
```

resources are processed by the target loader.

### Target Matching

Deployment matching is based on:

```yaml
metadata:
  name: ...
```

The plugin does not search the OpenShift cluster for the Deployment.

### Container Selection

The Deployment update context identifies the container to update.

The plugin does not independently determine the appropriate container
from the live OpenShift environment.

### Transactionality

Multiple resources are not processed as one atomic transaction.

Successful changes are not automatically rolled back when another
resource fails.

### Network Dependency

The plugin has no network dependency and cannot update a remote YAML
repository unless that repository is mounted or otherwise accessible
through the local filesystem.

---

## Troubleshooting

### Problem

```text
Deployment resources received: []
```

**Cause**

The `deployments` workflow argument is empty.

A common cause is an incorrect workflow output reference or argument
name.

For example, the release context output is:

```text
deployment.resources.deployments
```

Therefore the workflow argument should be:

```json
{
    "deployments": "${steps.BuildReleaseContext.outputs.deployment.resources.deployments}"
}
```

Do not use:

```json
{
    "deployment": "${steps.BuildReleaseContext.outputs.deployment.resources.deployments}"
}
```

The plugin expects the argument name:

```text
deployments
```

### Solution

Verify the workflow configuration and confirm that the release context
contains Deployment resources.

---

### Problem

```text
Target Deployment 'app-1' not found in '/path/deployments/app-1.yaml'.
```

**Cause**

The specified YAML file does not contain a Deployment with the expected
`metadata.name`.

**Solution**

Check the target YAML:

```yaml
kind: Deployment
metadata:
  name: app-1
```

and ensure that the context contains:

```json
{
    "name": "app-1"
}
```

---

### Problem

```text
Target YAML file '/path/file.yaml' does not exist.
```

**Cause**

The repository or `file` value points to a path that does not exist.

**Solution**

Verify:

```text
repository
+
file
```

resolve to the actual Deployment YAML.

For example:

```text
repository:
/opt/repository/yamls

file:
deployments/app-1.yaml
```

must resolve to:

```text
/opt/repository/yamls/deployments/app-1.yaml
```

---

### Problem

The plugin reports success but the file does not appear to change.

**Cause**

The update engine may have determined that the requested value is
already present.

When all operations return:

```text
status = unchanged
```

the change count remains zero.

**Solution**

Compare:

```text
current_image
target_image
```

in the release context and inspect the target Deployment YAML.

---

### Problem

The target image is not updated.

**Cause**

The Deployment context may specify an incorrect container name.

**Solution**

Verify that the Deployment contains the expected container and that
the context identifies the correct container:

```json
{
    "container": "app-1"
}
```

---

### Problem

```text
Deployment resource requires 'target_image'.
```

**Cause**

The deployment context does not contain a valid target image.

**Solution**

Ensure the resource contains a non-empty string:

```json
{
    "target_image": "quay.io/project1/app-1:1.1.10"
}
```

---

### Problem

The plugin fails with:

```text
Deployment repository '/path' does not exist.
```

**Cause**

The `repository` argument points to a nonexistent path.

**Solution**

Ensure the Deployment repository exists before executing the plugin.

---

### Problem

The workflow reaches `DeploymentYAMLUpdate`, but no Deployment resources
are processed.

**Cause**

The workflow may be passing the wrong context field.

The expected release context structure is:

```text
outputs
└── deployment
    └── resources
        └── deployments
```

**Solution**

Use:

```json
{
    "deployments": "${steps.BuildReleaseContext.outputs.deployment.resources.deployments}"
}
```

---

## Notes

### Recommended Integration

The recommended integration with the release context builder is:

```text
release.context_builder
        |
        | deployment.resources.deployments
        v
oc.deployment
        |
        | modified YAML
        v
oc.generic
```

The context builder determines which Deployment resources require image
updates.

The Deployment plugin applies those changes to the repository.

A subsequent OpenShift plugin can then apply the resulting YAML.

### Separation of Responsibilities

`oc.deployment` is intentionally limited to Deployment YAML processing.

It does not perform:

* OpenShift authentication.
* Project selection.
* OpenShift API operations.
* `oc apply`.
* `oc replace`.

This separation allows YAML modification and OpenShift execution to be
handled by independent workflow steps.

### Repository-relative Files

In `deployments` mode, the `file` field is relative to the configured
`repository`.

Example:

```json
{
    "repository": "/opt/yamls/SIT",
    "deployments": [
        {
            "name": "trade-workitem-service",
            "file": "deployments/trade-workitem-service.yaml",
            "container": "trade-workitem-service",
            "target_image": "quay.io/project1/trade-workitem-service:1.1.10"
        }
    ]
}
```

The target file is:

```text
/opt/yamls/SIT/deployments/trade-workitem-service.yaml
```

### Multi-document Files

A single YAML file may contain multiple Deployment documents.

The plugin identifies the correct Deployment by its `metadata.name`
and preserves the complete document collection when writing the file
back.

### Image Updates

The plugin uses the `target_image` supplied by the deployment context.

It does not independently calculate the image tag or image repository.

### env,mounts, and mountvolumes add/update/delete
Sure buddy. For the documentation, I’d add a single **complete `DeploymentUpdate` example** showing `env`, `mounts`, and `mountvolume` together. The current documentation describes the plugin as image-focused, so this example will make the new operation model much clearer. 

## Complete example — env + mounts + mountvolume

```yaml
apiVersion: entropy/v1
kind: DeploymentUpdate

target:
  kind: Deployment
  name: app-1

operations:

  # Add an environment variable
  - action: add
    field: env
    container: app
    value:
      name: APP_ENV
      value: SIT

  # Add an environment variable from a Secret
  - action: add
    field: env
    container: app
    value:
      name: DATABASE_PASSWORD
      valueFrom:
        secretKeyRef:
          name: database-secret
          key: password

  # Add an environment variable from a ConfigMap
  - action: add
    field: env
    container: app
    value:
      name: DATABASE_HOST
      valueFrom:
        configMapKeyRef:
          name: database-config
          key: host

  # Add a volume
  - action: add
    field: mountvolume
    value:
      name: app-config
      configMap:
        name: app-config

  # Mount the volume into the container
  - action: add
    field: mounts
    container: app
    value:
      name: app-config
      mountPath: /etc/app

  # Add another volume
  - action: add
    field: mountvolume
    value:
      name: app-secret
      secret:
        secretName: app-secret

  # Mount the Secret volume
  - action: add
    field: mounts
    container: app
    value:
      name: app-secret
      mountPath: /etc/secrets
      readOnly: true
```

### Resulting Deployment

The relevant part of the Deployment would become:

```yaml
spec:
  template:
    spec:
      containers:
        - name: app
          image: quay.io/project1/app-1:1.1.10

          env:
            - name: APP_ENV
              value: SIT

            - name: DATABASE_PASSWORD
              valueFrom:
                secretKeyRef:
                  name: database-secret
                  key: password

            - name: DATABASE_HOST
              valueFrom:
                configMapKeyRef:
                  name: database-config
                  key: host

          volumeMounts:
            - name: app-config
              mountPath: /etc/app

            - name: app-secret
              mountPath: /etc/secrets
              readOnly: true

      volumes:
        - name: app-config
          configMap:
            name: app-config

        - name: app-secret
          secret:
            secretName: app-secret
```

## Individual operation examples

### Environment variable — simple value

```yaml
- action: add
  field: env
  container: app
  value:
    name: LOG_LEVEL
    value: DEBUG
```

### Environment variable — Secret

```yaml
- action: add
  field: env
  container: app
  value:
    name: DB_PASSWORD
    valueFrom:
      secretKeyRef:
        name: database-secret
        key: password
```

### Environment variable — ConfigMap

```yaml
- action: add
  field: env
  container: app
  value:
    name: DB_HOST
    valueFrom:
      configMapKeyRef:
        name: database-config
        key: host
```

### Environment variable — update

```yaml
- action: update
  field: env
  container: app
  value:
    name: LOG_LEVEL
    value: INFO
```

`update` replaces the complete environment-variable object.

### Environment variable — delete

```yaml
- action: delete
  field: env
  container: app
  value:
    name: LOG_LEVEL
```

---

## Volume — ConfigMap

```yaml
- action: add
  field: mountvolume
  value:
    name: application-config
    configMap:
      name: application-config
```

## Volume — Secret

```yaml
- action: add
  field: mountvolume
  value:
    name: application-secret
    secret:
      secretName: application-secret
```

## Volume — PVC

```yaml
- action: add
  field: mountvolume
  value:
    name: application-data
    persistentVolumeClaim:
      claimName: application-pvc
```

## Volume — update

```yaml
- action: update
  field: mountvolume
  value:
    name: application-config
    configMap:
      name: application-config-v2
```

## Volume — delete

```yaml
- action: delete
  field: mountvolume
  value:
    name: application-config
```

---

## Volume mount — add

```yaml
- action: add
  field: mounts
  container: app
  value:
    name: application-config
    mountPath: /etc/application
```

## Volume mount — read-only

```yaml
- action: add
  field: mounts
  container: app
  value:
    name: application-secret
    mountPath: /etc/secrets
    readOnly: true
```

## Volume mount — update

```yaml
- action: update
  field: mounts
  container: app
  value:
    name: application-config
    mountPath: /etc/application/config
    readOnly: true
```

## Volume mount — delete

```yaml
- action: delete
  field: mounts
  container: app
  value:
    name: application-config
```

### Important relationship

For a volume-backed mount, the two operations are separate:

```text
mountvolume
    ↓
spec.template.spec.volumes
    ↓
defines the volume

mounts
    ↓
spec.template.spec.containers[].volumeMounts
    ↓
mounts that volume into a container
```

So this:

```yaml
- action: add
  field: mountvolume
  value:
    name: app-config
    configMap:
      name: app-config
```

should normally be paired with:

```yaml
- action: add
  field: mounts
  container: app
  value:
    name: app-config
    mountPath: /etc/app
```
---

## Changelog

### 1.0.0

* Initial plugin release.
* Added Deployment YAML update support.
* Added `folder` execution mode.
* Added `deployments` execution mode.
* Added release-context integration.
* Added Deployment resource validation.
* Added Deployment YAML target loading.
* Added multi-document YAML support.
* Added container image update support.
* Added repository-relative Deployment file resolution.
* Added detailed resource-level error reporting.
* Added workflow output reporting.
* Added filesystem-based Deployment modification.
* Kept OpenShift cluster operations outside the plugin.

### 1.0.7
* Added mounts add/update/delete.
* Added mountVolumes add/update/delete.
* Added env add/update/delete.
```
```
