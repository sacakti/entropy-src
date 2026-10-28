# image_transfer

Pull release images from the source registry, push them to the target
registry, and prepare the release's `apply_yaml.sh` for deployment.

------------------------------------------------------------------------

## Overview

Some releases do not build images. Instead they ship a script,
`scripts/deploy/image_transfer.sh`, that copies ready-made images from
one registry (for example Azure) to another (for example Quay), and a
script, `apply_yaml.sh`, that applies the release's YAML files.

`custom.image_transfer` runs that release safely:

1. Extracts the release ZIP beside the archive.
2. Reads `docker login/pull/tag/push` commands from `image_transfer.sh`
   and runs each one on its own (the script itself is never executed).
3. Checks and, if needed, frees Docker storage first.
4. Rewrites `apply_yaml.sh` so its `oc apply -f` paths point into the
   extracted release, removes Git commands and login credentials, and
   checks that the referenced YAML files exist. It does **not** run
   `apply_yaml.sh`.

### Where it fits with `release.context_builder` and `oc.deployment`

This plugin moves the **images**. It does not change any Deployment YAML.
Moving Deployments to the transferred image tags is done by
`oc.deployment`, using entries that `release.context_builder` builds
from the **same** `image_transfer.sh`:

```text
release ZIP (with scripts/deploy/image_transfer.sh)
   │
   ├─► release.context_builder   reads the docker push lines
   │        └─ outputs.deployment.resources.deployments  (image entries)
   │
   ├─► custom.image_transfer     runs pull / tag / push
   │
   └─► oc.deployment             sets the pushed tags (and any
                                 DeploymentUpdate field changes)
                                 in the YAML repository
```

### When to use

- Releases whose images are built elsewhere and only need to be copied
  between registries.
- App-Published packages (`App-Published/App/yamls` +
  `App-Published/scripts/deploy`).
- Preparing `apply_yaml.sh` for a later deployment step, with or without
  transferring images (`skip_docker`).

------------------------------------------------------------------------

## Requirements

- Docker CLI on the host, with access to both registries. **Log in
  beforehand** (for example `docker login` as the run user, or a
  credential helper): credentials in the script are removed.
- `df` on the host (storage check).
- Enough free Docker storage (`min_free_storage_gb`, default 10 GB).
- A release ZIP containing, in `release_scripts_directory`:
  - `image_transfer.sh` (unless the script name is changed),
  - `apply_yaml.sh`.

  Both are required, even with `skip_docker`.

------------------------------------------------------------------------

## Arguments

| Argument | Required | Type | Default | Description |
| --- | --- | --- | --- | --- |
| `release` | Yes | `path` (file) | --- | Release ZIP; extracted beside the archive. |
| `release_scripts_directory` | No | `string` | `scripts/deploy` | Scripts directory, relative to the extracted directory. |
| `transfer_script` | No | `string` | `image_transfer.sh` | Image transfer script name. |
| `apply_script` | No | `string` | `apply_yaml.sh` | OpenShift apply script name. |
| `release_base_path` | No | `string` | `/home/devops` | Path prefix in `oc apply -f` lines that is replaced by the extracted path. |
| `min_free_storage_gb` | No | `number` | `10` | Minimum free Docker storage in GB (greater than zero). |
| `old_image_pattern` | No | `string` | `25.01.01.` | Regular expression for old local images that may be removed to free storage. |
| `cleanup_builder_cache` | No | `boolean` | `false` | Run `docker builder prune -f` before transferring. |
| `skip_docker` | No | `boolean` | `false` | Skip storage checks, cleanup and the transfer. |
| `validate_yaml` | No | `boolean` | `true` | Check that the YAML paths in the prepared apply script exist. |
| `force_remove_processed` | No | `boolean` | `false` | Remove an existing extracted directory before extracting. |

### Argument Details

#### `release`

Path to a `.zip`. It is extracted to the same path without the
extension (`/releases/H001.zip` → `/releases/H001/`). If that directory
already exists, the step fails unless `force_remove_processed` is
`true`.

#### `release_scripts_directory`

Directory of the scripts, **relative to the extracted directory**, not to
a folder inside it. Set it to match the package:

| Package | Value |
| --- | --- |
| `H001.zip` → `scripts/deploy/...` | `scripts/deploy` (default) |
| `H010.zip` → `App-Published/scripts/deploy/...` | `App-Published/scripts/deploy` |

#### `transfer_script` / `apply_script`

File names inside `release_scripts_directory`. Both files must exist.

#### `release_base_path`

Every `oc apply -f <path>` in the apply script must start with this
prefix. The prefix is replaced with the extracted release directory.
A path outside the prefix is rejected.

#### `min_free_storage_gb`

Free space required on Docker's root filesystem before images are
pulled. Must be greater than zero.

#### `old_image_pattern`

Regular expression matched against local `repository:tag` names. When
storage is short, matching images are removed with `docker rmi`.

#### `cleanup_builder_cache`

When `true`, prunes the Docker builder cache and checks storage again.

#### `skip_docker`

When `true`, no Docker command runs. Extraction and `apply_yaml.sh`
preparation still happen. Use it to prepare a release without moving
images.

#### `validate_yaml`

When `true`, each rewritten `oc apply -f` path must be an existing
`.yaml`/`.yml` file or a directory containing at least one.

#### `force_remove_processed`

When `true`, an existing extracted directory is deleted and the release
is extracted again. Needed when `release.context_builder` has already
extracted the same release in this run.

------------------------------------------------------------------------

## Input files

### `image_transfer.sh`

```bash
#/bin/bash

docker login azurerepo.io/sacakti -u $1 -p $2

docker pull azurerepo.io/sacakti/app1/app-service:1.0.0
docker pull azurerepo.io/sacakti/app2/app-service:1.2.0

docker login quay.io/sacakti -u $1 -p $2

docker tag azurerepo.io/sacakti/app1/app-service:1.0.0 quay.io/sacakti/app1/app-service:1.0.0
docker tag azurerepo.io/sacakti/app2/app-service:1.2.0 quay.io/sacakti/app2/app-service:1.2.0

docker push quay.io/sacakti/app1/app-service:1.0.0
docker push quay.io/sacakti/app2/app-service:1.2.0
```

Rules:

- Only `docker login`, `docker pull`, `docker tag` and `docker push`
  lines are used. Other lines (variables, comments, `echo`) are ignored.
- Lines continued with `\` are joined.
- `login`, `pull`, `tag` and `push` must all be present, a `login` must
  come before the first `pull`, and `tag` must come after `pull`.
- Credentials are removed from `docker login`, which then runs as
  `docker login <registry>`:

  | Script line | Runs as |
  | --- | --- |
  | `docker login quay.io/sacakti $user $password` | `docker login quay.io/sacakti` |
  | `docker login quay.io/sacakti -u $1 -p $2` | `docker login quay.io/sacakti` |
  | `docker login quay.io/sacakti --username=$1 --password=$2` | `docker login quay.io/sacakti` |
  | `docker login -u $1 -p $2 quay.io/sacakti` | `docker login quay.io/sacakti` |
  | `docker login quay.io/sacakti --password-stdin` | unchanged |

  The first positional argument is the registry; later positional
  arguments are credentials. A login without a registry is rejected.
- The `docker push` lines are also what `release.context_builder` uses to
  set Deployment image tags.

### `apply_yaml.sh`

```bash
user=$1
password=$2
oc login -u $user -p $password https://api.cluster:6443
git pull
oc apply -f /home/devops/scripts/app-1/test-deployment/deployment-service1.yaml
oc apply -f /home/devops/scripts/app-1/test-deployment/svc-service1.yaml
```

becomes, for a release extracted to `/releases/H001`:

```bash
oc login https://api.cluster:6443
oc apply -f /releases/H001/scripts/app-1/test-deployment/deployment-service1.yaml
oc apply -f /releases/H001/scripts/app-1/test-deployment/svc-service1.yaml
```

- Standalone `git` commands are removed.
- Lines that only assign a positional parameter (`user=$1`) are removed.
- Credentials are removed from `oc login`: the options `-u`,
  `--username`, `-p`, `--password`, `--token` with their values, their
  `--option=value` forms, and any unresolved shell variable (`$1`,
  `$user`, `${TOKEN}`). The server and other options are kept:

  | Script line | Prepared line |
  | --- | --- |
  | `oc login $1 $2` | `oc login` |
  | `oc login -u $1 -p $2 https://api.cluster:6443` | `oc login https://api.cluster:6443` |
  | `oc login --token $TOKEN https://api.cluster:6443` | `oc login https://api.cluster:6443` |
  | `oc login https://api.cluster:6443 --insecure-skip-tls-verify` | unchanged |
- `/home/devops` (`release_base_path`) is replaced with the extracted
  directory.
- The file is rewritten in place inside the extracted release and is
  **not executed**.

### Package layouts

Standard:

```text
H001/
└── scripts/
    ├── deploy/
    │   ├── image_transfer.sh
    │   └── apply_yaml.sh
    └── app-1/test-deployment/*.yaml
```

App-Published (set `release_scripts_directory` to
`App-Published/scripts/deploy`):

```text
H010/
└── App-Published/
    ├── App/yamls/deployment.yaml      ← DeploymentUpdate, used by context_builder / oc.deployment
    └── scripts/deploy/
        ├── image_transfer.sh
        └── apply_yaml.sh
```

------------------------------------------------------------------------

## Workflow Configuration

### Basic Configuration

```json
{
    "name": "TransferImages",
    "plugin": "custom.image_transfer",
    "enabled": true,
    "on_failure": "abort",
    "arguments": {
        "release": "${release}"
    }
}
```

------------------------------------------------------------------------

## Complete Workflow Example

App-Published release: transfer the images, then move Deployments to the
pushed tags and apply the `DeploymentUpdate` field changes.

```json
{
    "name": "PublishedRelease",
    "version": "1.0.0",
    "description": "Transfer images and update Deployments for an App-Published release.",
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
            "name": "TransferImages",
            "plugin": "custom.image_transfer",
            "on_failure": "abort",
            "arguments": {
                "release": "${release}",
                "release_scripts_directory": "App-Published/scripts/deploy",
                "force_remove_processed": true
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
        }
    ]
}
```

### Step order

Both `release.context_builder` and this plugin extract the ZIP to the
same directory:

- `release.context_builder` always deletes and re-extracts it.
- This plugin fails if it exists, unless `force_remove_processed` is
  `true`.

So run `release.context_builder` **first** and this plugin second, with
`force_remove_processed: true`. In the opposite order the context
builder would delete the `apply_yaml.sh` this plugin prepared.

------------------------------------------------------------------------

## Workflow Variables

```json
{
    "variables": {
        "release": "/opt/releases/H010.zip"
    }
}
```

```json
{
    "arguments": {
        "release": "${release}",
        "release_scripts_directory": "App-Published/scripts/deploy"
    }
}
```

------------------------------------------------------------------------

## Vault Variables

Not used. Registry access comes from the host's Docker login;
credentials in the scripts are stripped, never filled in.

------------------------------------------------------------------------

## Execution

```text
Release ZIP
  → validate (.zip, exists)
  → extract beside the ZIP
  → locate image_transfer.sh and apply_yaml.sh
  → read and validate Docker commands
  → (unless skip_docker)
        check storage → remove old images if short → check storage
        → prune builder cache (optional) → check storage
        → run each Docker command
  → prepare apply_yaml.sh (remove git/credentials, rewrite paths)
  → validate YAML paths (optional)
  → publish outputs and artifacts
```

Each Docker command runs as its own activity. Docker's own output goes to
the workflow log, not the UI. The first failing command stops the step.

------------------------------------------------------------------------

## Outputs

| Output | Type | Description |
| --- | --- | --- |
| `configuration` | `dictionary` | Resolved arguments. |
| `force_remove_processed` | `boolean` | Whether an existing extraction could be removed. |
| `docker_storage` | `dictionary` | `docker_root`, `free_bytes`, `free_gb`, `minimum_required_gb`. |
| `cleanup_performed` | `boolean` | Whether old images were removed. |
| `docker_skipped` | `boolean` | Whether Docker work was skipped. |
| `image_transfer` | `boolean` | Whether images were transferred. |
| `yaml_script_prepared` | `boolean` | Whether `apply_yaml.sh` was prepared. |
| `yaml_validation_enabled` | `boolean` | Whether YAML paths were checked. |
| `yaml_paths` | `list` | YAML paths referenced by the prepared script. |
| `release_path` | `string` | Extracted release directory. |

### Example

```json
{
    "docker_skipped": false,
    "image_transfer": true,
    "cleanup_performed": false,
    "docker_storage": {
        "docker_root": "/var/lib/docker",
        "free_bytes": 53687091200,
        "free_gb": 50.0,
        "minimum_required_gb": 10
    },
    "yaml_script_prepared": true,
    "yaml_validation_enabled": true,
    "yaml_paths": [
        "/releases/H001/scripts/app-1/test-deployment/deployment-service1.yaml"
    ],
    "release_path": "/releases/H001"
}
```

------------------------------------------------------------------------

## Artifacts

| Artifact | Path |
| --- | --- |
| `release` | Extracted release directory. |
| `apply_yaml_script` | Prepared `apply_yaml.sh`. |

------------------------------------------------------------------------

## Examples

### Example 1 --- Standard release

```json
{
    "plugin": "custom.image_transfer",
    "arguments": {
        "release": "/opt/releases/H001.zip"
    }
}
```

### Example 2 --- App-Published release

```json
{
    "plugin": "custom.image_transfer",
    "arguments": {
        "release": "/opt/releases/H010.zip",
        "release_scripts_directory": "App-Published/scripts/deploy",
        "force_remove_processed": true
    }
}
```

### Example 3 --- Prepare only (no Docker)

```json
{
    "plugin": "custom.image_transfer",
    "arguments": {
        "release": "/opt/releases/H001.zip",
        "skip_docker": true,
        "force_remove_processed": true
    }
}
```

### Example 4 --- Low disk host

```json
{
    "plugin": "custom.image_transfer",
    "arguments": {
        "release": "/opt/releases/H001.zip",
        "min_free_storage_gb": 20,
        "old_image_pattern": "^quay\\.io/sacakti/.*:1\\.0\\.",
        "cleanup_builder_cache": true
    }
}
```

------------------------------------------------------------------------

## Validation

- `release` exists, is a file and ends in `.zip`.
- The extraction directory does not exist, or `force_remove_processed`
  is `true`.
- Both scripts exist in `release_scripts_directory`.
- `image_transfer.sh` has `login`, `pull`, `tag` and `push`, in a valid
  order.
- `min_free_storage_gb` is greater than zero; `old_image_pattern` is a
  valid regular expression.
- Every `oc apply -f` path starts with `release_base_path`.
- With `validate_yaml`, every rewritten path exists.

### Validation Errors

| Message | Meaning |
| --- | --- |
| `Release archive not found: ...` | Wrong `release`. |
| `Release path must be a ZIP archive: ...` | Not a `.zip`. |
| `Release extraction directory already exists: ...` | Set `force_remove_processed: true` (always when `release.context_builder` ran first). |
| `Required release script not found: .../scripts/deploy/image_transfer.sh` | Wrong `release_scripts_directory` (App-Published needs `App-Published/scripts/deploy`). |
| `No supported Docker commands were found in ...` | The transfer script has no `docker login/pull/tag/push` lines. |
| `... is missing required Docker operation(s): ...` | One of login/pull/tag/push is missing. |
| `image_transfer.sh must contain a Docker login before Docker pull.` | Move a `docker login` above the first pull. |
| `Docker tag must occur after Docker pull.` | Reorder the script. |
| `Argument 'min_free_storage_gb' must be greater than zero.` | Invalid storage minimum. |

------------------------------------------------------------------------

## Error Handling

The step stops at the first error. Images already pushed before a failure
stay pushed; re-running is safe because pull, tag and push are
idempotent. The extracted directory is left in place for inspection.

------------------------------------------------------------------------

## Security

- `image_transfer.sh` and `apply_yaml.sh` are never executed as scripts.
- Docker commands run without a shell, so shell syntax in the script is
  not interpreted.
- Credentials are stripped from `docker login` and `oc login` lines;
  registry and cluster access rely on the host's existing login.

------------------------------------------------------------------------

## Filesystem

| Path | Access |
| --- | --- |
| `<release>.zip` | read |
| `<release>/` | created (deleted first with `force_remove_processed`) |
| `<release>/<scripts>/image_transfer.sh` | read |
| `<release>/<scripts>/apply_yaml.sh` | rewritten |

------------------------------------------------------------------------

## External Commands

```text
docker system df
docker info --format ...
df ...
docker images --format ...
docker rmi <image>              (only when storage is short)
docker builder prune -f         (only with cleanup_builder_cache)
docker login <registry>
docker pull <image>
docker tag <source> <target>
docker push <image>
```

------------------------------------------------------------------------

## External Services

The source and target container registries named in `image_transfer.sh`.

------------------------------------------------------------------------

## Side Effects

- Images are pulled into, and possibly removed from, the local Docker
  storage.
- Images are pushed to the target registry.
- The release is extracted beside the ZIP and `apply_yaml.sh` is
  rewritten there.

------------------------------------------------------------------------

## Performance

Dominated by image size and registry bandwidth. Commands run one at a
time.

------------------------------------------------------------------------

## Limitations

- Credentials cannot be supplied through the plugin; log in on the host.
- Commands built with variables, loops or `$(...)` in the transfer
  script are passed to Docker literally.
- Deployment YAMLs are not updated by this plugin; use
  `release.context_builder` + `oc.deployment`.

------------------------------------------------------------------------

## Troubleshooting

### Problem

`Required release script not found` for an App-Published package.

### Cause

The scripts are under `App-Published/scripts/deploy`, not
`scripts/deploy`.

### Solution

Set `"release_scripts_directory": "App-Published/scripts/deploy"`.

### Problem

`Release extraction directory already exists`.

### Cause

An earlier run, or `release.context_builder` in this run, already
extracted the release.

### Solution

Set `"force_remove_processed": true`.

### Problem

`docker push` fails with an authentication error.

### Cause

The host is not logged in to the target registry (credentials from the
script are removed on purpose).

### Solution

Log in on the host as the user that runs Entropy, then re-run.

### Problem

Images were transferred but Deployments still use the old tag.

### Cause

This plugin does not edit YAML.

### Solution

Add `release.context_builder` before and `oc.deployment` after this step
(see [Complete Workflow Example](#complete-workflow-example)).

------------------------------------------------------------------------

## Notes

1. The original release ZIP is never modified.
2. The extracted release stays beside the ZIP.
3. The prepared `apply_yaml.sh` is meant for a later deployment step.

------------------------------------------------------------------------

## Changelog

### 1.0.4

- `docker login`: positional credentials after the registry
  (`docker login <registry> $user $password`) are now removed; they were
  passed to Docker as literal text before.
- `oc login`: credential options (`-u`, `-p`, `--username`, `--password`,
  `--token`) are removed with their values, and so is any unresolved
  shell variable; before, only `$1` and `$2` were removed, leaving
  `oc login -u -p <server>`.
- Invalid shell syntax (for example an unclosed quote) in
  `image_transfer.sh` or `apply_yaml.sh` is now reported as
  `Invalid shell syntax in ...` instead of an unhandled error; a
  non-numeric `df` result is reported as
  `Invalid available-space value in df output`.
- Manual rewritten: input formats, App-Published packages, and how this
  plugin works with `release.context_builder` and `oc.deployment`.
