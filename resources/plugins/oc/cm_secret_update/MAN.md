# cm_secret_update

------------------------------------------------------------------------

## Overview

`cm_secret_update` updates OpenShift `ConfigMap` and `Secret` YAML
resources stored in a repository.

The plugin supports two execution modes:

- `folder`
- `deployments`

The plugin can process two types of source definitions:

1. Native Kubernetes/OpenShift `ConfigMap` or `Secret` resources.
2. Entropy `ConfigMapSecretUpdate` definitions containing explicit
   update operations.

The plugin modifies YAML files on the local filesystem. It does not
execute `oc` commands and does not require an active OpenShift session.

The plugin is useful when release processing needs to update
ConfigMap or Secret values before those YAML files are subsequently
applied or replaced by another workflow step.

### Main responsibilities

The plugin:

1. Validates its arguments.
2. Loads ConfigMap/Secret source definitions.
3. Locates the corresponding target resources.
4. Applies update operations or native-resource changes.
5. Creates missing native resources when possible.
6. Writes the modified YAML back to the target repository.
7. Reports detailed resource and key-level changes.
8. Publishes workflow outputs for subsequent workflow steps.

### Important behavior

The plugin is designed to be idempotent for update operations.

For an `add` operation:

- Existing key -> existing value is replaced.
- Missing key -> key is added.

For an `update` operation:

- Existing key -> value is updated.
- Missing key -> value is added.

For a `delete` operation:

- Existing key -> key is deleted.
- Missing key -> no change.

Structured `properties` and `yaml` operations use the same general
override behavior.

------------------------------------------------------------------------

## Requirements

The plugin requires:

- Entropy runtime.
- A valid workflow execution.
- Read access to the source YAML files.
- Write access to the target YAML files.
- Valid YAML source and target files.
- ConfigMap/Secret resources with valid metadata.
- The source and target paths supplied to the plugin must be accessible
  from the machine running Entropy.

The plugin does not require:

- `oc` CLI.
- An OpenShift login session.
- Kubernetes API access.
- Docker.
- Git.
- A network connection.

### Entropy requirements

The plugin requires the Entropy filesystem abstraction and plugin
runtime services provided by `BasePlugin`.

The following plugin services are used:

- Argument handling.
- Filesystem operations.
- YAML parsing.
- YAML serialization.
- Workflow output handling.
- Workflow messaging.
- Plugin activity reporting.

------------------------------------------------------------------------

## Arguments

The plugin accepts different arguments depending on the selected
execution mode.

| Argument | Required | Type | Default | Description |
|-----------|----------|------|---------|-------------|
| `mode` | No | `string` | `folder` | Selects the plugin execution mode. |
| `source` | Yes for `folder` | `path` | --- | Source directory containing ConfigMap/Secret definitions. |
| `target` | Yes for `folder` | `path` | --- | Target directory containing ConfigMap/Secret YAML files. |
| `configmaps` | Yes for `deployments`* | `list` | `[]` | ConfigMap resources from release context. |
| `secrets` | Yes for `deployments`* | `list` | `[]` | Secret resources from release context. |
| `replace` | No | `boolean` | `false` | Controls complete replacement behavior for native resources. |

\* `configmaps` and `secrets` are individually optional from the
argument parser's perspective and default to empty lists. At least one
resource must be supplied for the plugin to perform work in
`deployments` mode.

------------------------------------------------------------------------

## Argument Details

### `mode`

Selects how the plugin obtains source and target information.

Accepted values:

```text
folder
deployments
````

The value is normalized using `strip()` and converted to lowercase.

Default:

```text
folder
```

#### `folder`

The plugin expects:

```text
source
target
replace
```

The source directory contains ConfigMap/Secret source definitions.

The target directory contains the ConfigMap/Secret resources that will
be modified.

#### `deployments`

The plugin expects release-context resource lists:

```text
configmaps
secrets
```

Each resource identifies:

* Resource kind.
* Resource name.
* Source YAML file.
* Target repository YAML file.

The source YAML is loaded at runtime and the plugin resolves either:

* an Entropy `ConfigMapSecretUpdate`, or
* a native ConfigMap/Secret.

---

### `source`

Used by `folder` mode.

The source directory containing ConfigMap/Secret definitions.

The path:

* Must exist.
* Must be a directory.
* Must be readable.
* Is not modified by the plugin.

Example:

```json
{
    "source": "/opt/entropy/releases/configmaps"
}
```

---

### `target`

Used by `folder` mode.

The target directory containing ConfigMap/Secret YAML resources.

The target directory:

* Must exist or be created by the plugin.
* Must be a directory.
* Must be writable.
* May contain multiple YAML files.

Example:

```json
{
    "target": "/opt/entropy/repository/configmaps"
}
```

If the directory does not exist, the plugin creates it.

---

### `configmaps`

Used by `deployments` mode.

A list of ConfigMap resources obtained from release context.

Example:

```json
[
    {
        "kind": "ConfigMap",
        "name": "cm-testyaml",
        "action": "UPDATE",
        "source": "/opt/releases/RAN001/App/openshift/yamls/configmap.yaml",
        "repository": "/opt/repository/configmaps/cm-testyaml.yaml",
        "operations": [
            {
                "action": "update",
                "key": "application.yaml",
                "format": "yaml",
                "entries": {
                    "server": {
                        "port": 8080
                    }
                }
            }
        ]
    }
]
```

The list must contain objects.

Each resource must contain:

```text
kind
name
source
repository
```

Supported kinds:

```text
ConfigMap
Secret
```

The `operations` field is optional.

If present, it represents an Entropy `ConfigMapSecretUpdate`
definition.

If absent, the source is treated as a native ConfigMap/Secret resource.

---

### `secrets`

Used by `deployments` mode.

A list of Secret resources obtained from release context.

The structure is the same as `configmaps`.

Example:

```json
[
    {
        "kind": "Secret",
        "name": "application-secret",
        "action": "UPDATE",
        "source": "/opt/releases/RAN001/App/openshift/yamls/secret.yaml",
        "repository": "/opt/repository/secrets/application-secret.yaml"
    }
]
```

Supported kinds:

```text
ConfigMap
Secret
```

---

### `replace`

Controls behavior when the source is a native ConfigMap or Secret and
the target already exists.

Default:

```json
false
```

When `false`:

* Existing target data is preserved.
* Source `data` keys are merged into the target.
* Existing matching keys are updated.
* Missing keys are added.
* Target-only keys remain unchanged.

When `true`:

* The complete target resource is replaced with the source resource.

Example:

```json
{
    "replace": true
}
```

For `ConfigMapSecretUpdate` sources, `replace` does not make individual
update operations destructive. Complete-resource replacement is handled
only for native resources.

---

## Workflow Configuration

The plugin is executed through a workflow step.

### Basic Configuration

```json
{
    "name": "Update ConfigMaps and Secrets",
    "plugin": "oc.cm_secret_update",
    "enabled": true,
    "on_failure": "abort",
    "tags": [
        "openshift",
        "deployment"
    ],
    "arguments": {
        "mode": "folder",
        "source": "/opt/releases/configmaps",
        "target": "/opt/repository/configmaps",
        "replace": false
    }
}
```

The plugin identifier is:

```text
oc.cm_secret_update
```

---

## Complete Workflow Example

### Folder mode

```json
{
    "name": "ConfigMapSecretUpdateWorkflow",
    "version": "1.0.0",
    "description": "Update ConfigMap and Secret YAML resources.",
    "variables": {
        "source": "/opt/releases/configmaps",
        "target": "/opt/repository/configmaps"
    },
    "steps": [
        {
            "name": "Update ConfigMaps and Secrets",
            "plugin": "oc.cm_secret_update",
            "enabled": true,
            "on_failure": "abort",
            "tags": [
                "openshift",
                "deployment"
            ],
            "arguments": {
                "mode": "folder",
                "source": "${source}",
                "target": "${target}",
                "replace": false
            }
        }
    ]
}
```

### Deployment context mode

```json
{
    "name": "ConfigMapSecretUpdateWorkflow",
    "version": "1.0.0",
    "description": "Update ConfigMaps and Secrets from release context.",
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
            "name": "CmSecretUpdate",
            "plugin": "oc.cm_secret_update",
            "enabled": true,
            "on_failure": "abort",
            "tags": [
                "openshift",
                "deployment"
            ],
            "arguments": {
                "mode": "deployments",
                "configmaps": "${steps.BuildReleaseContext.outputs.deployment.resources.configmaps}",
                "secrets": "${steps.BuildReleaseContext.outputs.deployment.resources.secrets}",
                "replace": false
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
        "source": "/opt/releases/configmaps",
        "target": "/opt/repository/configmaps"
    }
}
```

The variables can then be referenced by plugin arguments:

```json
{
    "arguments": {
        "mode": "folder",
        "source": "${source}",
        "target": "${target}"
    }
}
```

Variables are resolved by the workflow engine before the plugin
receives the runtime arguments.

### Deployment context variables

The plugin can consume outputs produced by another workflow step.

For example:

```json
{
    "configmaps": "${steps.BuildReleaseContext.outputs.deployment.resources.configmaps}",
    "secrets": "${steps.BuildReleaseContext.outputs.deployment.resources.secrets}"
}
```

This is the recommended configuration when the plugin is part of a
release deployment workflow.

---

## Vault Variables

Vault-backed workflow variables can be resolved by the workflow engine
before the plugin executes.

Example:

```json
{
    "variables": {
        "config_value": "${entv:SIT/CONFIG_VALUE}"
    }
}
```

The resolved variable can then be passed to plugin arguments where
supported by the workflow configuration.

Example:

```json
{
    "arguments": {
        "example": "${config_value}"
    }
}
```

Vault resolution is performed by the workflow engine.

The plugin itself does not authenticate against Vault.

Do not place actual passwords, tokens, credentials, private keys, or
other sensitive values in workflow documentation.

---

## Execution

### Folder mode

The execution flow is:

1. Resolve `mode`.
2. Resolve `source`.
3. Resolve `target`.
4. Resolve `replace`.
5. Validate source and target directories.
6. Load ConfigMap/Secret source definitions.
7. Load target ConfigMap/Secret resources.
8. Create the update engine.
9. Apply source definitions to matching targets.
10. Write modified target YAML files.
11. Build detailed change information.
12. Publish workflow outputs.
13. Return the plugin result.

The source directory is never modified.

The target directory is modified when changes are required.

### Deployment mode

The execution flow is:

1. Resolve `configmaps`.
2. Resolve `secrets`.
3. Combine the two resource lists.
4. Validate each deployment resource.
5. Resolve the source YAML path.
6. Resolve the target repository YAML path.
7. Load the existing target if it exists.
8. Load all YAML documents from the source file.
9. Locate the requested source resource.
10. Determine whether the source is:

    * `ConfigMapSecretUpdate`, or
    * native `ConfigMap`/`Secret`.
11. Apply the update or native resource merge/replacement.
12. Create the target when supported.
13. Write the target YAML.
14. Record detailed changes.
15. Publish workflow outputs.
16. Return the plugin result.

### Source resource resolution

The deployment mode supports both:

```yaml
kind: ConfigMap
```

and:

```yaml
kind: Secret
```

as native resources.

It also supports:

```yaml
kind: ConfigMapSecretUpdate
```

where the actual target is specified under:

```yaml
target:
  kind: ConfigMap
  name: cm-testyaml
```

The plugin resolves the source by matching:

```text
kind
name
```

against either the native resource metadata or the
`ConfigMapSecretUpdate.target` definition.

---

## Outputs

The plugin publishes the following outputs.

| Output                | Type      | Description                                                    |
| --------------------- | --------- | -------------------------------------------------------------- |
| `success`             | `boolean` | Indicates whether all processed resources succeeded.           |
| `failed`              | `boolean` | Indicates whether at least one resource failed in folder mode. |
| `resources_processed` | `integer` | Number of resources processed.                                 |
| `resources_succeeded` | `integer` | Number of successfully processed resources.                    |
| `resources_failed`    | `integer` | Number of resources that failed.                               |
| `changes`             | `integer` | Number of changes applied.                                     |
| `errors`              | `list`    | Detailed resource errors.                                      |

### Example

```text
outputs:

    success = true

    resources_processed = 2

    resources_succeeded = 2

    resources_failed = 0

    changes = 3

    errors = []
```

### `success`

Boolean indicating overall plugin success.

Example:

```json
true
```

If one or more resources fail:

```json
false
```

### `failed`

Indicates whether a failure occurred during folder-mode processing.

Example:

```json
false
```

### `resources_processed`

Number of resources processed.

Example:

```json
2
```

### `resources_succeeded`

Number of successfully processed resources.

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

Total number of changes applied.

Example:

```json
3
```

This value is based on the detailed changes returned by the update
engine or native-resource processing.

### `errors`

List of detailed errors.

Example:

```json
[
    {
        "kind": "ConfigMap",
        "name": "cm-testyaml",
        "path": "/opt/repository/configmaps/cm-testyaml.yaml",
        "key": "application.yaml",
        "message": "Unable to update resource."
    }
]
```

### Consuming outputs from later steps

A later workflow step can reference plugin outputs using standard
workflow interpolation.

Example:

```json
{
    "command": "echo Changes: $1",
    "args": [
        "${steps.CmSecretUpdate.outputs.changes}"
    ]
}
```

---

## Artifacts

The plugin does not intentionally create workflow artifacts.

The plugin result contains the standard Entropy artifact metadata:

```json
{
    "artifacts": {}
}
```

unless artifacts are registered by the surrounding plugin runtime.

The actual modified YAML files are filesystem outputs rather than
Entropy artifacts.

---

## Examples

### Example 1 --- Basic Folder Usage

```json
{
    "arguments": {
        "mode": "folder",
        "source": "/opt/release/configmaps",
        "target": "/opt/repository/configmaps",
        "replace": false
    }
}
```

This processes ConfigMap/Secret definitions from the source directory
and updates matching resources in the target directory.

---

### Example 2 --- Native Resource Replacement

```json
{
    "arguments": {
        "mode": "folder",
        "source": "/opt/release/configmaps",
        "target": "/opt/repository/configmaps",
        "replace": true
    }
}
```

For native ConfigMap/Secret sources, an existing target resource is
replaced by the complete source resource.

Use this mode carefully because target-only fields/data can be removed.

---

### Example 3 --- Using Workflow Variables

```json
{
    "variables": {
        "source": "/opt/release/configmaps",
        "target": "/opt/repository/configmaps"
    },
    "steps": [
        {
            "name": "Update ConfigMaps",
            "plugin": "oc.cm_secret_update",
            "enabled": true,
            "on_failure": "abort",
            "tags": [],
            "arguments": {
                "mode": "folder",
                "source": "${source}",
                "target": "${target}",
                "replace": false
            }
        }
    ]
}
```

---

### Example 4 --- Using Release Context

```json
{
    "steps": [
        {
            "name": "BuildReleaseContext",
            "plugin": "release.context_builder",
            "enabled": true,
            "on_failure": "abort",
            "arguments": {
                "release": "/opt/releases/TC01.zip",
                "docker_repository": "/opt/repository/docker",
                "yaml_repository": "/opt/repository/yamls",
                "image_tag": "1.1.10"
            }
        },
        {
            "name": "CmSecretUpdate",
            "plugin": "oc.cm_secret_update",
            "enabled": true,
            "on_failure": "abort",
            "arguments": {
                "mode": "deployments",
                "configmaps": "${steps.BuildReleaseContext.outputs.deployment.resources.configmaps}",
                "secrets": "${steps.BuildReleaseContext.outputs.deployment.resources.secrets}",
                "replace": false
            }
        }
    ]
}
```

---

### Example 5 --- ConfigMapSecretUpdate Source

A source YAML can contain an Entropy update definition:

```yaml
apiVersion: entropy/v1
kind: ConfigMapSecretUpdate

target:
  kind: ConfigMap
  name: cm-testyaml

operations:
  - action: update
    key: application.properties
    format: properties
    entries:
      server.port: "8080"
      application.name: "trade-service"
```

The plugin locates:

```text
ConfigMap/cm-testyaml
```

in the target repository and applies the operations.

---

### Example 6 --- Simple Key Update

```yaml
apiVersion: entropy/v1
kind: ConfigMapSecretUpdate

target:
  kind: ConfigMap
  name: cm-testyaml

operations:
  - action: update
    key: application.properties
    value: |
      application.name=trade-service
      server.port=8080
```

The existing value of `application.properties` is replaced with the
specified value.

If the key does not exist, it is added.

---

### Example 7 --- Properties Update

```yaml
apiVersion: entropy/v1
kind: ConfigMapSecretUpdate

target:
  kind: ConfigMap
  name: cm-testyaml

operations:
  - action: update
    key: application.properties
    format: properties
    entries:
      server.port: "8080"
      logging.level.root: "INFO"
```

The plugin parses the existing properties content and updates the
specified properties.

Other properties remain intact.

---

### Example 8 --- YAML Update

```yaml
apiVersion: entropy/v1
kind: ConfigMapSecretUpdate

target:
  kind: ConfigMap
  name: cm-testyaml

operations:
  - action: update
    key: application.yaml
    format: yaml
    entries:
      server:
        port: 8080
      application:
        name: trade-service
```

The plugin parses the existing embedded YAML value and recursively
merges the supplied values.

---

### Example 9 --- Delete a Key

```yaml
apiVersion: entropy/v1
kind: ConfigMapSecretUpdate

target:
  kind: ConfigMap
  name: cm-testyaml

operations:
  - action: delete
    key: obsolete.properties
```

If the key exists, it is deleted.

If it does not exist, the operation is reported as unchanged.

---

### Example 10 --- Delete Properties

```yaml
apiVersion: entropy/v1
kind: ConfigMapSecretUpdate

target:
  kind: ConfigMap
  name: cm-testyaml

operations:
  - action: delete
    key: application.properties
    format: properties
    entries:
      - obsolete.property
      - deprecated.setting
```

Only the specified properties are removed.

The ConfigMap key itself remains.

---

### Example 11 --- Delete YAML Fields

```yaml
apiVersion: entropy/v1
kind: ConfigMapSecretUpdate

target:
  kind: ConfigMap
  name: cm-testyaml

operations:
  - action: delete
    key: application.yaml
    format: yaml
    entries:
      - server.debug
      - application.legacy
```

The specified YAML paths are removed from the embedded YAML document.

---

## Validation

The plugin performs validation at multiple levels.

### Mode validation

The `mode` must be:

```text
folder
```

or:

```text
deployments
```

Otherwise execution fails.

Example:

```text
Unsupported mode 'invalid'. Expected 'folder' or 'deployments'.
```

### Folder validation

In `folder` mode:

* `source` is required.
* `target` is required.
* `source` must exist.
* `source` must be a directory.
* `target` must be a directory if it already exists.
* Missing target directories are created.

### Deployment resource validation

Every deployment resource must be an object.

The following fields are required:

```text
kind
name
source
repository
```

Supported kinds are:

```text
ConfigMap
Secret
```

The optional `operations` field must be a list when supplied.

### Source validation

The source YAML file:

* Must exist.
* Must be a file.
* Must contain valid YAML.
* Must contain the requested resource.

### Target validation

When a target exists:

* It must be a valid YAML file.
* ConfigMap and Secret resources must contain valid metadata.
* `metadata.name` must be present.

### ConfigMap/Secret validation

Supported target kinds are:

```text
ConfigMap
Secret
```

A target resource must contain:

```yaml
metadata:
  name: resource-name
```

### Embedded properties validation

A properties operation requires:

```text
entries
```

to be an object for add/update operations.

For delete operations, `entries` must be a list.

The existing embedded value must be a string.

### Embedded YAML validation

A YAML operation requires:

```text
entries
```

to be an object for update operations.

For delete operations, `entries` must be a list.

The existing embedded value must be a string containing a YAML object.

---

## Validation Errors

Examples of validation errors include:

```text
Argument 'source' must be a non-empty path.
```

```text
Argument 'target' must be a non-empty path.
```

```text
Unsupported mode 'invalid'. Expected 'folder' or 'deployments'.
```

```text
Argument 'configmaps' must be a list.
```

```text
Argument 'secrets' must be a list.
```

```text
Deployment resource must be an object.
```

```text
Deployment resource requires 'repository'.
```

```text
Unsupported deployment resource kind 'Deployment'.
```

```text
Deployment resource 'operations' must be a list.
```

```text
Source YAML file '/path/source.yaml' does not exist.
```

```text
Source resource 'ConfigMap/example' not found in '/path/source.yaml'.
```

---

## Error Handling

The plugin catches plugin-specific runtime exceptions and returns a
failed `PluginResult`.

Individual deployment-mode resources are processed independently.

If one resource fails:

* The error is recorded.
* Processing continues with subsequent resources.
* The final plugin result reports failure.

The workflow can determine whether to continue after the plugin based on
the workflow step's `on_failure` configuration.

### Partial operation behavior

In deployment mode, processing is resource-oriented.

For example, if three resources are supplied:

```text
ConfigMap/a
ConfigMap/b
Secret/c
```

and only `ConfigMap/b` fails:

```text
resources_processed = 3
resources_succeeded = 2
resources_failed = 1
success = false
```

Successful resources remain modified.

The plugin does not provide a transaction that rolls back previously
successful filesystem changes.

### File operation failures

Read, parse, serialize, or write failures are reported as plugin
errors.

The plugin does not intentionally delete source files.

### OpenShift failures

The plugin itself does not execute `oc`.

OpenShift application/replacement should be handled by another workflow
step, such as `oc.generic`.

---

## Security

The plugin operates on local YAML files.

### Credentials and sensitive data

ConfigMaps and Secrets may contain sensitive values.

The plugin does not intentionally print complete ConfigMap or Secret
contents during normal operation.

Users should still treat target repositories containing Secret YAML
files as sensitive.

Do not commit credentials or other secrets into source control unless
that is explicitly part of the deployment design.

### Authentication

The plugin does not authenticate against OpenShift.

It does not require:

```text
oc login
```

or an OpenShift session.

### Authorization

Authorization is provided by filesystem permissions.

The process must have:

* Read permission for source files.
* Read permission for existing target files.
* Write permission for target files.
* Directory creation permission when a target directory does not exist.

### Secret handling

Secret values can be written to target YAML files.

Therefore:

* Protect target directories.
* Use appropriate filesystem permissions.
* Avoid exposing plugin output in shared logs.
* Do not place sensitive examples containing real credentials in
  workflow documentation.

### External command execution

The plugin does not execute operating-system commands directly.

---

## Filesystem

| Path                  | Purpose                              |
| --------------------- | ------------------------------------ |
| `source`              | Source directory in folder mode.     |
| `target`              | Target directory in folder mode.     |
| `resource.source`     | Source YAML file in deployment mode. |
| `resource.repository` | Target YAML file in deployment mode. |

### Source directory

The source directory:

* Must exist.
* Must be a directory.
* Must be readable.
* Is not modified.

### Target directory

The target directory:

* Must exist in normal deployment processing.
* Is created automatically in folder mode if missing.
* Must be writable.

### Target YAML files

Existing target YAML files:

* Are read.
* Are modified when changes are applied.
* Are written back to their original path.

The plugin preserves all YAML documents loaded from an existing target
file when serializing the file.

### Newly created target files

When a supported native resource is missing, the plugin can create a new
target YAML file from the native source resource.

The created file is written to the target repository path.

### Temporary files

The plugin does not intentionally create temporary files for its own
update processing.

---

## External Commands

The plugin does not execute external commands.

In particular, it does not execute:

```bash
oc
```

Therefore no OpenShift CLI installation is required for this plugin.

---

## External Services

The plugin does not directly access external services.

It does not directly access:

* OpenShift API.
* Kubernetes API.
* Docker.
* Git.
* Vault.
* Databases.
* HTTP/HTTPS services.

OpenShift deployment is expected to be performed by another workflow
plugin after this plugin modifies the YAML files.

---

## Side Effects

The plugin modifies local filesystem state.

Possible side effects include:

* Creating a target directory in folder mode.
* Creating a new ConfigMap YAML file.
* Creating a new Secret YAML file.
* Modifying existing ConfigMap YAML files.
* Modifying existing Secret YAML files.
* Updating individual `data` keys.
* Deleting individual `data` keys.
* Updating embedded properties.
* Deleting embedded properties.
* Updating embedded YAML.
* Deleting embedded YAML fields.
* Replacing complete native ConfigMap/Secret resources when
  `replace=true`.

The plugin does not directly modify the live OpenShift cluster.

---

## Performance

Performance is primarily determined by:

* Number of source resources.
* Number of target resources.
* Size of YAML files.
* Number of embedded properties/YAML operations.
* Filesystem performance.

The plugin processes resources sequentially.

Large YAML files containing many resources may require additional
serialization time.

There are no network operations performed by the plugin.

---

## Limitations

The plugin has the following operational limitations.

### Resource types

Only these native resource kinds are supported:

```text
ConfigMap
Secret
```

### Source update definitions

Entropy update definitions use:

```yaml
kind: ConfigMapSecretUpdate
```

and identify their actual target through:

```yaml
target:
  kind: ConfigMap
  name: example
```

### Embedded YAML

Embedded YAML update operations require the existing value to represent
a YAML object.

Scalar or unsupported YAML structures are rejected.

### Embedded properties

Embedded properties operations require string content.

Non-string values cannot be processed as properties documents.

### Filesystem scope

The plugin operates on local filesystem paths.

It does not retrieve files from remote repositories itself.

### Transactionality

The plugin does not provide an all-or-nothing transaction across
multiple resources.

A failure on one resource does not automatically roll back successful
changes made to earlier resources.

### OpenShift state

The plugin does not inspect the live OpenShift cluster.

It operates exclusively on YAML files.

---

## Troubleshooting

### Problem

```text
Argument 'source' must be a non-empty path.
```

**Cause**

The `source` argument is missing or empty in `folder` mode.

**Solution**

Provide a valid source directory:

```json
{
    "source": "/opt/releases/configmaps"
}
```

---

### Problem

```text
Source directory '/path' does not exist.
```

**Cause**

The configured source directory does not exist.

**Solution**

Verify the path and ensure the release/source directory has been
prepared before executing the plugin.

---

### Problem

```text
Source resource 'ConfigMap/cm-testyaml' not found in '/path/configmap.yaml'.
```

**Cause**

The plugin could not find either:

* a native `ConfigMap` with the requested name, or
* a `ConfigMapSecretUpdate` targeting that ConfigMap.

**Solution**

Verify that the source YAML contains the expected resource.

For an Entropy update definition:

```yaml
kind: ConfigMapSecretUpdate

target:
  kind: ConfigMap
  name: cm-testyaml
```

Make sure the target name exactly matches the deployment context.

---

### Problem

```text
Target resource 'ConfigMap/cm-testyaml' not found.
```

**Cause**

The target repository does not contain the requested ConfigMap.

**Solution**

If the source is a native ConfigMap, the plugin can create the missing
resource.

If the source is a `ConfigMapSecretUpdate`, ensure the workflow/source
design provides the appropriate native resource when creation is
required.

---

### Problem

The plugin reports success but no values changed.

**Cause**

The update definition may contain no operations, or all operations may
result in no effective changes.

**Solution**

Inspect the release context:

```text
steps.BuildReleaseContext.outputs.deployment.resources.configmaps
```

Verify that the resource contains the expected `operations` when the
source is a `ConfigMapSecretUpdate`.

Example:

```json
{
    "kind": "ConfigMap",
    "name": "cm-testyaml",
    "operations": [
        {
            "action": "update",
            "key": "application.properties",
            "value": "..."
        }
    ]
}
```

Also verify that the source YAML contains the corresponding
`ConfigMapSecretUpdate`.

---

### Problem

```text
YAML operation for key 'application.yaml' requires object entries.
```

**Cause**

The YAML update's `entries` value is not an object.

**Solution**

Use a mapping:

```yaml
entries:
  server:
    port: 8080
```

---

### Problem

```text
Properties operation for key 'application.properties' requires object entries.
```

**Cause**

The properties update does not contain object-style entries.

**Solution**

Use:

```yaml
entries:
  server.port: "8080"
  application.name: "trade-service"
```

---

### Problem

```text
Embedded properties value for key 'application.properties' must be a string.
```

**Cause**

The target ConfigMap/Secret value is not string content.

**Solution**

Properties operations require the target value to be a string.

---

### Problem

```text
Embedded YAML value for key 'application.yaml' must contain an object.
```

**Cause**

The embedded YAML value is not a YAML mapping.

**Solution**

Ensure the ConfigMap/Secret key contains YAML representing an object,
for example:

```yaml
server:
  port: 8080
application:
  name: trade-service
```

---

### Problem

The target YAML file is not modified.

**Cause**

Possible causes include:

* The resource was not selected by the deployment context.
* The resource name does not match.
* No update operations were generated.
* The source resource could not be resolved.
* The calculated change set is empty.
* The target path points to a different file than expected.

**Solution**

Verify:

1. `configmaps`/`secrets` contain the expected resource.
2. `kind` matches.
3. `name` matches.
4. `source` points to the expected release YAML.
5. `repository` points to the expected target YAML.
6. `ConfigMapSecretUpdate.operations` contains operations.

---

### Problem

The plugin cannot update a Secret.

**Cause**

The resource may have an unsupported kind or invalid metadata.

**Solution**

Ensure the resource contains:

```yaml
kind: Secret
metadata:
  name: example
```

---

## Notes

### Recommended workflow ordering

When used as part of a deployment workflow, the typical sequence is:

```text
BuildReleaseContext
        |
        v
CmSecretUpdate
        |
        v
DeploymentYAMLUpdate
        |
        v
ApplyDeployments
        |
        v
ReplaceConfigMapsSecrets
```

The exact workflow can vary depending on the deployment design.

### Separation of responsibilities

`cm_secret_update` is responsible for modifying YAML files.

It does not perform:

* OpenShift login.
* OpenShift project selection.
* `oc apply`.
* `oc replace`.

These responsibilities belong to other workflow components.

### Deployment context integration

When using `mode=deployments`, the recommended source of
`configmaps` and `secrets` is the output of the release context builder:

```text
${steps.BuildReleaseContext.outputs.deployment.resources.configmaps}
```

and:

```text
${steps.BuildReleaseContext.outputs.deployment.resources.secrets}
```

This keeps release analysis and resource modification separated.

### Native versus update source

The plugin distinguishes between:

```yaml
kind: ConfigMap
```

or:

```yaml
kind: Secret
```

and:

```yaml
kind: ConfigMapSecretUpdate
```

A native resource supplies resource content.

A `ConfigMapSecretUpdate` supplies operations to apply to an existing
target.

### Idempotency

Update operations are designed to be safely repeatable.

For example:

```yaml
action: update
key: application.properties
value: "..."
```

can be executed repeatedly and the target value will converge to the
specified value.

---

## Changelog

### 1.0.0

* Initial plugin release.
* Added ConfigMap support.
* Added Secret support.
* Added folder execution mode.
* Added deployment-context execution mode.
* Added native ConfigMap/Secret resource processing.
* Added `ConfigMapSecretUpdate` processing.
* Added add/update/delete operations.
* Added embedded properties updates.
* Added embedded YAML updates.
* Added native resource merge behavior.
* Added complete native resource replacement with `replace=true`.
* Added creation of supported missing native resources.
* Added detailed workflow outputs.
* Added detailed resource-level error reporting.

```

One point I deliberately kept conservative in the documentation is **missing-target creation for `ConfigMapSecretUpdate`**. Your current plugin code still has `_create_source_document()` rejecting creation for `SourceType.UPDATE`; it only directly creates a missing target from a **native** source. :contentReference[oaicite:1]{index=1}

So the documentation above does **not** claim that every `ConfigMapSecretUpdate` can create a missing ConfigMap/Secret. That distinction is important for the TC04 behavior we worked through.
```
