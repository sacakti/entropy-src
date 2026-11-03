# consolidate.images

------------------------------------------------------------------------

## Overview

`consolidate.images` finds the images of several release packages and keeps the latest of
each: one image to build per service, and one image to transfer per repository.

The plugin only reads releases and writes files. It never runs Docker, and it never runs
`image_transfer.sh` or `apply_yaml.sh`.

Every output is safe to use when there is nothing to do, so one workflow suits releases
with any content.

------------------------------------------------------------------------

## Arguments

| Argument | Type | Required | Default | Meaning |
|---|---|---|---|---|
| `release_directory` | path (folder) | one of the two | | Folder of release packages (ZIPs or extracted folders), applied in natural name order. |
| `releases` | list | one of the two | | Release packages, applied in exactly the order given. |
| `image_tag` | string | yes | | Tag the images from `App/services` are built and deployed with. |
| `docker_repository` | path (folder) | no | | Last released images. A service whose image is identical is not built. |
| `yaml_repository` | path (folder) | no | | Repository with `.entropy/resource_index.json`, for the `deployments` output. |
| `output_directory` | path (folder) | no | `<workspace>/consolidated/images` | Where the output is written. |
| `overwrite` | boolean | no | `false` | Empty a non-empty `output_directory` first. |

Give `release_directory` **or** `releases`, not both.

------------------------------------------------------------------------

## What is consolidated

### Images to build

`App/services/<service>/image`, at the top of the package or one folder down. The image
folder of the latest release replaces earlier ones **as a whole**. Files only an earlier
release had are not included, and a warning names them: check that the latest release's
image is complete.

A service's image must have a `Dockerfile`, or the run fails naming the release.

With `docker_repository`, a service whose latest image holds the same files as
`<docker_repository>/<service>/image` is not built. Without it, every service found is built.

The repository is only read. Keep it up to date as you do today, for example with
`custom.stage_release_copy`.

### Images to transfer

`scripts/deploy/image_transfer.sh`, at the top of the package or one folder down (this
covers App-Published and scripts-only packages). The script is read, never run. Its
`docker pull`, `tag` and `push` commands are used, and the latest release's push to each
repository wins.

Pushes that use a shell variable or have no tag are skipped with a warning, as are other
commands in the script. The generated script logs in with `docker login <registry>`, using
the credentials Docker already holds: credentials in the original script are not carried over.

### What is not consolidated

`apply_yaml.sh` is neither consolidated nor run, and a warning says so for each release that
has one. Plain YAMLs it names are not applied by this plugin.

### Deployment updates

With `yaml_repository`, each image is matched to a Deployment container in the resource index:
built images by service name, transferred images by image path, or by final name when only one
container uses it. Containers keep their registry; only the tag changes. An image with no match
gives a warning.

When several releases set one container's image, the latest wins; within one release, the built
image wins over a transferred one.

Run this update **after** applying `consolidate.deployment`'s output: an image from
`DeploymentUpdate` is then replaced by the image here.

------------------------------------------------------------------------

## Output

```text
<output_directory>/
  services/app-3/image/Dockerfile
  image_transfer.sh
  consolidation-report.json
```

### Workflow outputs

| Output | Meaning |
|---|---|
| `output_directory` | Folder holding the output. |
| `report` | Path of `consolidation-report.json`. |
| `releases` | Release names in the order applied. |
| `images` | Give it to `docker.build` as `images`. Empty when nothing needs building. |
| `transfer_script` | Give it to `builtin.shell` as `script`. Does nothing when there are no images. |
| `transfers` | Images the transfer script pushes. |
| `deployments` | Give it to `oc.deployment` as `deployments` (deployments mode). |
| `changed` | True when there is an image to build or transfer. |

`docker.build` only builds. As with `release.context_builder`, pushing built images is a
separate step, and `docker.generic` push fails when given no images, so it is not part of
the example workflow.

------------------------------------------------------------------------

## Example

See `workflow.json`: the complete consolidation of releases H001 and H002.
