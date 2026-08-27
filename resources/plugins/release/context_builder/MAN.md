# release.context_builder

------------------------------------------------------------------------

## Overview

The `release.context_builder` plugin analyses an Entropy release package
and produces a structured execution context for subsequent workflow
steps.

The plugin is responsible for resolving release-related information
needed by deployment and operational plugins. The generated context is
published as workflow outputs and may be consumed by later steps using
workflow interpolation.

The plugin can analyse:

- Release package content.
- Docker services and images requiring builds.
- OpenShift Deployment changes.
- OpenShift ConfigMap and Secret resources.
- OpenShift Service and Route resources when identified by the release
  analysis.
- Common-path/rsync operations.
- Database scripts.
- Database execution-plan information.

The plugin does **not** itself build Docker images, modify Deployment
YAML files, apply OpenShift resources, execute database scripts, or
perform rsync operations. It produces the context required by other
plugins to perform those operations.

------------------------------------------------------------------------

## Requirements

The plugin requires:

- A valid Entropy release package.
- A Docker repository containing the repository structure expected by
  the release analysis.
- A YAML repository containing the target OpenShift YAML files.
- A valid image tag.
- A valid release structure definition, either supplied explicitly or
  available as the plugin's bundled `structure.yaml`.
- Entropy workflow execution with the plugin installed and available.

The plugin uses Entropy's filesystem and archive services through the
plugin runtime.

No direct OpenShift login is performed by this plugin.

No direct Docker registry authentication is performed by this plugin.

No direct database connection is established by this plugin.

------------------------------------------------------------------------

## Arguments

| Argument | Required | Type | Default | Description |
|---|---|---|---|---|
| `release` | Yes | `path` | --- | Release package to analyse. |
| `docker_repository` | Yes | `path` | --- | Docker repository used during release analysis. |
| `yaml_repository` | Yes | `path` | --- | YAML repository containing target OpenShift resources. |
| `image_tag` | Yes | `string` | --- | Target image tag used when generating deployment context. |
| `structure` | No | `path` | Plugin `structure.yaml` | Optional release structure definition. |

### Argument Details

#### `release`

Path to the release package that must be analysed.

The value is resolved as an Entropy path argument and must identify a
release that can be processed by the release analyzer.

The plugin does not itself extract or modify the release permanently;
release processing is delegated to `ReleaseAnalyzer`.

#### `docker_repository`

Path to the Docker repository used by release analysis.

The analyzer uses this repository to determine Docker-related release
information, including services and image build requirements.

#### `yaml_repository`

Path to the repository containing the target OpenShift YAML resources.

The analyzer uses this repository when determining deployment and other
OpenShift resource changes.

#### `image_tag`

Target image tag associated with the release.

The value is passed to the release analyzer and is used when producing
deployment context, including target image information.

#### `structure`

Optional path to a release structure YAML file.

When omitted, the plugin uses the bundled structure definition located
beside the plugin:

```text
structure.yaml
```

The supplied structure file must conform to the release structure format
expected by the release structure resolver.

------------------------------------------------------------------------

## Workflow Configuration

The plugin is executed through a workflow step.

### Basic Configuration

```json
{
    "name": "Build Release Context",
    "plugin": "release.context_builder",
    "enabled": true,
    "on_failure": "abort",
    "tags": [
        "release",
        "context_builder"
    ],
    "arguments": {
        "release": "/path/to/release.zip",
        "docker_repository": "/path/to/docker/repository",
        "yaml_repository": "/path/to/yaml/repository",
        "image_tag": "1.0.0"
    }
}
```

------------------------------------------------------------------------

## Complete Workflow Example

```json
{
    "name": "Release Context Workflow",
    "version": "1.0.0",
    "description": "Build release execution context.",
    "variables": {
        "release": "/path/to/release.zip",
        "docker_repository": "/path/to/docker/repository",
        "yaml_repository": "/path/to/yaml/repository",
        "image_tag": "1.0.0"
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
        }
    ]
}
```

------------------------------------------------------------------------

## Workflow Variables

The plugin does not define its own persistent workflow variables.

Plugin arguments can receive values from workflow variables through
Entropy workflow interpolation.

### Example

```json
{
    "variables": {
        "release": "/path/to/release.zip",
        "docker_repository": "/path/to/docker/repository",
        "yaml_repository": "/path/to/yaml/repository",
        "image_tag": "1.1.10"
    }
}
```

The variables can then be referenced by plugin arguments:

```json
{
    "arguments": {
        "release": "${release}",
        "docker_repository": "${docker_repository}",
        "yaml_repository": "${yaml_repository}",
        "image_tag": "${image_tag}"
    }
}
```

The resolved values must satisfy the argument requirements described in
the **Arguments** section.

------------------------------------------------------------------------

## Vault Variables

The plugin does not directly require Vault values.

Workflow variables may still be resolved from Entropy Vault by the
workflow engine before the plugin receives its runtime arguments, if
such values are used by the workflow.

Example:

```json
{
    "variables": {
        "release": "${entv:RELEASE_PATH}"
    }
}
```

Do not place actual passwords, tokens, credentials, private keys, or
other sensitive values in workflow documentation.

------------------------------------------------------------------------

## Execution

The plugin executes in the following major stages:

1. Log the beginning of release context analysis.
2. Resolve the required `release` path.
3. Resolve the required `docker_repository` path.
4. Resolve the required `yaml_repository` path.
5. Resolve the required `image_tag`.
6. Resolve the optional `structure` path.
7. If `structure` is not supplied, use the plugin's bundled
   `structure.yaml`.
8. Create a `ReleaseAnalyzer`.
9. Analyse the release.
10. Store the generated context in plugin outputs.
11. Report the number of images requiring builds.
12. Report the number of planned deployment resource changes.
13. Report the number of discovered database scripts.
14. Report the number of rsync/common-path operations.
15. Return the generated context as a successful `PluginResult`.

The plugin itself performs analysis. Actual deployment, OpenShift
application, YAML replacement, Docker image transfer, rsync execution,
and database execution are handled by other workflow plugins.

------------------------------------------------------------------------

## Outputs

The plugin publishes the release analysis context into workflow
outputs.

The top-level output structure is:

```text
outputs
├── release
├── images
├── deployment
│   ├── required
│   ├── resources
│   │   ├── deployments
│   │   ├── configmaps
│   │   ├── secrets
│   │   ├── services
│   │   └── routes
│   └── operations
│       ├── apply
│       └── replace
├── common_paths
└── database
    ├── scripts
    └── execution_plan
```

The exact contents of these structures are produced by the
`ReleaseAnalyzer`.

### `release`

Contains release-related paths and information produced by analysis.

A typical context may contain values such as:

```json
{
    "package": "/path/to/release.zip",
    "root": "/path/to/release",
    "docker_source_release": "/path/to/release/App/services",
    "docker_dest_repo": "/path/to/docker/repository"
}
```

### `images`

Contains Docker image build information identified during release
analysis.

A typical image entry contains:

```json
{
    "app-1": {
        "dockerfile": "/path/to/repository/app-1/image/Dockerfile",
        "context": "/path/to/repository/app-1",
        "image_name": "app-1",
        "image_tag": "1.0.0"
    }
}
```

### `deployment`

Contains the OpenShift deployment execution context.

Example:

```json
{
    "required": true,
    "resources": {
        "deployments": [
            {
                "name": "app-1",
                "file": "deployments/app-1.yaml",
                "container": "app-1",
                "current_image": "quay.io/project/app-1:1.0.0",
                "target_image": "quay.io/project/app-1:1.1.0"
            }
        ],
        "configmaps": [],
        "secrets": [],
        "services": [],
        "routes": []
    },
    "operations": {
        "apply": [
            "/path/to/yaml/repository/deployments/app-1.yaml"
        ],
        "replace": []
    }
}
```

The deployment output is intended to be consumed by subsequent
deployment-related plugins.

### `common_paths`

Contains common-path/rsync operations identified from the release.

Example:

```json
[
    {
        "deployment": "app-1",
        "target": "/opt/app/jrxml",
        "source": "/path/to/release/App/openshift/common_path/jrxml"
    }
]
```

### `database`

Contains database scripts and execution-plan information discovered
during analysis.

Example:

```json
{
    "scripts": [],
    "execution_plan": null
}
```

### Example Workflow Output Consumption

A later workflow step can consume generated deployment context:

```json
{
    "arguments": {
        "deployments": "${steps.BuildReleaseContext.outputs.deployment.resources.deployments}"
    }
}
```

Likewise, OpenShift operations can consume the generated operation
lists:

```json
{
    "arguments": {
        "resource": "${steps.BuildReleaseContext.outputs.deployment.operations.apply}"
    }
}
```

------------------------------------------------------------------------

## Artifacts

The plugin does not explicitly create workflow artifacts in the supplied
implementation.

Its result metadata exposes the standard Entropy artifact collection:

```text
metadata.artifacts
```

This collection is populated from artifacts registered by the plugin
runtime. No plugin-specific artifact is created directly by the
`ContextBuilderPlugin` implementation shown here.

------------------------------------------------------------------------

## Examples

### Example 1 --- Basic Usage

```json
{
    "arguments": {
        "release": "/releases/TC01.zip",
        "docker_repository": "/repos/docker",
        "yaml_repository": "/repos/yamls/SIT",
        "image_tag": "1.1.10"
    }
}
```

This uses the plugin's bundled release structure definition.

### Example 2 --- Custom Structure

```json
{
    "arguments": {
        "release": "/releases/TC01.zip",
        "docker_repository": "/repos/docker",
        "yaml_repository": "/repos/yamls/SIT",
        "image_tag": "1.1.10",
        "structure": "/config/custom-structure.yaml"
    }
}
```

The custom structure replaces the plugin's default `structure.yaml`.

### Example 3 --- Using Workflow Variables

```json
{
    "variables": {
        "release": "/releases/TC01.zip",
        "docker_repository": "/repos/docker",
        "yaml_repository": "/repos/yamls/SIT",
        "image_tag": "1.1.10"
    },
    "steps": [
        {
            "name": "BuildReleaseContext",
            "plugin": "release.context_builder",
            "enabled": true,
            "on_failure": "abort",
            "tags": [],
            "arguments": {
                "release": "${release}",
                "docker_repository": "${docker_repository}",
                "yaml_repository": "${yaml_repository}",
                "image_tag": "${image_tag}"
            }
        }
    ]
}
```

### Example 4 --- Passing Context to Later Steps

```json
{
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

------------------------------------------------------------------------

## Validation

The plugin performs the following argument validation through Entropy's
typed argument interface:

- `release` is required and resolved as a path.
- `docker_repository` is required and resolved as a path.
- `yaml_repository` is required and resolved as a path.
- `image_tag` is required and resolved as a string.
- `structure` is optional and resolved as a path.
- A default structure file is selected when `structure` is omitted.

Additional release-content validation is performed by
`ReleaseAnalyzer` and the release structure resolver.

### Validation Errors

Failures during argument resolution or release analysis are converted
into an unsuccessful `PluginResult`.

The plugin records the exception message in the result's `errors`
collection.

The implementation does not expose a separate plugin-specific
validation-error schema.

------------------------------------------------------------------------

## Error Handling

The plugin catches `ContextBuilderPluginException` and returns:

```text
success = false
changed = false
errors = [error message]
```

Unexpected exceptions are also caught and returned as an unsuccessful
plugin result.

The plugin logs the exception and displays the error through the
Entropy message interface.

Because the plugin is normally executed as a workflow step, the
workflow's failure policy (`on_failure`) determines whether subsequent
workflow execution continues or aborts.

The plugin does not perform destructive rollback operations because its
primary responsibility is context generation.

------------------------------------------------------------------------

## Security

The plugin itself does not authenticate to OpenShift, Docker registries,
databases, or other external services.

Important considerations:

- Release paths may expose deployment or application information.
- Generated context can contain repository paths and deployment
  information.
- Database execution-plan data may contain operational information.
- Workflow outputs should be treated according to the sensitivity of the
  underlying release data.
- Do not place credentials directly into release context documentation.
- Do not log or persist sensitive workflow variables unnecessarily.

Vault values, when used by a workflow, are resolved by the workflow
engine rather than directly by this plugin.

------------------------------------------------------------------------

## Filesystem

| Path | Purpose |
|---|---|
| `release` | Release package supplied for analysis. |
| `docker_repository` | Docker repository used during analysis. |
| `yaml_repository` | Target OpenShift YAML repository. |
| `structure` | Optional release structure definition. |
| Plugin `structure.yaml` | Default structure definition used when no custom structure is supplied. |

The exact files read from the release package and repositories are
determined by `ReleaseAnalyzer` and the release structure definition.

The plugin's supplied implementation does not explicitly delete the
release, Docker repository, YAML repository, or structure file.

------------------------------------------------------------------------

## External Commands

The `ContextBuilderPlugin` implementation does not directly execute
operating-system commands.

No `docker`, `oc`, `kubectl`, `git`, `rsync`, or database CLI command is
executed by this plugin itself.

Those operations are represented in the generated context for
subsequent workflow steps.

------------------------------------------------------------------------

## External Services

The plugin does not directly connect to an external service.

It analyses local release and repository content and produces execution
context.

The generated context may subsequently be consumed by plugins that
interact with:

- Docker registries.
- OpenShift/Kubernetes.
- Git repositories.
- Remote filesystems.
- Databases.

Authentication for those services is outside the direct responsibility
of this plugin.

------------------------------------------------------------------------

## Side Effects

The plugin's primary side effect is generation of workflow output.

It:

- Reads the supplied release.
- Reads the Docker repository.
- Reads the YAML repository.
- Reads the release structure.
- Produces an in-memory execution context.
- Publishes that context through plugin outputs.
- Emits informational and error messages.

The supplied `ContextBuilderPlugin` implementation does not directly
modify Deployment YAML files or apply OpenShift resources.

------------------------------------------------------------------------

## Performance

Performance depends primarily on:

- Release package size.
- Number of release files.
- Number of Docker services.
- Number of YAML resources.
- Number of database scripts.
- Number of common-path resources.
- Filesystem performance.

The plugin performs release analysis synchronously during workflow
execution.

For large releases and repositories, analysis time may increase with
the number of files that must be inspected.

------------------------------------------------------------------------

## Limitations

Known limitations from the supplied implementation include:

- The plugin only supports the release structure understood by
  `ReleaseStructureResolver` and `ReleaseAnalyzer`.
- A missing or invalid release structure can cause analysis failure.
- Required paths and image tag must be supplied.
- The plugin does not itself perform the operations represented in the
  generated context.
- The exact resource discovery behavior depends on the implementation
  of `ReleaseAnalyzer`.
- The exact output contents are determined by release analysis and can
  vary between releases.
- The plugin does not provide a separate execution-plan validation layer
  beyond the validation performed by the underlying analysis components.

------------------------------------------------------------------------

## Troubleshooting

### Problem

`release` argument is missing or invalid.

**Cause**

The workflow did not provide a valid release path.

**Solution**

Provide the release package through the `release` argument.

```json
{
    "arguments": {
        "release": "/releases/TC01.zip"
    }
}
```

### Problem

Docker-related output is empty or incomplete.

**Cause**

The Docker repository or release structure does not match the expected
release layout.

**Solution**

Verify the `docker_repository` path and ensure the release follows the
configured structure.

### Problem

Deployment resources are missing from the generated context.

**Cause**

The release analyzer did not identify matching Deployment resources in
the supplied release/YAML repository.

**Solution**

Verify:

- `yaml_repository` points to the correct repository.
- The target YAML files exist.
- The release contains the expected OpenShift information.
- The release structure correctly identifies the OpenShift YAML path.

### Problem

The default structure file cannot be loaded.

**Cause**

The plugin's bundled `structure.yaml` is missing or invalid.

**Solution**

Verify that the plugin installation contains its `structure.yaml` beside
the plugin implementation.

Alternatively, supply an explicit `structure` argument.

### Problem

A later deployment plugin receives an empty resource list.

**Cause**

The context builder did not identify a corresponding resource, or the
workflow is referencing the wrong output path.

**Solution**

Inspect:

```text
${steps.BuildReleaseContext.outputs.deployment.resources}
```

and verify the specific resource collection being consumed.

For example:

```text
${steps.BuildReleaseContext.outputs.deployment.resources.deployments}
```

### Problem

A later OpenShift operation receives no resources.

**Cause**

The generated operation list is empty.

**Solution**

Inspect:

```text
${steps.BuildReleaseContext.outputs.deployment.operations.apply}
```

or:

```text
${steps.BuildReleaseContext.outputs.deployment.operations.replace}
```

depending on the required operation.

------------------------------------------------------------------------

## Notes

The plugin is designed as a **planning/context-building step** in a
larger Entropy release workflow.

A typical workflow uses it before operational plugins:

```text
Release Package
      |
      v
release.context_builder
      |
      +--> Docker build context
      |
      +--> Deployment context
      |
      +--> ConfigMap/Secret context
      |
      +--> Apply/Replace operations
      |
      +--> Rsync context
      |
      +--> Database context
      |
      v
Subsequent execution plugins
```

The generated context is therefore an interface between release
analysis and execution plugins.

When adding or changing release structure definitions, ensure that the
resulting context remains compatible with the plugins consuming it.

------------------------------------------------------------------------

## Changelog

### 1.0.0

- Initial plugin release.
- Added release package analysis.
- Added Docker image build context generation.
- Added OpenShift deployment context generation.
- Added ConfigMap and Secret resource context generation.
- Added Service and Route resource context generation.
- Added apply and replace operation context generation.
- Added common-path/rsync context generation.
- Added database script and execution-plan context generation.
- Added configurable release structure support.
- Added bundled default `structure.yaml`.
