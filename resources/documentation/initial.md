# Entropy

> **A modular, plugin-driven deployment automation framework for
> enterprise application delivery.**

Entropy is a Python-based deployment automation platform designed to
orchestrate release workflows across Oracle databases, OpenShift, YAML
repositories, shell commands, Git repositories, and extensible plugins.

The framework combines:

-   JSON-defined workflows
-   plugin-based execution
-   centralized command execution
-   process/workflow lifecycle management
-   SQLite persistence
-   authentication and authorization
-   role/group-based access control
-   namespaced encrypted Vault values
-   environment-aware workflow interpolation
-   OpenShift and Oracle deployment plugins
-   structured console output and logging

This document describes the current architecture, runtime model,
installation, commands, authorization model, Vault, workflows, plugins,
and development history.

------------------------------------------------------------------------

## Table of Contents

1.  [Project Overview](#project-overview)
2.  [Design Principles](#design-principles)
3.  [Technology](#technology)
4.  [Installation](#installation)
5.  [Application Architecture](#application-architecture)
6.  [Application Startup](#application-startup)
7.  [Database and Persistence](#database-and-persistence)
8.  [Authentication](#authentication)
9.  [Authorization](#authorization)
10. [Users](#users)
11. [Groups](#groups)
12. [Roles and Permissions](#roles-and-permissions)
13. [Vault](#vault)
14. [Vault Namespaces and Access](#vault-namespaces-and-access)
15. [Workflow Engine](#workflow-engine)
16. [Workflow Variables and
    Interpolation](#workflow-variables-and-interpolation)
17. [Tags and Selective Workflow
    Execution](#tags-and-selective-workflow-execution)
18. [Plugins](#plugins)
19. [Extension Management](#extension-management)
20. [Artifact Generation](#artifact-generation)
21. [Database Migration and Upgrade](#database-migration-and-upgrade)
22. [OpenShift and Deployment
    Automation](#openshift-and-deployment-automation)
23. [Logging and Observability](#logging-and-observability)
24. [CLI Reference](#cli-reference)
25. [Security Model](#security-model)
26. [Development Architecture](#development-architecture)
27. [Testing and Troubleshooting](#testing-and-troubleshooting)
28. [Changelog](#changelog)
29. [Future Enhancements](#future-enhancements)

------------------------------------------------------------------------

# Project Overview

Entropy is a deployment automation framework rather than a collection of
deployment scripts.

A deployment is represented as a workflow. A workflow contains ordered
steps, and each step invokes a plugin. Plugins perform focused
operations such as:

-   building release context
-   manipulating YAML
-   executing shell commands
-   updating ConfigMaps and Secrets
-   modifying deployments
-   applying OpenShift resources
-   running rsync operations
-   executing SQLPlus plans
-   managing Docker operations
-   interacting with Git

The core application is responsible for orchestration, authorization,
persistence, configuration, workflow execution, and plugin lifecycle.

A simplified runtime flow is:

``` text
CLI
 │
 ▼
Command Manager
 │
 ▼
Entropy Context
 │
 ├── Authentication
 ├── Authorization
 ├── Managers / Services
 ├── Repositories
 ├── Workflow Engine
 └── Plugin System
       │
       ▼
    Plugin
       │
       ▼
 Central execution / operating-system integration
```

------------------------------------------------------------------------

# Design Principles

Entropy follows several architectural rules.

## Modular responsibilities

Commands handle CLI concerns.

Managers handle business rules.

Repositories handle persistence.

Plugins handle deployment-specific operations.

The authorization layer decides whether an authenticated user may
execute an operation.

## Authorization at the command boundary

Authorization is enforced before privileged operations are performed.

The command layer resolves the current session and asks the
authorization service for the required permission.

For example:

``` text
users delete
    │
    └── requires users.delete
```

and:

``` text
vault namespace create
    │
    └── requires vault.namespace.create
```

This keeps business managers independent from CLI authorization
mechanics.

## Idempotent initialization

Built-in modules, permissions, roles, and administrator authorization
data are seeded using idempotent initialization.

Re-running initialization must not duplicate existing records.

## Repository abstraction

Database access is isolated behind repositories.

For example:

``` text
UserManager
    └── UserRepository

RoleManager
    ├── RoleRepository
    ├── PermissionRepository
    └── RolePermissionRepository

GroupManager
    ├── GroupRepository
    ├── UserGroupRepository
    ├── RoleRepository
    └── GroupRoleRepository

VaultManager
    ├── VaultRepository
    └── VaultNamespaceManager
```

------------------------------------------------------------------------

# Technology

  -----------------------------------------------------------------------
  Property                            Current Design
  ----------------------------------- -----------------------------------
  Language                            Python

  Target Python                       3.9+ design baseline

  Database                            SQLite

  Console UI                          Rich

  YAML processing                     ruamel.yaml

  Deployment target                   Linux

  Primary deployment targets          Oracle Database and OpenShift

  Configuration                       JSON / application configuration

  Workflow format                     JSON

  Package / plugin format             Python packages / wheels / Entropy
                                      resources
  -----------------------------------------------------------------------

The original project specification identifies `ruamel.yaml` and `rich`
as the principal external libraries. fileciteturn45file0

------------------------------------------------------------------------

# Installation

Install dependencies when internet access is available:

``` bash
pip install -r requirements.txt
```

For offline installation:

``` bash
pip download -r requirements.txt -d offline_packages
```

Then install without reaching PyPI:

``` bash
pip install \
    --no-index \
    --find-links=offline_packages \
    -r requirements.txt
```

Run Entropy from the project root:

``` bash
python3 entropy.py <command>
```

If the `ent` executable is installed or exposed on `PATH`, the same
commands can be written as:

``` bash
ent <command>
```

------------------------------------------------------------------------

# Application Architecture

A typical project is organized around these layers:

``` text
entropy.py
│
├── core/
│   ├── application
│   ├── context
│   ├── context_factory
│   ├── commands
│   ├── exceptions
│   └── authorization
│
├── lib/
│   ├── authorization/
│   ├── database/
│   │   ├── connection
│   │   ├── repositories
│   │   └── tables
│   ├── models/
│   ├── users/
│   ├── vault/
│   ├── workflow/
│   ├── extensions/
│   ├── plugins/
│   ├── upgrade/
│   └── ...
│
├── resources/
│   └── plugins/
│
├── tests/
│
└── database / runtime resources
```

The exact repository tree may evolve as new modules are introduced.

------------------------------------------------------------------------

# Application Startup

The application starts through `entropy.py`.

Initialization builds the application context and wires repositories,
managers, services, commands, and authorization.

A simplified sequence is:

``` text
entropy.py
   │
   ▼
Application.initialize()
   │
   ▼
ContextFactory.build()
   │
   ├── database connection
   ├── repositories
   ├── services
   ├── managers
   ├── authorization
   └── commands
   │
   ▼
CLI command execution
```

The application context acts as the dependency container for the
runtime.

This avoids commands constructing their own database repositories or
services.

------------------------------------------------------------------------

# Database and Persistence

SQLite is the application persistence layer.

Authorization is represented using relational tables including:

``` text
modules
permissions
roles
role_permissions
user_roles
groups
user_groups
group_roles
user_privileges
```

Vault adds:

``` text
vault_namespaces
vault_namespace_access
vault_entries
```

The Vault entry model is namespace-aware:

``` text
vault_entries
    namespace_id
    key
    value
    type
    sensitive
    created_at
    updated_at
```

The namespace/key pair is unique.

Therefore the same key may exist in different namespaces:

``` text
SIT / DB_CONNECTION
UAT / DB_CONNECTION
PROD / DB_CONNECTION
```

without collision.

------------------------------------------------------------------------

# Authentication

Entropy maintains an authenticated session containing:

``` text
user_id
username
token
created_at
expires_at
```

The session model can serialize itself to a dictionary and restore
itself from serialized data.

Typical authentication commands:

``` bash
ent auth login
ent auth logout
ent auth status
```

Check the current session:

``` bash
ent auth status
```

Authorization is evaluated using the authenticated user's identity and
assigned privileges.

------------------------------------------------------------------------

# Authorization

Entropy uses operation-level permissions.

A permission has:

``` text
module
name
permission type
description
```

Permission types are:

``` text
read
write
execute
```

Examples:

``` text
users.read
users.create
users.delete

groups.read
groups.users
groups.roles

vault.read
vault.add
vault.modify
vault.delete

vault.namespace.create
vault.namespace.read
vault.namespace.modify
vault.namespace.delete
vault.namespace.users
```

Authorization relationships are:

``` text
User
 │
 ├── direct privileges
 │
 ├── roles
 │     └── permissions
 │
 └── groups
       └── roles
             └── permissions
```

This permits both individual and group-based authorization.

------------------------------------------------------------------------

# Users

## Create

``` bash
ent users create <username>
```

Optional profile information:

``` bash
ent users create <username> \
    --full-name "<full name>" \
    --email "<email>"
```

## List

``` bash
ent users list
```

## Delete

``` bash
ent users delete <username>
```

The system user is protected from deletion.

## Password

Change the current user's password:

``` bash
ent users password
```

Administrative password change:

``` bash
ent users password <username>
```

## Enable

``` bash
ent users enable <username>
```

## Disable

``` bash
ent users disable <username>
```

The protected system user cannot be disabled.

## User roles

List assigned roles:

``` bash
ent users roles <username> list
```

Assign a role:

``` bash
ent users roles <username> grant <role>
```

Example:

``` bash
ent users roles aravinth grant read
```

Revoke a role:

``` bash
ent users roles <username> revoke <role>
```

Example:

``` bash
ent users roles aravinth revoke read
```

User role management is a privileged authorization operation and should
require the corresponding `users.roles` permission.

------------------------------------------------------------------------

# Groups

Groups provide reusable authorization membership.

## Create

``` bash
ent groups create <name>
```

With description:

``` bash
ent groups create <name> \
    --description "Development team"
```

## List

``` bash
ent groups list
```

## Read

``` bash
ent groups read <name>
```

## Modify

``` bash
ent groups modify <name> --new-name <new-name>
```

or:

``` bash
ent groups modify <name> \
    --description "Updated description"
```

## Delete

``` bash
ent groups delete <name>
```

------------------------------------------------------------------------

## Group users

List users:

``` bash
ent groups users <group>
```

Add a user:

``` bash
ent groups users <group> add <username>
```

Example:

``` bash
ent groups users developers add aravinth
```

Remove a user:

``` bash
ent groups users <group> remove <username>
```

------------------------------------------------------------------------

## Group roles

List roles:

``` bash
ent groups roles <group>
```

Grant:

``` bash
ent groups roles <group> grant <role>
```

Example:

``` bash
ent groups roles developers grant read
```

Revoke:

``` bash
ent groups roles <group> revoke <role>
```

------------------------------------------------------------------------

# Roles and Permissions

Roles are reusable collections of permissions.

## Create

``` bash
ent roles create <name>
```

With description:

``` bash
ent roles create <name> \
    --description "Deployment operations"
```

## List

``` bash
ent roles list
```

## Read

``` bash
ent roles read <name>
```

## Modify

``` bash
ent roles modify <name>
```

With a new name:

``` bash
ent roles modify <name> --new-name <new-name>
```

## Delete

``` bash
ent roles delete <name>
```

The built-in `admin` role is protected and cannot be modified or
deleted.

------------------------------------------------------------------------

## Role permissions

List permissions:

``` bash
ent roles permissions <role>
```

Grant:

``` bash
ent roles permissions <role> grant <permission>
```

Example:

``` bash
ent roles permissions deployment grant users.read
```

Revoke:

``` bash
ent roles permissions <role> revoke <permission>
```

Example:

``` bash
ent roles permissions deployment revoke users.read
```

------------------------------------------------------------------------

# Built-in Authorization Roles

Entropy seeds reusable authorization roles during initialization.

The intended role model provides broad access levels:

``` text
read
write
execute
full
```

and module-scoped access such as:

``` text
vault-read
vault-write
vault-execute
vault-full

users-read
users-write
users-execute
users-full

groups-read
groups-write
groups-execute
groups-full
```

The exact installed role set should always be confirmed from the
database:

``` bash
ent roles list
```

The administrator role is:

``` text
admin
```

The administrator role is seeded with all available permissions and
assigned to the bootstrap administrator.

------------------------------------------------------------------------

# Authorization Initialization

Built-in authorization is initialized idempotently.

The initialization process:

``` text
1. Seed modules
2. Seed permissions
3. Create admin role if missing
4. Assign all permissions to admin
5. Assign admin role to bootstrap administrator
6. Seed built-in reusable roles
```

The bootstrap administrator is the fixed system administrator account.

The administrator role is deliberately protected from normal role
modification and deletion.

------------------------------------------------------------------------

# Vault

Entropy Vault provides a persistent, namespaced key/value store for
deployment secrets and configuration.

A Vault entry contains:

``` text
namespace
key
value
type
sensitive
timestamps
```

Supported value types include:

``` text
string
number
boolean
array
object
json
```

Vault operations are authorization-controlled.

------------------------------------------------------------------------

# Vault Namespaces

Namespaces isolate environments or logical secret sets.

Typical namespaces:

``` text
SIT
UAT
PROD
```

## Create

``` bash
ent vault namespace create <name>
```

Example:

``` bash
ent vault namespace create deployer
```

## List

``` bash
ent vault namespace list
```

## Read

``` bash
ent vault namespace read <name>
```

## Modify

``` bash
ent vault namespace modify <name> \
    --new-name <new-name>
```

## Delete

``` bash
ent vault namespace delete <name>
```

Deleting a namespace also deletes its entries because `vault_entries`
references the namespace with cascade deletion.

------------------------------------------------------------------------

# Vault Namespace Access

A namespace owner has administrative ownership of the namespace.

Explicit user access can also be assigned.

List namespace users:

``` bash
ent vault namespace users <namespace>
```

Grant read access:

``` bash
ent vault namespace users <namespace> \
    grant <username> \
    --access read
```

Grant write access:

``` bash
ent vault namespace users <namespace> \
    grant <username> \
    --access write
```

Grant administrative access:

``` bash
ent vault namespace users <namespace> \
    grant <username> \
    --access admin
```

Revoke access:

``` bash
ent vault namespace users <namespace> \
    revoke <username>
```

Namespace access levels are:

``` text
read
write
admin
```

------------------------------------------------------------------------

# Vault Entries

## Add a string

``` bash
ent vault add DB_HOST db.example.com -n deployer
```

## Add a number

``` bash
ent vault add DB_PORT 5432 \
    --type number \
    -n deployer
```

## Add a boolean

``` bash
ent vault add DEBUG true \
    --type boolean \
    -n deployer
```

## Add an encrypted value

``` bash
ent vault add DB_PASSWORD \
    --enc \
    -n deployer
```

## List entries

``` bash
ent vault list -n deployer
```

## Inspect an entry

``` bash
ent vault inspect DB_HOST -n deployer
```

For sensitive values, reveal explicitly:

``` bash
ent vault inspect DB_PASSWORD \
    --reveal \
    -n deployer
```

## Update

``` bash
ent vault update DB_HOST db-new.example.com \
    -n deployer
```

## Delete

``` bash
ent vault delete DB_PORT \
    -n deployer
```

------------------------------------------------------------------------

# Workflow Engine

Entropy deployments are driven by JSON workflows.

A workflow contains:

``` text
metadata
variables
steps
```

A simplified workflow:

``` json
{
    "name": "ReleaseDeployment",
    "version": "1.0.0",
    "variables": {
        "environment": "SIT"
    },
    "steps": [
        {
            "name": "BuildContext",
            "plugin": "release.context_builder",
            "enabled": true,
            "on_failure": "abort",
            "arguments": {}
        }
    ]
}
```

Each step identifies a plugin and its arguments.

------------------------------------------------------------------------

# Workflow Execution

Run a workflow file:

``` bash
ent wf run -f ./tests/test_interpolation.json
```

Execute only steps matching a tag:

``` bash
ent wf run \
    -f ./tests/test_interpolation.json \
    --tags db_creds
```

This is useful for focused testing and operational execution.

The workflow engine resolves variables before invoking the selected
plugin.

------------------------------------------------------------------------

# Workflow Variables and Interpolation

Entropy supports normal variables:

``` json
{
    "variables": {
        "environment": "SIT",
        "image_tag": "1.1.10"
    }
}
```

Reference them using:

``` text
${environment}
${image_tag}
```

Step outputs can be referenced using:

``` text
${steps.BuildReleaseContext.outputs.images}
```

Nested structures are supported through the step-output path.

------------------------------------------------------------------------

# Vault Workflow Interpolation

Vault values can be injected directly into workflow variables.

Static namespace:

``` json
{
    "connection": "${entv:SIT/DB_CONNECTION}"
}
```

Environment-driven namespace:

``` json
{
    "environment": "UAT",
    "connection": "${entv:${environment}/DB_CONNECTION}"
}
```

The nested variable is resolved before the Vault reference is evaluated.

Therefore:

``` text
${environment}
```

becomes:

``` text
UAT
```

and the final Vault reference becomes:

``` text
${entv:UAT/DB_CONNECTION}
```

Wildcard retrieval is supported:

``` json
{
    "schemas": "${entv:${environment}/SCHEMAS_*}"
}
```

For example:

``` text
${entv:UAT/SCHEMAS_*}
```

can resolve multiple matching Vault entries.

This provides environment-independent workflows:

``` text
same workflow
      │
      ├── SIT → SIT namespace
      ├── UAT → UAT namespace
      └── PROD → PROD namespace
```

------------------------------------------------------------------------

# Vault Authorization During Workflow Execution

Vault interpolation is not merely a database lookup.

The current authenticated session is checked against the namespace.

A workflow referencing:

``` text
${entv:SIT/DB_CONNECTION}
```

requires the executing user to have sufficient access to the `SIT`
namespace.

The namespace owner has administrative ownership, while other users can
receive explicit namespace access.

This prevents a workflow user from bypassing Vault namespace security
simply by knowing the namespace name.

------------------------------------------------------------------------

# Tags and Selective Workflow Execution

Steps can define tags:

``` json
{
    "name": "PrintDatabaseCreds",
    "tags": [
        "test",
        "db_creds"
    ]
}
```

Execute only matching steps:

``` bash
ent wf run \
    -f workflow.json \
    --tags db_creds
```

This is useful for:

-   debugging
-   targeted tests
-   environment verification
-   validating interpolation
-   running only a subset of deployment operations

------------------------------------------------------------------------

# Plugins

Plugins are the primary extension mechanism for deployment operations.

A plugin encapsulates one focused capability.

Examples include:

``` text
builtin.hello
builtin.shell

docker.build
docker.clean
docker.generic

oc.cm_secret_update
oc.deployment
oc.generic
oc.rsync

release.context_builder

sqlplus.generic

custom.stage_release_copy
```

Plugins are installed and managed independently from the core command
implementation.

------------------------------------------------------------------------

# Plugin Lifecycle

The plugin system supports operations such as:

``` text
discover
install
uninstall
upgrade
execute
```

Example plugin installation:

``` bash
ent pl install ./resources/plugins/builtin/hello
ent pl install ./resources/plugins/builtin/shell
ent pl install ./resources/plugins/docker/build
ent pl install ./resources/plugins/docker/clean
ent pl install ./resources/plugins/docker/generic
ent pl install ./resources/plugins/oc/cm_secret_update
ent pl install ./resources/plugins/release/context_builder
```

The exact plugin inventory depends on the installed resources.

------------------------------------------------------------------------

# Extension Management

Python extensions are managed separately from workflow plugins.

List local extension wheels:

``` bash
ent extension wheels
```

Install an extension:

``` bash
ent extension install <name>
```

With a version:

``` bash
ent extension install <name> \
    --version <version>
```

Uninstall:

``` bash
ent extension uninstall <name>
```

List installed extensions:

``` bash
ent extension list
```

Verify:

``` bash
ent extension verify <name>
```

Repair:

``` bash
ent extension repair <name>
```

Download:

``` bash
ent extension download <name>
```

With version:

``` bash
ent extension download <name> \
    --version <version>
```

Extension operations are authorization-controlled according to the
corresponding `extensions.*` permissions.

------------------------------------------------------------------------

# Artifact Generation

Entropy can generate framework artifacts.

Generate a plugin:

``` bash
ent generate plugin <name>
```

Specify a namespace:

``` bash
ent generate plugin <name> \
    --namespace <namespace>
```

Short form:

``` bash
ent generate plugin <name> \
    -n <namespace>
```

The default plugin namespace is:

``` text
custom
```

------------------------------------------------------------------------

# Database Migration and Upgrade

## Migration

Apply pending migrations:

``` bash
ent migrate
```

Alias:

``` bash
ent mig
```

Database migration is an application-level operation and is
intentionally treated separately from normal authenticated deployment
commands.

## Upgrade

Upgrade Entropy from an `.epkg` package:

``` bash
ent upgrade \
    --source /path/to/entropy.epkg
```

Alias:

``` bash
ent up \
    --source /path/to/entropy.epkg
```

------------------------------------------------------------------------

# OpenShift and Deployment Automation

Entropy is designed for deployment environments where OpenShift is part
of the release process.

Typical operations include:

``` text
oc apply
oc replace
oc rollout status
oc rsync
oc exec
```

The framework can update local YAML repositories before applying
resources.

For ConfigMaps and Secrets, YAML processing is performed locally so
formatting and comments can be preserved.

A typical deployment sequence is:

``` text
Build release context
        │
        ▼
Resolve YAML resources
        │
        ▼
Update ConfigMaps / Secrets
        │
        ▼
Update Deployment YAML
        │
        ▼
oc apply / replace
        │
        ▼
Rsync required paths
        │
        ▼
Execute database plan
```

------------------------------------------------------------------------

# Release Context

The release context builder produces structured deployment information
that later workflow steps consume through interpolation.

For example:

``` text
${steps.BuildReleaseContext.outputs.deployment}
```

and:

``` text
${steps.BuildReleaseContext.outputs.database}
```

This avoids duplicating release-analysis logic across individual
plugins.

------------------------------------------------------------------------

# SQLPlus Automation

Oracle deployment can be represented as a workflow step.

A database execution plan may contain:

``` text
connection
schemas
execution plan
error policy
```

Example:

``` json
{
    "plugin": "sqlplus.generic",
    "arguments": {
        "mode": "plan",
        "on_error": "continue",
        "connection": "${connection}",
        "schemas": "${schemas}",
        "execution": "${steps.BuildReleaseContext.outputs.database}"
    }
}
```

Vault can supply the connection and schema credentials dynamically.

This allows credentials to remain outside the workflow source.

------------------------------------------------------------------------

# YAML Automation

Entropy uses YAML manipulation for OpenShift resources.

The intended model is:

``` text
Remote/OpenShift resource
        │
        ▼
Local YAML repository
        │
        ▼
ruamel.yaml modification
        │
        ▼
Preserve comments / ordering / formatting
        │
        ▼
oc replace / oc apply
```

This supports controlled Git-backed configuration management.

------------------------------------------------------------------------

# Git Integration

Git can be used to preserve deployment configuration history.

A typical flow is:

``` text
Download YAML
      ↓
Modify YAML
      ↓
Validate
      ↓
OpenShift operation
      ↓
Commit
      ↓
Tag release
```

This provides:

-   configuration history
-   auditability
-   release traceability
-   rollback support through repository history

------------------------------------------------------------------------

# Logging and Observability

Entropy provides structured console output and application logging.

The original architecture calls for:

``` text
INFO
DEBUG
WARNING
ERROR
EXCEPTION
```

Deployment execution should retain:

-   timestamps
-   execution duration
-   command output
-   error information
-   stack traces
-   plugin results
-   workflow step status

The console UI uses Rich-style tables, status indicators, rules, and
structured result output.

A workflow execution therefore provides clear step-level visibility:

``` text
▶ Step 1/1 : PrintDatabaseCreds
ℹ Starting plugin execution.
...
✔ Plugin completed successfully.
✔ Step completed
```

------------------------------------------------------------------------

# CLI Reference

Top-level command families include:

``` text
auth
extension / extensions / ext
format
generate / gen / create
migrate / mig
plugin / plugins / pl
upgrade / up
user / users
vault / entv
workflow / workflows / wf
```

Authorization-related commands include:

``` text
users
groups
roles
```

Vault commands include:

``` text
vault namespace
vault add
vault list
vault inspect
vault update
vault delete
```

Workflow commands include:

``` text
wf run
```

The exact command aliases are intentionally kept short for operational
use.

------------------------------------------------------------------------

# Security Model

Entropy's security model is layered.

## Authentication

Identifies the current user.

``` text
Session
  ↓
Authenticated user
```

## Authorization

Determines whether the user may perform the requested operation.

``` text
User
  ↓
Roles / Groups / Privileges
  ↓
Permissions
  ↓
Command
```

## Vault namespace authorization

Separately controls access to secret data.

``` text
Workflow
  ↓
Vault interpolation
  ↓
Namespace
  ↓
Namespace access
  ↓
Vault value
```

This prevents generic authorization from becoming a substitute for
secret-specific access control.

------------------------------------------------------------------------

# System User

Entropy has a protected system username represented by the application's
`SYSTEM_USERNAME`.

The system user cannot be deleted or disabled.

This is intentionally enforced using a model-level identity rather than
assuming a particular administrator username.

The bootstrap administrator is fixed as:

``` text
admin
```

The administrator receives the protected `admin` role during
authorization initialization.

------------------------------------------------------------------------

# Administrator Role

The built-in administrator role:

``` text
admin
```

is immutable through normal role-management operations.

The role receives all seeded permissions.

Therefore the administrator can manage:

-   users
-   groups
-   roles
-   permissions
-   Vault
-   namespaces
-   plugins
-   extensions
-   workflows
-   other protected operations

The role itself cannot be modified or deleted through the normal role
manager.

------------------------------------------------------------------------

# Permission Inventory

Current permission definitions include:

## Vault

``` text
vault.add
vault.read
vault.modify
vault.delete

vault.namespace.create
vault.namespace.read
vault.namespace.modify
vault.namespace.delete
vault.namespace.users
```

## Users

``` text
users.create
users.read
users.modify
users.delete
users.enable
users.disable
users.roles
```

## Workflows

``` text
workflows.add
workflows.list
workflows.edit
workflows.run
workflows.start
```

## Plugins

``` text
plugins.install
plugins.uninstall
plugins.list
plugins.upgrade
plugins.run
```

## Extensions

``` text
extensions.download
extensions.install
extensions.list
```

## Generate

``` text
generate.plugin
```

## Migration

``` text
migrate.database
```

## Upgrade

``` text
upgrade.entropy
```

## Authentication

``` text
auth.login
auth.logout
auth.status
```

## Roles

``` text
roles.create
roles.read
roles.modify
roles.delete
roles.permissions
```

## Groups

``` text
groups.create
groups.read
groups.modify
groups.delete
groups.users
groups.roles
```

------------------------------------------------------------------------

# Typical Authorization Scenarios

## Give a user read-only access to the platform

``` bash
ent users roles aravinth grant read
```

## Give a user full Vault access

``` bash
ent users roles aravinth grant vault-full
```

## Give a group full Vault access

``` bash
ent groups roles developers grant vault-full
```

## Give a user full user-management access

``` bash
ent users roles aravinth add users-full
```

## Inspect a user's roles

``` bash
ent users roles aravinth list
```

## Inspect role permissions

``` bash
ent roles permissions vault-full
```

The authorization chain can therefore be understood as:

``` text
user
  ↓
role
  ↓
permission
  ↓
command
```

------------------------------------------------------------------------

# Development Architecture

Entropy uses dependency injection through the application context.

The context is constructed by `ContextFactory`.

Repositories are created around a shared database connection.

Managers are constructed from repositories.

Commands receive managers/services through the context.

A representative dependency graph:

``` text
Application
    │
    ▼
ContextFactory
    │
    ├── DatabaseConnection
    │      │
    │      ├── Repositories
    │      │
    │      └── Tables / migrations
    │
    ├── Authentication services
    │
    ├── Authorization services
    │
    ├── UserManager
    ├── RoleManager
    ├── GroupManager
    ├── VaultManager
    ├── VaultNamespaceManager
    ├── Workflow services
    ├── Plugin services
    └── Extension services
```

------------------------------------------------------------------------

# Repository Responsibilities

Repositories should remain persistence-focused.

Examples:

``` text
UserRepository
RoleRepository
PermissionRepository
RolePermissionRepository
UserRoleRepository
GroupRepository
UserGroupRepository
GroupRoleRepository
VaultRepository
VaultNamespaceRepository
VaultNamespaceAccessRepository
```

Repositories should not decide whether a user is authorized to execute
an operation.

That belongs to the authorization layer.

------------------------------------------------------------------------

# Manager Responsibilities

Managers implement business rules.

For example:

``` text
GroupManager
    create group
    modify group
    delete group
    add/remove users
    grant/revoke roles
```

and:

``` text
RoleManager
    create role
    modify role
    delete role
    grant/revoke permissions
```

and:

``` text
VaultNamespaceManager
    create namespace
    modify namespace
    delete namespace
    grant/revoke namespace access
```

Commands remain responsible for translating CLI input into those
operations.

------------------------------------------------------------------------

# Exception Model

Entropy uses domain-specific exception hierarchies rather than relying
on generic `ValueError` for user-facing business failures.

Examples:

``` text
VaultError
 ├── VaultEntryExistsError
 ├── VaultEntryNotFoundError
 └── VaultValueError

VaultKeyError

UserError
 ├── UserAlreadyExistsError
 ├── UserNotFoundError
 ├── WeakPasswordError
 ├── SystemUserError
 ├── PasswordReuseError
 └── ...
```

This makes errors easier to classify and report consistently.

------------------------------------------------------------------------

# Testing and Troubleshooting

## Check authentication

``` bash
python3 entropy.py auth status
```

## List Vault namespaces

``` bash
python3 entropy.py vault namespace list
```

## List Vault entries

``` bash
python3 entropy.py vault list -n SIT
```

## Test workflow interpolation

``` bash
python3 entropy.py wf run \
    -f ./tests/test_interpolation.json \
    --tags db_creds
```

## Test a user's authorization

Authenticate as the target user and execute a command requiring the
expected permission.

For a read-only role:

``` text
read     → allowed
write    → denied
execute  → denied
```

This is the most important verification for the role hierarchy.

------------------------------------------------------------------------

# Common Failure Modes

## Vault namespace not found

Example:

``` text
Vault namespace 'SIT' not found.
```

Verify:

``` bash
ent vault namespace list
```

Then create the namespace or correct the workflow environment.

## Vault permission denied

Example:

``` text
Permission denied for Vault namespace 'SIT'
```

The authenticated user may have application-level Vault permissions but
still lack namespace access.

Grant explicit access:

``` bash
ent vault namespace users SIT \
    grant aravinth \
    --access read
```

The namespace owner has ownership and should not normally need to grant
access to themselves.

## Workflow variable not resolved inside Vault reference

Incorrect behavior occurs if the interpolation engine treats:

``` text
${entv:${environment}/DB_CONNECTION}
```

as a single unresolved Vault expression.

The correct resolution order is:

``` text
${environment}
        ↓
UAT
        ↓
${entv:UAT/DB_CONNECTION}
        ↓
Vault lookup
```

## User has a role but lacks an operation

Inspect the role:

``` bash
ent roles permissions <role>
```

Then verify that the required permission exists.

For example:

``` text
users.roles
```

is required to manage roles assigned to users.

------------------------------------------------------------------------

# Deployment Lifecycle

The intended enterprise deployment lifecycle is:

``` text
Release
   │
   ▼
Load configuration
   │
   ▼
Load workflow
   │
   ▼
Authenticate / authorize
   │
   ▼
Resolve variables
   │
   ▼
Resolve Vault values
   │
   ▼
Validate plugins and inputs
   │
   ▼
Build release context
   │
   ▼
Analyze / prepare database operations
   │
   ▼
Update YAML resources
   │
   ▼
OpenShift deployment
   │
   ▼
Database execution
   │
   ▼
Git commit / release tracking
   │
   ▼
Reporting / observability
   │
   ▼
Deployment complete
```

The exact sequence depends on the workflow definition.

------------------------------------------------------------------------

# Example End-to-End Workflow

A deployment workflow can use:

``` json
{
    "variables": {
        "environment": "UAT",
        "connection": "${entv:${environment}/DB_CONNECTION}",
        "schemas": "${entv:${environment}/SCHEMAS_*}"
    },
    "steps": [
        {
            "name": "BuildReleaseContext",
            "plugin": "release.context_builder",
            "enabled": true,
            "on_failure": "abort",
            "arguments": {}
        },
        {
            "name": "PrintDatabaseCreds",
            "plugin": "builtin.shell",
            "enabled": true,
            "on_failure": "abort",
            "arguments": {
                "command": "echo \"Connection: $1 Schemas: $2\"",
                "args": [
                    "${connection}",
                    "${schemas}"
                ]
            }
        },
        {
            "name": "SQLPlusPlan",
            "plugin": "sqlplus.generic",
            "enabled": true,
            "on_failure": "abort",
            "arguments": {
                "mode": "plan",
                "connection": "${connection}",
                "schemas": "${schemas}",
                "execution": "${steps.BuildReleaseContext.outputs.database}"
            }
        }
    ]
}
```

The key security property is that the workflow contains references to
Vault data rather than hard-coding credentials.

------------------------------------------------------------------------

# Changelog

## 2026-08 --- Authorization and Vault namespace evolution

### Authorization

Entropy's authorization model was expanded from individual operation
checks into a reusable role/group model.

Implemented:

-   authorization modules
-   operation-level permissions
-   roles
-   role-permission assignments
-   user-role assignments
-   groups
-   user-group assignments
-   group-role assignments
-   protected administrator role
-   authorization initialization/seeding
-   command-level authorization enforcement

The administrator role is seeded with all available permissions.

### User protection

The system user was made independent of a hard-coded username
assumption.

Protected system identity is represented by:

``` text
SYSTEM_USERNAME
```

The system user cannot be deleted or disabled.

The bootstrap administrator is fixed as:

``` text
admin
```

### Default roles

The authorization model was extended to support reusable access levels:

``` text
read
write
execute
full
```

and module-scoped role patterns such as:

``` text
vault-full
users-full
groups-full
```

The purpose is to avoid manually assigning individual permissions for
common access profiles.

### User role management

User-role assignment was introduced around `UserRoleRepository` and
`UserRoleManager`.

Expected interface:

``` bash
ent users roles <username> list
ent users roles <username> grant <role>
ent users roles <username> revoke <role>
```

### Group role management

Groups can receive reusable roles:

``` bash
ent groups roles <group> grant <role>
ent groups roles <group> revoke <role>
```

This allows:

``` text
Users
  ↓
Groups
  ↓
Roles
  ↓
Permissions
```

### Vault namespace authorization

Vault was moved to a namespace-aware security model.

Namespaces contain isolated entries:

``` text
namespace
    └── key/value entries
```

Namespace access levels:

``` text
read
write
admin
```

Explicit namespace access is stored in:

``` text
vault_namespace_access
```

### Vault workflow interpolation

Workflow variables can reference namespaced Vault values:

``` text
${entv:SIT/DB_CONNECTION}
```

and dynamically:

``` text
${entv:${environment}/DB_CONNECTION}
```

Wildcard lookup is supported:

``` text
${entv:${environment}/SCHEMAS_*}
```

This enables a single workflow to operate across SIT, UAT, PROD, and
other namespaces.

### Vault security

Vault interpolation now checks the authenticated user's namespace access
instead of allowing unrestricted database lookup.

### CLI improvements

The CLI was extended across:

-   users
-   groups
-   roles
-   permissions
-   Vault namespaces
-   Vault namespace access
-   Vault entries
-   plugins
-   extensions
-   workflow execution

### Generate command

The plugin generator supports:

``` bash
ent generate plugin <name> --namespace <namespace>
```

and:

``` bash
ent generate plugin <name> -n <namespace>
```

The default namespace is `custom`.

### Migration / upgrade commands

Database migration and application upgrade remain dedicated operational
commands:

``` bash
ent migrate
ent upgrade --source <package>
```

------------------------------------------------------------------------

## Earlier architecture

The original Entropy design established:

-   plugin-driven deployment
-   workflow-driven execution
-   Oracle SQLPlus integration
-   OpenShift automation
-   YAML modification
-   Git-based configuration history
-   SQLite persistence
-   Rich console output
-   logging and observability
-   release tracking
-   process lifecycle management
-   queue-oriented background work
-   HTML reporting

The original project specification described the deployment lifecycle
as:

``` text
Release
  ↓
Load Configuration
  ↓
Load Workflow
  ↓
Validate Plugins
  ↓
Analyze SQL
  ↓
Validate Files
  ↓
Execute Workflow
  ↓
Update YAML
  ↓
OpenShift Deployment
  ↓
Git Commit
  ↓
Generate HTML Report
```

fileciteturn45file0

------------------------------------------------------------------------

# Future Enhancements

Potential future work identified during the project includes:

-   destructive-operation confirmation
-   more granular authorization administration
-   richer authorization inspection commands
-   parallel workflow execution
-   dependency-aware scheduling
-   rollback framework
-   web dashboard
-   REST API
-   multi-environment deployment management
-   email / Slack notifications
-   plugin marketplace
-   YAML schema validation
-   Kubernetes-native deployment mode
-   stronger packaging and source protection
-   expanded static type checking
-   additional automated integration tests

------------------------------------------------------------------------

# Operational Philosophy

Entropy should be treated as an automation platform rather than a script
runner.

The intended separation is:

``` text
CLI
 │
 ▼
Command
 │
 ├── authentication
 ├── authorization
 │
 ▼
Manager / Service
 │
 ▼
Repository / Plugin
 │
 ▼
Operating system / Database / OpenShift
```

For deployment automation:

``` text
Workflow
   ↓
Variables
   ↓
Vault / Context
   ↓
Plugin
   ↓
Execution
   ↓
Result
   ↓
Next workflow step
```

For authorization:

``` text
Authenticated user
   ↓
Direct privileges / Roles / Groups
   ↓
Permissions
   ↓
Command authorization
   ↓
Operation
```

For secrets:

``` text
Workflow
   ↓
Vault reference
   ↓
Namespace authorization
   ↓
Vault entry
   ↓
Resolved runtime value
```

These boundaries are the foundation of Entropy's maintainability and
security.

------------------------------------------------------------------------

# Quick Reference

``` bash
# Authentication
ent auth login
ent auth status
ent auth logout

# Users
ent users create <user>
ent users list
ent users delete <user>
ent users password
ent users enable <user>
ent users disable <user>
ent users roles <user> list
ent users roles <user> grant <role>
ent users roles <user> revoke <role>

# Groups
ent groups create <group>
ent groups list
ent groups read <group>
ent groups modify <group>
ent groups delete <group>
ent groups users <group>
ent groups users <group> add <user>
ent groups users <group> remove <user>
ent groups roles <group>
ent groups roles <group> grant <role>
ent groups roles <group> revoke <role>

# Roles
ent roles create <role>
ent roles list
ent roles read <role>
ent roles modify <role>
ent roles delete <role>
ent roles permissions <role>
ent roles permissions <role> grant <permission>
ent roles permissions <role> revoke <permission>

# Vault
ent vault namespace create <namespace>
ent vault namespace list
ent vault namespace read <namespace>
ent vault namespace modify <namespace>
ent vault namespace delete <namespace>
ent vault namespace users <namespace>
ent vault namespace users <namespace> grant <user> --access <access>
ent vault namespace users <namespace> revoke <user>

ent vault add <key> <value> -n <namespace>
ent vault list -n <namespace>
ent vault inspect <key> -n <namespace>
ent vault inspect <key> --reveal -n <namespace>
ent vault update <key> <value> -n <namespace>
ent vault delete <key> -n <namespace>

# Plugins
ent pl install <path>
ent pl list
ent pl uninstall <name>

# Extensions
ent ext install <name>
ent ext uninstall <name>
ent ext list
ent ext verify <name>
ent ext repair <name>
ent ext download <name>
ent ext wheels

# Generation
ent generate plugin <name>
ent generate plugin <name> -n <namespace>

# Workflow
ent wf run -f <workflow.json>
ent wf run -f <workflow.json> --tags <tag>

# Database
ent migrate

# Upgrade
ent upgrade --source <entropy.epkg>
```

------------------------------------------------------------------------

# Conclusion

Entropy combines deployment orchestration, extensibility, persistence,
authorization, and secret management into one operational framework.

Its most important architectural boundaries are:

``` text
Workflow
    → defines what should happen

Plugin
    → implements how a deployment operation happens

Manager
    → enforces business rules

Repository
    → persists state

Authorization
    → determines who may perform an operation

Vault
    → stores protected runtime configuration

Namespace Access
    → determines who may retrieve protected Vault data

Context
    → wires the application together
```

The result is a framework where deployment behavior can evolve
independently from the core application while authorization and secret
access remain centralized and enforceable.
