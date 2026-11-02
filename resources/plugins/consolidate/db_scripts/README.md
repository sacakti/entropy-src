# Consolidate database scripts (consolidate.db_scripts)

`consolidate.db_scripts` collects the database scripts of several release packages
into **one package with one execution plan**, so an environment that skips releases
(say H010 to H015 at once) runs them all in one step, in release order.

Unlike configuration, scripts have no net result: each one changes the database, so
every script runs, and none is merged, skipped or edited.

It only writes files. Run them with `sqlplus.generic` (plan mode), as `workflow.json`
shows.

```text
H010: App1 (schema S1), App2 (schema S2)
H011: App1 (schema S1)
=> DBScripts/execution_plan.yaml runs H010__App1, H010__App2, H011__App1
```

Releases come from `release_directory` (natural name order: H9, H10, H101)
or `releases` (the order given). Each is a ZIP or an extracted folder with a
`DBScripts` folder.

See [MAN.md](MAN.md) for the details.
