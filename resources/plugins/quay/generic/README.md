# Quay Plugin

`quay.generic` cleans images from a Quay registry. For every repository
(service) of a namespace it keeps the newest tags, **6 by default**, and
deletes the rest. Custom rules give selected tags their own retention.

With `operation=list` it only lists the tags of each repository (newest
first), with what the retention policy would do; nothing is deleted.

Both operations write an HTML report (every repository and tag: pushed,
digest, size, action, reason, rule). It is added to **Artifacts →
Generated** and kept in the plugin's data folder (`reports/<namespace>`),
or in `report_directory`.

Deleting a tag removes the image once no other tag points to it (Quay's
garbage collection). The plugin runs as a **dry run by default**: set
`dry_run=false` to delete.

## Arguments

| Name | Type | Default | Description |
|---|---|---:|---|
| `operation` | string | `clean` | `clean` deletes per the policy (see `dry_run`); `list` only lists tags. |
| `url` | string | — | Quay server URL. |
| `token` | string (secret) | — | OAuth application or robot token with admin rights on the repositories. |
| `namespace` | string | — | Organization (or user) to clean. |
| `repositories` | list | all | Repositories to clean: names or patterns. |
| `keep` | integer | `6` | Newest tags kept per repository (default rule). |
| `rules` | list | `[]` | Custom rules for selected tags (below). |
| `protect` | list | `["latest"]` | Tags never deleted. |
| `min_age_days` | integer | `0` | Tags younger than this are never deleted. |
| `dry_run` | boolean | `true` | Report only; set `false` to delete. |
| `report` | boolean | `true` | Write the HTML report (added to Artifacts → Generated). |
| `report_directory` | path | data folder | Where reports are kept. |
| `insecure_skip_tls_verify` | boolean | `false` | Skip TLS verification. |

Patterns are shell globs (`release-*`), or regular expressions prefixed
with `re:` (`re:^v\d+\.\d+\.\d+$`).

## Custom rules

Each rule is an object; the first rule matching a tag decides for it:

| Field | Description |
|---|---|
| `tags` | Tag pattern or list of patterns (required). |
| `keep` | Newest matching tags kept; `0` deletes them all; omit to never delete them. |
| `repositories` | Only in these repositories (patterns); all when omitted. |
| `min_age_days` | Overrides `min_age_days` for this rule. |
| `name` | Label shown in the plan. |

Tags matched by no rule (and not protected) follow the default `keep`.

## Examples

```bash
# List the tags of every service (and what cleanup would do)
ent pl run quay.generic -a operation=list -a url=https://quay.example.com \
    -a 'token=${entv:quay/cleanup_token}' -a namespace=payments

# What would be deleted, keeping 6 tags per service
ent pl run quay.generic -a url=https://quay.example.com \
    -a 'token=${entv:quay/cleanup_token}' -a namespace=payments

# Delete, keeping 10 per service
ent pl run quay.generic -a url=https://quay.example.com \
    -a 'token=${entv:quay/cleanup_token}' -a namespace=payments \
    -a keep=10 -a dry_run=false
```

Rules are easiest in a workflow; see `workflow.json`.

## Outputs

`operation`, `tags` (per repository, tag names newest first), `deleted`
(`repository:tag`), `deleted_count`, `tags_scanned`, `tags_kept`, `errors`,
`repositories`, `dry_run`, `report` (the HTML file), and `plan`: for each
repository, every tag with its status (keep, delete, deleted, failed),
reason and rule.
