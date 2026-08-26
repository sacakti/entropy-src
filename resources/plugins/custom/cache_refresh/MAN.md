# cache_refresh

------------------------------------------------------------------------

## Overview

`cache_refresh` is a custom Entropy plugin for coordinating OpenShift
service lifecycle operations when an application cache must be refreshed.

The plugin supports two execution paths:

- **Cache refresh (`rebuild=true`)** — optionally stop the complete
  service fleet, perform a controlled cache refresh on a designated
  cache service, and then restart the remaining services.
- **Service restart (`rebuild=false`)** — restart the configured
  services without performing a cache refresh.

The cache-refresh path follows a controlled sequence:

1. Optionally stop all configured services.
2. Stop the cache service when necessary.
3. Set the configured cache-refresh environment variable.
4. Start the cache service.
5. Wait for a configured application startup message.
6. Remove the cache-refresh environment variable.
7. Wait for the cache service to start again.
8. Restart the remaining services.
9. Wait until the services are ready.

The plugin does not use `oc rollout status` as its application startup
verification mechanism. Startup is verified using configured log
messages.

The plugin uses the supplied OpenShift kubeconfig and does not perform
`oc login`.

------------------------------------------------------------------------

## Requirements

- Entropy with the `cache_refresh` plugin installed.
- OpenShift CLI (`oc`) available in `PATH`.
- A valid OpenShift kubeconfig.
- An authenticated OpenShift session represented by the kubeconfig.
- Access to the target OpenShift namespace.
- Required permissions to inspect and modify deployments, inspect pods,
  and read pod logs.
- Configured deployment names must exist in the target namespace.
- Configured startup messages must be emitted by application logs.
- Network connectivity to the OpenShift cluster.

The plugin does not perform OpenShift authentication.

------------------------------------------------------------------------

## Arguments

| Argument | Required | Type | Default | Description |
|---|---|---|---|---|
| `kubeconfig` | Yes | `string/path` | --- | OpenShift kubeconfig used for all `oc` commands. |
| `namespace` | Yes | `string` | --- | OpenShift namespace containing the deployments. |
| `rebuild` | No | `boolean` | `false` | Selects cache-refresh mode when `true`; normal restart when `false`. |
| `stop_all_before_refresh` | No | `boolean` | `true` | When rebuilding, controls whether all services are stopped before refresh. |
| `mode` | No | `string` | `force` | Restart mechanism: `force` or `graceful`. |
| `services` | Yes | `array[string]` | --- | Ordered list of OpenShift deployment names. |
| `cache` | Conditional | `object` | --- | Cache-refresh configuration; required when `rebuild=true`. |
| `cache.deployment` | Conditional | `string` | --- | Deployment responsible for cache refresh; must be in `services`. |
| `cache.environment` | Conditional | `object` | --- | Temporary environment variable used during refresh. |
| `cache.environment.name` | Conditional | `string` | --- | Environment variable name. |
| `cache.environment.value` | Conditional | `string` | --- | Environment variable value. |
| `startup` | Yes | `object` | --- | Application startup verification configuration. |
| `startup.messages` | Yes | `array[string]` | --- | Log messages used to determine startup completion. |
| `startup.timeout` | No | `integer` | `300` | Maximum seconds to wait for startup. |
| `startup.poll_interval` | No | `integer` | `5` | Seconds between startup checks. |
| `parallel` | No | `boolean` | `false` | Whether remaining services are restarted in parallel. |

### Argument Details

#### `kubeconfig`

Path to the kubeconfig used by the plugin.

All OpenShift commands are executed with:

```text
KUBECONFIG=<kubeconfig>
```

The plugin does not execute `oc login`.

#### `namespace`

Target OpenShift namespace. It must be a non-empty string.

#### `rebuild`

Controls the execution path:

```json
"rebuild": true
```

performs the cache-refresh workflow.

```json
"rebuild": false
```

performs a normal service restart.

Default: `false`.

#### `stop_all_before_refresh`

Controls the initial shutdown when `rebuild=true`.

When `true`, all configured services are stopped before cache refresh.

When `false`, only the cache deployment is stopped before refresh.

Default: `true`.

This has no operational effect when `rebuild=false`.

#### `mode`

Accepted values:

- `force`
- `graceful`

The value is case-insensitive.

`force` uses explicit deployment scaling (`0 → 1`).

`graceful` uses `oc rollout restart`.

Default: `force`.

#### `services`

Ordered list of deployment names.

Each item must be a non-empty string and service names must be unique.
The cache deployment must be included when `rebuild=true`.

The order is significant when `parallel=false`.

#### `cache`

Required when `rebuild=true`.

Example:

```json
"cache": {
    "deployment": "app-1",
    "environment": {
        "name": "CACHE_REFRESH",
        "value": "true"
    }
}
```

#### `cache.deployment`

Deployment responsible for cache refresh. It must be present in
`services`.

#### `cache.environment.name`

Temporary environment variable name. It must be a valid environment
variable name, such as `CACHE_REFRESH`.

#### `cache.environment.value`

Temporary environment variable value. It must be a string.

#### `startup`

Controls application startup verification.

The plugin uses application log messages rather than `oc rollout status`.

#### `startup.messages`

Non-empty list of log messages indicating startup completion.

Example:

```json
"messages": [
    "Catalina server startup completed"
]
```

#### `startup.timeout`

Maximum startup wait time in seconds.

Default: `300`.

Must be a positive integer.

#### `startup.poll_interval`

Interval between startup checks in seconds.

Default: `5`.

Must be a positive integer and cannot exceed `startup.timeout`.

#### `parallel`

Controls restart of the remaining services.

`false` processes services sequentially.

`true` allows the remaining services to be started/restarted together.

The cache service remains a separately controlled part of the refresh
sequence.

------------------------------------------------------------------------

## Workflow Configuration

### Basic Configuration

```json
{
    "name": "Execute cache_refresh",
    "plugin": "custom.cache_refresh",
    "enabled": true,
    "on_failure": "abort",
    "tags": [
        "openshift",
        "cache"
    ],
    "arguments": {
        "kubeconfig": "/path/to/kubeconfig",
        "namespace": "SIT",
        "rebuild": true,
        "stop_all_before_refresh": true,
        "mode": "force",
        "services": [
            "app-1",
            "app-2"
        ],
        "cache": {
            "deployment": "app-1",
            "environment": {
                "name": "CACHE_REFRESH",
                "value": "true"
            }
        },
        "startup": {
            "messages": [
                "Catalina server startup completed"
            ],
            "timeout": 300,
            "poll_interval": 5
        },
        "parallel": true
    }
}
```

------------------------------------------------------------------------

## Complete Workflow Example

```json
{
    "name": "Cache Refresh Workflow",
    "version": "1.0.0",
    "description": "Refresh application cache and restart OpenShift services.",
    "variables": {},
    "steps": [
        {
            "name": "Cache Refresh",
            "plugin": "custom.cache_refresh",
            "enabled": true,
            "on_failure": "abort",
            "tags": [
                "openshift",
                "cache"
            ],
            "arguments": {
                "kubeconfig": "/path/to/kubeconfig",
                "namespace": "SIT",
                "rebuild": true,
                "stop_all_before_refresh": true,
                "mode": "force",
                "services": [
                    "app-1",
                    "app-2",
                    "app-3",
                    "app-4",
                    "app-5",
                    "app-6",
                    "app-7",
                    "app-8",
                    "app-9",
                    "app-10",
                    "app-11",
                    "app-12",
                    "app-13",
                    "app-14"
                ],
                "cache": {
                    "deployment": "app-1",
                    "environment": {
                        "name": "CACHE_REFRESH",
                        "value": "true"
                    }
                },
                "startup": {
                    "messages": [
                        "Catalina server startup completed"
                    ],
                    "timeout": 300,
                    "poll_interval": 5
                },
                "parallel": true
            }
        }
    ]
}
```

------------------------------------------------------------------------

## Workflow Variables

Plugin arguments can consume Entropy workflow variables.

```json
{
    "variables": {
        "namespace": "SIT",
        "kubeconfig": "/path/to/kubeconfig"
    }
}
```

Reference them from arguments:

```json
{
    "arguments": {
        "namespace": "${namespace}",
        "kubeconfig": "${kubeconfig}"
    }
}
```

Workflow interpolation is performed by the Entropy workflow engine.

------------------------------------------------------------------------

## Vault Variables

Vault values can be consumed through workflow variables.

Example:

```json
{
    "variables": {
        "kubeconfig": "${entv:SIT_KUBECONFIG}"
    }
}
```

Then:

```json
{
    "arguments": {
        "kubeconfig": "${kubeconfig}"
    }
}
```

Vault interpolation is handled by the Entropy workflow engine. The
plugin does not perform Vault authentication or lookups.

Do not place real credentials, tokens, private keys, or sensitive
kubeconfig material in documentation.

------------------------------------------------------------------------

## Execution

The plugin validates configuration before performing state-changing
OpenShift operations.

### Common stages

1. Validate arguments.
2. Resolve kubeconfig and namespace.
3. Verify the OpenShift session with `oc whoami`.
4. Verify namespace access.
5. Verify required permissions.
6. Execute the selected workflow.
7. Monitor service state and application startup.
8. Publish outputs, changes, and errors.

### Normal restart: `rebuild=false`

The configured services are restarted using the selected `mode`.

### Cache refresh: `rebuild=true`

When `stop_all_before_refresh=true`:

```text
Stop all services
        ↓
Perform cache refresh
        ↓
Restart remaining services
```

When `stop_all_before_refresh=false`:

```text
Stop cache service
        ↓
Perform cache refresh
        ↓
Restart remaining services
```

The cache refresh sequence is:

```text
Set CACHE_REFRESH
        ↓
Start cache service
        ↓
Wait for startup message
        ↓
Remove CACHE_REFRESH
        ↓
Wait for startup again
        ↓
Restart remaining services
        ↓
Wait for services to become ready
```

------------------------------------------------------------------------

## Outputs

Typical workflow outputs include:

| Output | Type | Description |
|---|---|---|
| `rebuild` | `boolean` | Whether cache-refresh mode was selected. |
| `stop_all_before_refresh` | `boolean` | Whether the full fleet is stopped before refresh. |
| `mode` | `string` | Resolved restart mode. |
| `services` | `array[string]` | Configured deployment names. |
| `parallel` | `boolean` | Resolved parallel setting. |
| `namespace` | `string` | Target namespace. |

Example:

```text
outputs:

    rebuild = true
    stop_all_before_refresh = true
    mode = "force"
    services = ["app-1", "app-2", "app-3"]
    parallel = true
    namespace = "SIT"
```

Outputs are intended for consumption by subsequent workflow steps.

------------------------------------------------------------------------

## Artifacts

The plugin does not currently produce workflow artifacts.

The artifact collection remains available for future implementation.

------------------------------------------------------------------------

## Examples

### Example 1 — Cache Refresh With Complete Service Shutdown

```json
{
    "arguments": {
        "kubeconfig": "/path/to/kubeconfig",
        "namespace": "SIT",
        "rebuild": true,
        "stop_all_before_refresh": true,
        "mode": "force",
        "services": [
            "app-1",
            "app-2",
            "app-3"
        ],
        "cache": {
            "deployment": "app-1",
            "environment": {
                "name": "CACHE_REFRESH",
                "value": "true"
            }
        },
        "startup": {
            "messages": [
                "Catalina server startup completed"
            ],
            "timeout": 300,
            "poll_interval": 5
        },
        "parallel": true
    }
}
```

### Example 2 — Cache Refresh Without Stopping All Services

```json
{
    "arguments": {
        "kubeconfig": "/path/to/kubeconfig",
        "namespace": "SIT",
        "rebuild": true,
        "stop_all_before_refresh": false,
        "mode": "force",
        "services": [
            "app-1",
            "app-2",
            "app-3"
        ],
        "cache": {
            "deployment": "app-1",
            "environment": {
                "name": "CACHE_REFRESH",
                "value": "true"
            }
        },
        "startup": {
            "messages": [
                "Catalina server startup completed"
            ]
        },
        "parallel": true
    }
}
```

### Example 3 — Normal Graceful Restart

```json
{
    "arguments": {
        "kubeconfig": "/path/to/kubeconfig",
        "namespace": "SIT",
        "rebuild": false,
        "mode": "graceful",
        "services": [
            "app-1",
            "app-2",
            "app-3"
        ],
        "startup": {
            "messages": [
                "Catalina server startup completed"
            ],
            "timeout": 300,
            "poll_interval": 5
        },
        "parallel": false
    }
}
```

### Example 4 — Using Workflow Variables

```json
{
    "variables": {
        "kubeconfig": "/path/to/kubeconfig",
        "namespace": "SIT",
        "restart_mode": "force"
    },
    "steps": [
        {
            "name": "Execute cache_refresh",
            "plugin": "custom.cache_refresh",
            "enabled": true,
            "on_failure": "abort",
            "tags": [
                "openshift",
                "cache"
            ],
            "arguments": {
                "kubeconfig": "${kubeconfig}",
                "namespace": "${namespace}",
                "rebuild": false,
                "mode": "${restart_mode}",
                "services": [
                    "app-1",
                    "app-2"
                ],
                "startup": {
                    "messages": [
                        "Catalina server startup completed"
                    ]
                }
            }
        }
    ]
}
```

### Example 5 — Using Vault Variables

```json
{
    "variables": {
        "kubeconfig": "${entv:SIT_KUBECONFIG}",
        "namespace": "SIT"
    },
    "steps": [
        {
            "name": "Execute cache_refresh",
            "plugin": "custom.cache_refresh",
            "enabled": true,
            "on_failure": "abort",
            "tags": [
                "openshift",
                "cache"
            ],
            "arguments": {
                "kubeconfig": "${kubeconfig}",
                "namespace": "${namespace}",
                "rebuild": true,
                "stop_all_before_refresh": true,
                "mode": "force",
                "services": [
                    "app-1",
                    "app-2"
                ],
                "cache": {
                    "deployment": "app-1",
                    "environment": {
                        "name": "CACHE_REFRESH",
                        "value": "true"
                    }
                },
                "startup": {
                    "messages": [
                        "Catalina server startup completed"
                    ]
                },
                "parallel": true
            }
        }
    ]
}
```

------------------------------------------------------------------------

## Validation

Validation is performed before state-changing operations.

The plugin validates:

- Required `kubeconfig`.
- Non-empty `namespace`.
- Boolean `rebuild`.
- Boolean `stop_all_before_refresh`.
- `mode` is `force` or `graceful`.
- Non-empty `services` list.
- Service names are strings.
- Service names are non-empty.
- Service names are unique.
- `cache` is required when `rebuild=true`.
- `cache.deployment` is non-empty and is included in `services`.
- `cache.environment` is an object.
- `cache.environment.name` is a valid environment variable name.
- `cache.environment.value` is a string.
- `startup` is an object.
- `startup.messages` is a non-empty list of strings.
- `startup.timeout` is a positive integer.
- `startup.poll_interval` is a positive integer.
- `startup.poll_interval` does not exceed `startup.timeout`.
- `parallel` is a boolean.

Runtime validation includes:

- `oc` availability.
- OpenShift authentication.
- Namespace access.
- Required OpenShift permissions.

### Validation Errors

Examples:

```text
Argument 'services' must not be empty.
```

```text
Unsupported mode 'restart'. Allowed values: force, graceful.
```

```text
Argument 'cache' must be an object when 'rebuild' is true.
```

```text
Cache deployment 'app-1' is not present in 'services'.
```

```text
'startup.timeout' must be a positive integer.
```

Validation failures occur before state-changing operations begin.

------------------------------------------------------------------------

## Error Handling

### Validation failures

Invalid configuration produces a failed `PluginResult` and no
OpenShift service lifecycle operation is started.

### OpenShift command failures

`oc` command failures are captured and reported as structured plugin
errors where supported.

Expected external-command failures should not result in an unhandled
Python traceback.

### Authentication failures

If `oc whoami` fails, the plugin reports an OpenShift authentication
failure. It does not attempt `oc login`.

### Permission failures

Missing permissions cause validation to fail before destructive
operations begin.

### Startup failures

If a configured startup message is not detected within the timeout,
the relevant operation fails.

### Partial-operation behavior

The plugin performs multiple state-changing operations. A failure can
therefore occur after earlier services have already been modified.

The workflow-level `on_failure` setting controls workflow continuation
after the plugin reports failure.

The plugin does not guarantee rollback of already completed OpenShift
operations.

### Cleanup

During normal cache refresh, the temporary environment variable is
removed after cache startup.

Automatic rollback is not guaranteed after an unexpected failure.

------------------------------------------------------------------------

## Security

- The kubeconfig may contain sensitive authentication material.
- Do not commit sensitive kubeconfigs to source control.
- Prefer Entropy Vault for sensitive values where appropriate.
- The plugin does not execute `oc login`.
- OpenShift RBAC controls authorization.
- Required permissions are checked before lifecycle operations.
- The temporary cache environment variable is removed during the normal
  refresh sequence.
- Commands are executed through Entropy's shell/process execution layer.
- The plugin does not persist OpenShift credentials.

------------------------------------------------------------------------

## Filesystem

| Path | Purpose |
|---|---|
| Supplied `kubeconfig` | OpenShift authentication/session configuration. |

The kubeconfig must be readable by the Entropy process.

The plugin does not modify or delete the kubeconfig.

No application files are created, modified, or deleted by this plugin.

------------------------------------------------------------------------

## External Commands

The plugin executes the OpenShift CLI through Entropy's shell execution
facility.

### Session verification

```bash
oc whoami
```

### Permission verification

```bash
oc auth can-i get deployments -n <namespace>
oc auth can-i update deployments -n <namespace>
oc auth can-i patch deployments -n <namespace>
oc auth can-i get pods -n <namespace>
oc auth can-i get pods/log -n <namespace>
```

### Graceful restart

```bash
oc rollout restart deployment/<deployment> -n <namespace>
```

### Force stop

```bash
oc scale deployment/<deployment> --replicas=0 -n <namespace>
```

### Force start

```bash
oc scale deployment/<deployment> --replicas=1 -n <namespace>
```

### Set cache environment

```bash
oc set env deployment/<deployment> <NAME>=<VALUE> -n <namespace>
```

### Remove cache environment

```bash
oc set env deployment/<deployment> <NAME>- -n <namespace>
```

All commands use the supplied kubeconfig through the `KUBECONFIG`
environment variable.

------------------------------------------------------------------------

## External Services

### OpenShift

The plugin communicates with an OpenShift cluster to:

- Manage deployments.
- Scale deployments.
- Restart deployments.
- Set and remove deployment environment variables.
- Inspect pods.
- Read application logs.
- Verify startup.

Authentication is provided by the supplied kubeconfig.

The Entropy host must be able to reach the OpenShift API server.

OpenShift authentication, authorization, API, or connectivity failures
cause the relevant operation to fail.

------------------------------------------------------------------------

## Side Effects

The plugin can:

- Scale deployments to zero replicas.
- Scale deployments back to one replica.
- Restart deployments.
- Add temporary environment variables.
- Remove temporary environment variables.
- Create new application pods through deployment operations.
- Stop application instances.
- Start application instances.
- Read application pod logs.
- Contact the OpenShift API server.

When `rebuild=true` and `stop_all_before_refresh=true`, the plugin can
temporarily stop the complete configured service fleet.

------------------------------------------------------------------------

## Performance

Performance depends primarily on:

- OpenShift API response time.
- Pod scheduling time.
- Container startup time.
- Application startup time.
- Log availability.
- Number of configured services.
- `parallel` setting.
- Startup timeout and polling interval.

Sequential processing can take substantially longer than parallel
processing.

Parallel processing can reduce total restart time but increases
simultaneous OpenShift activity.

------------------------------------------------------------------------

## Limitations

- Requires the OpenShift CLI (`oc`).
- Requires a valid authenticated kubeconfig.
- Does not perform `oc login`.
- Depends on OpenShift RBAC.
- Startup verification depends on application log messages.
- Incorrect startup messages can cause startup verification to fail.
- Does not use `oc rollout status` for application startup verification.
- Force restart uses `0 → 1` replicas and therefore assumes the
  deployment should run with one replica after the operation.
- Can cause service interruption.
- Partial execution can leave services in different lifecycle states.
- Automatic rollback is not guaranteed.
- `cache.deployment` must be present in `services` when rebuilding.

------------------------------------------------------------------------

## Troubleshooting

### Problem

```text
OpenShift CLI 'oc' was not found.
```

**Cause**

The OpenShift CLI is not installed or is not available in `PATH`.

**Solution**

Install the OpenShift CLI and ensure `oc` is available to Entropy.

### Problem

```text
OpenShift authentication is not available.
```

**Cause**

The supplied kubeconfig does not represent an authenticated session.

**Solution**

Authenticate with OpenShift outside the plugin and supply the valid
kubeconfig.

### Problem

```text
Current OpenShift user does not have permission ...
```

**Cause**

The OpenShift user lacks the required RBAC permission.

**Solution**

Grant the required permission in the target namespace or use an
appropriately authorized identity.

### Problem

Startup timeout is reached.

**Cause**

The configured startup message was not detected within
`startup.timeout`.

Possible causes:

- Application startup is taking longer than expected.
- Startup message is incorrect.
- Message is emitted by another container.
- Pod logs are unavailable.
- Application failed during startup.

**Solution**

Inspect application logs, verify the startup message, and increase
`startup.timeout` when appropriate.

### Problem

Cache refresh does not occur.

**Cause**

The cache environment variable may not have been applied, or the cache
service may not have restarted after it was set.

**Solution**

Verify:

- `cache.deployment`
- `cache.environment.name`
- `cache.environment.value`
- OpenShift permissions
- Application startup logs

### Problem

Services remain unavailable after a failure.

**Cause**

The plugin performs multiple state-changing operations and does not
guarantee rollback of completed operations.

**Solution**

Inspect deployment and pod state in OpenShift and manually restore the
required services if necessary.

------------------------------------------------------------------------

## Notes

- Treat `rebuild=true` with `stop_all_before_refresh=true` as a
  potentially disruptive maintenance operation.
- Validate the service list before running in production.
- The cache deployment must be explicitly identified.
- Use `parallel=true` when services can safely start concurrently.
- Use `parallel=false` when service dependencies require ordered
  startup.
- Use `force` when explicit `0 → 1` lifecycle control is required.
- Use `graceful` when deployment restart should use
  `oc rollout restart`.
- Configure deterministic startup messages that reliably appear in
  application logs.
- Keep startup timeouts appropriate for the target environment.
- The plugin relies on the OpenShift session represented by the supplied
  kubeconfig and does not authenticate itself.
- Prefer secure Vault-backed handling for sensitive kubeconfig values.
- The plugin coordinates application lifecycle operations; it does not
  itself implement application cache logic.

------------------------------------------------------------------------

## Changelog

### 1.0.0

- Initial plugin release.
- Added OpenShift session validation.
- Added configurable cache-refresh workflow.
- Added optional full service shutdown before cache refresh.
- Added graceful and force restart modes.
- Added sequential and parallel service processing.
- Added application startup verification using configured log messages.
- Added temporary cache-refresh environment variable management.
