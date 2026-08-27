# docker.generic

------------------------------------------------------------------------

## Overview

The `docker.generic` plugin executes generic Docker operations.

It provides a single workflow interface for the following operations:

- `login`
- `pull`
- `push`
- `tag`
- `inspect`
- `raw`

The plugin is intended for Docker operations that are outside the focused
responsibility of the `docker.build` plugin.

The plugin deliberately executes Docker commands locally through the
Entropy shell service. It does not provide Docker image building.

For `pull`, `push`, and `inspect`, the plugin accepts either:

- A list of Docker image references.
- A mapping compatible with the output produced by `docker.build`.

------------------------------------------------------------------------

## Requirements

The plugin requires:

- Docker installed on the execution system.
- The `docker` executable available in `PATH`.
- A functioning Docker daemon.
- Permission for the workflow user to execute the requested Docker
  operation.
- Entropy workflow execution with the plugin installed.

Additional requirements depend on the selected operation.

### `login`

The Docker registry must be reachable when registry authentication is
required.

### `pull`

The requested image must be available from the configured registry and
the Docker daemon must have network access to it.

### `push`

The user must already have the required registry authorization.

### `tag`

The source image must be available locally and the user must have
permission to create the requested local tag.

### `inspect`

The requested image must be available to Docker.

### `raw`

The supplied Docker command and arguments must be valid for the installed
Docker version.

------------------------------------------------------------------------

## Arguments

| Argument | Required | Type | Default | Description |
|---|---|---|---|---|
| `operation` | Yes | `string` | --- | Docker operation to execute. |
| `registry` | Conditional | `string` | --- | Registry used by the `login` operation. |
| `username` | Conditional | `string` | --- | Registry username for `login`. |
| `password` | Conditional | `string` | --- | Registry password for `login`. |
| `images` | Conditional | `list` or `dictionary` | --- | Images used by `pull`, `push`, or `inspect`. |
| `source` | Conditional | `string` | --- | Source image for `tag`. |
| `target` | Conditional | `string` | --- | Target image tag for `tag`. |
| `command` | Conditional | `string` | --- | Docker subcommand for `raw`. |
| `arguments` | No | `list[string]` | `[]` | Arguments passed to the `raw` Docker command. |

### Argument Details

#### `operation`

Selects the Docker operation.

Accepted values are:

```text
login
pull
push
tag
inspect
raw
```

The value is normalized to lowercase before dispatch.

Any other value causes validation failure.

#### `registry`

Registry address used by the `login` operation.

The value must be a non-empty string.

Example:

```text
quay.io
```

This argument is required for `login`.

The plugin does not independently validate registry URL syntax.

#### `username`

Optional username for Docker registry login.

If `username` is supplied, `password` must also be supplied.

The value must be a non-empty string.

When credentials are supplied, the plugin passes the password to Docker
through standard input using Docker's `--password-stdin` option.

#### `password`

Optional password for Docker registry login.

If `password` is supplied, `username` must also be supplied.

The value must be a string.

The plugin does not require a password when neither username nor password
is supplied, allowing Docker to perform login using its normal interactive
or configured authentication behavior.

Sensitive values should be supplied through secure workflow variable
resolution where available.

#### `images`

Images used by the following operations:

```text
pull
push
inspect
```

Two formats are supported.

##### List format

```json
{
    "images": [
        "quay.io/project1/app-1:1.1.7",
        "quay.io/project1/app-2:1.1.7"
    ]
}
```

Every list element must be a non-empty string.

At least one image is required.

##### Docker build output mapping

The plugin also accepts a dictionary containing image build results,
such as the `images` output from `docker.build`.

Example:

```json
{
    "images": {
        "app-1": {
            "image_name": "app-1",
            "image_tag": "1.1.7",
            "image": "quay.io/project1/app-1:1.1.7"
        },
        "app-2": {
            "image_name": "app-2",
            "image_tag": "1.1.7",
            "image": "quay.io/project1/app-2:1.1.7"
        }
    }
}
```

Each mapping value must be a dictionary containing a valid non-empty
`image` field.

The mapping itself must contain at least one valid image.

#### `source`

Source image used by the `tag` operation.

The value must be a non-empty string.

Example:

```text
app-1:1.1.7
```

#### `target`

Target image reference created by the `tag` operation.

The value must be a non-empty string.

Example:

```text
quay.io/project1/app-1:1.1.7
```

#### `command`

Docker subcommand used by the `raw` operation.

The value must be a non-empty string.

The plugin automatically prepends:

```text
docker
```

Therefore:

```json
{
    "operation": "raw",
    "command": "images"
}
```

executes:

```bash
docker images
```

#### `arguments`

Additional arguments for the `raw` operation.

The default is an empty list.

Every value must be a string.

Example:

```json
{
    "operation": "raw",
    "command": "image",
    "arguments": [
        "inspect",
        "quay.io/project1/app-1:1.1.7"
    ]
}
```

The plugin executes:

```bash
docker image inspect quay.io/project1/app-1:1.1.7
```

------------------------------------------------------------------------

## Workflow Configuration

The plugin is executed through a workflow step.

### Basic Configuration

```json
{
    "name": "Docker Operation",
    "plugin": "docker.generic",
    "enabled": true,
    "on_failure": "abort",
    "tags": [
        "docker"
    ],
    "arguments": {
        "operation": "inspect",
        "images": [
            "quay.io/project1/app-1:1.1.7"
        ]
    }
}
```

------------------------------------------------------------------------

## Complete Workflow Example

```json
{
    "name": "Docker Generic Workflow",
    "version": "1.0.0",
    "description": "Execute a generic Docker operation.",
    "variables": {},
    "steps": [
        {
            "name": "InspectImages",
            "plugin": "docker.generic",
            "enabled": true,
            "on_failure": "abort",
            "tags": [
                "docker"
            ],
            "arguments": {
                "operation": "inspect",
                "images": [
                    "quay.io/project1/app-1:1.1.7"
                ]
            }
        }
    ]
}
```

------------------------------------------------------------------------

## Workflow Variables

Plugin arguments can consume workflow variables after the workflow engine
resolves them.

Example:

```json
{
    "variables": {
        "registry": "quay.io/project1",
        "image": "app-1:1.1.7"
    },
    "steps": [
        {
            "name": "PullImage",
            "plugin": "docker.generic",
            "enabled": true,
            "on_failure": "abort",
            "arguments": {
                "operation": "pull",
                "images": [
                    "${registry}/${image}"
                ]
            }
        }
    ]
}
```

A previous workflow step can also provide the image mapping produced by
`docker.build`.

Example:

```json
{
    "steps": [
        {
            "name": "BuildImages",
            "plugin": "docker.build",
            "enabled": true,
            "arguments": {
                "images": {
                    "app-1": {
                        "dockerfile": "/workspace/app-1/image/Dockerfile",
                        "context": "/workspace/app-1",
                        "image_name": "app-1",
                        "image_tag": "1.1.7"
                    }
                },
                "image_registry": "quay.io/project1"
            }
        },
        {
            "name": "PushImages",
            "plugin": "docker.generic",
            "enabled": true,
            "arguments": {
                "operation": "push",
                "images": "${steps.BuildImages.outputs.images}"
            }
        }
    ]
}
```

------------------------------------------------------------------------

## Vault Variables

The plugin does not directly access Vault.

Workflow variables may contain values resolved by the Entropy workflow
engine before they reach the plugin.

This is particularly useful for registry credentials.

Example:

```json
{
    "variables": {
        "registry_username": "${entv:DOCKER_USERNAME}",
        "registry_password": "${entv:DOCKER_PASSWORD}"
    },
    "steps": [
        {
            "name": "DockerLogin",
            "plugin": "docker.generic",
            "enabled": true,
            "arguments": {
                "operation": "login",
                "registry": "quay.io",
                "username": "${registry_username}",
                "password": "${registry_password}"
            }
        }
    ]
}
```

The plugin itself does not retrieve Vault values.

Do not place actual passwords, tokens, private keys, or other sensitive
values in this document.

------------------------------------------------------------------------

## Execution

The plugin executes the following major stages:

1. Verify that Docker is available.
2. Read and normalize the `operation` argument.
3. Validate that the requested operation is supported.
4. Dispatch to the corresponding operation handler.
5. Validate operation-specific arguments.
6. Execute the appropriate Docker command through the Entropy shell
   service.
7. Log Docker command output.
8. Populate operation-specific workflow outputs.
9. Return a `PluginResult`.

### Login

The plugin constructs:

```bash
docker login <registry>
```

When username and password are supplied, it additionally uses:

```text
--username <username>
--password-stdin
```

The password is supplied through command standard input.

### Pull

For each image:

```bash
docker pull <image>
```

Images are processed sequentially.

### Push

For each image:

```bash
docker push <image>
```

Images are processed sequentially.

### Inspect

For each image:

```bash
docker inspect <image>
```

Images are processed sequentially.

### Tag

The plugin executes:

```bash
docker tag <source> <target>
```

### Raw

The plugin prepends `docker` to the supplied command and arguments.

For:

```json
{
    "operation": "raw",
    "command": "ps",
    "arguments": [
        "-a"
    ]
}
```

it executes:

```bash
docker ps -a
```

------------------------------------------------------------------------

## Outputs

The outputs depend on the selected operation.

### `login`

| Output | Type | Description |
|---|---|---|
| `operation` | `string` | Always `login`. |
| `registry` | `string` | Registry supplied for login. |
| `success` | `boolean` | Docker login result. |
| `exit_code` | `integer` | Docker exit code. |

### `pull`, `push`, and `inspect`

| Output | Type | Description |
|---|---|---|
| `operation` | `string` | Operation executed. |
| `successful` | `list[string]` | Images processed successfully. |
| `failed` | `list[string]` | Images that failed. |
| `total` | `integer` | Number of images requested. |

### `tag`

| Output | Type | Description |
|---|---|---|
| `operation` | `string` | Always `tag`. |
| `source` | `string` | Source image. |
| `target` | `string` | Target image tag. |
| `success` | `boolean` | Docker tag result. |
| `exit_code` | `integer` | Docker exit code. |

### `raw`

| Output | Type | Description |
|---|---|---|
| `operation` | `string` | Always `raw`. |
| `command` | `string` | Command reported by the shell service. |
| `exit_code` | `integer` | Docker exit code. |
| `success` | `boolean` | Command success status. |
| `stdout` | `string` | Docker standard output. |
| `stderr` | `string` | Docker standard error. |
| `duration` | `number` | Command duration reported by the shell service. |

### Example

```text
outputs:
    operation = "push"
    successful = [
        "quay.io/project1/app-1:1.1.7"
    ]
    failed = []
    total = 1
```

Outputs are available to subsequent workflow steps through normal
workflow-step output interpolation.

------------------------------------------------------------------------

## Artifacts

The plugin does not explicitly create plugin-specific artifacts.

The result metadata contains an `artifacts` mapping, which is empty in
the implementation.

Therefore, there are no documented plugin-generated artifacts for
subsequent workflow steps.

------------------------------------------------------------------------

## Examples

### Example 1 --- Docker Login

Without explicit credentials:

```json
{
    "arguments": {
        "operation": "login",
        "registry": "quay.io"
    }
}
```

With credentials:

```json
{
    "arguments": {
        "operation": "login",
        "registry": "quay.io",
        "username": "${docker_username}",
        "password": "${docker_password}"
    }
}
```

When both credentials are supplied, the password is passed through
standard input rather than being appended directly to the Docker command.

### Example 2 --- Pull Multiple Images

```json
{
    "arguments": {
        "operation": "pull",
        "images": [
            "quay.io/project1/app-1:1.1.7",
            "quay.io/project1/app-2:1.1.7"
        ]
    }
}
```

### Example 3 --- Push Docker Build Output

```json
{
    "arguments": {
        "operation": "push",
        "images": {
            "app-1": {
                "image_name": "app-1",
                "image_tag": "1.1.7",
                "image": "quay.io/project1/app-1:1.1.7"
            }
        }
    }
}
```

This format is compatible with the image mapping produced by
`docker.build`.

### Example 4 --- Tag an Image

```json
{
    "arguments": {
        "operation": "tag",
        "source": "app-1:1.1.7",
        "target": "quay.io/project1/app-1:1.1.7"
    }
}
```

### Example 5 --- Inspect an Image

```json
{
    "arguments": {
        "operation": "inspect",
        "images": [
            "quay.io/project1/app-1:1.1.7"
        ]
    }
}
```

### Example 6 --- Raw Docker Command

```json
{
    "arguments": {
        "operation": "raw",
        "command": "images",
        "arguments": [
            "--format",
            "{{.Repository}}:{{.Tag}}"
        ]
    }
}
```

The resulting command is equivalent to:

```bash
docker images --format "{{.Repository}}:{{.Tag}}"
```

### Example 7 --- Using Workflow Variables

```json
{
    "variables": {
        "image": "quay.io/project1/app-1:1.1.7"
    },
    "steps": [
        {
            "name": "InspectImage",
            "plugin": "docker.generic",
            "enabled": true,
            "on_failure": "abort",
            "arguments": {
                "operation": "inspect",
                "images": [
                    "${image}"
                ]
            }
        }
    ]
}
```

------------------------------------------------------------------------

## Validation

The plugin validates:

- Docker availability.
- Presence of `operation`.
- Supported operation value.
- Login registry.
- Login username/password pairing.
- Login username type and content.
- Login password type.
- Image argument type.
- Non-empty image lists.
- Image reference types.
- Docker build image mappings.
- Valid `image` values inside build output mappings.
- Tag source.
- Tag target.
- Raw command.
- Raw command argument type.
- Raw command argument string values.

### Validation Errors

Examples:

```text
Docker is not available on this system.
```

```text
Argument 'operation' must be specified.
```

```text
Unsupported Docker operation 'example'. Supported operations: login, pull, push, tag, inspect, raw.
```

```text
Argument 'registry' must be a non-empty string.
```

```text
Arguments 'username' and 'password' must be provided together.
```

```text
Argument 'username' must be a non-empty string.
```

```text
Argument 'password' must be a string.
```

```text
Argument 'images' must be either a list of image references or a Docker build image mapping.
```

```text
Argument 'images' must contain at least one image.
```

```text
All values in 'images' must be non-empty strings.
```

```text
Image specification 'app-1' must be a dictionary.
```

```text
Image specification 'app-1' does not contain a valid 'image'.
```

```text
Argument 'source' must be a non-empty string.
```

```text
Argument 'target' must be a non-empty string.
```

```text
Argument 'command' must be a non-empty string.
```

```text
Argument 'arguments' must be a list.
```

```text
All values in 'arguments' must be strings.
```

------------------------------------------------------------------------

## Error Handling

`GenericPluginException` is converted into a failed `PluginResult`.

A validation failure returns:

```text
success = false
changed = false
errors = [error message]
```

### Docker Command Failures

Docker command failures are represented as failed `PluginResult` objects.

For `login`, `tag`, and `raw`, the plugin reports the Docker error as a
single failure message.

For `pull`, `push`, and `inspect`, the plugin records individual
successful and failed images.

Example:

```text
Docker push failed for 'quay.io/project1/app-1:1.1.7': <Docker error>
```

### Partial Operation Behavior

`pull`, `push`, and `inspect` process images sequentially.

A failed image does not immediately stop the loop. The plugin continues
processing the remaining images.

If one or more images fail:

```text
success = false
```

The `failed` output identifies the unsuccessful images.

For `pull` and `push`, successful operations still cause:

```text
changed = true
```

when at least one operation succeeds.

For `inspect`, successful inspection does not mark the plugin as changed.

### Other Operations

`login`, `tag`, and `raw` return failure when their Docker command fails.

------------------------------------------------------------------------

## Security

The plugin can execute Docker operations with the privileges available to
the Docker daemon and workflow user.

Important considerations:

- Docker access may provide significant control over the execution host.
- Registry passwords must not be hard-coded into workflow files.
- When username and password are supplied to `login`, the password is
  passed through standard input using `--password-stdin`.
- Docker may persist registry authentication according to the user's
  Docker configuration.
- The plugin does not itself store credentials.
- Docker command output is logged by the plugin.
- Raw Docker commands should be restricted to trusted workflow
  definitions.
- Do not expose sensitive credentials through `raw` arguments or other
  command-line arguments.

The `raw` operation is intentionally flexible and should therefore be
used only with trusted command definitions.

------------------------------------------------------------------------

## Filesystem

The plugin does not directly read or write user-specified files.

Docker itself may access local filesystem resources depending on the
operation and supplied Docker arguments.

For example, a `raw` command may reference files through Docker-supported
options.

The plugin itself does not:

- Create files.
- Modify files.
- Delete files.
- Create directories.
- Manage temporary files.

------------------------------------------------------------------------

## External Commands

The plugin executes the `docker` executable through the Entropy shell
service.

### Login

```bash
docker login <registry>
```

With credentials:

```bash
docker login <registry> --username <username> --password-stdin
```

The password is sent through standard input.

### Pull

```bash
docker pull <image>
```

### Push

```bash
docker push <image>
```

### Tag

```bash
docker tag <source> <target>
```

### Inspect

```bash
docker inspect <image>
```

### Raw

The plugin constructs:

```bash
docker <command> <arguments...>
```

The exact raw command is controlled by the workflow configuration.

------------------------------------------------------------------------

## External Services

### Docker

Purpose:

- Execute Docker image and registry operations.

Required authentication:

- Depends on the requested operation.
- `login` can establish registry authentication.
- `pull` and `push` may require existing registry credentials.

Connectivity:

- Registry-dependent operations require appropriate network
  connectivity.
- Local-only operations depend on the Docker daemon being available.

Failure behavior:

- Docker command failures are returned through the plugin result.

The plugin does not directly call OpenShift, Kubernetes, Git, databases,
or HTTP APIs.

------------------------------------------------------------------------

## Side Effects

Depending on the operation, the plugin may:

### `login`

- Modify Docker authentication state/configuration.

### `pull`

- Download image layers.
- Create/update local Docker images.
- Consume Docker storage.

### `push`

- Upload image layers and manifests to a registry.

### `tag`

- Create a local Docker image tag.

### `inspect`

- Read Docker image/container metadata.
- Does not intentionally modify Docker state.

### `raw`

- May have arbitrary Docker side effects depending on the command.

The `raw` operation should therefore be treated as potentially
state-changing.

------------------------------------------------------------------------

## Performance

Performance depends on the selected operation.

### Pull and Push

Performance is affected by:

- Image size.
- Number of layers.
- Registry response time.
- Network bandwidth.
- Registry load.
- Local Docker storage performance.

Multiple images are processed sequentially.

### Inspect

Inspection is generally lightweight but may depend on Docker daemon
responsiveness.

### Raw

Performance depends entirely on the supplied Docker command.

The plugin does not define a separate Docker operation timeout; execution
is provided by Entropy's shell service.

------------------------------------------------------------------------

## Limitations

- The plugin requires Docker to be installed and available in `PATH`.
- It does not build Docker images.
- It does not independently validate complete Docker image-reference
  grammar.
- `pull`, `push`, and `inspect` process images sequentially.
- `images` accepts either a list or a Docker-build-style mapping, not an
  arbitrary structure.
- Build mappings must contain an `image` field for every image.
- `username` and `password` must be supplied together.
- The `raw` operation intentionally provides broad command flexibility and
  therefore requires trusted workflow configuration.
- Docker behavior depends on the installed Docker CLI and daemon version.
- Registry connectivity and authorization are external prerequisites.
- The plugin does not provide its own retry mechanism.

------------------------------------------------------------------------

## Troubleshooting

### Problem

```text
Docker is not available on this system.
```

**Cause**

The `docker` executable cannot be found in `PATH`.

**Solution**

Install Docker and ensure the Docker CLI is available to the user running
Entropy.

### Problem

```text
Argument 'operation' must be specified.
```

**Cause**

The workflow did not provide an operation.

**Solution**

Supply one of:

```text
login
pull
push
tag
inspect
raw
```

### Problem

```text
Arguments 'username' and 'password' must be provided together.
```

**Cause**

Only one login credential was supplied.

**Solution**

Provide both credentials or omit both.

### Problem

```text
Argument 'images' must contain at least one image.
```

**Cause**

The image list or build mapping is empty.

**Solution**

Provide at least one image reference.

### Problem

```text
Image specification 'app-1' does not contain a valid 'image'.
```

**Cause**

The supplied Docker build output mapping does not contain a valid
`image` value.

**Solution**

Ensure the mapping contains:

```json
{
    "image": "quay.io/project1/app-1:1.1.7"
}
```

### Problem

```text
Docker push failed for '<image>': ...
```

**Cause**

The image may not exist locally, the registry may be unreachable, or
authentication/authorization may be insufficient.

**Solution**

Verify:

- The image exists locally.
- The image reference is correct.
- Docker registry authentication is valid.
- The registry is reachable.
- The account has permission to push the image.

### Problem

Docker login fails.

**Cause**

The registry, credentials, Docker configuration, or network connection
may be invalid.

**Solution**

Verify the registry and credentials and inspect the Docker stderr reported
by the plugin.

### Problem

A raw Docker command fails.

**Cause**

The command or arguments may not be valid for the installed Docker
version or environment.

**Solution**

Reproduce the generated command manually and verify Docker's command
syntax.

------------------------------------------------------------------------

## Notes

`docker.generic` is intended to complement `docker.build`.

A typical Docker workflow can be structured as:

```text
docker.build
      |
      v
Local tagged image
      |
      v
docker.generic (login)
      |
      v
docker.generic (push)
```

The image mapping produced by `docker.build` can be passed directly to
`docker.generic` for `push` or `inspect` operations because the generic
plugin understands the `image` field contained in each build result.

Use `raw` when a Docker operation is required that is not covered by the
dedicated operations. Because `raw` executes the supplied Docker
subcommand directly, it should be reserved for trusted workflow
configuration.

------------------------------------------------------------------------

## Changelog

### 1.0.0

- Initial plugin release.
- Added Docker registry login.
- Added Docker image pull.
- Added Docker image push.
- Added Docker image tagging.
- Added Docker image inspection.
- Added raw Docker command execution.
- Added support for multiple image operations.
- Added support for Docker build output image mappings.
- Added Docker availability validation.
- Added operation-specific argument validation.
- Added Docker command result logging.
- Added workflow output reporting.
- Added controlled Docker operation error handling.
