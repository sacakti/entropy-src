# docker.clean

------------------------------------------------------------------------

## Overview

The `docker.clean` plugin performs controlled Docker storage cleanup.

Its purpose is to reclaim Docker storage while allowing workflows to
choose how aggressively cleanup is performed. By default, cleanup is
storage-aware: if available storage is already at or above the configured
minimum, no cleanup is performed unless `force=true`.

Supported cleanup strategies are:

- `tag` — remove Docker images whose full image reference contains a
  supplied pattern.
- `cache` — prune unused Docker builder cache.
- `unused` — prune unused Docker images.
- `complete` — prune all unused Docker resources and images.

The plugin can also operate in `dry_run` mode so that cleanup decisions
can be evaluated without removing Docker resources.

The plugin does not perform cleanup merely because the workflow invokes
it. Unless `force=true`, cleanup is skipped when the available Docker
storage satisfies `minimum_storage`.

------------------------------------------------------------------------

## Requirements

The plugin requires:

- Docker to be installed and available in `PATH`.
- A functioning Docker daemon.
- Permission to execute Docker commands.
- The `df` operating-system command.
- Access to Docker's storage filesystem.
- Entropy workflow execution with the plugin installed.

The plugin executes Docker commands through Entropy's shell service.

------------------------------------------------------------------------

## Arguments

| Argument | Required | Type | Default | Description |
|---|---|---|---|---|
| `minimum_storage` | No | `integer` | `10` | Minimum available Docker storage in GB. |
| `cleanup` | No | `string` | `tag` | Cleanup strategy to execute. |
| `tag_pattern` | Conditional | `string` | `""` | Pattern used by `tag` cleanup to select images. |
| `force` | No | `boolean` | `false` | Run cleanup even when minimum storage is available. |
| `dry_run` | No | `boolean` | `false` | Do not remove Docker resources. |
| `confirm` | No | `boolean` | `false` | Required confirmation for `complete` cleanup. |

### Argument Details

#### `minimum_storage`

Defines the minimum amount of available storage, in GB, that should
remain available on Docker's storage filesystem.

Default:

```text
10
```

The value must be greater than zero.

If `force=false` and available storage is greater than or equal to this
value, cleanup is skipped.

#### `cleanup`

Selects the cleanup strategy.

Accepted values:

```text
tag
cache
unused
complete
```

The value is normalized to lowercase and surrounding whitespace is
removed.

Default:

```text
tag
```

#### `tag_pattern`

Pattern used by `cleanup=tag`.

The plugin obtains Docker image references in the form:

```text
repository:tag
```

and selects images whose complete reference contains `tag_pattern`.

The value must be non-empty when `cleanup=tag`.

The matching operation is a substring check; it is not a regular
expression.

Example:

```json
{
    "cleanup": "tag",
    "tag_pattern": "1.1.6"
}
```

#### `force`

Controls the storage threshold check.

Default:

```text
false
```

When `false`, cleanup runs only when available Docker storage is below
`minimum_storage`.

When `true`, the selected cleanup strategy runs regardless of available
storage.

#### `dry_run`

Controls whether destructive Docker operations are executed.

Default:

```text
false
```

When `true`, Docker resources are not removed.

For `tag` cleanup, matched image references are reported as resources that
would be removed.

For prune-based cleanup, the Docker prune command is not executed.

#### `confirm`

Confirmation flag required by the `complete` cleanup strategy.

Default:

```text
false
```

`cleanup=complete` requires:

```json
{
    "confirm": true
}
```

Without this value, plugin execution fails before the cleanup command is
run.

------------------------------------------------------------------------

## Workflow Configuration

The plugin is executed through a workflow step.

### Basic Configuration

```json
{
    "name": "Docker Cleanup",
    "plugin": "docker.clean",
    "enabled": true,
    "on_failure": "abort",
    "tags": [
        "docker",
        "cleanup"
    ],
    "arguments": {
        "minimum_storage": 10,
        "cleanup": "tag",
        "tag_pattern": "old",
        "force": false,
        "dry_run": false,
        "confirm": false
    }
}
```

------------------------------------------------------------------------

## Complete Workflow Example

```json
{
    "name": "Docker Cleanup Workflow",
    "version": "1.0.0",
    "description": "Clean Docker storage when required.",
    "variables": {},
    "steps": [
        {
            "name": "DockerCleanup",
            "plugin": "docker.clean",
            "enabled": true,
            "on_failure": "abort",
            "tags": [
                "docker",
                "cleanup"
            ],
            "arguments": {
                "minimum_storage": 10,
                "cleanup": "unused",
                "force": false,
                "dry_run": false,
                "confirm": false
            }
        }
    ]
}
```

------------------------------------------------------------------------

## Workflow Variables

The plugin arguments can use Entropy workflow variables.

### Example

```json
{
    "variables": {
        "minimum_storage": 20,
        "cleanup_type": "unused",
        "force_cleanup": false
    },
    "steps": [
        {
            "name": "DockerCleanup",
            "plugin": "docker.clean",
            "enabled": true,
            "on_failure": "abort",
            "arguments": {
                "minimum_storage": "${minimum_storage}",
                "cleanup": "${cleanup_type}",
                "force": "${force_cleanup}"
            }
        }
    ]
}
```

Variable values must resolve to values accepted by the corresponding
plugin argument type.

------------------------------------------------------------------------

## Vault Variables

The plugin does not directly consume Vault values.

A workflow may resolve values through Entropy Vault before passing them to
the plugin, where appropriate.

Example:

```json
{
    "variables": {
        "cleanup_pattern": "${entv:DOCKER_CLEANUP_PATTERN}"
    },
    "steps": [
        {
            "name": "DockerCleanup",
            "plugin": "docker.clean",
            "enabled": true,
            "arguments": {
                "cleanup": "tag",
                "tag_pattern": "${cleanup_pattern}"
            }
        }
    ]
}
```

The plugin itself does not retrieve Vault values.

Do not store passwords, tokens, credentials, or private keys in this
documentation.

------------------------------------------------------------------------

## Execution

The plugin executes in the following stages:

1. Display the start of Docker cleanup.
2. Resolve cleanup arguments.
3. Validate the configured cleanup strategy and related arguments.
4. Query Docker for its storage root.
5. Query filesystem availability for that storage root.
6. Publish initial storage and cleanup information to workflow outputs.
7. Compare available storage against `minimum_storage`, unless
   `force=true`.
8. Skip cleanup when the storage requirement is satisfied and force is
   disabled.
9. Execute the selected cleanup strategy when cleanup is required.
10. Measure Docker storage availability again.
11. Publish post-cleanup storage information.
12. Return a `PluginResult`.

The cleanup strategy determines the actual Docker operation.

### Storage-Aware Path

When:

```text
force=false
```

and:

```text
available_storage >= minimum_storage
```

the plugin returns successfully without removing Docker resources.

### Forced Path

When:

```text
force=true
```

the selected cleanup strategy runs regardless of available storage.

### Dry-Run Path

When:

```text
dry_run=true
```

the plugin evaluates the requested cleanup but does not execute
resource-removal commands.

------------------------------------------------------------------------

## Cleanup Strategies

### `tag`

Lists local Docker image references:

```bash
docker image ls --format "{{.Repository}}:{{.Tag}}"
```

The plugin removes every image whose complete reference contains
`tag_pattern`.

Images represented as:

```text
<none>:<none>
```

are excluded.

Each matching image is removed individually.

### `cache`

Runs Docker builder cache cleanup:

```bash
docker builder prune --force
```

This removes unused Docker builder cache according to Docker's prune
behavior.

### `unused`

Runs Docker image cleanup:

```bash
docker image prune --force
```

This removes unused Docker images according to Docker's prune behavior.

### `complete`

Runs:

```bash
docker system prune --all --force
```

This is the most aggressive cleanup strategy supported by the plugin.

Because it can remove multiple categories of unused Docker resources,
the plugin requires:

```text
confirm=true
```

before execution.

------------------------------------------------------------------------

## Outputs

The plugin publishes execution information through workflow outputs.

| Output | Type | Description |
|---|---|---|
| `cleanup` | `string` | Selected cleanup strategy. |
| `minimum_storage_gb` | `integer` | Configured minimum available storage. |
| `storage_before_gb` | `number` | Available storage before cleanup. |
| `force` | `boolean` | Whether cleanup was forced. |
| `dry_run` | `boolean` | Whether cleanup was a dry run. |
| `cleanup_required` | `boolean` | Indicates whether cleanup was required by the current execution path. |
| `items_removed` | `integer` | Number of items reported as removed. |
| `matched_images` | `list[string]` | Images matched by `tag` cleanup. |
| `storage_after_gb` | `number` | Available storage after cleanup. |
| `storage_reclaimed_gb` | `number` | Increase in available storage after cleanup. |
| `exit_code` | `integer` | Exit code of the most recently executed external command. |
| `success` | `boolean` | Success status of the most recently executed Docker command. |
| `stdout` | `string` | Standard output of the most recently executed Docker command. |
| `stderr` | `string` | Standard error of the most recently executed Docker command. |
| `duration` | `number` | Duration reported for the most recently executed shell command. |
| `errors` | `list[string]` | Cleanup errors when applicable. |

### Output Availability

The following outputs are initialized during normal execution:

```text
cleanup
minimum_storage_gb
storage_before_gb
force
dry_run
cleanup_required
items_removed
```

`storage_after_gb` and `storage_reclaimed_gb` are produced after the
cleanup strategy has been processed.

`matched_images` is produced for tag cleanup.

Command-related outputs such as `exit_code`, `success`, `stdout`,
`stderr`, and `duration` are updated whenever an external command is
executed.

### Example

```text
outputs:
    cleanup = "unused"
    minimum_storage_gb = 10
    storage_before_gb = 7.42
    storage_after_gb = 12.18
    storage_reclaimed_gb = 4.76
    force = false
    dry_run = false
    cleanup_required = false
    items_removed = 5
```

The exact values depend on the Docker environment.

------------------------------------------------------------------------

## Artifacts

The plugin does not explicitly create plugin-specific artifacts.

Its result metadata exposes the standard Entropy artifact collection:

```text
metadata.artifacts
```

Any artifacts registered by the surrounding plugin runtime are included
in this metadata.

------------------------------------------------------------------------

## Examples

### Example 1 --- Basic Usage

Run the default tag cleanup:

```json
{
    "arguments": {
        "cleanup": "tag",
        "tag_pattern": "old"
    }
}
```

Cleanup is storage-aware and runs only when available Docker storage is
below the configured 10 GB threshold.

### Example 2 --- Unused Image Cleanup

```json
{
    "arguments": {
        "cleanup": "unused",
        "minimum_storage": 20
    }
}
```

The plugin runs `docker image prune --force` when available storage is
below 20 GB.

### Example 3 --- Builder Cache Cleanup

```json
{
    "arguments": {
        "cleanup": "cache",
        "minimum_storage": 10
    }
}
```

### Example 4 --- Complete Cleanup

```json
{
    "arguments": {
        "cleanup": "complete",
        "confirm": true
    }
}
```

The `complete` strategy is destructive and explicitly requires
`confirm=true`.

### Example 5 --- Forced Cleanup

```json
{
    "arguments": {
        "cleanup": "unused",
        "force": true
    }
}
```

The cleanup executes regardless of the amount of available Docker
storage.

### Example 6 --- Dry Run

```json
{
    "arguments": {
        "cleanup": "tag",
        "tag_pattern": "1.1.6",
        "force": true,
        "dry_run": true
    }
}
```

Matching images are identified and reported, but they are not removed.

### Example 7 --- Using Workflow Variables

```json
{
    "variables": {
        "minimum_storage": 15,
        "cleanup": "unused"
    },
    "steps": [
        {
            "name": "DockerCleanup",
            "plugin": "docker.clean",
            "enabled": true,
            "on_failure": "abort",
            "arguments": {
                "minimum_storage": "${minimum_storage}",
                "cleanup": "${cleanup}"
            }
        }
    ]
}
```

------------------------------------------------------------------------

## Validation

The plugin validates:

- `minimum_storage` must be greater than zero.
- `cleanup` must be one of:
  - `tag`
  - `cache`
  - `unused`
  - `complete`
- `tag_pattern` is required for `cleanup=tag`.
- `complete` requires `confirm=true`.

### Validation Errors

Examples:

```text
Argument 'minimum_storage' must be greater than zero.
```

```text
Invalid cleanup type 'foo'. Expected one of: cache, complete, tag, unused.
```

```text
Argument 'tag_pattern' is required when cleanup is 'tag'.
```

```text
Cleanup type 'complete' is destructive and requires 'confirm=true'.
```

------------------------------------------------------------------------

## Error Handling

The plugin converts `CleanPluginException` into an unsuccessful
`PluginResult`.

The result contains:

```text
success = false
changed = false
errors = [error message]
```

Errors during individual tag-image removal are collected. If some images
are removed successfully while others fail:

- `success` is `false`.
- `changed` is `true` when at least one image was removed.
- The errors are returned in the result.

Docker command failures for prune operations return an unsuccessful
result.

The plugin also handles:

- Docker command not found.
- Docker command execution errors.
- Invalid Docker storage-root output.
- Empty Docker storage root.
- `df` failures.
- Invalid filesystem-storage output.
- Invalid storage values.

Workflow-level `on_failure` determines whether the surrounding workflow
continues after a failed plugin result.

------------------------------------------------------------------------

## Security

The plugin executes Docker and filesystem commands using the Entropy
shell service.

Important security considerations:

- Docker access generally grants significant control over the local
  container environment.
- The plugin can remove Docker resources.
- `complete` cleanup is intentionally protected by an explicit
  `confirm=true` requirement.
- `force=true` bypasses the storage threshold and should therefore be
  used deliberately.
- `dry_run=true` should be preferred when validating cleanup selection.
- Docker command output is written to the Entropy log.
- Avoid placing credentials or sensitive data in `tag_pattern`.
- The plugin does not directly handle Docker registry credentials.

------------------------------------------------------------------------

## Filesystem

The plugin does not use a configured Entropy application data directory
for cleanup.

It determines Docker's storage root dynamically by executing:

```bash
docker info --format "{{json .DockerRootDir}}"
```

It then checks filesystem availability using:

```bash
df -Pk <DockerRootDir>
```

The Docker storage filesystem is inspected but not directly modified
through Python file operations.

Actual cleanup is delegated to Docker.

------------------------------------------------------------------------

## External Commands

### Docker Storage Root

```bash
docker info --format "{{json .DockerRootDir}}"
```

Purpose:

- Determine the Docker storage root.
- Identify the filesystem whose available capacity should be measured.

### Filesystem Availability

```bash
df -Pk <DockerRootDir>
```

Purpose:

- Determine available storage on Docker's storage filesystem.
- The plugin converts the reported available kilobytes to GB.

### Tag Listing

```bash
docker image ls --format "{{.Repository}}:{{.Tag}}"
```

Purpose:

- Enumerate local Docker image references for tag-based cleanup.

### Tag Removal

```bash
docker image rm <image-reference>
```

Purpose:

- Remove each image selected by `tag_pattern`.

### Builder Cache Cleanup

```bash
docker builder prune --force
```

Purpose:

- Remove unused Docker builder cache.

### Unused Image Cleanup

```bash
docker image prune --force
```

Purpose:

- Remove unused Docker images.

### Complete Cleanup

```bash
docker system prune --all --force
```

Purpose:

- Remove unused Docker resources and images using Docker's system
  prune behavior.

The `complete` command is only permitted when `confirm=true`.

------------------------------------------------------------------------

## External Services

The plugin does not directly communicate with a remote external service.

It interacts with the local Docker daemon through the Docker CLI.

Docker daemon availability and permissions are therefore required.

No OpenShift, Kubernetes, Git, registry, database, or HTTP service is
directly accessed by this plugin.

------------------------------------------------------------------------

## Side Effects

Depending on configuration, the plugin may:

- Remove Docker images.
- Remove Docker builder cache.
- Remove unused Docker resources.
- Remove multiple categories of unused Docker resources when
  `cleanup=complete`.
- Increase available Docker storage.
- Write Docker command output to Entropy logs.

When `dry_run=true`, resource-removal side effects are suppressed.

When storage is already sufficient and `force=false`, no Docker cleanup
side effect occurs.

------------------------------------------------------------------------

## Performance

Performance depends primarily on:

- Number of local Docker images.
- Amount of Docker builder cache.
- Number of unused Docker resources.
- Docker daemon response time.
- Filesystem performance.

`tag` cleanup lists all local image references and may execute one
`docker image rm` command per matching image.

Prune-based cleanup delegates resource discovery and removal to Docker.

The plugin does not define its own timeout in the supplied
implementation; command execution behavior is provided by Entropy's
shell service.

------------------------------------------------------------------------

## Limitations

- Cleanup decisions are based on available storage reported for
  Docker's storage filesystem.
- `tag_pattern` uses substring matching, not regular-expression
  matching.
- Tag cleanup only considers image references returned by
  `docker image ls`.
- `complete` cleanup depends on Docker's `system prune` semantics.
- The plugin does not provide a Python-level preview of exactly what
  prune operations will remove.
- `items_removed` for prune operations is estimated from Docker command
  output.
- The plugin relies on Docker CLI availability.
- The plugin does not authenticate to Docker registries.
- The plugin does not directly manage remote Docker hosts.
- Exact cleanup results depend on the Docker daemon and its current
  resource state.

------------------------------------------------------------------------

## Troubleshooting

### Problem

```text
Docker is not available on this system.
```

**Cause**

The Docker executable cannot be found.

**Solution**

Install Docker and ensure the `docker` executable is available in
`PATH`.

### Problem

```text
Unable to determine Docker storage root
```

**Cause**

`docker info` failed.

**Solution**

Verify that:

- Docker is installed.
- The Docker daemon is running.
- The current user has permission to access Docker.

### Problem

```text
Argument 'tag_pattern' is required when cleanup is 'tag'.
```

**Cause**

`cleanup` is `tag`, but no pattern was supplied.

**Solution**

Provide:

```json
{
    "cleanup": "tag",
    "tag_pattern": "pattern"
}
```

### Problem

```text
Cleanup type 'complete' is destructive and requires 'confirm=true'.
```

**Cause**

Complete cleanup was requested without explicit confirmation.

**Solution**

Set:

```json
{
    "cleanup": "complete",
    "confirm": true
}
```

### Problem

No cleanup occurs even though the plugin executes successfully.

**Cause**

Available Docker storage is greater than or equal to
`minimum_storage` and `force=false`.

**Solution**

Either lower `minimum_storage` appropriately or set:

```json
{
    "force": true
}
```

Use `force=true` only when unconditional cleanup is intended.

### Problem

Dry-run reports no resource removal.

**Cause**

`dry_run=true` intentionally prevents destructive Docker commands.

**Solution**

Set:

```json
{
    "dry_run": false
}
```

when actual cleanup is required.

------------------------------------------------------------------------

## Notes

The plugin is intentionally storage-aware.

The normal operating model is:

```text
Check Docker storage
        |
        v
Available >= minimum?
    /          \
  Yes           No
   |             |
Skip cleanup   Run cleanup
   |             |
   +------<------+ 
          |
          v
Measure storage again
```

Use `dry_run=true` to inspect tag-based cleanup behavior before deleting
images.

Use `complete` only when broad Docker resource cleanup is explicitly
intended.

The plugin does not decide which cleanup strategy is appropriate for a
particular environment; the workflow author chooses the strategy through
the `cleanup` argument.

------------------------------------------------------------------------

## Changelog

### 1.0.0

- Initial plugin release.
- Added storage-aware Docker cleanup.
- Added configurable minimum storage threshold.
- Added tag-based image cleanup.
- Added Docker builder-cache cleanup.
- Added unused-image cleanup.
- Added complete Docker cleanup.
- Added forced cleanup.
- Added dry-run support.
- Added explicit confirmation for complete cleanup.
- Added Docker storage-before and storage-after reporting.
- Added cleanup and command execution outputs.
- Added controlled error handling.
