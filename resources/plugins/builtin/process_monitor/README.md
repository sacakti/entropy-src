# ProcessMonitorPlugin

An example **app plugin**: a live, filterable list of the processes on the Entropy server.

---

## Overview

`builtin.process_monitor` declares an `app` page in its `plugin.json`. When it runs in an
**interactive** run, the run screen gets an **App** tab with:

- Inputs: **Filter** (name or user), **Sort by**, **Only my processes**, **Inspect selected**.
- Views: a **Summary** of headline numbers, the **Processes** table (selectable rows) and an
  **Activity** log.

The plugin refreshes the table every 2 seconds, or at once when an input changes, until
**Stop app** is pressed. The step then completes normally. Automated runs make one pass
and show that snapshot.

---

## Writing an app plugin

1. Declare the page in `plugin.json`:

```json
"app": {
    "title": "Process monitor",
    "refresh_seconds": 2,
    "inputs": [
        {"name": "filter", "type": "text", "label": "Filter"},
        {"name": "inspect", "type": "button", "label": "Inspect selected", "target": "processes"}
    ],
    "views": [
        {"name": "summary", "type": "stats"},
        {"name": "processes", "type": "table", "row_key": "pid", "selectable": true},
        {"name": "activity", "type": "log"}
    ]
}
```

   - Input types: `text`, `number`, `select` (needs `choices`), `toggle`, `button`.
   - View types: `table`, `stats`, `log`, `keyvalue`, `text`.
   - A button's `target` names a selectable table; pressing it sends the selected rows' `row_key`.

2. Run a loop with `self.app` in `execute()`:

```python
while self.app.running:
    rows = self._load(self.app.input("filter", ""))
    self.app.table("processes", rows)
    self.app.stats("summary", {"Matching": len(rows)})
    for press in self.app.events("inspect"):
        self._inspect(press.selection)
    self.app.wait()
```

`self.app.running` is False once the user presses **Stop app**; automated runs get one pass.
