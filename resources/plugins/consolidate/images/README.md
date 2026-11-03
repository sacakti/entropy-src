# Consolidate images (consolidate.images)

`consolidate.images` keeps the **latest image of each service** across several release
packages, so an environment that receives several releases at once builds and transfers
each image once.

It reads two kinds of package, and any mix of them. A release without images is skipped:

```text
H001: scripts/deploy/image_transfer.sh pushes app1:1.0.0, app2:1.2.0
H002: App/services/app-3/image, and a transfer of app1:1.1.0
=> build app-3; transfer app1:1.1.0 and app2:1.2.0
```

It only reads releases and writes files. `docker.build`, `builtin.shell` and `oc.deployment`
do the work, as `workflow.json` shows: that file is the complete consolidation workflow for
releases H001 and H002.

See [MAN.md](MAN.md) for the details.
