# Process Monitor Plugin — Release Notes

## Overview

`builtin.process_monitor` shows the processes of the Entropy server on a live page
(the run screen's **App** tab). It is the reference example of an app plugin.

---

## Basic Usage

Run it from Plugins or a workflow in **interactive** mode:

```json
{
    "name": "Process monitor",
    "plugin": "builtin.process_monitor",
    "arguments": {
        "max_rows": 200
    }
}
```

## Arguments

| Name | Type | Default | Description |
|---|---|---|---|
| max_rows | integer | 200 | Most processes shown in the table. |

## Outputs

| Name | Type | Description |
|---|---|---|
| process_count | integer | Processes matching the filter on the last refresh. |

## Releases

### 1.0.0
- First release: filter, sort, only-my-processes, selectable table, inspect selected.
