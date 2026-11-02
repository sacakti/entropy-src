# consolidate.deployment

------------------------------------------------------------------------

## Overview

`consolidate.deployment` reads the Deployment changes of several release
packages and writes their consolidated result: one YAML per Deployment, plus
`consolidation-report.json`.

Use it when an environment receives several releases at once. Applying the
consolidated files gives the same Deployments as applying every release one
after another, with fewer, clearer changes.

The plugin only reads releases and writes files. `oc.deployment` (folder mode)
applies the result to the YAML repository.

------------------------------------------------------------------------

## Arguments

| Argument | Type | Required | Default | Meaning |
|---|---|---|---|---|
| `release_directory` | path (folder) | one of the two | | Folder of release packages (ZIPs or extracted folders), applied in natural name order. |
| `releases` | list | one of the two | | Release packages, applied in exactly the order given. |
| `output_directory` | path (folder) | no | `<workspace>/consolidated/deployment` | Where the YAMLs and the report are written. |
| `overwrite` | boolean | no | `false` | Empty a non-empty `output_directory` first. |

Give `release_directory` **or** `releases`, not both.

------------------------------------------------------------------------

## What is consolidated

- `entropy/v1` `DeploymentUpdate`: `image`, `env`, `mounts` and `mountvolume`
  operations;
- `apps/v1` `Deployment`: a complete resource (see below).

Other resources (ConfigMaps, Secrets, Services, Routes, ...) are ignored here and
counted in the report; their own consolidation plugins handle them.

### Rules

`oc.deployment` is strict: `add` fails when the item exists, and `update` and
`delete` fail when it is missing. Each item (one env variable, one mount, one
volume, per container where that applies) therefore reduces to its net operation:

| Earlier | Later | Result |
|---|---|---|
| `add` | `update` | `add`, with the later value |
| `add` | `delete` | nothing; listed under `cancelled` in the report |
| `update` | `update` | `update`, with the later value |
| `update` | `delete` | `delete` |
| `delete` | `add` | `update`, with the later value |

The image of a container only sets a value, so the latest one wins, whichever of
`add` or `update` it uses. Deleting an image is not supported.

Any other pair (`add` after `add`, `update` after `delete`, ...) would fail when
applied one by one, whatever the Deployment holds. The run fails too, naming both
releases, so the problem is found before the repository is touched.

The order of items in the `env`, `volumeMounts` and `volumes` lists can differ from
applying the releases one by one: `delete` then `add` moves an item to the end,
while the consolidated `update` leaves it in place.

Malformed changes (unknown action or field, missing container or value, a target
that is not a Deployment) fail the run with the release and file they came from.

### Complete resources

`oc.deployment` folder mode updates existing Deployments; it does not create them
and does not read `apps/v1` documents as updates. A complete resource is therefore
written to the `native` subfolder, which it does not read, and a warning says what
to do:

- if the YAML repository lacks the Deployment, add the file there first;
- if a release ships a complete resource and others ship updates, the updates are
  applied to whatever the repository holds, so check that they still fit;
- if several releases ship a complete resource, only the latest is kept.

------------------------------------------------------------------------

## Output

```text
<output_directory>/
  deployment-app-1.yaml         net DeploymentUpdate, for oc.deployment
  native/deployment-app-4.yaml  complete resource, added by hand if missing
  consolidation-report.json
```

The report holds `releases`, `targets` (each with `file`, `native_file`, `releases`,
`sources`, and `keys`: the release that last changed each item, such as
`env/app/MODE` or `image/app`), `cancelled`, `ignored_documents` and `warnings`.

### Workflow outputs

| Output | Meaning |
|---|---|
| `output_directory` | Give it to `oc.deployment` as `source` (folder mode). |
| `report` | Path of `consolidation-report.json`. |
| `releases` | Release names in the order they were applied. |
| `targets` | One entry per Deployment. |
| `changed` | True when at least one release changes a Deployment. |

------------------------------------------------------------------------

## Example

See `workflow.json`.
