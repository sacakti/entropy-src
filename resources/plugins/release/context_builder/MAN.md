# release.context_builder

Analyse a release package and produce the deployment context that later
workflow steps (Docker build, image transfer, ConfigMap/Secret update,
Deployment update, apply, rsync, database) consume.

------------------------------------------------------------------------

## Overview

`release.context_builder` opens a release ZIP, works out **what the
release changes**, and publishes that as workflow outputs. It does not
change anything itself: it does not build images, edit YAML, apply
resources, run rsync or run SQL. Each of those is done by a later step
that reads this plugin's outputs through `${steps.<step>.outputs...}`.

The plugin answers these questions for a release:

| Question | Where it looks | Output |
| --- | --- | --- |
| Which Docker images must be rebuilt? | `App/services/<service>/image` | `images` |
| Which Deployments need a new image tag? | Docker build results, `image_transfer.sh` | `deployment.resources.deployments` |
| Which Deployment fields change (env, mounts, volumes)? | `DeploymentUpdate` YAML files | `deployment.resources.deployments` |
| Which ConfigMaps / Secrets change? | `ConfigMapSecretUpdate` and plain YAML files | `deployment.resources.configmaps` / `secrets` |
| Which resources are new or changed as whole files? | Plain OpenShift YAML files | `deployment.resources.*`, `deployment.operations` |
| Which common paths must be synced? | `App/openshift/common_path/rsync_plan.*` | `common_paths` |
| Which database scripts run, and in which order? | `DBScripts/**/*.sql`, `execution_plan.*` | `database` |

### When to use

Use it as the first real step of a release workflow, before any step that
needs to know what the release contains. Every deployment-related plugin
in a release workflow should take its input from this step instead of
hard-coded lists.

### Important behaviour

- The release ZIP is extracted **beside the archive**
  (`/releases/H010.zip` → `/releases/H010/`). An existing extracted
  directory is **deleted and extracted again** on every run.
- Two release layouts are supported: the standard package and the
  **App-Published** package (see [Release layouts](#release-layouts)).
- Image tags are only ever changed on Deployments that already exist in
  the YAML repository's resource index.
- `image_transfer.sh` is **read, never executed**.

------------------------------------------------------------------------

## Requirements

- A release package in `.zip` format.
- A **Docker repository** directory holding the last released state of
  each service: `<docker_repository>/<service>/image/...`.
- A **YAML repository** directory holding the environment's OpenShift
  YAML files and its resource index,
  `<yaml_repository>/.entropy/resource_index.json`. The index is created
  by `oc.sync_yamls`; run that plugin against the environment first.
- A release structure definition (the bundled `structure.yaml` is used
  when none is given).
- No OpenShift, Docker registry or database access is needed; the plugin
  only reads files.

------------------------------------------------------------------------

## Arguments

| Argument | Required | Type | Default | Description |
| --- | --- | --- | --- | --- |
| `release` | Yes | `path` (file) | --- | Release ZIP archive to analyse. |
| `docker_repository` | Yes | `path` (directory) | --- | Docker repository compared with the release to find images to build. |
| `yaml_repository` | Yes | `path` (directory) | --- | YAML repository with the target OpenShift resources and `.entropy/resource_index.json`. |
| `image_tag` | Yes | `string` | --- | Tag new images are built with and Deployments are moved to. |
| `structure` | No | `path` (file) | bundled `structure.yaml` | Release structure definition. |
| `image_transfer_script` | No | `string` | `scripts/deploy/image_transfer.sh` | Image transfer script, relative to the release root. |

### Argument Details

#### `release`

Path to the release `.zip`. It must exist and have a `.zip` extension.
It is extracted to the same path without the extension; any directory
already there is removed first.

#### `docker_repository`

The repository the release's service images are compared with. For each
release service `App/services/<service>/image`, the plugin compares it
with `<docker_repository>/<service>/image`. A service is reported in
`images` when the file names or file contents differ, or when the
repository has no copy yet.

#### `yaml_repository`

The environment's YAML repository (for example `/opt/yamls/SIT`). It
must contain `.entropy/resource_index.json`, which maps resources to
their files and lists every Deployment container and its current image.
The plugin uses it to:

- find the file of an existing resource,
- decide whether a release resource is new (`CREATE`) or changed
  (`UPDATE`),
- find which Deployment and container use an image.

#### `image_tag`

The tag for images built from this release, for example `1.1.10`. For a
Docker build, Deployments that use the image are moved to this tag.

#### `structure`

A structure YAML that describes where each component lives in the
release. Leave it out to use the bundled `structure.yaml`. A component's
`path` may be a single path or a list of alternatives; the first one
present in the release is used.

#### `image_transfer_script`

Path of the image transfer script **inside the release root**. The
default matches both layouts, because for an App-Published package the
release root is the `App-Published` directory itself. When the file is
missing, image-transfer analysis is skipped without an error.

------------------------------------------------------------------------

## Release layouts

The plugin finds the **release root**: the single directory in the
extracted archive that matches the structure definition. Directories
named `__MACOSX`, `.DS_Store` and `._*` entries are ignored.

### Standard package

```text
H010/
├── App/
│   ├── services/
│   │   └── app-1/
│   │       └── image/              ← compared with <docker_repository>/app-1/image
│   │           ├── Dockerfile
│   │           └── app1.war
│   └── openshift/
│       ├── yamls/                  ← DeploymentUpdate, ConfigMapSecretUpdate, plain YAML
│       │   └── deployment.yaml
│       └── common_path/
│           └── rsync_plan.yaml
├── DBScripts/
│   ├── App1/001_table.sql
│   └── execution_plan.yaml
└── scripts/deploy/image_transfer.sh   (optional)
```

### App-Published package

```text
App-Published/                      ← release root
├── App/
│   └── yamls/                      ← DeploymentUpdate, ConfigMapSecretUpdate, plain YAML
│       └── deployment.yaml
└── scripts/
    └── deploy/
        ├── image_transfer.sh       ← docker push lines give the new image tags
        └── apply_yaml.sh
```

The bundled structure resolves the OpenShift directory as `App/openshift`
first and `App` second, so `App/openshift/yamls` and `App/yamls` are both
found. An App-Published package normally has no `App/services`, so no
image is built; image tags come from `image_transfer.sh` instead.

### Scripts-only package

```text
H001/                               ← release root
└── scripts/
    ├── deploy/
    │   ├── image_transfer.sh       ← docker push lines give the new image tags
    │   └── apply_yaml.sh
    └── app-1/test-deployment/*.yaml
```

A release that only ships deployment scripts is recognised through its
`scripts/deploy` directory. Only image tags change; there are no field
changes or builds.

### Bundled `structure.yaml`

```yaml
name: default
structure:
  children: [docker, openshift, database, scripts]
  docker:
    path: App/services
    children:
      service:
        children:
          image:
            path: image
            dockerfile:
              name: Dockerfile
  openshift:
    path:
      - App/openshift
      - App
    children:
      yamls:
        path: yamls
      common_path:
        path: common_path
        rsync_plan:
          names: [rsync_plan.yaml, rsync_plan.yml, rsync_plan.json]
  database:
    path: DBScripts
    scripts:
      extensions: [.sql]
    execution_plan:
      names: [execution_plan.yaml, execution_plan.yml, execution_plan.json]
  scripts:
    path: scripts/deploy
```

------------------------------------------------------------------------

## Release inputs

These are the kinds of content the plugin understands inside the release.

### 1. Docker service image (`App/services/<service>/image`)

A changed `image` directory means the service image must be rebuilt.
The service directory name is the **image name**. Example: release file
`App/services/app-1/image/app1.war` differs from
`<docker_repository>/app-1/image/app1.war` → image `app-1` is built
with `image_tag`.

### 2. `DeploymentUpdate` (field changes on an existing Deployment)

A YAML document in the OpenShift `yamls` directory:

```yaml
apiVersion: entropy/v1
kind: DeploymentUpdate
target:
  kind: Deployment
  name: app-1
operations:
  - action: add          # add | update | delete
    field: env           # env | mounts | mountvolume | image
    container: app       # required for env, mounts, image
    value:
      name: APP_MODE
      value: production
```

The target must be in the resource index. The operations are passed
through unchanged; `oc.deployment` validates and applies them. See the
`oc.deployment` manual for every field and action.

### 3. `ConfigMapSecretUpdate` (key changes on a ConfigMap or Secret)

Key-level changes for an existing ConfigMap or Secret. They are listed
under `configmaps` / `secrets` with their `operations` and consumed by
`oc.cm_secret_update`.

### 4. Plain OpenShift YAML (`Deployment`, `ConfigMap`, `Secret`, `Service`, `Route`)

A full resource manifest. The plugin looks the resource up in the index:

| Situation | Action |
| --- | --- |
| Not in the YAML repository | `CREATE` (target: `<yaml_repository>/<category>/<name>.yaml`) |
| In the repository, content differs | `UPDATE` |
| In the repository, content identical | ignored |

### 5. `scripts/deploy/image_transfer.sh` (images moved between registries)

Only `docker push <image>` lines are used. Every other line (`login`,
`pull`, `tag`, comments) is ignored:

```bash
docker login azurerepo.io/sacakti -u $1 -p $2
docker pull azurerepo.io/sacakti/app1/app-service:1.0.0
docker tag  azurerepo.io/sacakti/app1/app-service:1.0.0 quay.io/sacakti/app1/app-service:1.0.0
docker push quay.io/sacakti/app1/app-service:1.0.0
```

gives the image `quay.io/sacakti/app1/app-service:1.0.0`. Duplicate
pushes are reported once.

### 6. Common paths and database scripts

`common_path/rsync_plan.*` entries become `common_paths` (with `source`
made absolute). `DBScripts/**/*.sql` and `execution_plan.*` become
`database`.

------------------------------------------------------------------------

## How Deployment entries are produced

Every entry in `deployment.resources.deployments` is one unit of work for
`oc.deployment`. The same Deployment can appear **more than once**, for
example once for its field changes and once for its new image tag;
`oc.deployment` applies them one after the other to the same file.

### A. Image tag from a Docker build

For each image in `images`, the plugin searches the index for a container
whose image repository ends in `/<image name>`:

```text
images.app-1  +  index: deployments/app-1.yaml → container "app"
                        image quay.io/sacakti/app-1:1.0.0
             →  target_image quay.io/sacakti/app-1:<image_tag>
```

```json
{
    "name": "app-1",
    "kind": "Deployment",
    "action": "UPDATE",
    "file": "deployments/app-1.yaml",
    "repository": "/opt/yamls/SIT",
    "container": "app",
    "current_image": "quay.io/sacakti/app-1:1.0.0",
    "target_image": "quay.io/sacakti/app-1:1.1.10"
}
```

If the release also has a plain `Deployment` YAML that uses the image,
that entry is enriched with `container` and `target_image` instead of a
new entry being added.

### B. Field changes from a `DeploymentUpdate`

```json
{
    "name": "app-1",
    "kind": "Deployment",
    "action": "UPDATE",
    "source": "/releases/H010/App/openshift/yamls/deployment.yaml",
    "repository": "/opt/yamls/SIT",
    "file": "deployments/app-1.yaml",
    "operations": [
        {"action": "add", "field": "env", "container": "app",
         "value": {"name": "APP_MODE", "value": "production"}}
    ],
    "deployment_update": true
}
```

### C. Image tag from `image_transfer.sh`

For each pushed image the registry host is removed
(`quay.io/sacakti/app1/app-service` → `sacakti/app1/app-service`) and
the index is searched for a container image ending in that path. The
Deployment **keeps its own registry**; only the tag changes:

```text
push  quay.io/sacakti/app1/app-service:1.0.0
index mirror.local:5000/sacakti/app1/app-service:0.9.0
  →   mirror.local:5000/sacakti/app1/app-service:1.0.0
```

```json
{
    "name": "app1",
    "kind": "Deployment",
    "action": "UPDATE",
    "file": "deployments/app1.yaml",
    "repository": "/opt/yamls/SIT",
    "container": "app",
    "current_image": "quay.io/sacakti/app1/app-service:0.9.0",
    "target_image": "quay.io/sacakti/app1/app-service:1.0.0",
    "image_transfer": true
}
```

Rules:

- If a Docker build already moves the same Deployment container to a new
  image, the Docker build wins and the pushed image is not used.
- A field-change entry (B) for the same Deployment does **not** stop the
  image update; both entries are produced.
- Pushes that use a shell variable (`$TAG`) or a digest (`@sha256:...`),
  or that have no tag, are skipped with a warning.
- Images that match no indexed Deployment are skipped with a warning.

### D. Plain Deployment YAML

```json
{"name": "app-2", "kind": "Deployment", "action": "CREATE",
 "source": "/releases/H010/App/openshift/yamls/app-2.yaml",
 "repository": "/opt/yamls/SIT/deployments/app-2.yaml"}
```

For `CREATE`, `repository` is the **full target file path**. An
`UPDATE` without operations or an image change is a whole-file change:
`oc.deployment` skips it and the file is applied through the
`deployment.operations` lists.

### Release scenarios

| Release content | Entries produced |
| --- | --- |
| `App/services/app-1/image/*` changed | A |
| `DeploymentUpdate` for app-1 | B |
| Image change + `DeploymentUpdate` for app-1 | B and A (both applied) |
| `image_transfer.sh` only | C |
| App-Published: `App/yamls` `DeploymentUpdate` + `scripts/deploy/image_transfer.sh` | B and C (both applied) |
| New Deployment YAML | D (`CREATE`) |

------------------------------------------------------------------------

## Workflow Configuration

### Basic Configuration

```json
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
}
```

The step name (`BuildReleaseContext` here) is what later steps use in
`${steps.BuildReleaseContext.outputs...}`.

------------------------------------------------------------------------

## Complete Workflow Example

A release workflow where the context drives every later step:

```json
{
    "name": "ReleaseDeployment",
    "version": "1.0.0",
    "description": "Analyse a release and deploy it.",
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
            "arguments": {
                "images": "${steps.BuildReleaseContext.outputs.images}"
            }
        },
        {
            "name": "CmSecretUpdate",
            "plugin": "oc.cm_secret_update",
            "arguments": {
                "mode": "deployments",
                "configmaps": "${steps.BuildReleaseContext.outputs.deployment.resources.configmaps}",
                "secrets": "${steps.BuildReleaseContext.outputs.deployment.resources.secrets}"
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

For an App-Published package that also transfers images, add the
`custom.image_transfer` step **after** this step (see that plugin's
manual for why the order matters).

------------------------------------------------------------------------

## Workflow Variables

All arguments accept workflow variables:

```json
{
    "variables": {
        "release": "/opt/releases/H010.zip",
        "image_tag": "1.1.10"
    }
}
```

```json
{
    "arguments": {
        "release": "${release}",
        "image_tag": "${image_tag}"
    }
}
```

------------------------------------------------------------------------

## Vault Variables

The plugin needs no credentials. Do not pass vault values to it.

------------------------------------------------------------------------

## Execution

1. Resolve `release`, `docker_repository`, `yaml_repository`,
   `image_tag`, `structure` and `image_transfer_script`.
2. Load the structure definition.
3. Load `<yaml_repository>/.entropy/resource_index.json`.
4. Extract the release beside the ZIP (replacing any earlier extraction).
5. Find the single release root that matches the structure.
6. For each structure component:
   - `docker`: compare service image directories → `images`.
   - `openshift`: read every YAML file under `yamls`
     (`DeploymentUpdate`, `ConfigMapSecretUpdate`, plain resources), and
     read `common_path` rsync plans.
   - `database`: list `.sql` scripts and load the execution plan.
7. Correlate built images with Deployments (entries A).
8. Read `image_transfer.sh` and correlate pushed images (entries C).
9. Set `deployment.required` and publish all outputs.

------------------------------------------------------------------------

## Outputs

| Output | Type | Description |
| --- | --- | --- |
| `workspace` | `string` | Workspace directory of the run. |
| `release` | `dictionary` | `package`, `root`, `docker_source_release`, `docker_dest_repo`. |
| `images` | `dictionary` | Images to build, keyed by image name. |
| `deployment` | `dictionary` | `required`, `resources` by type, `operations` (`create`, `apply`, `replace`). |
| `common_paths` | `list` | Rsync operations from the release. |
| `database` | `dictionary` | `dir`, `scripts`, `execution_plan`. |

### Example

```json
{
    "workspace": "/opt/entropy-workspace/executions/release_1a2b3c4d",
    "release": {
        "package": "/opt/releases/H010.zip",
        "root": "/opt/releases/H010",
        "docker_source_release": "/opt/releases/H010/App/services",
        "docker_dest_repo": "/opt/entropy/docker"
    },
    "images": {
        "app-1": {
            "dockerfile": "/opt/entropy/docker/app-1/image/Dockerfile",
            "context": "/opt/entropy/docker/app-1",
            "image_name": "app-1",
            "image_tag": "1.1.10"
        }
    },
    "deployment": {
        "required": true,
        "resources": {
            "deployments": ["... entries A-D ..."],
            "configmaps": [],
            "secrets": [],
            "services": [],
            "routes": []
        },
        "operations": {
            "create": [],
            "apply": ["/opt/entropy/yamls/SIT/deployments/app-1.yaml"],
            "replace": []
        }
    },
    "common_paths": [],
    "database": {"dir": null, "scripts": [], "execution_plan": null}
}
```

### Referencing outputs

| Need | Reference |
| --- | --- |
| Deployment entries for `oc.deployment` | `${steps.BuildReleaseContext.outputs.deployment.resources.deployments}` |
| Images for `docker.build` | `${steps.BuildReleaseContext.outputs.images}` |
| ConfigMaps / Secrets | `${steps.BuildReleaseContext.outputs.deployment.resources.configmaps}` / `.secrets` |
| Services / Routes | `${steps.BuildReleaseContext.outputs.deployment.resources.services}` / `.routes` |
| Apply/create/replace lists | `${steps.BuildReleaseContext.outputs.deployment.operations}` |
| Rsync plan | `${steps.BuildReleaseContext.outputs.common_paths}` |
| Database plan | `${steps.BuildReleaseContext.outputs.database}` |
| Extracted release root | `${steps.BuildReleaseContext.outputs.release.root}` |

------------------------------------------------------------------------

## Artifacts

None. The extracted release directory stays beside the ZIP.

------------------------------------------------------------------------

## Examples

### Example 1 --- Standard release

```json
{
    "plugin": "release.context_builder",
    "arguments": {
        "release": "/opt/releases/H010.zip",
        "docker_repository": "/opt/entropy/docker",
        "yaml_repository": "/opt/entropy/yamls/SIT",
        "image_tag": "1.1.10"
    }
}
```

### Example 2 --- App-Published release with image transfer

Same arguments; the layout is detected automatically. The script path
default (`scripts/deploy/image_transfer.sh`) is relative to the
`App-Published` root.

### Example 3 --- Transfer script with a different name

```json
{
    "arguments": {
        "release": "${release}",
        "docker_repository": "${docker_repository}",
        "yaml_repository": "${yaml_repository}",
        "image_tag": "${image_tag}",
        "image_transfer_script": "scripts/deploy/transfer_images.sh"
    }
}
```

### Example 4 --- Custom structure

```json
{
    "arguments": {
        "release": "${release}",
        "docker_repository": "${docker_repository}",
        "yaml_repository": "${yaml_repository}",
        "image_tag": "${image_tag}",
        "structure": "/opt/entropy/structures/legacy.yaml"
    }
}
```

------------------------------------------------------------------------

## Validation

- `release` must exist and be a `.zip`.
- The structure file must have a `name`, a `structure` mapping, and a
  definition for each child; `path` must be a non-empty string or a list
  of non-empty strings.
- The resource index must exist and contain a JSON object.
- Exactly one directory may match the structure.
- A `DeploymentUpdate` must name a `Deployment`/`DeploymentConfig` that
  exists in the index, with a list of `operations`.

### Validation Errors

| Message | Meaning |
| --- | --- |
| `Release archive not found: ...` | Wrong `release` path. |
| `Release must be a ZIP archive: ...` | `release` is not a `.zip`. |
| `Resource index not found: .../.entropy/resource_index.json` | Run `oc.sync_yamls` for the YAML repository first. |
| `Unable to locate the release root matching the configured release structure.` | The package has none of the configured component directories. |
| `Multiple directories match the configured release structure: ...` | The ZIP holds more than one release. |
| `DeploymentUpdate target 'Deployment/<name>' was not found in the resource index.` | The Deployment does not exist in this environment, or the index is stale. |
| `DeploymentUpdate '<file>' has invalid 'operations'.` | `operations` is not a list. |

------------------------------------------------------------------------

## Error Handling

Any of the errors above fails the step and no outputs are published.
Problems that only affect one image (no matching Deployment, several
candidate containers, unusable push line) are logged as warnings and
analysis continues.

------------------------------------------------------------------------

## Security

The plugin reads files only. `image_transfer.sh` is parsed, never run,
so credentials passed to it as `$1 $2` are never seen or logged.

------------------------------------------------------------------------

## Filesystem

| Path | Access |
| --- | --- |
| `<release>.zip` | read |
| `<release>/` (beside the ZIP) | deleted and re-created |
| `<docker_repository>/**` | read |
| `<yaml_repository>/**`, `.entropy/resource_index.json` | read |

------------------------------------------------------------------------

## External Commands

None.

------------------------------------------------------------------------

## External Services

None.

------------------------------------------------------------------------

## Side Effects

The extracted release directory beside the ZIP is replaced on every run.
Any step that works on the same extracted directory (for example
`custom.image_transfer`) must run **after** this step.

------------------------------------------------------------------------

## Performance

Cost grows with the number of files in the release and in the compared
Docker image directories (each file is hashed).

------------------------------------------------------------------------

## Limitations

- An image is matched to the **first** indexed Deployment container that
  uses it; if several Deployments share an image, only one is updated.
- Field changes must be written as `DeploymentUpdate`. A full
  `kind: Deployment` YAML that already exists produces a whole-file
  `UPDATE`, not field operations.
- `oc.deployment` only edits `kind: Deployment`; `DeploymentConfig`
  targets are listed but cannot be updated by it.
- Image transfer reads `docker push` lines only; pushes inside loops or
  built from variables are not understood.

------------------------------------------------------------------------

## Troubleshooting

### Problem

`Resource index not found`.

### Cause

The YAML repository has never been synchronized.

### Solution

Run `oc.sync_yamls` against the environment with the same
`yaml_repository`.

### Problem

A changed service image produced no Deployment entry.

### Cause

No container image in the index ends in `/<service directory name>`.

### Solution

Check the run log for `No deployment found for image '<name>'` and make
sure the service directory name matches the image name used by the
Deployment.

### Problem

`image_transfer.sh` images were not applied.

### Cause

The script is not at `<release root>/scripts/deploy/image_transfer.sh`,
or the pushed image path does not match any indexed container image.

### Solution

Check `release.root` in the outputs, set `image_transfer_script` if the
script lives elsewhere, and look for `No deployment found for
transferred image` warnings.

### Problem

`Unable to locate the release root ...`.

### Cause

The package has none of `App/openshift`, `App/yamls`, `App/services`,
`DBScripts` or `scripts/deploy` (for an App-Published package: under
`App-Published`).

### Solution

Check the ZIP layout against [Release layouts](#release-layouts).

------------------------------------------------------------------------

## Notes

- Keep the YAML repository index fresh (`oc.sync_yamls`) before a
  release; image matching and `CREATE`/`UPDATE` decisions depend on it.
- The image tag in `image_tag` applies to Docker builds only. Image
  transfer keeps the tag from the `docker push` line.

------------------------------------------------------------------------

## Changelog

### 1.1.5

- Scripts-only packages (`scripts/deploy/...` and no `App` directory)
  are recognised, so their `image_transfer.sh` images update
  Deployments.

### 1.1.4

- Added `image_transfer_script`: `docker push` images in the release's
  image transfer script update the tags of matching Deployments.
- Added App-Published package support (`App/yamls`); structure `path`
  may list alternative layouts.

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
