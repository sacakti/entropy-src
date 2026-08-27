# sync_yamls

------------------------------------------------------------------------

## Overview

`sync_yamls` is an Entropy plugin for synchronizing supported
OpenShift resources from a namespace into a YAML repository.

The plugin retrieves the following OpenShift resource types:

- Deployments
- ConfigMaps
- Secrets
- Services
- Routes

Each resource is normalized using Entropy's OpenShift structure
definition and written to the configured YAML repository.

The plugin also creates a common OpenShift resource index at:

```text
.entropy/resource_index.json
```

The index records the repository location of synchronized resources and
contains additional Deployment/container image information used by
other Entropy plugins.

### Purpose

The plugin provides a repository representation of resources currently
available in an OpenShift namespace.

It is intended for workflows that need to:

- Synchronize OpenShift resources into YAML files.
- Maintain a normalized YAML repository.
- Build an index of synchronized resources.
- Supply resource metadata to later workflow steps.
- Prepare a YAML repository for subsequent deployment operations.

### Important Behavior

Authentication is **not performed by this plugin**.

The plugin requires an existing OpenShift authentication context and
receives an explicit kubeconfig path.

The plugin verifies:

1. The current OpenShift user can be identified.
2. The user can read each supported resource type in the target
   namespace.

The plugin does not perform `oc login`, project selection, or session
creation.

------------------------------------------------------------------------

## Requirements

The plugin requires:

- Entropy runtime.
- OpenShift CLI (`oc`) installed and available in `PATH`.
- An existing authenticated OpenShift session.
- A valid kubeconfig file.
- Network connectivity to the OpenShift cluster.
- Permission to `get` the supported resource types in the target
  namespace.
- A writable YAML repository directory.
- The plugin's OpenShift structure definition.

### Required OpenShift Permissions

The current implementation verifies the following permissions using
`oc auth can-i`:

```text
get deployments
get configmaps
get secrets
get services
get routes
```

These permissions are checked in the configured namespace.

### Required Structure

The plugin expects the OpenShift normalization structure:

```text
<plugin structures>/openshift.yaml
```

The structure is loaded through the Entropy normalizer.

------------------------------------------------------------------------

## Arguments

| Argument | Required | Type | Default | Description |
|----------|----------|------|---------|-------------|
| `kubeconfig` | Yes | `path` | --- | Existing kubeconfig used for OpenShift operations. |
| `namespace` | Yes | `string` | --- | OpenShift namespace to synchronize. |
| `yaml_repository` | Yes | `string` | --- | Destination YAML repository. |
| `ignore_resources` | No | `dictionary` | Built-in defaults | Resources or data keys to exclude from synchronization. |

------------------------------------------------------------------------

## Argument Details

### `kubeconfig`

Specifies the kubeconfig file used by the OpenShift CLI.

Example:

```json
{
    "kubeconfig": "/home/user/.kube/config"
}
```

The plugin passes the value through the `KUBECONFIG` environment
variable when executing `oc`.

The kubeconfig must already exist and provide an authenticated
OpenShift context.

The plugin does not create or modify the kubeconfig.

------------------------------------------------------------------------

### `namespace`

Specifies the OpenShift namespace from which resources are retrieved.

Example:

```json
{
    "namespace": "sit"
}
```

The value:

- Must be a non-empty string.
- Is used for OpenShift resource retrieval.
- Is used for permission checks.

The namespace is passed to OpenShift commands with:

```bash
-n <namespace>
```

------------------------------------------------------------------------

### `yaml_repository`

Specifies the local directory into which synchronized YAML resources
are written.

Example:

```json
{
    "yaml_repository": "/opt/entropy/yamls/SIT"
}
```

The directory is created automatically when it does not exist.

The plugin creates resource subdirectories beneath it, such as:

```text
deployments/
configmaps/
secrets/
services/
routes/
```

It also creates:

```text
.entropy/
```

for the resource index.

------------------------------------------------------------------------

### `ignore_resources`

Controls which ConfigMaps and Secrets are excluded or have individual
data keys removed.

Example:

```json
{
    "ignore_resources": {
        "configmaps": {
            "names": [
                "my-configmap"
            ],
            "keys": [
                "password"
            ]
        },
        "secrets": {
            "names": [
                "my-secret"
            ],
            "keys": [
                "token"
            ]
        }
    }
}
```

Only these resource types are supported for ignore configuration:

```text
configmaps
secrets
```

Each supported resource type accepts:

```text
names
keys
```

Both values must be lists of strings.

### Default Ignore Configuration

The plugin always applies these built-in defaults:

```json
{
    "configmaps": {
        "names": [],
        "keys": [
            "kube.crt"
        ]
    },
    "secrets": {
        "names": [],
        "keys": []
    }
}
```

Therefore, `kube.crt` is removed from synchronized ConfigMap data by
default.

Custom values are merged with the defaults and duplicates are removed.

### Ignoring Complete Resources

A resource name listed under `names` is skipped completely.

Example:

```json
{
    "ignore_resources": {
        "configmaps": {
            "names": [
                "cluster-generated-config"
            ]
        }
    }
}
```

The ConfigMap is not written to the repository and is not added to the
resource index.

### Ignoring Data Keys

A key listed under `keys` is removed from the normalized resource's
`data` mapping.

This applies only to ConfigMaps and Secrets.

Example:

```json
{
    "ignore_resources": {
        "configmaps": {
            "keys": [
                "kube.crt"
            ]
        }
    }
}
```

The resource itself is still synchronized.

### Unsupported Ignore Types

Unsupported top-level resource types cause validation failure.

For example:

```json
{
    "ignore_resources": {
        "deployments": {
            "names": []
        }
    }
}
```

is rejected because ignore configuration is currently supported only
for ConfigMaps and Secrets.

------------------------------------------------------------------------

## Workflow Configuration

The plugin is executed through an Entropy workflow step.

### Basic Configuration

```json
{
    "name": "Sync OpenShift YAMLs",
    "plugin": "oc.sync_yamls",
    "enabled": true,
    "on_failure": "abort",
    "tags": [
        "openshift",
        "sync"
    ],
    "arguments": {
        "kubeconfig": "/home/user/.kube/config",
        "namespace": "sit",
        "yaml_repository": "/opt/entropy/yamls/SIT"
    }
}
```

Authentication must already be available in the supplied kubeconfig.

------------------------------------------------------------------------

## Complete Workflow Example

```json
{
    "name": "Synchronize OpenShift YAMLs",
    "version": "1.0.0",
    "description": "Synchronize OpenShift resources into a YAML repository.",
    "variables": {
        "kubeconfig": "/home/user/.kube/config",
        "namespace": "sit",
        "yaml_repository": "/opt/entropy/yamls/SIT"
    },
    "steps": [
        {
            "name": "Sync OpenShift YAMLs",
            "plugin": "oc.sync_yamls",
            "enabled": true,
            "on_failure": "abort",
            "tags": [
                "openshift",
                "sync"
            ],
            "arguments": {
                "kubeconfig": "${kubeconfig}",
                "namespace": "${namespace}",
                "yaml_repository": "${yaml_repository}"
            }
        }
    ]
}
```

------------------------------------------------------------------------

## Workflow Variables

Workflow variables can be used for plugin arguments.

Example:

```json
{
    "variables": {
        "kubeconfig": "/home/user/.kube/config",
        "namespace": "sit",
        "yaml_repository": "/opt/entropy/yamls/SIT"
    }
}
```

The variables can then be referenced as:

```json
{
    "arguments": {
        "kubeconfig": "${kubeconfig}",
        "namespace": "${namespace}",
        "yaml_repository": "${yaml_repository}"
    }
}
```

The workflow engine resolves workflow variables before the plugin
receives its runtime arguments.

------------------------------------------------------------------------

## Vault Variables

The plugin does not directly access Vault.

Vault-backed values can be resolved by the workflow engine before the
plugin receives its arguments.

For example:

```json
{
    "variables": {
        "kubeconfig": "${entv:openshift_kubeconfig}"
    }
}
```

The resolved value can then be supplied to:

```json
{
    "arguments": {
        "kubeconfig": "${kubeconfig}"
    }
}
```

The plugin itself does not perform Vault lookups.

Do not place actual passwords, tokens, credentials, private keys, or
other sensitive values in this document.

------------------------------------------------------------------------

## Execution

The plugin executes synchronization in the following major stages.

1. Initialize an empty resource index.
2. Resolve plugin arguments.
3. Validate required arguments.
4. Resolve the YAML repository path.
5. Create the repository if required.
6. Load the OpenShift normalization structure.
7. Verify the current OpenShift user with `oc whoami`.
8. Verify read access for all supported resource types.
9. Retrieve each supported resource type from the namespace.
10. Parse the OpenShift JSON response.
11. Process each returned resource.
12. Skip configured resources.
13. Normalize each resource using the OpenShift structure.
14. Remove configured ignored data keys from ConfigMaps and Secrets.
15. Write each normalized resource as an individual YAML file.
16. Add the resource to the resource index.
17. Register the generated YAML file as a workflow artifact.
18. Create `.entropy/resource_index.json`.
19. Add the index to workflow artifacts.
20. Publish synchronization outputs.
21. Return a successful plugin result.

### Resource Processing Order

Resources are processed in this order:

```text
deployments
configmaps
secrets
services
routes
```

------------------------------------------------------------------------

## OpenShift Access Verification

Before downloading resources, the plugin verifies the current
OpenShift identity:

```bash
oc whoami
```

The username is displayed through the Entropy message interface.

The plugin then verifies read permission for each supported resource
type:

```bash
oc auth can-i get deployments -n <namespace>
oc auth can-i get configmaps -n <namespace>
oc auth can-i get secrets -n <namespace>
oc auth can-i get services -n <namespace>
oc auth can-i get routes -n <namespace>
```

The plugin requires a positive `yes` response for every resource type.

If any permission check fails, synchronization stops before resource
retrieval.

------------------------------------------------------------------------

## Resource Synchronization

For each supported resource type, the plugin executes:

```bash
oc get <resource-type> -n <namespace> -o json
```

For example:

```bash
oc get deployments -n sit -o json
```

The returned JSON is parsed and its `items` list is processed.

Each valid resource is:

1. Checked for a valid `metadata.name`.
2. Checked against `ignore_resources`.
3. Normalized.
4. Written to the corresponding repository directory.
5. Added to the resource index.
6. Added to the workflow artifact collection.

------------------------------------------------------------------------

## YAML Repository Layout

A successful synchronization produces a repository structure similar
to:

```text
<yaml_repository>/
├── deployments/
│   ├── app-1.yaml
│   └── app-2.yaml
├── configmaps/
│   └── app-config.yaml
├── secrets/
│   └── app-secret.yaml
├── services/
│   └── app-service.yaml
├── routes/
│   └── app-route.yaml
└── .entropy/
    └── resource_index.json
```

Only resource types returned by OpenShift are populated.

------------------------------------------------------------------------

## Resource Normalization

The plugin uses the Entropy normalizer with:

```text
openshift.yaml
```

The structure is loaded from:

```text
<plugin structures>/openshift.yaml
```

Normalization occurs before the resource is written.

This allows repository YAML to follow the configured OpenShift
normalization rules instead of simply storing the raw OpenShift API
response.

------------------------------------------------------------------------

## Outputs

The plugin publishes the following outputs.

| Output | Type | Description |
|--------|------|-------------|
| `repository` | `string` | YAML repository path. |
| `namespace` | `string` | OpenShift namespace synchronized. |
| `resources` | `object` | Repository-relative YAML files grouped by resource type. |
| `deployment_index` | `string` | Path to `.entropy/resource_index.json`. |

### `resources`

The `resources` output contains one list for every supported resource
type:

```json
{
    "resources": {
        "deployments": [
            "deployments/app-1.yaml"
        ],
        "configmaps": [
            "configmaps/app-config.yaml"
        ],
        "secrets": [
            "secrets/app-secret.yaml"
        ],
        "services": [
            "services/app-service.yaml"
        ],
        "routes": [
            "routes/app-route.yaml"
        ]
    }
}
```

Paths are relative to the configured YAML repository.

### Example

```text
outputs:

    repository = "/opt/entropy/yamls/SIT"

    namespace = "sit"

    resources =
        {
            "deployments": [
                "deployments/app-1.yaml"
            ],
            "configmaps": [
                "configmaps/app-config.yaml"
            ],
            "secrets": [],
            "services": [
                "services/app-service.yaml"
            ],
            "routes": []
        }

    deployment_index =
        "/opt/entropy/yamls/SIT/.entropy/resource_index.json"
```

These outputs are intended for consumption by later workflow steps.

------------------------------------------------------------------------

## Resource Index

The plugin creates:

```text
.entropy/resource_index.json
```

under the YAML repository.

The index contains two top-level sections:

```json
{
    "resources": {},
    "deployments": {}
}
```

### `resources`

The `resources` section maps Kubernetes kinds and resource names to
repository-relative YAML files.

Example:

```json
{
    "resources": {
        "Deployment": {
            "app-1": {
                "file": "deployments/app-1.yaml"
            }
        },
        "ConfigMap": {
            "app-config": {
                "file": "configmaps/app-config.yaml"
            }
        }
    }
}
```

Supported kinds are:

```text
Deployment
ConfigMap
Secret
Service
Route
```

### `deployments`

The `deployments` section is populated for synchronized Deployments.

Each Deployment entry records:

- Deployment name.
- Container names.
- Container images.

Example:

```json
{
    "deployments": {
        "deployments/app-1.yaml": {
            "deployment": "app-1",
            "containers": {
                "app-1": {
                    "image": "quay.io/project/app-1:1.1.10"
                }
            }
        }
    }
}
```

This index is intended to be consumed by other Entropy plugins that
need to locate resources or inspect Deployment container images.

------------------------------------------------------------------------

## Artifacts

Each successfully written resource YAML file is registered as a
workflow artifact using its repository-relative path.

The resource index is also registered as an artifact.

Example artifact metadata:

```json
{
    "artifacts": {
        "deployments/app-1.yaml":
            "/opt/entropy/yamls/SIT/deployments/app-1.yaml",
        "configmaps/app-config.yaml":
            "/opt/entropy/yamls/SIT/configmaps/app-config.yaml",
        ".entropy/resource_index.json":
            "/opt/entropy/yamls/SIT/.entropy/resource_index.json"
    }
}
```

Artifacts are created when the corresponding files are successfully
written.

------------------------------------------------------------------------

## Examples

### Example 1 --- Basic Usage

```json
{
    "arguments": {
        "kubeconfig": "/home/user/.kube/config",
        "namespace": "sit",
        "yaml_repository": "/opt/entropy/yamls/SIT"
    }
}
```

This synchronizes all supported OpenShift resource types into the
repository using the default ignore configuration.

------------------------------------------------------------------------

### Example 2 --- Ignoring Resources

```json
{
    "arguments": {
        "kubeconfig": "/home/user/.kube/config",
        "namespace": "sit",
        "yaml_repository": "/opt/entropy/yamls/SIT",
        "ignore_resources": {
            "configmaps": {
                "names": [
                    "generated-config"
                ],
                "keys": [
                    "kube.crt"
                ]
            },
            "secrets": {
                "names": [
                    "generated-secret"
                ],
                "keys": [
                    "token"
                ]
            }
        }
    }
}
```

The named ConfigMap and Secret are skipped completely.

The configured keys are removed from other synchronized ConfigMaps and
Secrets.

------------------------------------------------------------------------

### Example 3 --- Using Workflow Variables

```json
{
    "variables": {
        "kubeconfig": "/home/user/.kube/config",
        "namespace": "sit",
        "repository": "/opt/entropy/yamls/SIT"
    },
    "steps": [
        {
            "name": "Sync OpenShift YAMLs",
            "plugin": "oc.sync_yamls",
            "enabled": true,
            "on_failure": "abort",
            "tags": [],
            "arguments": {
                "kubeconfig": "${kubeconfig}",
                "namespace": "${namespace}",
                "yaml_repository": "${repository}"
            }
        }
    ]
}
```

------------------------------------------------------------------------

### Example 4 --- Consuming the Resource Index

After synchronization, another workflow step can use:

```text
${steps.SyncOpenShiftYAMLs.outputs.deployment_index}
```

to obtain the generated resource index path.

The `resources` output can also be consumed directly:

```text
${steps.SyncOpenShiftYAMLs.outputs.resources}
```

------------------------------------------------------------------------

### Example 5 --- Synchronization for a Release Repository

```json
{
    "name": "Synchronize SIT YAML Repository",
    "plugin": "oc.sync_yamls",
    "enabled": true,
    "on_failure": "abort",
    "tags": [
        "openshift",
        "repository"
    ],
    "arguments": {
        "kubeconfig": "/home/user/.kube/sit/config",
        "namespace": "sit",
        "yaml_repository": "/opt/entropy/repos/SIT",
        "ignore_resources": {
            "configmaps": {
                "keys": [
                    "kube.crt"
                ]
            }
        }
    }
}
```

------------------------------------------------------------------------

## Validation

The plugin validates the following.

### Required Arguments

The following arguments must resolve to non-empty values:

```text
namespace
yaml_repository
```

`kubeconfig` is resolved as a required path argument.

### `ignore_resources`

The plugin validates:

- The value is a dictionary.
- Supported resource types are only `configmaps` and `secrets`.
- Each supported resource configuration is a dictionary.
- `names` is a list when supplied.
- `keys` is a list when supplied.
- Every `names` value is a string.
- Every `keys` value is a string.

### OpenShift Structure

The `openshift.yaml` structure must be loadable and must be a valid
normalizer structure.

### OpenShift Authentication

`oc whoami` must succeed.

### OpenShift Authorization

The current user must have permission to get:

```text
deployments
configmaps
secrets
services
routes
```

in the target namespace.

### OpenShift Responses

Each resource query must return valid JSON.

The JSON response must contain an `items` list.

Individual invalid items are skipped when their structure or metadata
cannot be processed.

------------------------------------------------------------------------

## Validation Errors

Examples include:

```text
Missing required argument(s): namespace, yaml_repository
```

```text
'ignore_resources' must be a dictionary.
```

```text
'ignore_resources.configmaps' must be a dictionary.
```

```text
'ignore_resources.configmaps.names' must be a list.
```

```text
All values in 'ignore_resources.configmaps.names' must be strings.
```

```text
Unsupported ignore resource type(s): deployments
```

```text
Unable to load OpenShift structure '<path>': ...
```

```text
OpenShift CLI 'oc' was not found. Please install the OpenShift CLI
and ensure it is available in PATH.
```

```text
Unable to determine the current OpenShift user.
```

```text
Current OpenShift user does not have permission to get deployments in
namespace 'sit'.
```

------------------------------------------------------------------------

## Error Handling

The plugin converts expected synchronization failures into a failed
`PluginResult`.

### Authentication Failure

If `oc whoami` fails, the plugin reports the OpenShift error and stops
execution.

### Authorization Failure

If any required `oc auth can-i` check fails or returns something other
than `yes`, synchronization stops.

All required resource permissions are checked before synchronization
begins.

### Resource Retrieval Failure

If an `oc get` operation fails for a resource type, the plugin reports
the OpenShift error and fails the plugin.

### Invalid JSON

If OpenShift returns invalid JSON, the corresponding synchronization
operation fails.

### Invalid Resource Items

Invalid individual resource items may be skipped with a warning when:

- The item is not an object.
- Its metadata is invalid.
- It has no valid resource name.

### Normalization Failure

If the normalizer cannot process a resource, the plugin reports the
resource type and resource name and fails execution.

### File Operation Failure

If the repository or generated YAML file cannot be created or written,
the plugin returns a failure.

### Index Failure

If the resource index cannot be written, the plugin fails.

### Cleanup

The plugin does not create temporary synchronization files requiring
special cleanup.

------------------------------------------------------------------------

## Security

### Authentication

Authentication is intentionally outside this plugin.

The plugin uses the supplied kubeconfig and does not execute login
operations.

### Authorization

The plugin explicitly verifies read permissions for every supported
resource category before synchronization.

### Secret Handling

Secrets are synchronized unless explicitly ignored.

Because the plugin writes Secret resources to the local repository,
users must ensure that the repository is appropriately protected.

Use `ignore_resources` when sensitive resource names or keys should not
be synchronized.

### Default Secret/ConfigMap Filtering

The default configuration removes:

```text
ConfigMap.data["kube.crt"]
```

The default configuration does not automatically remove Secret data.

### Kubeconfig

The kubeconfig path is supplied to `oc` through:

```text
KUBECONFIG
```

The plugin does not intentionally print the kubeconfig contents.

### Logging

OpenShift command invocation is logged at debug level.

OpenShift stderr is logged at warning level when present.

Users should consider that OpenShift command errors can contain
environment-specific information.

------------------------------------------------------------------------

## Filesystem

| Path | Purpose |
|------|---------|
| `<yaml_repository>` | Root synchronization repository. |
| `<yaml_repository>/deployments/` | Synchronized Deployment YAML files. |
| `<yaml_repository>/configmaps/` | Synchronized ConfigMap YAML files. |
| `<yaml_repository>/secrets/` | Synchronized Secret YAML files. |
| `<yaml_repository>/services/` | Synchronized Service YAML files. |
| `<yaml_repository>/routes/` | Synchronized Route YAML files. |
| `<yaml_repository>/.entropy/resource_index.json` | Common OpenShift resource index. |
| `<plugin structures>/openshift.yaml` | OpenShift normalization structure. |
| `kubeconfig` argument | Existing OpenShift kubeconfig. |

### Repository

The repository root is created automatically:

```text
mkdir(parents=True, exist_ok=True)
```

Resource directories are also created automatically when resources of
that type are found.

### Generated Resource Files

Each synchronized resource is written as:

```text
<yaml_repository>/<resource_type>/<resource_name>.yaml
```

### Resource Index

The index is written as:

```text
<yaml_repository>/.entropy/resource_index.json
```

The plugin does not explicitly delete old repository resource files
that are no longer present in OpenShift.

Therefore, the synchronization operation should be understood as
writing the currently retrieved resources rather than performing a
complete repository garbage-collection operation.

------------------------------------------------------------------------

## External Commands

The plugin executes the OpenShift CLI.

### Identify Current User

```bash
oc whoami
```

Purpose:

- Verify that authentication is available.
- Determine the current OpenShift user.

### Verify Resource Permissions

The plugin executes:

```bash
oc auth can-i get deployments -n <namespace>
oc auth can-i get configmaps -n <namespace>
oc auth can-i get secrets -n <namespace>
oc auth can-i get services -n <namespace>
oc auth can-i get routes -n <namespace>
```

Purpose:

- Verify that the current user can retrieve all supported resources.

### Retrieve Resources

For each resource type:

```bash
oc get <resource_type> -n <namespace> -o json
```

Examples:

```bash
oc get deployments -n sit -o json
oc get configmaps -n sit -o json
oc get secrets -n sit -o json
oc get services -n sit -o json
oc get routes -n sit -o json
```

The commands are executed with:

```text
KUBECONFIG=<configured kubeconfig>
```

------------------------------------------------------------------------

## External Services

### OpenShift

The plugin accesses an OpenShift cluster through the `oc` CLI.

OpenShift is used for:

- Authentication verification.
- Authorization verification.
- Resource retrieval.

### Authentication

The plugin relies on the existing authentication state represented by
the supplied kubeconfig.

It does not perform authentication itself.

------------------------------------------------------------------------

## Side Effects

The plugin can:

- Create the YAML repository directory.
- Create resource subdirectories.
- Write Deployment YAML files.
- Write ConfigMap YAML files.
- Write Secret YAML files.
- Write Service YAML files.
- Write Route YAML files.
- Create `.entropy/resource_index.json`.
- Register generated files as workflow artifacts.
- Contact the OpenShift API through `oc`.

The plugin does not:

- Modify OpenShift resources.
- Create OpenShift resources.
- Delete OpenShift resources.
- Modify the supplied kubeconfig.
- Perform OpenShift login.
- Select an OpenShift project.

------------------------------------------------------------------------

## Performance

Performance depends primarily on:

- Number of resources in the namespace.
- Size of OpenShift API responses.
- YAML normalization cost.
- Number of files written.
- Local filesystem performance.
- OpenShift API response time.

The plugin performs one `oc get ... -o json` request per supported
resource type and several authorization checks.

The five supported resource categories are processed sequentially.

Large namespaces may produce large JSON responses and many repository
files.

------------------------------------------------------------------------

## Limitations

- Only these resource types are synchronized:
  - Deployments
  - ConfigMaps
  - Secrets
  - Services
  - Routes
- Ignore configuration is supported only for ConfigMaps and Secrets.
- Authentication is not performed by the plugin.
- Project selection is not performed by the plugin.
- The supplied kubeconfig must already provide usable authentication.
- The user must have `get` permission for all supported resource types.
- Individual invalid OpenShift resource items may be skipped.
- The plugin does not explicitly remove stale YAML files from the
  repository.
- The plugin depends on the configured OpenShift normalization
  structure.
- The plugin depends on the OpenShift CLI being available in `PATH`.
- Synchronization is sequential.
- The plugin does not implement rollback for files already written if a
  later stage fails.
- Secret data may be written to the repository unless explicitly
  excluded through configuration.

------------------------------------------------------------------------

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

------------------------------------------------------------------------

### Problem

```text
OpenShift authentication is not available.
```

or an error returned by:

```bash
oc whoami
```

**Cause**

The supplied kubeconfig does not contain a valid authenticated
OpenShift context.

**Solution**

Authenticate using the appropriate OpenShift login process and provide
the resulting kubeconfig to the plugin.

The plugin itself does not perform login.

------------------------------------------------------------------------

### Problem

```text
Current OpenShift user does not have permission to get deployments
in namespace 'sit'.
```

**Cause**

The authenticated user does not have the required permission.

**Solution**

Verify:

```bash
oc auth can-i get deployments -n sit
```

Repeat for:

```text
configmaps
secrets
services
routes
```

The plugin requires access to all five resource types.

------------------------------------------------------------------------

### Problem

```text
Unable to retrieve configmaps from namespace 'sit'.
```

**Cause**

The OpenShift `get` request failed.

Possible causes include:

- Invalid namespace.
- Authentication failure.
- Authorization failure.
- Cluster connectivity problem.
- OpenShift API error.

**Solution**

Test manually:

```bash
oc get configmaps -n sit -o json
```

using the same kubeconfig.

------------------------------------------------------------------------

### Problem

```text
Unable to load OpenShift structure '<path>': ...
```

**Cause**

The `openshift.yaml` structure cannot be loaded or is invalid.

**Solution**

Verify that the plugin structure file exists and contains a valid
normalizer structure.

------------------------------------------------------------------------

### Problem

```text
Unable to create YAML repository '/path/...'
```

**Cause**

The repository cannot be created.

Possible causes include:

- Parent directory permissions.
- Invalid path.
- Filesystem failure.

**Solution**

Verify that the Entropy process can create and write to the requested
repository.

------------------------------------------------------------------------

### Problem

A ConfigMap or Secret is missing from the repository.

**Cause**

The resource may have been explicitly ignored through:

```text
ignore_resources.<type>.names
```

or it may not have been returned by OpenShift.

**Solution**

Inspect the plugin configuration and verify:

```bash
oc get configmaps -n <namespace>
oc get secrets -n <namespace>
```

------------------------------------------------------------------------

### Problem

A ConfigMap does not contain a specific data key after synchronization.

**Cause**

The key may be configured under:

```text
ignore_resources.configmaps.keys
```

The default configuration also removes:

```text
kube.crt
```

from ConfigMap data.

**Solution**

Review the ignore configuration if the key is required in the
repository.

------------------------------------------------------------------------

### Problem

The generated repository contains an unexpected old YAML file.

**Cause**

The plugin does not explicitly delete repository files for resources
that are no longer returned by OpenShift.

**Solution**

Remove stale repository files through an appropriate repository
maintenance process if complete mirroring is required.

------------------------------------------------------------------------

### Problem

The resource index is missing.

**Cause**

The index is created only after resource synchronization completes.

A failure during synchronization or index creation can result in an
unsuccessful plugin execution.

**Solution**

Inspect the plugin error and verify that the repository and `.entropy`
directory are writable.

------------------------------------------------------------------------

## Notes

### Single Responsibility

`sync_yamls` is responsible for synchronization only.

It does not perform:

- OpenShift login.
- Project selection.
- Deployment.
- Resource application.
- Resource replacement.

These operations should be handled by dedicated workflow steps or
plugins.

### Existing Authentication

The recommended workflow pattern is:

```text
Authenticate
     |
     v
Select project/context
     |
     v
sync_yamls
     |
     v
Consume generated YAML/index
```

The exact authentication and project-selection implementation depends on
the surrounding Entropy workflow.

### Resource Index Integration

The generated:

```text
.entropy/resource_index.json
```

is an important integration point.

It allows later plugins to locate synchronized resources without
scanning the entire YAML repository.

For Deployments, it also records container image information.

### Repository Safety

Because ConfigMaps and Secrets can contain sensitive information, the
destination YAML repository should be treated as potentially sensitive
data.

Use appropriate filesystem and repository access controls.

### Default Filtering

The plugin always retains the built-in ConfigMap ignore key:

```text
kube.crt
```

even when custom ignore configuration is supplied.

Custom ignore values are added to the defaults rather than replacing
them.

------------------------------------------------------------------------

## Changelog

### 1.0.0

- Initial plugin release.
- Added OpenShift resource synchronization.
- Added Deployment synchronization.
- Added ConfigMap synchronization.
- Added Secret synchronization.
- Added Service synchronization.
- Added Route synchronization.
- Added OpenShift user verification.
- Added namespace resource permission verification.
- Added configurable ConfigMap and Secret ignore rules.
- Added default `kube.crt` ConfigMap key exclusion.
- Added OpenShift resource normalization.
- Added per-resource YAML generation.
- Added `.entropy/resource_index.json`.
- Added Deployment container image indexing.
- Added workflow output reporting.
- Added workflow artifact registration.
- Authentication and project selection intentionally remain outside the
  plugin.
