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

### 1.0.0
- First release.
