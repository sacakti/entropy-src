# consolidate.db_scripts

------------------------------------------------------------------------

## Overview

`consolidate.db_scripts` reads the `DBScripts` folder of several release packages
and writes one `DBScripts` folder whose execution plan runs them all, plus
`consolidation-report.json`.

The plugin only reads releases and writes files; it never connects to a database.
`sqlplus.generic` (plan mode) runs the result.

------------------------------------------------------------------------

## Arguments

| Argument | Type | Required | Default | Meaning |
|---|---|---|---|---|
| `release_directory` | path (folder) | one of the two | | Folder of release packages (ZIPs or extracted folders), run in natural name order. |
| `releases` | list | one of the two | | Release packages, run in exactly the order given. |
| `output_directory` | path (folder) | no | `<workspace>/consolidated/db_scripts` | Where `DBScripts` and the report are written. |
| `overwrite` | boolean | no | `false` | Empty a non-empty `output_directory` first. |

Give `release_directory` **or** `releases`, not both.

------------------------------------------------------------------------

## How scripts are consolidated

Each application in a release's execution plan becomes one entry in the combined
plan, with its own folder named `<release>__<application>`:

```yaml
applications:
  H010__App1:
    schema: S1
    calling_script: App1_calling_script.sql
  H010__App2:
    schema: S2
    calling_script: App2_calling_script.sql
  H011__App1:
    schema: S1
    calling_script: App1_calling_script.sql
```

`sqlplus.generic` runs each calling script from its own folder, in a new session,
under the schema of its entry. A script therefore behaves as it does in its own
release:

- `@file` and `@@file` find the same files;
- an `exit` in a script ends only that script;
- two releases may use different schemas for one application;
- the order is kept across applications, so H010's App2 runs before H011's App1.

Grouped applications (`DBScripts/H01/App1`, plan key `H01/App1`) are supported
too. Each gets one flat folder, `<release>__H01__App1`, so the consolidated
package stays one level deep. A group folder such as `H01` is only reported as
left out when none of its applications are in the plan.

Files are copied unchanged. Only what earlier runs left behind (`.entropy`) and
packaging files (`__MACOSX`, `.DS_Store`, `._*`) are left out.

### What is reported

| Situation | Result |
|---|---|
| A release has no `DBScripts` folder | Skipped quietly. |
| Scripts but no execution plan | Warning; not included, as `sqlplus.generic` would not run them. |
| A folder not named in the plan | Warning; not included, for the same reason. |
| An empty calling script | Warning; still included. |
| A calling script named in the plan is missing | The run fails, naming the release. |
| A malformed execution plan | The run fails, naming the release. |

The same script in two releases runs twice, as it would one release at a time. Check
that scripts are safe to run in sequence; the plugin does not read or compare SQL.

### When a script fails

With `on_error: abort`, `sqlplus.generic` stops at the first failure and the later
entries do not run. Running the plan again runs every entry from the start, so remove
the entries that have already succeeded first.

------------------------------------------------------------------------

## Output

```text
<output_directory>/
  DBScripts/
    execution_plan.yaml
    H010__App1/App1_calling_script.sql
    H010__App2/App2_calling_script.sql
    H011__App1/App1_calling_script.sql
  consolidation-report.json
```

The report holds `releases`, `steps` (the executions in order) and `warnings`.

### Workflow outputs

| Output | Meaning |
|---|---|
| `output_directory` | Folder holding `DBScripts` and the report. |
| `report` | Path of `consolidation-report.json`. |
| `releases` | Release names in the order they run. |
| `steps` | The executions in order: `application`, `release`, `source_application`, `schema`, `calling_script`. |
| `database` | Give it to `sqlplus.generic` as `execution` (plan mode). |
| `changed` | True when at least one release has database scripts to run. |

------------------------------------------------------------------------

## Example

See `workflow.json`.
