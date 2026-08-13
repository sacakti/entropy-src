# Image Transfer Plugin — Release Notes

## Overview

The `custom.image_transfer` plugin prepares a release for deployment and transfers container images to the configured Docker registry.

It is designed for release packages that contain deployment scripts such as:

```text
scripts/deploy/image_transfer.sh
scripts/deploy/apply_yaml.sh
```

The plugin handles the preparation and image-transfer workflow automatically.

It can:

* Extract a release ZIP archive
* Remove a previously extracted release when explicitly requested
* Locate deployment scripts inside the release
* Parse Docker commands from `image_transfer.sh`
* Validate Docker command ordering
* Check available Docker storage
* Remove matching old Docker images when storage is low
* Optionally clean Docker builder cache
* Execute Docker image operations
* Remove Git commands from `apply_yaml.sh`
* Remove positional credentials from Docker/OC login commands
* Rewrite release paths in `oc apply -f` commands
* Validate deployment YAML paths
* Prepare `apply_yaml.sh` without executing it
* Preserve the extracted release beside the original ZIP

The original release ZIP is **never modified**.

---

# Basic Usage

The plugin is identified as:

```text
custom.image_transfer
```

A minimal workflow step is:

```json
{
    "name": "Transfer Images",
    "plugin": "custom.image_transfer",
    "enabled": true,
    "continue_on_error": false,
    "arguments": {
        "release": "/home/devops/releases/H001.zip"
    }
}
```

The plugin provides sensible defaults for the remaining configuration.

---

# Release Package

The plugin expects a ZIP release containing deployment scripts.

For example:

```text
H001.zip
└── ...
    └── scripts/
        └── deploy/
            ├── image_transfer.sh
            └── apply_yaml.sh
```

The default deployment-script directory is:

```text
scripts/deploy
```

The default script names are:

```text
image_transfer.sh
apply_yaml.sh
```

---

# Extracted Release

The supplied release ZIP is extracted beside the archive.

For example:

```text
/home/devops/releases/H001.zip
```

becomes:

```text
/home/devops/releases/
├── H001.zip
└── H001/
```

The original ZIP remains untouched.

The extracted release directory is retained after the plugin completes because the prepared deployment files are intended to be consumed later in the workflow.

---

# Removing an Existing Extracted Release

By default, the plugin refuses to overwrite an existing extracted release directory.

For example, if:

```text
H001/
```

already exists, the plugin fails rather than silently replacing it.

To explicitly remove the existing extracted release before extraction:

```json
{
    "release": "/home/devops/releases/H001.zip",
    "force_remove_processed": true
}
```

This is useful when the same release needs to be processed again.

---

# Deployment Script Configuration

The location and names of the deployment scripts can be customized.

```json
{
    "release": "/home/devops/releases/H001.zip",
    "release_scripts_directory": "scripts/deploy",
    "transfer_script": "image_transfer.sh",
    "apply_script": "apply_yaml.sh"
}
```

Defaults:

| Argument                    | Default             |
| --------------------------- | ------------------- |
| `release_scripts_directory` | `scripts/deploy`    |
| `transfer_script`           | `image_transfer.sh` |
| `apply_script`              | `apply_yaml.sh`     |

Both scripts must exist in the extracted release.

---

# Docker Image Transfer

The plugin reads supported Docker commands from `image_transfer.sh`.

Supported operations are:

```text
docker login
docker pull
docker tag
docker push
```

The plugin does **not** execute the complete `image_transfer.sh` as a shell script.

Instead, it:

1. Reads the script.
2. Extracts supported Docker commands.
3. Validates them.
4. Executes each Docker command individually.

This provides more controlled execution and reporting.

---

# Docker Command Ordering

The transfer script must contain the required operations:

```text
login
pull
tag
push
```

The plugin validates the broad ordering:

```text
Docker login
      ↓
Docker pull
      ↓
Docker tag
      ↓
Docker push
```

Multiple commands of each type are supported.

For example:

```bash
docker login registry.example.com
docker pull source/app:1.0
docker tag source/app:1.0 registry.example.com/app:1.0
docker push registry.example.com/app:1.0
```

The plugin rejects scripts where the required operations are missing or appear in an invalid order.

---

# Docker Login Credentials

The plugin removes positional credentials from Docker login commands.

For example:

```bash
docker login registry.example.com $1 $2
```

is transformed into:

```bash
docker login registry.example.com
```

This prevents credentials passed as positional shell parameters from being executed by the plugin.

Authentication is therefore expected to be handled by the Docker environment or its configured authentication mechanism.

---

# Docker Storage Validation

Before transferring images, the plugin checks the storage available to Docker.

The configured minimum is:

```json
{
    "min_free_storage_gb": 10
}
```

The default is:

```text
10 GB
```

The plugin checks Docker's root filesystem and compares available storage with the configured minimum.

If insufficient storage is available, the plugin can attempt the configured cleanup process before continuing.

---

# Automatic Old Image Cleanup

When Docker storage falls below the configured threshold, the plugin searches for old Docker images matching:

```json
{
    "old_image_pattern": "25.01.01."
}
```

The pattern is interpreted as a regular expression.

For example:

```text
25.01.01.
```

can be used to identify older image tags following that naming convention.

Matching images are removed using:

```text
docker rmi
```

If no matching images are found, the plugin reports that no cleanup was performed.

---

# Docker Builder Cache Cleanup

Docker builder cache cleanup is optional.

Enable it with:

```json
{
    "cleanup_builder_cache": true
}
```

The plugin executes:

```text
docker builder prune -f
```

After cleanup, Docker storage is checked again before image transfer continues.

The default is:

```text
false
```

---

# Skipping Docker Transfer

Docker operations can be skipped entirely:

```json
{
    "skip_docker": true
}
```

When enabled:

* Docker prerequisite checks are skipped.
* Old-image cleanup is skipped.
* Builder-cache cleanup is skipped.
* Docker image-transfer commands are not executed.

The release extraction and `apply_yaml.sh` preparation still take place.

This is useful when testing or preparing a release without actually transferring images.

---

# Preparing `apply_yaml.sh`

The plugin prepares the deployment YAML script but **does not execute it**.

This distinction is important.

The plugin modifies the extracted `apply_yaml.sh` so that it can reference the actual extracted release location.

For example, if the original script contains:

```bash
oc apply -f /home/devops/scripts/app-1/deployment.yaml
```

and the release was extracted to:

```text
/home/devops/releases/H001
```

the configured release base path:

```text
/home/devops
```

is replaced with the extracted release path.

The resulting command becomes equivalent to:

```bash
oc apply -f /home/devops/releases/H001/scripts/app-1/deployment.yaml
```

---

# Release Base Path

The default release base path is:

```text
/home/devops
```

It can be changed:

```json
{
    "release_base_path": "/opt/releases"
}
```

The plugin expects `oc apply -f` paths in `apply_yaml.sh` to begin with this configured base path.

For example:

```text
/home/devops/scripts/app/deployment.yaml
```

with:

```json
{
    "release_base_path": "/home/devops"
}
```

is valid.

A path outside the configured release base path is rejected.

This prevents unexpected filesystem paths from being silently rewritten.

---

# Git Commands

Standalone Git commands are removed from `apply_yaml.sh`.

For example:

```bash
git checkout something
git pull
```

are removed from the prepared script.

The plugin validates that no standalone Git command remains in the resulting script.

---

# OpenShift Login

Positional credentials are also removed from `oc login`.

For example:

```bash
oc login -u $1 -p $2
```

is converted to:

```bash
oc login
```

The plugin does not execute `apply_yaml.sh`, so the prepared script can subsequently be handled by another workflow step or deployment mechanism.

---

# YAML Validation

YAML path validation is enabled by default:

```json
{
    "validate_yaml": true
}
```

The plugin validates the **rewritten** paths, not the original paths.

An `oc apply -f` target may point to:

### A YAML file

```text
deployment.yaml
```

Supported extensions:

```text
.yaml
.yml
```

### A directory

A directory is valid when it contains at least one YAML file.

For example:

```text
deployments/
├── deployment.yaml
├── service.yaml
└── configmap.yml
```

If a referenced YAML path does not exist, the plugin fails.

---

# Disable YAML Validation

YAML validation can be disabled:

```json
{
    "validate_yaml": false
}
```

The script is still rewritten, but the resulting YAML paths are not checked.

---

# Complete Configuration

A complete configuration can look like:

```json
{
    "name": "Image Transfer",
    "plugin": "custom.image_transfer",
    "enabled": true,
    "continue_on_error": false,
    "tags": [
        "image_transfer"
    ],
    "arguments": {
        "release": "/home/devops/releases/H001.zip",

        "release_scripts_directory": "scripts/deploy",
        "transfer_script": "image_transfer.sh",
        "apply_script": "apply_yaml.sh",

        "release_base_path": "/home/devops",

        "force_remove_processed": true,

        "skip_docker": false,
        "cleanup_builder_cache": false,

        "validate_yaml": true,

        "min_free_storage_gb": 10,
        "old_image_pattern": "25.01.01."
    }
}
```

---

# Testing / Preparation Mode

A useful configuration for testing release preparation without transferring images is:

```json
{
    "arguments": {
        "release": "/home/devops/releases/H001.zip",
        "release_scripts_directory": "scripts/deploy",
        "transfer_script": "image_transfer.sh",
        "apply_script": "apply_yaml.sh",
        "release_base_path": "/home/devops",
        "force_remove_processed": true,
        "skip_docker": true,
        "cleanup_builder_cache": false,
        "validate_yaml": true
    }
}
```

This allows you to verify:

* Release extraction
* Script discovery
* `image_transfer.sh` parsing
* `apply_yaml.sh` transformation
* Git command removal
* Login credential removal
* YAML path rewriting
* YAML path validation

without performing Docker image transfer.

---

# Workflow Outputs

The plugin publishes several outputs.

## Configuration

```text
configuration
```

Contains the resolved plugin configuration.

## Docker status

```text
docker_skipped
```

Indicates whether Docker operations were skipped.

## Image transfer

```text
image_transfer
```

Indicates whether Docker image transfer was performed.

## Cleanup

```text
cleanup_performed
```

Indicates whether old Docker images were removed.

## YAML preparation

```text
yaml_script_prepared
```

Indicates that `apply_yaml.sh` was successfully prepared.

## YAML validation

```text
yaml_validation_enabled
```

Indicates whether YAML path validation was enabled.

## YAML paths

```text
yaml_paths
```

Contains the deployment YAML paths discovered in the prepared script.

## Release path

```text
release_path
```

Contains the path of the extracted release directory.

---

# Workflow Artifacts

The plugin publishes two workflow artifacts.

### Release

```text
release
```

Points to the extracted release directory.

### Prepared deployment script

```text
apply_yaml_script
```

Points to the prepared `apply_yaml.sh`.

These artifacts can be consumed by subsequent workflow steps.

---

# Complete Example

```json
{
    "name": "ImageTransferPlugin Workflow",
    "version": "1.0.0",
    "description": "Prepare release and transfer container images.",
    "variables": {},
    "steps": [
        {
            "name": "Execute ImageTransferPlugin",
            "plugin": "custom.image_transfer",
            "enabled": true,
            "continue_on_error": false,
            "tags": [
                "image_transfer"
            ],
            "arguments": {
                "release": "/home/devops/releases/H001.zip",

                "release_scripts_directory": "scripts/deploy",
                "transfer_script": "image_transfer.sh",
                "apply_script": "apply_yaml.sh",

                "release_base_path": "/home/devops",

                "force_remove_processed": true,

                "skip_docker": false,
                "cleanup_builder_cache": false,

                "validate_yaml": true,

                "min_free_storage_gb": 10,
                "old_image_pattern": "25.01.01."
            }
        }
    ]
}
```

---

# Argument Reference

| Argument                    | Required | Default             | Description                                   |
| --------------------------- | -------: | ------------------- | --------------------------------------------- |
| `release`                   |      Yes | —                   | Release ZIP archive                           |
| `release_scripts_directory` |       No | `scripts/deploy`    | Directory containing deployment scripts       |
| `transfer_script`           |       No | `image_transfer.sh` | Image transfer script                         |
| `apply_script`              |       No | `apply_yaml.sh`     | OpenShift deployment script                   |
| `release_base_path`         |       No | `/home/devops`      | Base path rewritten in `oc apply -f` commands |
| `force_remove_processed`    |       No | `false`             | Remove existing extracted release             |
| `skip_docker`               |       No | `false`             | Skip Docker checks and image transfer         |
| `cleanup_builder_cache`     |       No | `false`             | Run Docker builder cache cleanup              |
| `validate_yaml`             |       No | `true`              | Validate resulting YAML paths                 |
| `min_free_storage_gb`       |       No | `10`                | Minimum required Docker storage               |
| `old_image_pattern`         |       No | `25.01.01.`         | Regex used to identify old Docker images      |

---

# Processing Flow

The plugin follows this sequence:

```text
Release ZIP
     │
     ▼
Validate release
     │
     ▼
Extract beside ZIP
     │
     ▼
Locate deployment scripts
     │
     ├───────────────┐
     ▼               ▼
image_transfer.sh   apply_yaml.sh
     │               │
     ▼               │
Extract Docker      │
commands             │
     │               │
     ▼               │
Validate ordering    │
     │               │
     ▼               │
Check Docker storage │
     │               │
     ▼               │
Cleanup old images   │
     │               │
     ▼               │
Cleanup builder      │
cache                │
     │               │
     ▼               │
Execute Docker       │
commands             │
                     │
                     ▼
              Remove Git commands
                     │
                     ▼
              Remove login credentials
                     │
                     ▼
              Rewrite oc apply paths
                     │
                     ▼
              Validate YAML paths
                     │
                     ▼
              Prepared apply_yaml.sh
```

---

## Important Notes

1. The original release ZIP is never modified.
2. The extracted release directory remains beside the ZIP.
3. `image_transfer.sh` itself is not executed as a shell script.
4. Only supported Docker commands are extracted from `image_transfer.sh`.
5. Docker operations must contain login, pull, tag, and push in the expected order.
6. Docker login positional credentials `$1` and `$2` are removed.
7. `apply_yaml.sh` is prepared but **never executed** by this plugin.
8. Git commands are removed from the prepared deployment script.
9. `oc login` positional credentials `$1` and `$2` are removed.
10. `oc apply -f` paths are rewritten relative to the extracted release.
11. YAML validation occurs after path rewriting.
12. Docker storage is checked before image transfer unless `skip_docker` is enabled.
13. Old Docker images are removed only when storage is below the configured threshold.
14. Builder cache cleanup is optional.
15. The plugin is intended to prepare and transfer release artifacts; execution of the prepared OpenShift deployment script is outside this plugin's responsibility.

```
```
