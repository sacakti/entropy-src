# consolidate.cm_secret

------------------------------------------------------------------------

## Overview

`consolidate.cm_secret` reads the ConfigMap and Secret changes of several
release packages and writes their consolidated result: one YAML file per
ConfigMap/Secret, plus `consolidation-report.json`.

Use it when an environment receives several releases at once. Applying the
consolidated files gives the same ConfigMaps and Secrets as applying every
release one after another, with fewer, clearer changes.

The plugin only reads releases and writes files. `oc.cm_secret_update`
(folder mode) applies the result to the YAML repository.

------------------------------------------------------------------------

## Arguments

| Argument | Type | Required | Default | Meaning |
|---|---|---|---|---|
| `release_directory` | path (folder) | one of the two | | Folder of release packages (ZIPs or extracted folders), applied in natural name order. |
| `releases` | list | one of the two | | Release packages, applied in exactly the order given. |
| `output_directory` | path (folder) | no | `<workspace>/consolidated/cm_secret` | Where the YAMLs and the report are written. |
| `overwrite` | boolean | no | `false` | Empty a non-empty `output_directory` first. |

Give `release_directory` **or** `releases`, not both.

### Release order

- `release_directory`: every ZIP (or `.tar`, `.tar.gz`, `.tgz`) and folder
  in it, sorted by name with numbers compared by value: `H9`, `H10`, `H101`.
  `H010.zip` and a folder `H010` are the same release; having both is an
  error.
- `releases`: exactly the order of the list.

### Release layout

Each release is a ZIP (extracted into the run workspace) or a folder. Its
OpenShift YAMLs are found at the top or one folder down:

```text
H010/App/openshift/yamls/...        standard package
App-Published/App/yamls/...         App-Published package
```

Every `.yaml`/`.yml` file below that folder is read (sub-folders too), in
natural path order, and every document in it. A release without such a
folder only gives a warning.

### `output_directory`

Must be empty or missing; otherwise the run fails unless `overwrite` is
`true`. This keeps YAMLs of an earlier run from being applied by mistake.

------------------------------------------------------------------------

## What is consolidated

The documents `oc.cm_secret_update` understands:

- `entropy/v1` `ConfigMapSecretUpdate` (`target: {kind, name}` and
  `operations`);
- `v1` `ConfigMap` and `Secret` (native resources, merged key by key).

Other resources (Deployments, Services, Routes, ...) are ignored here and
counted in the report; their own consolidation plugins handle them.

### Rules

For each ConfigMap/Secret, the changes are taken in release order:

| Earlier | Later | Result |
|---|---|---|
| `update a=1` | `update a=2` | `update a=2` |
| `add a` | `delete a` | `delete a` |
| `delete a` | `add a=3` | `add a=3` |
| structured `a` (any) | plain `update a=...` or `delete a` | the plain change only |

Structured values (`format: properties`, `yaml`, `json`) merge by entry or
path, as long as the format stays the same:

| Earlier | Later | Result |
|---|---|---|
| `{x: 1, y: 1}` | `{x: 2}` | `{x: 2, y: 1}` |
| `{x: 1}` | delete `x` | delete `x` |
| delete `x` | `{x: 5}` | `{x: 5}` |
| yaml `{server: {port: 80}}` | yaml `{server: {port: 8080}}` | `{server: {port: 8080}}` |

A delete of a path is kept even when nothing earlier set it: the target
YAML may still have the key. In the output, deletes come before writes;
they never overlap, so the result is the same as applying the releases in
sequence.

Comments around `format: properties` entries are kept in the output, above
the property they precede, and `oc.cm_secret_update` writes them into the
properties content. When several releases comment on one property, all their
comments are kept. A later delete of the property drops them. Comments around
`yaml` and `json` entries are not kept.

Native resources in a row merge into one (later keys win). An update
between two native resources keeps its place, so the output may hold
several documents for one ConfigMap/Secret, in the order they must be
applied. `oc.cm_secret_update` applies them in that order.

Malformed changes (unknown action or format, missing key or value, a
target that is not a ConfigMap/Secret) fail the run with the release and
file they came from.

------------------------------------------------------------------------

## Output

```text
<output_directory>/
├── configmap-cm-app.yaml
├── secret-app-secret.yaml
└── consolidation-report.json
```

`consolidation-report.json`:

```json
{
  "releases": ["H9", "H10", "H101"],
  "targets": [
    {
      "kind": "ConfigMap",
      "name": "cm-app",
      "file": ".../configmap-cm-app.yaml",
      "releases": ["H9", "H10", "H101"],
      "sources": [{"release": "H10", "file": "sub/cm.yml"}],
      "keys": {"db.url": "H10", "feature.x": "H101"}
    }
  ],
  "ignored_documents": 1,
  "warnings": []
}
```

`keys` names the release that last changed each key.

### Workflow outputs

| Output | Meaning |
|---|---|
| `output_directory` | The folder to give `oc.cm_secret_update` as `source`. |
| `report` | Path of `consolidation-report.json` (also an artifact). |
| `releases` | Release names in the order applied. |
| `targets` | The report's `targets`. |
| `changed` | `true` when any release changes a ConfigMap or Secret. |

------------------------------------------------------------------------

## Example

```json
{
    "name": "ConsolidateCmSecret",
    "plugin": "consolidate.cm_secret",
    "arguments": {
        "release_directory": "/opt/releases/2026-R4"
    }
},
{
    "name": "ApplyCmSecret",
    "plugin": "oc.cm_secret_update",
    "arguments": {
        "mode": "folder",
        "source": "${steps.ConsolidateCmSecret.outputs.output_directory}",
        "target": "${yaml_repository}"
    }
}
```

An explicit order:

```json
"arguments": {
    "releases": ["/opt/releases/H012.zip", "/opt/releases/H015.zip"],
    "output_directory": "/opt/entropy/consolidated/R4",
    "overwrite": true
}
```
