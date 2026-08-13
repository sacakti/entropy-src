# Stage Release Copy Plugin — Release Notes

## Overview

The `StageReleaseCopyPlugin` stages application artifacts from a release ZIP archive into a local repository directory.

The plugin provides:

* Release ZIP validation
* Automatic extraction into the workflow workspace
* Application artifact discovery
* Destination directory creation
* Backup of existing files
* Backup rotation by file count or age
* Temporary extraction cleanup
* Workflow outputs describing the staging operation
* Workflow artifacts for the staged release and backup location

All filesystem and archive operations are performed through the Entropy Plugin SDK.

---

## Basic Usage

The plugin is identified as:

```text
custom.stage_release_copy
```

A basic workflow step looks like:

```json
{
    "name": "Stage Release",
    "plugin": "custom.stage_release",
    "enabled": true,
    "continue_on_error": false,
    "arguments": {
        "release_path": "/home/devops/releases/application.zip",
        "destination_path": "/home/devops/repository"
    }
}
```

The release must be a ZIP archive.

---

## Release Archive Structure

The plugin expects the release archive to contain an `App` directory.

For example:

```text
release.zip
└── App/
    ├── app-1/
    │   └── image/
    │       ├── image.tar
    │       └── metadata.json
    │
    └── app-2/
        └── image/
            └── image.tar
```

The `App` directory itself is not copied to the destination.

Given:

```text
App/
└── app-1/
    └── image/
        └── image.tar
```

and:

```text
destination_path=/home/devops/repository
```

the resulting destination is:

```text
/home/devops/repository/
└── app-1/
    └── image/
        └── image.tar
```

---

## Required Arguments

### `release_path`

Path to the release ZIP archive.

```json
{
    "release_path": "/home/devops/releases/application.zip"
}
```

The plugin validates that:

1. The path exists.
2. The path is a file.
3. The file has a `.zip` extension.

Example:

```text
/home/devops/releases/application.zip
```

---

### `destination_path`

Directory where the release artifacts should be staged.

```json
{
    "destination_path": "/home/devops/repository"
}
```

The destination is created automatically when it does not already exist.

---

# Backup Support

Backups are enabled by default.

```json
{
    "backup": true
}
```

When an artifact already exists at the destination, the existing file is moved into a timestamped backup directory before the new release file is copied.

The backup structure is:

```text
repository/
├── app-1/
│   └── image/
│       └── image.tar
│
└── .backup/
    └── 20260811_141306_123456/
        └── app-1/
            └── image/
                └── image.tar
```

The original directory structure is preserved inside the backup.

---

## Disable Backups

Backups can be disabled:

```json
{
    "release_path": "/home/devops/releases/application.zip",
    "destination_path": "/home/devops/repository",
    "backup": false
}
```

When backup is disabled and a destination file already exists, the plugin fails instead of overwriting the existing file.

This provides protection against accidental replacement when backup functionality has explicitly been disabled.

---

# Backup Rotation

When backups are enabled, the plugin supports two rotation policies.

## Maximum Number of Backups

Use:

```json
{
    "backup": true,
    "rotate_backup_type": "max_files",
    "max_files": 5
}
```

Only the newest five backup directories are retained.

Older backup directories are removed automatically.

The default policy is:

```text
rotate_backup_type = max_files
max_files = 5
```

---

## Maximum Backup Age

Backups can instead be retained based on their age.

```json
{
    "backup": true,
    "rotate_backup_type": "max_timestamp",
    "max_timestamp": 5,
    "max_timestamp_unit": "days"
}
```

This keeps backups newer than five days and removes older backups.

Supported units are:

```text
hours
days
```

For example:

```json
{
    "rotate_backup_type": "max_timestamp",
    "max_timestamp": 24,
    "max_timestamp_unit": "hours"
}
```

retains backups from the last 24 hours.

---

# Complete Configuration

A full configuration can look like:

```json
{
    "name": "Stage Application Release",
    "plugin": "custom.stage_release_copy",
    "enabled": true,
    "continue_on_error": false,
    "tags": [
        "release",
        "staging"
    ],
    "arguments": {
        "release_path": "/home/devops/releases/application.zip",
        "destination_path": "/home/devops/repository",
        "backup": true,
        "rotate_backup_type": "max_files",
        "max_files": 5,
        "max_timestamp": 5,
        "max_timestamp_unit": "days"
    }
}
```

`max_timestamp` and `max_timestamp_unit` are only relevant when:

```text
rotate_backup_type = max_timestamp
```

Similarly, `max_files` is used when:

```text
rotate_backup_type = max_files
```

---

# Artifact Discovery

The plugin recursively discovers files under:

```text
App/<application>/
```

Only files are staged.

Directories are created automatically at the destination as required.

For example:

```text
App/
├── application-a/
│   ├── image/
│   │   ├── image.tar
│   │   └── config.json
│   └── config/
│       └── application.yaml
│
└── application-b/
    └── image/
        └── image.tar
```

produces:

```text
destination/
├── application-a/
│   ├── image/
│   │   ├── image.tar
│   │   └── config.json
│   └── config/
│       └── application.yaml
│
└── application-b/
    └── image/
        └── image.tar
```

---

# Temporary Extraction

The release is extracted into the workflow workspace before artifacts are processed.

The temporary staging location is:

```text
<workflow-workspace>/stage_release_copy
```

After processing completes, the extracted release is removed.

Cleanup is performed even when an error occurs during artifact processing.

This prevents temporary release contents from being left behind after workflow execution.

---

# Workflow Outputs

The plugin exposes information about the staging operation through workflow outputs.

Available outputs include:

```text
release_path
destination_path
backup_enabled
rotate_backup_type
files_copied
copied_files
backup_path
```

For example:

```text
files_copied
    12
```

and:

```text
copied_files
    [
        "/home/devops/repository/app-1/image/image.tar",
        "/home/devops/repository/app-1/image/config.json"
    ]
```

When backups are enabled and a backup is created:

```text
backup_path
    /home/devops/repository/.backup/20260811_141306_123456
```

---

# Workflow Artifacts

The plugin also exposes workflow artifacts.

### Staged release

```text
staged_release
```

points to the destination directory.

### Backup

When a backup is created:

```text
backup
```

points to the backup directory created for that staging operation.

---

# Validation

The plugin validates the following before staging:

### Release

```text
release_path
```

must:

* exist
* be a file
* have a `.zip` extension

### Release structure

The archive must contain:

```text
App/
```

The plugin fails if the `App` directory is missing or is not a directory.

### Backup configuration

`rotate_backup_type` must be:

```text
max_files
```

or:

```text
max_timestamp
```

`max_timestamp_unit` must be:

```text
hours
```

or:

```text
days
```

---

# Example Deployment Workflow

A typical release staging workflow could look like:

```json
{
    "name": "Stage Release",
    "version": "1.0.0",
    "description": "Stage application release artifacts.",
    "variables": {
        "release": "${entv:release_zip}",
        "repository": "${entv:docker_repository}"
    },
    "steps": [
        {
            "name": "Stage Release Artifacts",
            "plugin": "custom.stage_release_copy",
            "enabled": true,
            "continue_on_error": false,
            "tags": [
                "release"
            ],
            "arguments": {
                "release_path": "${release}",
                "destination_path": "${repository}",
                "backup": true,
                "rotate_backup_type": "max_files",
                "max_files": 5
            }
        }
    ]
}
```

The workflow variable resolver resolves the variables before the plugin receives its arguments.

---

# Argument Reference

| Argument             | Required | Default     | Description                          |
| -------------------- | -------- | ----------- | ------------------------------------ |
| `release_path`       | Yes      | —           | Path to the release ZIP              |
| `destination_path`   | Yes      | —           | Destination repository directory     |
| `backup`             | No       | `true`      | Enable backups of existing files     |
| `rotate_backup_type` | No       | `max_files` | Backup rotation policy               |
| `max_files`          | No       | `5`         | Maximum number of backup directories |
| `max_timestamp`      | No       | `5`         | Maximum backup age                   |
| `max_timestamp_unit` | No       | `days`      | Backup age unit                      |

---

# Operational Behavior

The staging process follows this sequence:

```text
Release ZIP
     │
     ▼
Validate release
     │
     ▼
Create destination
     │
     ▼
Extract release
     │
     ▼
Validate App/
     │
     ▼
Discover artifacts
     │
     ▼
Create backup
     │
     ▼
Backup existing files
     │
     ▼
Copy new artifacts
     │
     ▼
Rotate old backups
     │
     ▼
Publish workflow outputs/artifacts
     │
     ▼
Remove temporary extraction
```

This makes the plugin suitable for release staging workflows where existing repository contents need to be preserved before a new release is installed.

## Important Notes

1. The release must be a ZIP archive.
2. The archive must contain an `App` directory.
3. The `App` directory is stripped from the destination path.
4. Only files discovered under application directories are staged.
5. Existing files are backed up before replacement when backup is enabled.
6. If backup is disabled, an existing destination file causes the operation to fail.
7. Backup directories are automatically rotated according to the selected policy.
8. Temporary extracted release data is removed after processing.
9. The destination and backup locations must be writable by the Entropy process.
10. The plugin does not perform application-specific deployment logic; it stages release artifacts into the configured filesystem location.

```
```
