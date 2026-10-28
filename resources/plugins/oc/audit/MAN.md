# oc.audit

Detailed HTML audit of what changed in an OpenShift YAML repository since the previous audit.

## Overview

`oc.sync_yamls` overwrites the YAML files in a git repository with the current OpenShift
resources. Run `oc.audit` right after it (for example every morning and evening). The repository
is either a folder on the server (`repository`) or a repository from **Tools → Git repositories**
(`git_repository`). Each audit:

1. compares every changed `.yaml`/`.yml` file in the repository with the last commit;
2. writes an HTML report of what changed, resource by resource:
   - **ConfigMaps**: each data key added, removed or changed, with the old and new value
     (multi-line values such as `app.properties` as a line-by-line diff);
   - **Secrets**: each key added, removed or changed, **never the values**;
   - **Deployments and every other kind**: each field that changed
     (`spec.template.spec.containers[app].image`, `…env[LOG_LEVEL].value`, `spec.replicas`, …).
     Containers, env vars, volumes and ports are matched by name, so a reorder is not a change;
   - added and removed resources with a short summary (images, keys, replicas);
3. commits the files (`Entropy audit 2026-10-28 09:00: 2 modified, 1 added, 0 removed`), so the
   next audit reports only newer changes and git keeps the full history. For a Tools → Git
   repositories repository the commit is also pushed back to it;
4. removes reports older than `retention_days` (10 by default);
5. registers the report as a **generated artifact** (Tools → Artifacts → Generated).

Fields OpenShift changes on its own are left out: `status`, `metadata.resourceVersion`, `uid`,
`generation`, `creationTimestamp`, `managedFields`, `selfLink`, and the
`kubectl.kubernetes.io/last-applied-configuration` and `deployment.kubernetes.io/revision`
annotations. A resource where only those changed is not reported.

## Requirements

- The `git` command on the Entropy server.
- `repository` is a git working tree (run `git init` once if it is not). It does not need a
  remote; nothing is pushed unless `push` is on.
- `git_repository` is a repository from Tools → Git repositories that the run's user may use
  (their own, or the project's), by name or id.
- Commits use the repository's git identity, or `Entropy <entropy@localhost>` when none is set.
  Checkouts of Tools → Git repositories commit as the run's user.

## Arguments

| Name | Type | Required | Default | Description |
| --- | --- | --- | --- | --- |
| `repository` | path (directory) | one of the two | — | Git working tree on the server (the `yaml_repository` of `oc.sync_yamls`). |
| `git_repository` | string | one of the two | — | A repository from Tools → Git repositories (name or id). |
| `report_directory` | path (directory) | no | see below | Where reports are kept. |
| `retention_days` | integer ≥ 0 | no | `10` | Reports older than this are removed; `0` keeps all. |
| `commit` | boolean | no | `true` | Commit the files after the audit. |
| `push` | boolean | no | on for `git_repository`, off for `repository` | Push the audit commit to `origin`. |
| `commit_message` | string | no | `Entropy audit {date}: {summary}` | Commit message; `{date}` and `{summary}` are filled in. |
| `ignore_fields` | list | no | `[]` | More field paths to leave out, added to the built-in ones. |
| `title` | string | no | `OpenShift YAML audit` | Heading of the report. |

### Argument Details

#### `repository` or `git_repository`

Give one of them, not both. When neither is given and exactly one repository is assigned to
`oc.audit` or to the workflow (Tools → Git repositories → assignments), that one is used.

In the step form, `git_repository` is a dropdown of the repositories you may use.

How a `git_repository` is audited depends on how it was added under Tools → Git repositories:

- **From a folder on the Entropy server** ("local"): Entropy keeps its own copy, made when the
  repository was added, with only what was committed. `oc.sync_yamls` keeps writing to the
  original folder, so `oc.audit` audits **that folder**, commits there, and then updates
  Entropy's copy with the audit commit (pushed to the folder's current branch). Point
  `oc.sync_yamls` at the same folder, as before; no checkout step is needed.
- **New or from a remote URL**: it is cloned into the run's workspace
  (`.entropy-repositories/<id>-<name>`) and the audit commit is pushed back. Within one run every
  step gets the same clone, so `oc.sync_yamls` can write into it first; see the second workflow
  example below.

#### `report_directory`

By default reports go to a sibling directory: for `/opt/yamls/SIT` they are written to
`/opt/yamls/SIT-audit/`, outside the repository, so they are never committed.

For a `git_repository` the checkout is temporary, so reports go to the plugin's data folder
instead, which is kept between runs: `<workspace>/plugin-data/oc.audit/project-<id>/reports/<name>/`. When you choose a
directory **inside** the repository, the audit adds it to the repository's `.gitignore`
(`/audit-reports/`) before committing, so reports still stay out of git.

Report files are named `audit-YYYYmmdd-HHMMSS.html`; rotation only removes files with that name.

#### `ignore_fields`

Paths use the same form as the report: dots between keys, `[name]` for named list items, and
`["key"]` for keys with dots or slashes. A path also hides everything under it.

```json
"ignore_fields": ["spec.replicas", "metadata.labels[\"app.kubernetes.io/version\"]"]
```

#### `push`

On by default for `git_repository`: its checkout is deleted with the run workspace, so without
a push the commit (and the baseline for the next audit) would be lost. For a `repository` folder
it is off; turn it on to push to that folder's `origin`. Only the current branch is pushed.

#### `commit`

With `commit: false` git is not changed. The next audit then compares with the same commit
again, so the same changes are reported again until something commits them.

## Workflow Configuration

### Basic Configuration

```json
{
    "name": "AuditYamls",
    "plugin": "oc.audit",
    "arguments": {
        "repository": "${steps.SyncYamls.outputs.repository}"
    }
}
```

## Complete Workflow Example

`workflow.json` in this directory synchronizes, then audits. Schedule it twice a day
(Schedulers → for example `0 7,19 * * *`).

```json
{
    "name": "SyncAndAuditYamls",
    "variables": {"namespace": "sit", "yaml_repository": "/opt/entropy/yamls/SIT"},
    "steps": [
        {"name": "SyncYamls", "plugin": "oc.sync_yamls", "on_failure": "abort",
         "arguments": {"kubeconfig": "~/.kube/config", "namespace": "${namespace}",
                       "yaml_repository": "${yaml_repository}"}},
        {"name": "AuditYamls", "plugin": "oc.audit", "on_failure": "abort",
         "arguments": {"repository": "${steps.SyncYamls.outputs.repository}",
                       "retention_days": 10, "title": "SIT OpenShift audit"}}
    ]
}
```

### With Tools → Git repositories

Check the repository out first so `oc.sync_yamls` can write into it, then audit the same
repository; the audit commit is pushed back.

```json
{
    "name": "SyncAndAuditManagedYamls",
    "variables": {"namespace": "sit", "yamls": "sit-yamls"},
    "steps": [
        {"name": "CheckoutYamls", "plugin": "builtin.git", "on_failure": "abort",
         "arguments": {"operation": "status", "git_repository": "${yamls}"}},
        {"name": "SyncYamls", "plugin": "oc.sync_yamls", "on_failure": "abort",
         "arguments": {"kubeconfig": "~/.kube/config", "namespace": "${namespace}",
                       "yaml_repository": "${steps.CheckoutYamls.outputs.repository}"}},
        {"name": "AuditYamls", "plugin": "oc.audit", "on_failure": "abort",
         "arguments": {"git_repository": "${yamls}", "title": "SIT OpenShift audit"}}
    ]
}
```

## Execution

1. Use `repository`, check out `git_repository`, or take the one assigned repository; check that
   it is a git working tree; create the report directory.
2. If the report directory is inside the repository, add it to `.gitignore`.
3. `git status` lists changed, new and deleted YAML files; the previous version of each comes
   from `git show HEAD:<file>`. The first audit (no commit yet) lists every resource as added.
4. Compare each resource; write the report.
5. `git add -A -- .` and `git commit` (skipped when nothing changed or `commit` is false), then
   `git push origin HEAD` when `push` is on.
6. Remove reports older than `retention_days`.

Every run writes a report, including "No changes", so each sync leaves an audit trail.

## Outputs

| Name | Type | Description |
| --- | --- | --- |
| `report` | string | This run's report. |
| `reports` | list | All reports kept after rotation. |
| `removed_reports` | list | Reports removed by rotation. |
| `summary` | dictionary | `modified`, `added`, `removed` resources and `changes` (field and key changes). |
| `commit` | string | Short id of the audit commit; empty when nothing was committed. |
| `base_commit` | string | Commit compared with; empty on the first audit. |
| `repository` | string | Working tree audited (the run's checkout for `git_repository`). |
| `git_repository` | string | The Tools → Git repositories repository audited, if any. |
| `pushed` | boolean | Whether the audit commit was pushed. |

### Example

```json
{
    "report": "/opt/entropy/yamls/SIT-audit/audit-20261028-070012.html",
    "summary": {"modified": 2, "added": 1, "removed": 0, "changes": 7},
    "commit": "4f2c9e1",
    "base_commit": "9b1d0aa7c3…"
}
```

## Artifacts

| Name | Description |
| --- | --- |
| `audit_report` | The HTML report. It appears under Tools → Artifacts → Generated and opens in the viewer. |

When rotation removes an old report, its artifact entry stays and shows the file as missing.

## Security

- Secret values are never written to the report, not even base64-encoded: only the key name and
  whether it was added, removed or changed. Secret YAML files themselves stay in the repository
  as `oc.sync_yamls` wrote them.
- ConfigMap values are shown in full. Keep secrets out of ConfigMaps, or list such keys in
  `oc.sync_yamls` `ignore_resources` so they are never synchronized.
- The report is static HTML with every value escaped; it contains no scripts.

## Filesystem

- Reads the YAML files in `repository`.
- Writes reports to `report_directory`; may append one line to `repository/.gitignore`.
- Removes `audit-*.html` files older than `retention_days` from `report_directory`.

## External Commands

`git rev-parse`, `git status`, `git show`, `git log`, `git add`, `git diff --cached`,
`git config user.email`, `git commit` and, when `push` is on, `git push origin HEAD`, run in the
working tree. A `git_repository` is cloned by Entropy before that.

## Error Handling

| Problem | Result |
| --- | --- |
| `repository` is not a directory or not a git working tree | The step fails; no report. |
| Both or neither of `repository` and `git_repository` (and not exactly one assigned) | The step fails; no report. |
| `git_repository` is unknown or not available to the run's user | The step fails; no report. |
| The folder a "local" repository was created from no longer exists | A warning; Entropy's copy is checked out and audited instead. |
| Entropy's copy has commits the folder does not (e.g. edits in the repository browser) | Updating the copy is rejected; the report is written and the step fails. |
| The push fails | The report is still written and notes the error; the step then fails. The commit stays in the run's checkout only. |
| A file is not valid YAML | A warning; the file is compared as text. |
| The commit fails (hooks, signing, permissions) | The report is still written and notes the error; the step then fails. |
| `commit_message` uses another placeholder | The commit fails as above. |

## Changelog

- 1.2.0 — `git_repository` is a dropdown in the step form. A repository created from a server
  folder is audited in that folder (where `oc.sync_yamls` writes) instead of a checkout of
  Entropy's copy, which had no uncommitted changes and so reported none; the copy is then updated.
- 1.1.0 — `git_repository` (Tools → Git repositories) with push back, the assigned repository
  when neither argument is given, `push`, and the `repository`, `git_repository` and `pushed` outputs.
- 1.0.0 — First version.
