# oc.pod_logs

Browse, read and save the logs of an OpenShift namespace's pods, from a live page.

## Overview

`oc.pod_logs` is an **app plugin**: run its workflow in interactive mode and the run's
**App** tab shows a file-explorer tree beside a read-only viewer. Automated runs make one
pass: they list the pods and their log paths in the outputs.

The plugin only reads. It runs `oc get pods`, `oc logs`, and `oc exec … sh` with fixed
scripts that list a folder (`stat`) or read a file (`base64`, `tail -c`); paths are
passed as arguments, never as part of a script.

## Requirements

- `oc` on the Entropy server's PATH.
- An `oc.generic` login for the environment (operation `login`) earlier in the
  workflow, or in an earlier run: the plugin uses that session and never logs in.
- In the containers: `sh`, `stat`, `base64` and `tail` (BusyBox has them).
- Permission to `get` and `exec` into pods, and to read pod logs.

Not needed with `dry_run`.

## Arguments

| Argument | Required | Type | Default | Description |
|---|---|---|---|---|
| `environment` | Unless `dry_run` | `string` | — | oc.generic environment whose login session is used. |
| `namespace` | No | `string` | session project | Project to browse; can be changed on the page. |
| `default_paths` | No | `list` | `["/var/log"]` | Log folders or files shown for every pod. |
| `log_paths` | No | `dictionary` | `{}` | Deployment name or pattern to its log folders or files. |
| `timezone` | No | `string` | `UTC` | Zone of typed From/To times, of log timestamps without one, and of the time in download names. |
| `max_read_mb` | No | `integer` | `20` | Most MB read from one file (1–200). |
| `max_lines` | No | `integer` | `20000` | Most lines shown, and read from a console log. |
| `max_bundle_mb` | No | `integer` | `200` | Most MB in one download of the listed logs (1–2000). |
| `dry_run` | No | `boolean` | `false` | Use sample pods instead of OpenShift. |

### `log_paths`

Paths per deployment, shown after the default paths when that deployment's pod is
opened. Keys are deployment names or shell-style patterns:

```json
{
    "log_paths": {
        "orders-api": ["/opt/orders/logs"],
        "billing-*": ["/app/logs/billing.log", "/tmp"]
    }
}
```

A pod's deployment comes from its owner: the ReplicaSet of a Deployment (without its
hash), a DeploymentConfig, or a StatefulSet, DaemonSet or Job; else its `app` label.
Each path's note in the tree says why it is there (`default`, `configured for …`).
A path may name one file; a path missing in a container says so.

## The page

| Input | What it does |
|---|---|
| Namespace | Project to browse (blank: the argument, else the session's project). |
| Pods | Show only pods whose name or deployment contains this text. |
| Time range | Everything, Last 15 minutes … Last 7 days, or Between. |
| From / To | The times for Between, picked with a date and time picker, in `timezone`. |

- Click a pod to see its containers, console logs and paths; click a folder or an
  archive to look inside (a folder is read again each time it is opened).
- Click a file to read it. **Reload** reads it again.
- **Highlight** marks every match in the open file; Enter and Shift+Enter move
  between them. The full screen button gives the viewer the whole screen (Esc leaves).
- **Search** (the box above the tree) finds text, in any case, in every log of the
  ticked pods, containers, folders and files, or with nothing ticked, of every listed
  pod: console logs and the files under its paths, read inside the containers with
  `grep` whether or not they were opened. The matching lines show in the viewer as
  `<pod>/<container>  <path>:<line>  <text>`, and the files with matches are listed
  above the pods; click one to open it with the text highlighted. At most 200 matches a
  file and 2000 in all. Archives and `.gz` files are not searched (open them in the
  tree), and the time range does not narrow a search. Search with an empty box to clear
  the results.
- **Download** (in the viewer) saves what the viewer shows, in the browser.
- **Save** writes the open file, narrowed to the time range, to
  `pod_logs/<pod>/<container>/` in the workspace and offers it for download at once.
- **Download (time range)** and **Download (everything)**, above the tree, make one
  `.zip` of the ticked entries. Tick a pod, a container, a folder, a console log, a
  file, an archive or a file in an archive; a ticked entry includes everything under
  it, and folders are read from the container whether or not they were expanded
  (up to 8 levels deep and 5000 logs). With nothing ticked, the `.zip` holds every
  listed log:
  - the console log of each container of every listed pod (the Pods filter applies),
  - everything in the paths of the pods opened so far, expanded or not.

  With the time range, text files (and `.gz` files, unpacked) are narrowed to it, files
  last written before it are left out, and opened archives give their files, narrowed
  too; otherwise files go in as they are.

  The `.zip` and the folder inside it are named after the pod (or `<namespace>-logs`
  for several pods) and the time it was made, in the `timezone` argument, e.g.
  `orders-api-7c9d-x2kqp-2026-11-10_14-30-05`. Inside are `<container>/<path>` for one
  pod, else `<pod>/<container>/<path>`, and a `README.txt` naming the range, when it
  was made and anything left out (unreadable, or past `max_bundle_mb`).
- While a `.zip` is made, the page shows its progress: listing folders, reading each
  log (n of total), compressing. Downloading a file shows how much has arrived.

Saved files and bundles are listed as **Ready** above the tree, and in the run's
artifacts straight away.

### Time range

A line's time is the first timestamp near its start: ISO 8601
(`2026-11-08T10:00:00.123Z`, `2026-11-08 10:00:00,123`) or the access-log form
(`08/Nov/2026:10:00:00 +0000`). Lines without one, such as stack traces, go with the
line above. A file without timestamps is shown whole, and the viewer says so.
Console logs are read with `--since-time`. In folders, files last written before the
range starts are hidden, and the folder's note counts them.

### Large files

A file larger than `max_read_mb` is read from its end (its newest part), and the
viewer says how much was read. Archives and `.gz` files are read whole, so larger ones
are refused; raise `max_read_mb` to open them. The viewer shows the newest
`max_lines` lines.

Archives are read in memory and never extracted on the server.

## Outputs

| Output | Type | Description |
|---|---|---|
| `namespace` | `string` | Namespace browsed last. |
| `pods` | `list` | Pod, deployment, status and log paths of each pod listed. |
| `opened` | `list` | Files opened, as `pod/container: path`. |
| `saved` | `list` | Files saved as artifacts, relative to the workspace. |

## Dry run

`"dry_run": true` needs no login and runs no `oc`: two sample pods (one with two
containers) have `/var/log` with timestamped logs, an `archive` folder with a
`.tar.gz`, a `.zip` and a `.gz`, and a per-service folder under `/opt`. Use it to try
the page and the time range locally.

## Changelog

### 1.3.0

- Search finds text in every log of the ticked or listed pods, opened or not, and lists
  the matches; a match opens its file with the text highlighted.
- The viewer can go full screen.

### 1.2.0

- Tick pods, containers, folders and files in the tree to download just those.
- Downloads read folders that were not expanded.
- The page shows progress while a download is made and while it downloads.
- Downloads are named after the pod and the time they were made, in the `timezone`
  argument; the folder inside the `.zip` carries the same name.

### 1.1.0

- From and To use a date and time picker.
- Download every listed log as one `.zip`, narrowed to the time range or as it is.
- Saved files can be downloaded at once, while the app runs.

### 1.0.0

- Initial release: pod tree with console logs, default and per-deployment paths,
  read-only viewer with highlighting, time range, archives, save, dry run.
