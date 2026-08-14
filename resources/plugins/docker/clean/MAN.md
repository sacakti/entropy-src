# docker.clean

## NAME

docker.clean - controlled Docker storage cleanup.

## SYNOPSIS

```text
docker.clean
```

## DESCRIPTION

The plugin checks Docker storage availability before performing cleanup.

When available storage is at or above `minimum_storage`, no cleanup is
performed unless `force=true`.

## CLEANUP POLICIES

### tag

Removes Docker images whose full image reference contains `tag_pattern`.

### cache

Runs Docker builder cache cleanup.

### unused

Removes unused Docker images.

### complete

Runs complete Docker system cleanup with all unused images.

This mode requires `confirm=true`.

## ARGUMENTS

### minimum_storage

Minimum available storage in GB.

Default:

```text
10
```

### cleanup

One of:

```text
tag
cache
unused
complete
```

Default:

```text
tag
```

### tag_pattern

Required when `cleanup=tag`.

Example:

```text
:25.01.01.
```

### force

When `true`, bypasses the minimum-storage check and executes the
selected cleanup policy.

Default:

```text
false
```

### dry_run

When `true`, cleanup operations are not performed.

Default:

```text
false
```

### confirm

Required for `cleanup=complete`.

Default:

```text
false
```

## SAFETY

The plugin is storage-aware by default.

`complete` cleanup requires explicit confirmation.

`force` bypasses only the storage threshold. It does not bypass
validation such as the required `tag_pattern` or `confirm=true`.

## LOGGING

Docker stdout and stderr are written to the plugin log.

User-facing progress and status messages are emitted through the
Entropy plugin message API.
