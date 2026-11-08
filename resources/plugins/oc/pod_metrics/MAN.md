# oc.pod_metrics

## Overview

`oc.pod_metrics` shows the pods of an OpenShift namespace on a live page (the run screen's
**App** tab), refreshed every 5 seconds. It only runs `oc get`, using the login session of
`oc.generic` for the environment.

Run it in **interactive** mode for the live page. Automated runs (schedules, `ent`) make one
pass and report it in the outputs.

## Requirements

- `oc` on the machine that runs the plugin, and a session from `oc.generic` (`login`).
- Permission to list pods in the namespace.
- For usage: the cluster's metrics API (`metrics.k8s.io`) and permission to read it. Without
  it, the page still shows status and restarts, and says why usage is missing.

## Arguments

| Name | Type | Required | Default | Description |
|---|---|---|---|---|
| environment | string | yes | | `oc.generic` environment that is logged in. |
| namespace | string | no | session's project | Project to watch. |
| max_rows | integer | no | 500 | Most pods shown in the table. |

## Live page

| Control | Effect |
|---|---|
| Namespace | Watch another project (blank: the argument, else the session's project). |
| Filter | Pod name or status. |
| Sort by | CPU, Memory, CPU or Memory % of limit, Restarts or Name. |
| Only pods needing attention | Pods not finished and not fully running and ready. |
| Container details | Logs usage per container for the selected pods. |

If a refresh fails, the page keeps its last rows and says why in Activity.

### List: health marks

| Mark | When |
|---|---|
| Red row | Failing: `CrashLoopBackOff`, `Error`, `OOMKilled`, an image pull or container config error, or not ready and it has restarted. |
| Yellow row | Ready, but it has restarted. |
| Green Ready | Running, ready and never restarted (only the Ready cell is marked). |
| No mark | Anything else, such as a pod starting up or a finished job. |

### Graph

The Pods panel's **Graph** tab plots usage over the last 10 minutes of the page (120
refreshes; another namespace starts it again). Pick a metric, combine pods, filter by name
and limit the lines, or type a query and press **Run**:

```
[sum|avg|max|min](metric) [where condition [and condition]...] [top|bottom N]
```

- Metrics: `cpu`, `memory`, `cpu_percent`, `memory_percent`, `restarts`.
- Conditions: `pod ~ api` / `pod !~ job` (case-insensitive patterns), `pod = web-1`, or a
  metric's latest value, such as `memory_percent > 80` or `restarts > 0`.
- `top`/`bottom N` rank pods by the charted metric's latest value; at most 8 lines show.

Examples: `cpu top 5`, `memory where pod ~ "^api-" and restarts > 0`,
`sum(memory) where pod !~ job`. Press a legend entry to hide or show its line; hover the
graph (or focus it and use the arrow keys) to read the values.

## Reading the numbers

- Usage is the metrics API's latest sample, usually 15 to 60 seconds old, not this instant.
- "% of limit" shows `—` unless every container in the pod sets that limit: a partial total
  would mislead.
- A dash means no value: for example a pod too new to have a sample.

## Outputs

| Name | Type | Description |
|---|---|---|
| namespace | string | Namespace read on the last refresh. |
| pod_count | integer | Pods in the namespace. |
| attention_count | integer | Pods not finished and not fully running and ready. |
| cpu_millicores | number | CPU used by the namespace's pods. |
| memory_mib | number | Memory used by the namespace's pods. |
| metrics_available | boolean | False when the metrics API could not be read. |
| pods | list | One entry per pod. |

## Releases

### 1.1.0
- Health marks on the list: red failing rows, yellow restarted rows, a green Ready.
- A Graph tab with usage over time, filters and a query.

### 1.0.0
- First release.
