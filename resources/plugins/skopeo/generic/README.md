# Image Tags and Checksums (skopeo.generic)

`skopeo.generic` returns, for each container of the selected OpenShift
workloads, the **full image** (registry, repository and tag) and its
**checksum** (the `sha256:` digest).

## Modes

| `mode` | Where the details come from |
|---|---|
| `pod` | The running pods: the image in the pod spec and the digest in `containerStatuses[].imageID`, i.e. what is actually running. |
| `skopeo` | `skopeo inspect --no-tags docker://<image>` of each workload's image. |
| `auto` (default) | Running pods, and skopeo for workloads with no running pod (e.g. scaled to 0). |

Workloads are Deployments and DeploymentConfigs (also StatefulSets and
DaemonSets with `kinds`), matched to their pods through their
ReplicaSets/ReplicationControllers. All are read with one `oc get`.

## Requires oc.generic

The plugin uses the login session that **oc.generic** keeps for
`environment`; run oc.generic `login` first (see `workflow.json`). It
never logs in or out itself. `images` can be inspected without OpenShift.

## Selecting what to read

Patterns are shell globs (`app-finance-*`, `*-1.2.0*`) or regular
expressions prefixed with `re:` (`re:^app-(finance|hr)-`).

| Argument | Selects |
|---|---|
| `deployments` | Workload names, e.g. `app-finance-*`. |
| `tags` | Image tags, e.g. `*-1.2.0*`. |
| `containers` | Container names. |
| `rules` | Several selections: `[{"deployments": "app-finance-*", "tags": "*-1.2.0*"}, {"deployments": "app-hr-*"}]`. Patterns within a rule must all match; any rule may match. |
| `exclude` | Workload names never read. |

`deployments`/`tags`/`containers` form one more rule. Without any, every
workload is read.

## Other arguments

| Name | Default | Description |
|---|---|---|
| `environment` | — | oc.generic environment (login session). |
| `namespace` | current project | OpenShift project. |
| `kinds` | `deployment, deploymentconfig` | Workload kinds. |
| `include_init_containers` | `false` | Also report init containers. |
| `images` | `[]` | Image references to inspect with skopeo directly. |
| `credentials` (secret) | — | Registry `username` and `password`/`token` for skopeo, e.g. `${entv:quay/robot}`. |
| `authfile` | — | An existing registry auth file instead. |
| `tls_verify` | `true` | Verify registry certificates. |
| `timeout` | `120` | Seconds per skopeo inspect. |
| `generate` | `false` | Write `<namespace>-<YYYYMMDD-HHMMSS>.txt` with one `image:checksum` line per image (below). |
| `output_directory` | data folder | Where that file is written (default: the plugin's data folder, `generated/`). |
| `fail_on_error` | `true` | Fail the step when an image cannot be inspected. |

## Outputs

- `images`: one entry per container image with `deployment`, `container`,
  `image` (`registry/repository:tag`), `registry`, `repository`, `tag`,
  `digest`, `reference` (`registry/repository@digest`), `source` (`pod` or
  `skopeo`) and `pods`.
- `digests`: `deployment -> container -> {image, digest}`, e.g.
  `${steps.ImageChecksums.outputs.digests.app-finance-api.app.digest}`.
- `deployments`, `count`, `missing` (no running pod in mode `pod`), `errors`,
  `file` (the generated file, when `generate` is true).

## Generated file

With `generate=true` the plugin writes `<namespace>-<YYYYMMDD-HHMMSS>.txt`
(e.g. `finance-sit-20261029-101500.txt`), one line per distinct image:

```
quay.example.com/finance/app-finance-api:release-1.2.0-b7:sha256:4f1c...
quay.example.com/finance/app-finance-ui:release-1.2.0:sha256:9ab2...
```

The file is added to **Artifacts → Generated**, and its path is the
`file` output. Images without a checksum are left out (with a warning).

## Example

```bash
ent pl run oc.generic -a operation=login -a environment=SIT \
    -a api_url=https://api.sit.example.com:6443 -a 'username=...' -a 'password=...'
ent pl run skopeo.generic -a environment=SIT -a namespace=finance-sit \
    -a 'deployments=app-finance-*' -a 'tags=*-1.2.0*' -a generate=true
```
