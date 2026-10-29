# quay.generic

------------------------------------------------------------------------

## Overview

The `quay.generic` plugin removes old images from a Quay registry by
deleting tags through the Quay API (v1). For each repository of a
namespace it ranks the active tags newest first (by the time each tag
was pushed) and keeps:

- tags matching `protect` (default `latest`), always;
- for tags matching a custom rule (first match wins), the rule's newest
  `keep` tags (all of them when the rule has no `keep`);
- for all other tags, the newest `keep` (default 6).

A tag beyond its rule's limit is still kept while it is younger than
`min_age_days` (or the rule's own `min_age_days`).

Deleting a tag does not delete an image that another tag still points
to; Quay garbage-collects images without tags.

------------------------------------------------------------------------

## Listing and the report

`operation=list` reads the same tags and applies the same policy, but
never deletes: use it to see each service's tags and what a cleanup would
remove.

Every run (unless `report=false`) writes one self-contained HTML file:
summary tiles, the retention policy, and a table per repository with each
tag's push time and age, digest, size, action and reason. It is named
`quay-tags-*.html`, `quay-dry-run-*.html` or `quay-cleanup-*.html`, kept in
the plugin's data folder under `reports/<namespace>` (or `report_directory`)
so it outlasts the run, and registered under Artifacts → Generated. Its
path is the `report` output. The token never appears in it.

------------------------------------------------------------------------

## Safety

- `dry_run` is `true` by default: the plan is reported, nothing is deleted.
- `keep` must be at least 1. To purge selected tags, use a rule with
  `"keep": 0`.
- A failed deletion is reported in `errors` and fails the step; the
  other deletions still run.
- The token is sent only in the Authorization header and is never logged.

------------------------------------------------------------------------

## Token

Use an OAuth application token (Organization > Applications > Generate
Token, with "Administer Repositories") or a robot account with admin
permission on the repositories. Keep it in the vault and pass it as
`${entv:<namespace>/<key>}`.

------------------------------------------------------------------------

## Rule examples

```json
[
    {"name": "pull requests", "tags": "pr-*", "keep": 0, "min_age_days": 3},
    {"name": "releases", "tags": "re:^v\\d+\\.\\d+\\.\\d+$", "keep": 12},
    {"name": "payments snapshots", "tags": "*-SNAPSHOT", "keep": 2, "repositories": ["payments-*"]},
    {"name": "hotfixes", "tags": "hotfix-*"}
]
```
