# Entropy

> **A Modular Python-Based Deployment Automation Framework**

---
# Dependency libs installation using requirements.txt if internet connection available in the machine.

pip install -r requirements.txt

# If internet is accessible then use the below command to install

pip downlod offline_packages

pip install \
    --no-index \
    --find-links=offline_packages \
    -r requirements.txt

---

# Project Information

| Property | Value |
|----------|-------|
| **Project Name** | Entropy |
| **Python Version** | 3.9 |
| **Allowed External Libraries** | `ruamel.yaml`, `rich` |
| **Platform** | Linux |
| **Database** | SQLite |
| **Deployment Target** | Oracle Database + OpenShift |

---

# Overview

Entropy is a **plugin-driven deployment automation framework** designed for enterprise application deployments involving Oracle databases, OpenShift resources, shell scripts, ConfigMaps, Secrets, and deployment workflows.

The application is completely modular. Every deployment operation is implemented as an independent plugin managed by the **Entropy Process Manager**.

The deployment sequence is driven entirely by a configurable JSON workflow.

---

# Design Goals

- Fully modular architecture
- Plugin-based execution model
- Workflow-driven deployments
- Process lifecycle management
- Rich console interface
- Complete logging
- Release tracking
- YAML automation
- Database deployment automation
- OpenShift integration
- HTML reporting

---

# Core Requirements

## 1. Shell Script Execution

Support execution of independent Linux shell scripts.

Example:

```bash
deploy.sh
backup.sh
cleanup.sh
```

---

## 2. SQLPlus Master Script Execution

Execute Oracle deployment using a master SQL calling script.

Example

```sql
@app_master.sql
```

---

## 3. Master Script Analysis

Entropy should:

- Parse master SQL scripts
- Identify child SQL files
- Validate execution order
- Cross-reference workflow definition
- Build dependency graph before execution

---

## 4. SQL & Shell Validation

Before execution:

### SQL Validation

- Missing files
- Invalid includes
- SQL syntax validation (basic)
- Circular includes
- Duplicate execution detection

### Shell Validation

- Syntax checking

```bash
bash -n script.sh
```

---

## 5. OpenShift Command Execution

Execute OpenShift CLI commands using the installed `oc` client.

Examples

```bash
oc login

oc apply

oc replace

oc rollout status

oc rsync

oc exec
```

All commands must execute through the Linux Executor.

---

## 6. ConfigMap / Secret Update

Entropy downloads YAML files from OpenShift into a local Git repository.

Updates are performed locally using **ruamel.yaml** while preserving:

- comments
- formatting
- ordering

Finally:

```bash
oc replace -f yaml
```

---

## 7. Workflow Driven Deployment

Deployment execution follows a JSON workflow.

Each release may contain:

```
deployment_flow.json
```

Otherwise the default workflow is used.

---

## 8. Rich Console Output

Console output should resemble modern package managers.

Use:

```
rich
```

Examples

- Progress bars
- Status indicators
- Panels
- Tables
- Live updates
- Colored logging

---

## 9. Logging

Entropy must maintain complete logs.

Supported levels

- INFO
- DEBUG
- WARNING
- ERROR
- EXCEPTION

Requirements

- Log rotation
- Timestamped logs
- One log per release
- One log per process
- Stack traces
- Execution duration
- Command outputs

Example

```
logs/

    release_20260721.log

    analyse_db.log

    execute_yaml.log

    process_manager.log
```

---

## 10. Internal Queue Manager

Provide an internal queue capable of executing background jobs.

Example tasks

- Database backup
- YAML update
- Git commit
- Report generation

Queue features

- Multiple workers
- Retry
- Failure tracking
- Progress reporting

---

## 11. Plugin Architecture

Entropy must not be tightly coupled.

Every deployment operation is a plugin.

Examples

```
plugins/

    analyse_db

    execute_db

    execute_shell

    execute_yaml

    execute_oc

    report

    git

    validator
```

Users can:

- execute one plugin
- execute multiple plugins
- create new plugins
- register plugins without changing the core application

---

## 12. Process Management

Every execution creates

- PID
- Log file
- Runtime metadata

Supported operations

- Start
- Pause
- Resume
- Stop
- Monitor
- Query Status

Example

```
entropy status RELEASE001

entropy pause RELEASE001

entropy resume RELEASE001

entropy logs RELEASE001
```

---

## 13. Git Repository Management

Entropy maintains a local Git repository.

Workflow

```
Download YAML

↓

Modify locally

↓

oc replace

↓

Commit

↓

Tag using Release ID
```

Benefits

- Version history
- Rollback
- Audit trail

---

## 14. SQLite Release Database

SQLite stores deployment metadata.

Example tables

### Releases

| Column | Description |
|---------|-------------|
| release_id | Unique runtime ID |
| handoff | Release owner |
| status | Running / Failed / Completed |
| started_at | Timestamp |
| completed_at | Timestamp |

---

### Files

| Column | Description |
|---------|-------------|
| release_id | FK |
| file_name | Deployment file |
| file_type | SQL / YAML / Shell |
| status | Execution status |

---

## 15. Report Plugin

The Report Plugin executes after deployment.

Generated artifacts

- HTML report
- Deployment summary
- Execution timeline
- Database logs
- Plugin execution summary
- OpenShift pod status
- Failed commands
- Warnings
- Execution statistics

---

# Important Architecture Notes

## Process Manager

All deployment activities must be controlled by the Entropy Process Manager.

No plugin may execute external commands directly.

Instead

```
Plugin

↓

Process Manager

↓

Linux Executor

↓

Operating System
```

---

## Linux Executor

All external commands pass through a single execution layer.

Examples

- Shell scripts
- SQLPlus
- OC Client
- Git
- Bash
- SSH

This centralizes:

- logging
- timeout
- retries
- process tracking
- error handling

---

## Workflow Resolution

Priority

```
Release deployment_flow.json

↓

Default workflow.json
```

---

## Configuration

All environment-specific configuration resides in

```
entropy.json
```

Example

```json
{
    "database": {},
    "openshift": {},
    "servers": {},
    "logging": {}
}
```

---

## Common Libraries

Reusable Python modules reside under

```
lib/
```

Examples

```
lib/

    logger.py

    process_manager.py

    linux_executor.py

    yaml_helper.py

    sqlite.py

    git.py

    config.py
```

---

# Sample ConfigMap Update JSON

```json
{
    "name": "app1.yaml",
    "add": {
        "key1": "value1",
        "key2": 2,
        "key3": 1.8
    },
    "add.properties": {
        "property": "app.properties",
        "APP_KEY1": 1,
        "APP_KEY2": "hello"
    },
    "update": {
        "key4": "estimated"
    },
    "update.properties": {
        "property": "app.properties",
        "APP_KEY1": 2,
        "APP_KEY2": "welcome"
    },
    "delete": [
        "KEY1",
        "KEY2"
    ],
    "delete.properties": {
        "property": "app.properties",
        "keys": [
            "KEY1",
            "KEY2"
        ]
    }
}
```

---

# Sample Workflow

```json
{
    "name": "default",
    "metadata": {
        "version": "1.0.0",
        "created_at": "21-July-2026",
        "created_by": "Aravinthan",
        "target": "SIT",
        "strict_target": true,
        "plugin_validate": true,
        "ignore_plugin_error": false
    },
    "workflow": {
        "follow_incremental_steps": true,
        "ROOT": "/app/releases/",
        "steps": {
            "...": "Refer to provided workflow.json"
        }
    }
}
```

---

# Suggested Project Structure

```
entropy/

├── app.py
├── entropy.json
├── workflow.json
├── deployment_flow.json
│
├── lib/
│   ├── config.py
│   ├── logger.py
│   ├── process_manager.py
│   ├── linux_executor.py
│   ├── queue.py
│   ├── git.py
│   ├── sqlite.py
│   ├── yaml_helper.py
│   └── utilities.py
│
├── plugins/
│   ├── analyse_db/
│   ├── execute_db/
│   ├── execute_shell/
│   ├── execute_yaml_update/
│   ├── execute_yaml_apply/
│   ├── execute_oc/
│   ├── execute_rsync/
│   ├── validator/
│   └── report/
│
├── logs/
│
├── releases/
│
├── reports/
│
├── database/
│
└── repository/
```

---

# Deployment Lifecycle

```text
Release

      │

      ▼

Load Configuration

      │

      ▼

Load Workflow

      │

      ▼

Validate Plugins

      │

      ▼

Analyze SQL

      │

      ▼

Validate Files

      │

      ▼

Execute Workflow

      │

      ▼

Update YAML

      │

      ▼

OpenShift Deployment

      │

      ▼

Git Commit

      │

      ▼

Generate HTML Report

      │

      ▼

Deployment Complete
```

---

# Key Features

- Plugin-based architecture
- Workflow-driven deployment
- Oracle SQLPlus integration
- Shell execution
- OpenShift automation
- ConfigMap and Secret updates
- Git versioning
- SQLite release tracking
- Process lifecycle management
- Rich console interface
- Comprehensive logging
- HTML reporting
- Queue-based background processing
- Modular and extensible design

---

# Future Enhancements

- Parallel workflow execution
- Dependency-aware scheduling
- Rollback framework
- Web dashboard
- REST API
- Multi-environment deployment support
- Email and Slack notifications
- Plugin marketplace
- YAML schema validation
- Kubernetes native deployment mode

# Install plugins
- ent pl install ./resources/plugins/builtin/hello
- ent pl install ./resources/plugins/builtin/shell
- ent pl install ./resources/plugins/docker/build
- ent pl install ./resources/plugins/docker/clean
- ent pl install ./resources/plugins/docker/generic
- ent pl install ./resources/plugins/oc/cm_secret_update
- ent pl install ./resources/plugins/release/context_builder

# Vault namespace
# Namespace
python3 entropy.py vault namespace create deployer
python3 entropy.py vault namespace list
python3 entropy.py vault namespace read deployer

# Entries
python3 entropy.py vault add DB_HOST db.example.com -n deployer
python3 entropy.py vault add DB_PORT 5432 --type number -n deployer
python3 entropy.py vault add DEBUG true --type boolean -n deployer
python3 entropy.py vault add DB_PASSWORD --enc -n deployer

python3 entropy.py vault list -n deployer

python3 entropy.py vault inspect DB_HOST -n deployer
python3 entropy.py vault inspect DB_PASSWORD -n deployer
python3 entropy.py vault inspect DB_PASSWORD --reveal -n deployer

# Update
python3 entropy.py vault update DB_HOST db-new.example.com -n deployer
python3 entropy.py vault inspect DB_HOST -n deployer

# Namespace access
python3 entropy.py vault namespace users deployer
python3 entropy.py vault namespace users deployer grant aravinth --access read
python3 entropy.py vault namespace users deployer
python3 entropy.py vault namespace users deployer grant aravinth --access write
python3 entropy.py vault namespace users deployer
python3 entropy.py vault namespace users deployer revoke aravinth
python3 entropy.py vault namespace users deployer

# Namespace modification
python3 entropy.py vault namespace modify deployer --new-name production
python3 entropy.py vault namespace read production

# Delete entry
python3 entropy.py vault delete DB_PORT -n production

# Delete namespace
python3 entropy.py vault namespace delete production
