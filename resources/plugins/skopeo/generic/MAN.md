# skopeo.generic

------------------------------------------------------------------------

## Overview

`skopeo.generic` reports the full image reference and the checksum of
the containers of OpenShift workloads, for audits, release notes, or
pinning images by digest in a later step.

- **pod**: reads the running pods. The tag comes from the pod spec; the
  checksum from the container status `imageID`, which is the digest the
  node pulled. During a rollout pods can differ: each distinct image and
  digest is reported once, with its pods.
- **skopeo**: runs `skopeo inspect --no-tags docker://<image>` for each
  workload's image and reports its `Digest` (plus `Created` and
  `Architecture`). Each image is inspected once per run.
- **auto**: pods first; skopeo for workloads without a running pod.

------------------------------------------------------------------------

## Dependency on oc.generic

`oc.generic` is a required plugin. This plugin reuses its login session
(`<session>/.kube/<environment>/config`) and does not log in itself, the
same way `oc.rsync` does. Log in with `oc.generic` (operation `login`)
for the same `environment` before this step.

------------------------------------------------------------------------

## Selection

Out of, say, 50 deployments, read only the ones you need:

```json
{
  "deployments": "app-finance-*",
  "tags": "*-1.2.0*",
  "exclude": ["*-canary"]
}
```

or several rules (any may match; patterns inside one must all match):

```json
{
  "rules": [
    {"deployments": "app-finance-*", "tags": "*-1.2.0*"},
    {"deployments": "re:^app-hr-(api|ui)$"},
    {"tags": "re:-rc\\d+$", "containers": "app"}
  ]
}
```

Name patterns are checked before anything is inspected, so filtered-out
workloads cost nothing.

------------------------------------------------------------------------

## Registry credentials

`credentials` (`{"username": ..., "password": ...}` or a vault
reference) is written to a temporary, owner-only auth file in the run
workspace, passed with `--authfile`, and removed afterwards; it never
appears in a command line or in the logs. Alternatively pass `authfile`.

------------------------------------------------------------------------

## Notes

- For multi-architecture images, the digest a pod runs (pod mode) can be
  the platform manifest or the manifest list, depending on the container
  runtime; skopeo reports the digest of the manifest it resolved for its
  own platform. Compare digests from the same mode.
- Nothing in the cluster or registry is changed.
