# Docker Clean Plugin

`docker.clean` provides controlled Docker storage cleanup.

## Cleanup behavior

By default the plugin checks available storage before performing cleanup.

If available storage is greater than or equal to `minimum_storage`,
the plugin performs no action.

Use `force=true` to execute the selected cleanup policy regardless of
available storage.

## Arguments

| Name | Type | Default | Description |
|---|---|---:|---|
| `minimum_storage` | integer | `10` | Minimum available storage in GB. |
| `cleanup` | string | `tag` | Cleanup policy: `tag`, `cache`, `unused`, or `complete`. |
| `tag_pattern` | string | — | Required for `tag`; image reference pattern to remove. |
| `force` | boolean | `false` | Run cleanup even when the storage threshold is satisfied. |
| `dry_run` | boolean | `false` | Report actions without removing Docker resources. |
| `confirm` | boolean | `false` | Required for `complete`. |

## Examples

### Tag cleanup

```bash
ent pl run docker.clean \
    -a cleanup=tag \
    -a 'tag_pattern=:25.01.01.'
```

### Force tag cleanup

```bash
ent pl run docker.clean \
    -a cleanup=tag \
    -a 'tag_pattern=:25.01.01.' \
    -a force=true
```

### Builder cache

```bash
ent pl run docker.clean \
    -a cleanup=cache
```

### Unused images

```bash
ent pl run docker.clean \
    -a cleanup=unused
```

### Complete cleanup

`complete` is destructive and requires explicit confirmation.

```bash
ent pl run docker.clean \
    -a cleanup=complete \
    -a confirm=true
```

## Outputs

The plugin reports storage and cleanup information including:

- `cleanup`
- `minimum_storage_gb`
- `storage_before_gb`
- `storage_after_gb`
- `storage_reclaimed_gb`
- `cleanup_required`
- `force`
- `dry_run`
- `items_removed`

Docker command stdout and stderr are written to the plugin runtime log.
