# deployment

Update OpenShift Deployment YAML files: container image tags,
environment variables, volume mounts and volumes.

------------------------------------------------------------------------

## Overview

`oc.deployment` edits Deployment YAML files in a YAML repository on
disk. It does **not** talk to OpenShift: applying the changed files to a
cluster is done by a later step (for example `oc.generic`).

It changes four things on an existing Deployment:

| Field | What changes | Where |
| --- | --- | --- |
| `image` | Container image (tag) | `spec.template.spec.containers[].image` |
| `env` | Environment variables | `spec.template.spec.containers[].env` |
| `mounts` | Volume mounts | `spec.template.spec.containers[].volumeMounts` |
| `mountvolume` | Volumes | `spec.template.spec.volumes` |

and it can create a new Deployment file from a release YAML.

### Two modes

| Mode | Input | Typical use |
| --- | --- | --- |
| `deployments` | A list of Deployment entries, normally the output of `release.context_builder` | Release workflows |
| `folder` | A directory of `DeploymentUpdate` files and a directory of Deployment YAML files | One-off or manual updates |

### Release scenarios handled in `deployments` mode

| # | Release content | What `oc.deployment` does |
| --- | --- | --- |
| 1 | Service image changed (`App/services/<svc>/image`) | Moves the container to the new image tag |
| 2 | `DeploymentUpdate` with env/mounts/volume changes | Adds, updates or deletes those fields |
| 3 | 1 and 2 for the same Deployment | Applies the field changes and the new tag to the same file |
| 4 | `scripts/deploy/image_transfer.sh` pushes | Moves matching containers to the pushed tag |
| 5 | 2 and 4 together (including App-Published packages) | Applies the field changes and the new tag |
| 6 | New Deployment YAML in the release | Creates the Deployment file in the repository |

### Important behaviour

- Each Deployment entry is processed on its own. One failing entry does
  not stop the others, but the step reports `success: false`.
- The same Deployment may appear in several entries; each entry re-reads
  the file, so changes accumulate.
- Files are rewritten as YAML; multi-document files keep all their
  documents.

------------------------------------------------------------------------

## Requirements

- A YAML repository containing the Deployment files to update (usually
  synchronized with `oc.sync_yamls`).
- For `deployments` mode in a release workflow: a preceding
  `release.context_builder` step.
- Write access to the YAML repository.
- No OpenShift login, `oc` binary or network access is needed.

------------------------------------------------------------------------

## Arguments

| Argument | Required | Type | Default | Description |
| --- | --- | --- | --- | --- |
| `mode` | No | `string` | `folder` | `folder` or `deployments`. |
| `source` | In `folder` mode | `path` (directory) | --- | Directory of `DeploymentUpdate` files. |
| `target` | In `folder` mode | `path` (directory) | --- | Directory of Deployment YAML files to update. |
| `repository` | No | `path` (directory) | --- | YAML repository used for `UPDATE` entries that have no `repository`. |
| `deployments` | In `deployments` mode | `list` | `[]` | Deployment entries, normally from `release.context_builder`. |

`source`, `target` and `repository` are never asked for interactively;
leave them out when they do not apply.

### Argument Details

#### `mode`

- `folder`: read `DeploymentUpdate` files from `source` and apply them
  to matching Deployments found in `target`.
- `deployments`: apply each entry of `deployments`.

The value must be exactly `folder` or `deployments` (case does not
matter). `deployment` (singular) is rejected.

#### `source`

`folder` mode only. A directory; every `.yaml`/`.yml` file in it is read
and each document must be a `DeploymentUpdate`.

#### `target`

`folder` mode only. A directory of Deployment YAML files. For each
`DeploymentUpdate`, the Deployment with the same `metadata.name` is
searched for in the `.yaml`/`.yml` files of this directory (not in
sub-directories).

#### `repository`

`deployments` mode only. The YAML repository directory, for example
`/opt/yamls/SIT`. Used as the entry's `repository` when an `UPDATE`
entry has none. Entries produced by `release.context_builder` always
carry their own `repository`, so this is a fallback.

#### `deployments`

A list of entries (see [Deployment entries](#deployment-entries)). In a
release workflow pass the context builder output:

```json
{
    "deployments": "${steps.BuildReleaseContext.outputs.deployment.resources.deployments}"
}
```

An empty list ends the step successfully with nothing to do.

------------------------------------------------------------------------

## How the input reaches this plugin

```text
release ZIP
   │
   ▼
release.context_builder ──► outputs.deployment.resources.deployments
   │                          (list of Deployment entries)
   │
   ▼  "deployments": "${steps.BuildReleaseContext.outputs.deployment.resources.deployments}"
oc.deployment (mode: deployments)
   │  edits <yaml_repository>/<file>
   ▼
oc.generic / apply step  ──► OpenShift
```

`release.context_builder` decides **what** changes; `oc.deployment`
**makes** the change in the YAML repository. The two plugins never call
each other; the workflow passes the list from one step to the next.

Where each entry comes from:

| Entry | Produced from | Carries |
| --- | --- | --- |
| Image from Docker build | Changed `App/services/<svc>/image` + resource index | `container`, `target_image` |
| Field changes | `DeploymentUpdate` in `App/openshift/yamls` or `App/yamls` | `operations` |
| Image from transfer | `docker push` lines in `scripts/deploy/image_transfer.sh` | `container`, `target_image`, `image_transfer: true` |
| New Deployment | Plain `kind: Deployment` YAML not yet in the repository | `action: CREATE`, `source` |

See the `release.context_builder` manual for how each is detected.

------------------------------------------------------------------------

## Deployment entries

Every entry has `name`, `kind` and `action`. The other keys depend on
the kind of change.

### Image update

```json
{
    "name": "app-1",
    "kind": "Deployment",
    "action": "UPDATE",
    "repository": "/opt/yamls/SIT",
    "file": "deployments/app-1.yaml",
    "container": "app",
    "current_image": "quay.io/sacakti/app-1:1.0.0",
    "target_image": "quay.io/sacakti/app-1:1.1.10"
}
```

Sets `image` of container `app` to `target_image`. `current_image` is
informational.

### Field changes

```json
{
    "name": "app-1",
    "kind": "Deployment",
    "action": "UPDATE",
    "repository": "/opt/yamls/SIT",
    "file": "deployments/app-1.yaml",
    "operations": [
        {"action": "add", "field": "env", "container": "app",
         "value": {"name": "APP_MODE", "value": "production"}},
        {"action": "delete", "field": "env", "container": "app",
         "value": {"name": "LEGACY_FLAG"}}
    ]
}
```

Applies each operation in order (see [Operations](#operations)).

### Create

```json
{
    "name": "app-2",
    "kind": "Deployment",
    "action": "CREATE",
    "source": "/releases/H010/App/openshift/yamls/app-2.yaml",
    "repository": "/opt/yamls/SIT/deployments/app-2.yaml"
}
```

Copies the release Deployment to `repository` (the **target file path**
for `CREATE`). Optional `container` + `target_image` set the image of
that container in the new file; they must be given together.

### Keys

| Key | Used by | Meaning |
| --- | --- | --- |
| `name` | all | Deployment `metadata.name`. |
| `kind` | all | `Deployment`. |
| `action` | all | `UPDATE` or `CREATE`. |
| `repository` | all | `UPDATE`: YAML repository directory. `CREATE`: target file path. |
| `file` | `UPDATE` | File path relative to `repository`. |
| `operations` | `UPDATE` field changes | Non-empty list of operations. |
| `container` | image update, optional for `CREATE` | Container name. |
| `target_image` | image update, optional for `CREATE` | New image reference. |
| `source` | `CREATE` | Release Deployment YAML. |
| `current_image`, `image_transfer`, `deployment_update` | --- | Informational, set by the context builder. |

### Entries that are skipped

An `UPDATE` entry with no `operations`, no `container` and no
`target_image` is a **whole-file** change (a changed full Deployment YAML
in the release). It is skipped with the warning
`Skipped Deployment/<name>: no field or image changes to apply.` and
is not counted as processed. The file itself is applied by the
apply step from `deployment.operations`.

------------------------------------------------------------------------

## Operations

Operations come from `DeploymentUpdate` files (both modes) or from the
`operations` of an entry. `action` and `field` are case-insensitive.

| Field | `container` | `value` | add | update | delete |
| --- | --- | --- | --- | --- | --- |
| `env` | required | object with `name` | fails if the name exists | replaces the whole entry; fails if missing | removes by `name`; fails if missing |
| `mounts` | required | object with `name` | fails if the name exists | replaces the whole entry; fails if missing | removes by `name`; fails if missing |
| `mountvolume` | not allowed | object with `name` | fails if the name exists | replaces the whole entry; fails if missing | removes by `name`; fails if missing |
| `image` | required | image string | sets the image | sets the image | not supported |

An operation that would leave the file unchanged (same image, identical
entry) is reported as `unchanged` and not counted as a change.

### `DeploymentUpdate` file format

```yaml
apiVersion: entropy/v1
kind: DeploymentUpdate
target:
  kind: Deployment
  name: app-1
operations:
  - action: add
    field: env
    container: app
    value:
      name: APP_ENV
      value: SIT
```

`apiVersion` must be `entropy/v1`, `kind` must be `DeploymentUpdate`,
`target.kind` must be `Deployment`, and `operations` must be a non-empty
list.

### Complete example --- env + mounts + mountvolume

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

  # Add a Secret volume and mount it read-only
  - action: add
    field: mountvolume
    value:
      name: app-secret
      secret:
        secretName: app-secret

  - action: add
    field: mounts
    container: app
    value:
      name: app-secret
      mountPath: /etc/secrets
      readOnly: true
```

Resulting Deployment (relevant part):

```yaml
spec:
  template:
    spec:
      containers:
        - name: app
          env:
            - name: APP_ENV
              value: SIT
            - name: DATABASE_PASSWORD
              valueFrom:
                secretKeyRef: {name: database-secret, key: password}
            - name: DATABASE_HOST
              valueFrom:
                configMapKeyRef: {name: database-config, key: host}
          volumeMounts:
            - name: app-config
              mountPath: /etc/app
            - name: app-secret
              mountPath: /etc/secrets
              readOnly: true
      volumes:
        - name: app-config
          configMap: {name: app-config}
        - name: app-secret
          secret: {secretName: app-secret}
```

### Individual operations

Environment variable --- update (the whole entry is replaced):

```yaml
- action: update
  field: env
  container: app
  value:
    name: APP_ENV
    value: UAT
```

Environment variable --- delete:

```yaml
- action: delete
  field: env
  container: app
  value:
    name: APP_ENV
```

Volume --- PersistentVolumeClaim:

```yaml
- action: add
  field: mountvolume
  value:
    name: app-data
    persistentVolumeClaim:
      claimName: app-data-pvc
```

Volume --- update / delete:

```yaml
- action: update
  field: mountvolume
  value:
    name: app-config
    configMap:
      name: app-config-v2

- action: delete
  field: mountvolume
  value:
    name: app-config
```

Volume mount --- update / delete:

```yaml
- action: update
  field: mounts
  container: app
  value:
    name: app-config
    mountPath: /etc/app/config

- action: delete
  field: mounts
  container: app
  value:
    name: app-config
```

Image:

```yaml
- action: update
  field: image
  container: app
  value: quay.io/sacakti/app-1:1.1.10
```

A volume and its mounts are separate operations. Delete the mounts
before deleting the volume, and add the volume before (or together
with) its mounts, so the Deployment stays valid.

------------------------------------------------------------------------

## Workflow Configuration

### Basic Configuration

```json
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
```

------------------------------------------------------------------------

## Complete Workflow Example

Release with a Docker build and a `DeploymentUpdate` (scenario 3):

```json
{
    "name": "ReleaseDeploymentUpdate",
    "version": "1.0.0",
    "description": "Build changed images and update Deployments.",
    "variables": {
        "release": "/opt/releases/H010.zip",
        "docker_repository": "/opt/entropy/docker",
        "yaml_repository": "/opt/entropy/yamls/SIT",
        "image_tag": "1.1.10"
    },
    "steps": [
        {
            "name": "BuildReleaseContext",
            "plugin": "release.context_builder",
            "on_failure": "abort",
            "arguments": {
                "release": "${release}",
                "docker_repository": "${docker_repository}",
                "yaml_repository": "${yaml_repository}",
                "image_tag": "${image_tag}"
            }
        },
        {
            "name": "BuildImages",
            "plugin": "docker.build",
            "on_failure": "abort",
            "arguments": {
                "images": "${steps.BuildReleaseContext.outputs.images}"
            }
        },
        {
            "name": "DeploymentYAMLUpdate",
            "plugin": "oc.deployment",
            "on_failure": "abort",
            "arguments": {
                "mode": "deployments",
                "repository": "${yaml_repository}",
                "deployments": "${steps.BuildReleaseContext.outputs.deployment.resources.deployments}"
            }
        },
        {
            "name": "ApplyDeployments",
            "plugin": "oc.generic",
            "arguments": {
                "environment": "SIT",
                "operations": "${steps.BuildReleaseContext.outputs.deployment.operations}"
            }
        }
    ]
}
```

For an App-Published package with `image_transfer.sh` (scenario 5),
replace `BuildImages` with a `custom.image_transfer` step; the
`DeploymentYAMLUpdate` step stays the same.

------------------------------------------------------------------------

## Workflow Variables

```json
{
    "variables": {
        "yaml_repository": "/opt/entropy/yamls/SIT"
    }
}
```

```json
{
    "arguments": {
        "mode": "deployments",
        "repository": "${yaml_repository}",
        "deployments": "${steps.BuildReleaseContext.outputs.deployment.resources.deployments}"
    }
}
```

`deployments` may also be a literal list (see Example 3).

------------------------------------------------------------------------

## Vault Variables

Not used. The plugin needs no credentials. Do not put secret values in
`env` operations; reference a Secret with `valueFrom.secretKeyRef`.

------------------------------------------------------------------------

## Execution

### Deployments mode

For each entry in `deployments`:

1. Skip whole-file `UPDATE` entries (warning).
2. Use the `repository` argument when an `UPDATE` entry has none.
3. Validate the entry (`name`, `kind`, `action`; then the keys its action
   needs).
4. `CREATE`: check that `source` is a Deployment named `name`, that the
   target file does not exist, set the image if given, write the file.
5. `UPDATE`: open `<repository>/<file>`, find the Deployment named
   `name`, apply `operations` (or the image change), write the file.
6. Record success, or record the error and continue with the next entry.

### Folder mode

1. Check that `source` and `target` exist and are directories.
2. Load every `DeploymentUpdate` from `source`.
3. For each, find the Deployment with the same name in `target`, apply
   its operations and write the file.

------------------------------------------------------------------------

## Outputs

| Output | Type | Description |
| --- | --- | --- |
| `success` | `boolean` | `true` when no entry failed. |
| `resources_processed` | `integer` | Entries processed (skipped entries excluded). |
| `resources_succeeded` | `integer` | Entries created or updated. |
| `resources_failed` | `integer` | Entries that failed. |
| `changes` | `integer` | Field or image changes actually made. |
| `errors` | `list` | One object per failed entry: `kind`, `name`, `path`, `message`. |

### Example

```json
{
    "success": true,
    "resources_processed": 2,
    "resources_succeeded": 2,
    "resources_failed": 0,
    "changes": 3,
    "errors": []
}
```

------------------------------------------------------------------------

## Artifacts

None. The changed files are in the YAML repository.

------------------------------------------------------------------------

## Examples

### Example 1 --- Folder mode

```json
{
    "plugin": "oc.deployment",
    "arguments": {
        "mode": "folder",
        "source": "/opt/updates/deployment-updates",
        "target": "/opt/entropy/yamls/SIT/deployments"
    }
}
```

### Example 2 --- From the release context

```json
{
    "plugin": "oc.deployment",
    "arguments": {
        "mode": "deployments",
        "repository": "/opt/entropy/yamls/SIT",
        "deployments": "${steps.BuildReleaseContext.outputs.deployment.resources.deployments}"
    }
}
```

### Example 3 --- Image and field change on one Deployment (literal list)

```json
{
    "plugin": "oc.deployment",
    "arguments": {
        "mode": "deployments",
        "repository": "/opt/entropy/yamls/SIT",
        "deployments": [
            {
                "name": "app-1",
                "kind": "Deployment",
                "action": "UPDATE",
                "file": "deployments/app-1.yaml",
                "operations": [
                    {"action": "add", "field": "env", "container": "app",
                     "value": {"name": "APP_MODE", "value": "production"}}
                ]
            },
            {
                "name": "app-1",
                "kind": "Deployment",
                "action": "UPDATE",
                "file": "deployments/app-1.yaml",
                "container": "app",
                "target_image": "quay.io/sacakti/app-1:1.1.10"
            }
        ]
    }
}
```

Both entries use the `repository` argument, and both changes end up in
`deployments/app-1.yaml`.

### Example 4 --- App-Published release with image transfer

Release package:

```text
App-Published/
├── App/yamls/deployment.yaml          (DeploymentUpdate for app1)
└── scripts/deploy/image_transfer.sh   (docker push quay.io/sacakti/app1/app-service:1.0.0)
```

`release.context_builder` produces one field-change entry and one image
entry for `app1`; the step configuration is the same as Example 2.

------------------------------------------------------------------------

## Validation

| Check | Mode |
| --- | --- |
| `mode` is `folder` or `deployments` | both |
| `source` and `target` are given, exist and are directories | folder |
| `DeploymentUpdate` structure (`apiVersion`, `kind`, `target`, `operations`) | folder |
| `deployments` is a list; each entry is an object with `name`, `kind`, `action` | deployments |
| `UPDATE` has `file` and `repository`, and either non-empty `operations` or `container` + `target_image` | deployments |
| `CREATE` has `source` and `repository` | deployments |
| `repository` (for `UPDATE`) exists and is a directory | deployments |
| Target file contains a Deployment named `name` | both |
| `container` exists in the Deployment | both |

### Validation Errors

| Message | Meaning |
| --- | --- |
| `unknown argument ...` | An argument not in the table above was passed. |
| `'mode' must be one of folder, deployments` | Typo such as `deployment`. |
| `Argument 'source' must be a non-empty path.` | `folder` mode without `source`/`target` (often a `mode` that defaulted to `folder`). |
| `Argument 'deployments' must be a list.` | The reference did not resolve to a list. |
| `Deployment UPDATE resource requires 'file'.` | Entry without `file`. |
| `Deployment UPDATE resource requires 'container'.` | Entry with neither `operations` nor an image change. |
| `Deployment repository '...' does not exist.` | Wrong `repository`. |
| `Target Deployment '<name>' not found in '<file>'.` | The file has no Deployment with that name. |
| `Container '<name>' not found in Deployment.` | Wrong `container`. |
| `Environment variable '<name>' already exists in container '<c>'.` | `add` of an existing entry; use `update`. |
| `Volume mount '<name>' not found in container '<c>'.` | `update`/`delete` of a missing mount. |
| `Volume '<name>' already exists in Deployment.` | `add` of an existing volume. |
| `Unsupported Deployment field '<field>'.` | Field other than `image`, `env`, `mounts`, `mountvolume`. |
| `Deployment target already exists: ...` | `CREATE` of a file that is already there. |

------------------------------------------------------------------------

## Error Handling

- Argument errors fail the step before any file is touched.
- In `deployments` mode each entry fails on its own; other entries still
  run. The step result is `success: false` when any entry failed, and
  `errors` lists them. With `"on_failure": "abort"` the workflow stops
  after this step.
- A file is written only after all operations of its entry succeed, so a
  failed entry leaves its file unchanged. Entries that already succeeded
  are **not** rolled back.

------------------------------------------------------------------------

## Security

- No credentials are used or stored.
- Values in `env` operations are written to the YAML repository in plain
  text. Use `valueFrom.secretKeyRef` for secrets.

------------------------------------------------------------------------

## Filesystem

| Path | Access |
| --- | --- |
| `<repository>/<file>` | read and rewritten |
| `CREATE` `source` | read |
| `CREATE` `repository` (target file) and its parent directories | created |
| `source`, `target` (folder mode) | read; `target` files rewritten |

------------------------------------------------------------------------

## External Commands

None.

------------------------------------------------------------------------

## External Services

None. Apply the files with a later step.

------------------------------------------------------------------------

## Side Effects

Deployment YAML files are rewritten through a YAML serializer:
comments, key order details and quoting style in the file may change.

------------------------------------------------------------------------

## Performance

One read and one write per entry. Several entries for the same file read
and write it several times; this is expected.

------------------------------------------------------------------------

## Limitations

- Only `kind: Deployment` is supported (not `DeploymentConfig`).
- Only `image`, `env`, `mounts` and `mountvolume` can be changed.
- Changed full Deployment YAMLs (whole-file `UPDATE`) are not merged;
  they are skipped here and applied as files by the apply step.
- No rollback across entries.
- Init containers are not addressed.

------------------------------------------------------------------------

## Troubleshooting

### Problem

`Plugin 'oc.deployment': unknown argument repository (the plugin takes
deployments, mode, source, target).`

### Cause

Plugin version 1.0.8 or older is installed; `repository` was not
declared there.

### Solution

Install or upgrade to 1.0.9 or later.

### Problem

`Argument 'source' must be a non-empty path.` while you meant to use the
release context.

### Cause

`mode` is missing, so `folder` is used.

### Solution

Set `"mode": "deployments"`.

### Problem

The step succeeds but nothing changed.

### Cause

`deployments` is empty (the release has no Deployment changes), all
entries were whole-file updates (warnings in the log), or the values
were already in place (`unchanged`).

### Solution

Check `${steps.BuildReleaseContext.outputs.deployment.resources.deployments}`
and the step messages.

### Problem

The image was updated but the env change from the release is missing.

### Cause

The release ships a full `kind: Deployment` YAML instead of a
`DeploymentUpdate`.

### Solution

Describe field changes as a `DeploymentUpdate` document.

------------------------------------------------------------------------

## Notes

- Run `oc.sync_yamls` before a release so the YAML repository and its
  resource index match the cluster.
- Commit the YAML repository after this step to keep a history of each
  release's changes.

------------------------------------------------------------------------

## Changelog

### 1.0.9

- Declared the `repository` argument (used for `UPDATE` entries without
  their own repository); workflows passing it no longer fail with
  `unknown argument repository`.
- `source`, `target` and `repository` are no longer asked for in
  interactive runs.
- Whole-file `UPDATE` entries are skipped with a warning instead of
  failing.
- Folder mode: every `DeploymentUpdate` in `source` is now applied;
  before, every definition after the first failed.

### 1.0.7

- Added mounts add/update/delete.
- Added mountvolume add/update/delete.
- Added env add/update/delete.

### 1.0.0

- Initial plugin release with `folder` and `deployments` modes, image
  updates, multi-document YAML support and per-resource error reporting.
