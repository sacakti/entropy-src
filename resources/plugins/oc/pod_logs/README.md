# oc.pod_logs

An app plugin to browse, read and save the logs of an OpenShift namespace's pods.

- A file-explorer tree: pods, their containers, each container's console log
  (`oc logs`), the default log paths and the paths configured for the pod's deployment.
- A read-only viewer with line numbers; type in **Highlight** to mark every match and
  step through them (Enter / Shift+Enter).
- A time range (last 15 minutes … 7 days, or Between two times picked with a date and
  time picker) narrows what is shown.
- Opens text files, `.zip`, `.tar.gz`/`.tgz`/`.tar` (look inside and open a member) and
  `.gz` files.
- **Download** saves what the viewer shows; **Save** keeps the open file, narrowed to
  the time range, and offers it for download at once.
- **Download listed** (above the tree) makes one `.zip` of every listed log, narrowed
  to the time range or as it is.

It needs an `oc.generic` login first (see `workflow.json`). `dry_run: true` uses
built-in sample pods instead, so the page can be tried without a cluster.

See `MAN.md` for arguments, outputs and details.
