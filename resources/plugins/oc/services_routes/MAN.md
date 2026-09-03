# services_routes

## Overview

The `oc.services_routes` plugin creates OpenShift Service and Route YAML files in a repository. It performs repository file management only; it does not execute `oc` or contact an OpenShift cluster.

Currently supported:

- Create Service YAML files.
- Create Route YAML files.
- Validate resource kind and `metadata.name`.
- Prevent overwriting an existing target file.

## Requirements

- Accessible filesystem.
- Read permission for source YAML files.
- Write permission for destination paths.
- Valid YAML source files containing a single YAML object.
- No OpenShift login or cluster connectivity is required.
- No external command is executed.

## Arguments

| Argument | Required | Type | Default | Description |
|---|---|---|---|---|
| `resources` | Yes | `list` | --- | Service and Route resources to create. |

### Resource fields

| Field | Required | Type | Description |
|---|---|---|---|
| `name` | Yes | `string` | Expected resource name. |
| `kind` | Yes | `string` | `Service` or `Route`. |
| `action` | Yes | `string` | Currently only `CREATE`. |
| `source` | Yes | `string` | Source YAML path. |
| `repository` | Yes | `string` | Complete destination YAML file path. |

Example:

```json
{
    "resources": [
        {
            "name": "app1",
            "kind": "Service",
            "action": "CREATE",
            "source": "/home/devops/source/service.yaml",
            "repository": "/home/devops/repository/app1-service.yaml"
        },
        {
            "name": "app1",
            "kind": "Route",
            "action": "CREATE",
            "source": "/home/devops/source/route.yaml",
            "repository": "/home/devops/repository/app1-route.yaml"
        }
    ]
}
```

`kind` must be `Service` or `Route`. `action` currently supports only `CREATE` and is case-insensitive. The source YAML kind and `metadata.name` must match the requested resource.

## Workflow Configuration

```json
{
    "name": "Execute services_routes",
    "plugin": "oc.services_routes",
    "enabled": true,
    "on_failure": "abort",
    "tags": ["services_routes"],
    "arguments": {
        "resources": []
    }
}
```

## Complete Workflow Example

```json
{
    "name": "services_routes Workflow",
    "version": "1.0.0",
    "description": "Create OpenShift Service and Route YAML resources.",
    "variables": {},
    "steps": [
        {
            "name": "Create Services and Routes",
            "plugin": "oc.services_routes",
            "enabled": true,
            "on_failure": "abort",
            "tags": ["services_routes"],
            "arguments": {
                "resources": [
                    {
                        "name": "app1",
                        "kind": "Service",
                        "action": "CREATE",
                        "source": "/home/devops/source/service.yaml",
                        "repository": "/home/devops/repository/app1-service.yaml"
                    },
                    {
                        "name": "app1",
                        "kind": "Route",
                        "action": "CREATE",
                        "source": "/home/devops/source/route.yaml",
                        "repository": "/home/devops/repository/app1-route.yaml"
                    }
                ]
            }
        }
    ]
}
```

## Workflow Variables

Workflow variables may be referenced by plugin arguments where supported by the workflow engine.

```json
{
    "variables": {
        "source_dir": "/home/devops/source",
        "repository_dir": "/home/devops/repository"
    }
}
```

Example:

```json
{
    "name": "Create Services and Routes",
    "plugin": "oc.services_routes",
    "arguments": {
        "resources": [
            {
                "name": "app1",
                "kind": "Service",
                "action": "CREATE",
                "source": "${source_dir}/service.yaml",
                "repository": "${repository_dir}/app1-service.yaml"
            }
        ]
    }
}
```

## Vault Variables

The plugin does not require credentials, passwords, tokens, or other secret values. Vault variables are not required for normal operation.

Do not place actual credentials or secrets in this document.

## Execution

For each resource, the plugin:

1. Validates the resource object and fields.
2. Validates the supported kind and action.
3. Validates the source file.
4. Reads the YAML through the filesystem abstraction.
5. Validates the YAML object, kind, metadata, and name.
6. Verifies that the destination does not already exist.
7. Creates the destination YAML file.
8. Records resource-level success or failure.
9. Publishes aggregate outputs.

Resources are processed independently. A failure is recorded and subsequent resources can still be processed.

## Outputs

| Output | Type | Description |
|---|---|---|
| `success` | `boolean` | True when all resources succeed. |
| `resources_processed` | `integer` | Number processed. |
| `resources_succeeded` | `integer` | Number successfully created. |
| `resources_failed` | `integer` | Number that failed. |
| `changes` | `integer` | Number of files created. |
| `errors` | `list` | Resource-level errors. |

Example:

```text
outputs:
    success = true
    resources_processed = 2
    resources_succeeded = 2
    resources_failed = 0
    changes = 2
    errors = []
```

## Artifacts

No workflow artifacts are created by default. The metadata artifact map reflects any artifacts registered through the plugin framework.

## Examples

### Create a Service

```json
{
    "arguments": {
        "resources": [
            {
                "name": "app1",
                "kind": "Service",
                "action": "CREATE",
                "source": "/home/devops/source/service.yaml",
                "repository": "/home/devops/repository/app1-service.yaml"
            }
        ]
    }
}
```

### Create a Route

```json
{
    "arguments": {
        "resources": [
            {
                "name": "app1",
                "kind": "Route",
                "action": "CREATE",
                "source": "/home/devops/source/route.yaml",
                "repository": "/home/devops/repository/app1-route.yaml"
            }
        ]
    }
}
```

### Multiple Resources

```json
{
    "arguments": {
        "resources": [
            {
                "name": "app1",
                "kind": "Service",
                "action": "CREATE",
                "source": "/home/devops/source/service.yaml",
                "repository": "/home/devops/repository/app1-service.yaml"
            },
            {
                "name": "app1",
                "kind": "Route",
                "action": "CREATE",
                "source": "/home/devops/source/route.yaml",
                "repository": "/home/devops/repository/app1-route.yaml"
            }
        ]
    }
}
```

## Validation

The plugin validates:

- `resources` is a list.
- Each resource is an object.
- `name`, `kind`, `action`, `source`, and `repository` are non-empty strings.
- `kind` is `Service` or `Route`.
- `action` is `CREATE`.
- The source exists and is a file.
- The source contains a YAML object.
- Source `kind` matches the requested kind.
- Source contains `metadata` and `metadata.name`.
- Source `metadata.name` matches the requested name.
- The destination does not already exist.

### Validation Errors

```text
Argument 'resources' must be a list.
```

```text
Service/Route resource requires 'source'.
```

```text
Unsupported Service/Route kind 'Deployment'. Expected one of: Route, Service.
```

```text
Unsupported Service action 'UPDATE'. Expected one of: CREATE.
```

## Error Handling

Resource-level failures are returned in `errors`. A failure for one resource does not stop subsequent resources from being processed.

The plugin returns `success = false` when one or more resources fail. The workflow `on_failure` policy determines subsequent workflow behavior.

No external commands or network operations are performed.

## Security

The plugin does not authenticate to OpenShift, execute `oc`, or handle cluster credentials. It reads and writes files using the Entropy filesystem abstraction. Appropriate filesystem permissions are required.

## Filesystem

| Path | Purpose |
|---|---|
| `source` | Existing Service or Route YAML file. |
| `repository` | Complete destination YAML file path. |

The source must already exist and be readable. The destination must not already exist. Parent directories are created as required by the filesystem abstraction.

## External Commands

None. In particular, the plugin does not execute `oc apply`, `oc create`, `oc replace`, or `oc delete`.

Those cluster operations belong to the generic OpenShift plugin.

## External Services

None. The plugin does not directly access OpenShift, Kubernetes, Docker, Git, Vault, HTTP/HTTPS services, cloud services, or databases.

## Side Effects

The plugin can create destination directories and Service/Route YAML files. It does not modify existing targets, delete files, or contact a remote cluster.

## Performance

The plugin performs local YAML reads and writes. Performance is primarily affected by the number and size of resource files and filesystem performance.

## Limitations

- Only `Service` and `Route` are supported.
- Only `CREATE` is supported.
- Existing targets are not overwritten.
- Each resource currently represents one source YAML document.
- UPDATE is not implemented.
- Cluster operations are not performed.

## Troubleshooting

### Source does not exist

```text
Service source '/path/service.yaml' does not exist.
```

Verify the `source` path and ensure the file exists and is readable.

### Kind mismatch

```text
Service source '/path/service.yaml' must have kind 'Service'.
```

Ensure the workflow and source YAML specify the same kind.

### Name mismatch

If the workflow requests `app1` but the YAML has another `metadata.name`, update one so they match.

### Target already exists

```text
Service target '/path/repository/app1-service.yaml' already exists.
```

CREATE does not overwrite an existing target. Use a new target path or remove the existing file if replacement is intentionally required.

### Unsupported action

```text
Unsupported Service action 'UPDATE'. Expected one of: CREATE.
```

UPDATE is not currently implemented.

## Notes

`oc.services_routes` is a repository preparation plugin. Its output can be consumed by a later generic OpenShift operation:

```text
oc.services_routes
        |
        | creates
        v
Service/Route YAML files
        |
        v
oc.generic
        |
        | oc apply / oc replace
        v
OpenShift cluster
```

The `repository` field for CREATE is the complete destination file path, not the parent repository directory.

## Changelog

### 1.0.0

- Initial plugin release.
- Added Service YAML creation.
- Added Route YAML creation.
- Added kind and name validation.
- Added source YAML validation.
- Added protection against overwriting existing target files.
- Added resource-level execution results.
