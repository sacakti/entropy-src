# custom.load_data

Runs load procedures in order, using `sqlplus.generic` to run SQLPlus.

For each SQL file in `procedures` (default `procedure1.sql`, `procedure2.sql`):

1. Runs the file from the `sqls/` folder and waits for SQLPlus to return,
   that is, for the procedure to complete.
2. Counts the rows of the status table whose status column is NULL or not
   equal to `success_value` (default `STATUS` / `SUCCESS`).
3. If that count is above zero, the step fails with a message naming the
   table and count, and later files are not run.

Every file is read before anything runs, so a missing file changes nothing.

## SQL files

Kept in `sqls/`, for example `sqls/procedure1.sql`:

```sql
BEGIN
    LOAD_PKG.PROCEDURE1;
END;
/
```

End PL/SQL blocks with `/` and do not `EXIT`. Paths are relative to
`sqls/` and cannot leave it. The shipped files are placeholders: replace
them with the real calls.

## Status checks

The `status_check` argument is the default check; a procedure given as an
object (`{"sql": "procedure2.sql", "status_check": {...}}`) uses its own, and
any key it leaves out comes from the default.

`where` (optional) is one SQL condition that limits the rows checked, so each
procedure can check only its own jobs:

```json
"procedures": [
    {"sql": "procedure1.sql", "status_check": {"where": "JOB_ID LIKE '1%'"}},
    {"sql": "procedure2.sql", "status_check": {"where": "JOB_ID LIKE '2%'"}}
],
"status_check": {"table": "LOAD_STATUS", "column": "STATUS", "success_value": "SUCCESS"}
```

After `procedure1.sql` this counts:

```sql
SELECT COUNT(*) FROM LOAD_STATUS
WHERE (JOB_ID LIKE '1%')
  AND (STATUS IS NULL OR STATUS <> 'SUCCESS');
```

`where` must stay on one line and cannot contain `;`. To drop a default
`where` for one procedure, give it `"where": ""`.

## Changelog

### 1.2.0
- `status_check.where` limits the rows checked; a procedure's own check takes
  missing keys from the default.

See `plugin.json` for arguments and outputs, and `workflow.json` for an example.
