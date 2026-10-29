# custom.trd_mig

Migrates TRD data for one product, using `sqlplus.generic` to run SQLPlus.

## Steps

1. When `truncate` is true, truncates the resolved tables (below); when false, skips this step.
2. Counts `count_table`. If it is not empty, the run asks whether to
   continue (automated runs answer `no` and the step fails).
3. Runs the country's SQL file from `sqls/`, then `COMMIT`.
4. Counts `count_table` again and publishes it as `count_after` and
   `counts.<product>`.

Any SQLPlus error (ORA-/SP2-) fails the step; the insert is rolled back.

## mapping.json

```json
{
    "truncate_profiles": {
        "default": ["TRD_STAGE", "TRD_STAGE_DETAIL"]
    },
    "countries": {
        "IN": {
            "dblink": "TRD_IN_LINK",
            "sql": {"app1": "IN/app1.sql", "app2": "IN/app2.sql"}
        },
        "SG": {"dblink": "TRD_SG_LINK", "sql": "SG/insert.sql"}
    },
    "products": {
        "app1": {"count_table": "APP1_TRD"},
        "app2": {"count_table": "APP2_TRD"}
    }
}
```

- `countries.<country>.sql` is one file for every product, or an object
  with one file per product. Paths are relative to the `sqls` folder next
  to the mapping file and cannot leave it.
- `countries.<country>.dblink` is optional; it is needed only when the
  SQL file uses `{dblink}`.
- `truncate_profiles` holds named table lists; `default` is used unless
  the step picks another one.

## SQL files

Kept in `sqls/<COUNTRY>/`. Before a file runs, `{dblink}`, `{country}` and
`{product}` are replaced. End statements with `;` and PL/SQL blocks with
`/`. Do not `COMMIT` or `EXIT`: the plugin commits after the file succeeds.

The shipped mapping, table names and SQL files are placeholders: replace
them with the real ones.

## Truncate tables

Only when `truncate` is true:

1. `truncate_tables` argument: your own list, if given.
2. Otherwise the `truncate_profile` argument, which defaults to `default`.

See `plugin.json` for arguments and outputs, and `workflow.json` for an example.

## Adding a country or product

`country` and `product` are dropdowns filled from the keys of
`countries` and `products` in the plugin's `mapping.json`
(`choices_from` in `plugin.json`). Add the entry to `mapping.json` (and
its SQL file to `sqls/`) and it appears in the dropdowns and is accepted
on the next run; nothing else changes.

The dropdowns read the installed plugin's `mapping.json`. A `mapping`
argument pointing at another file does not change them.
