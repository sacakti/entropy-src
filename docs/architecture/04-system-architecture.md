# System Architecture

Version: 1.0

Status: Draft

---

# Purpose

This document defines the high-level architecture of the Entropy Workflow Orchestration Platform.

It describes the major platform components, their responsibilities, ownership boundaries, and communication model.

This document intentionally avoids implementation details and focuses on architectural responsibilities.

---

# Architectural Overview

Entropy is composed of a small set of core platform services.

```
                    +----------------------+
                    |         CLI          |
                    +----------+-----------+
                               |
                               v
                    +----------------------+
                    |     Application      |
                    +----------+-----------+
                               |
                               v
                    +----------------------+
                    |    Runtime Engine    |
                    +----------+-----------+
                               |
          +--------------------+--------------------+
          |                    |                    |
          v                    v                    v
 +----------------+   +----------------+   +----------------+
 | Workflow Mgmt  |   | Plugin Manager |   | Security Mgmt  |
 +----------------+   +----------------+   +----------------+
          |                    |                    |
          +----------+---------+---------+----------+
                     |                   |
                     v                   v
             +---------------+   +---------------+
             | Workflow Exec |   | Plugin Registry|
             +-------+-------+   +---------------+
                     |
      +--------------+-----------------------------+
      |              |             |               |
      v              v             v               v
 Workspace      Event Bus      Report Mgmt   Artifact Mgmt
      |              |
      |              +------------------------------+
      |                                             |
      v                                             v
 Plugin Executor --------------------------> Observability
      |
      v
   Plugins
```

---

# Architectural Layers

Entropy is organized into five layers.

```
Presentation Layer

↓

Platform Layer

↓

Runtime Layer

↓

Execution Layer

↓

Plugin Layer
```

Each layer depends only on the layer directly below it.

Business logic never exists above the Plugin Layer.

---

# Presentation Layer

Responsible for user interaction.

Components

- CLI
- Future REST API
- Future Web UI

Responsibilities

- Receive user input
- Display execution progress
- Display reports
- Display diagnostics

Does NOT

- Execute workflows
- Load plugins
- Store runtime state

---

# Platform Layer

The Platform Layer initializes and coordinates the system.

Components

- Application
- Configuration Manager
- Authentication Manager
- Plugin Discovery
- Repository Manager

Responsibilities

- Startup
- Shutdown
- Configuration
- Authentication
- Plugin discovery
- Workflow loading

The Platform Layer prepares the runtime but never owns workflow execution.

---

# Runtime Engine

The Runtime Engine coordinates execution.

It is responsible for creating and managing Workflow Execution instances.

Responsibilities

- Create execution
- Resolve variables
- Resolve secrets
- Initialize workspace
- Coordinate execution lifecycle
- Publish runtime events

The Runtime Engine contains no business logic.

---

# Workflow Manager

Responsible for workflow definitions.

Responsibilities

- Load workflow
- Validate schema
- Resolve includes
- Dependency validation
- Version compatibility

Produces immutable Workflow Definitions.

---

# Execution Manager

Responsible for managing Workflow Execution instances.

Responsibilities

- Create execution
- Assign execution ID
- Track state
- Maintain lifecycle
- Coordinate cleanup

The Execution Manager owns execution lifecycle.

---

# Plugin Manager

Responsible for plugin lifecycle.

Responsibilities

- Discover plugins
- Validate manifests
- Load plugins
- Version compatibility
- Dependency resolution

The Plugin Manager never executes plugins.

---

# Plugin Executor

Responsible for executing plugins.

Responsibilities

- Build Execution Context
- Invoke plugin
- Capture result
- Publish execution events
- Handle failures

Each plugin execution is isolated.

---

# Security Manager

Responsible for platform security.

Responsibilities

- Authentication
- Authorization
- Secret resolution
- Permission validation
- License enforcement (future)

Security policies are enforced before plugins execute.

---

# Variable Manager

Responsible for variable resolution.

Sources include

- CLI
- Environment
- Workflow
- Repository
- Runtime overrides

Produces immutable execution variables.

---

# Secret Manager

Responsible for resolving secrets.

Supported providers may include

- Vault
- AWS Secrets Manager
- Azure Key Vault
- Local encrypted storage

Secrets are injected into the Execution Context.

Plugins never retrieve secrets directly.

---

# Workspace Manager

Responsible for execution workspaces.

Responsibilities

- Create workspace
- Directory structure
- Cleanup
- Retention policy
- Temporary files

Every execution owns exactly one workspace.

---

# Artifact Manager

Responsible for execution artifacts.

Responsibilities

- Register artifacts
- Store metadata
- Validate ownership
- Archive artifacts

Artifacts always belong to a Workflow Execution.

---

# Event Bus

The Event Bus is the communication backbone of the platform.

Every subsystem communicates through events.

```
Plugin

↓

Event

↓

Event Bus

↓

Subscribers
```

Subscribers include

- Console
- Logger
- Report Generator
- Metrics
- Support Bundle

The Event Bus decouples execution from observability.

---

# Observability

Observability transforms execution events into outputs.

Outputs include

- Console
- Log Files
- HTML Reports
- JSON Reports
- Metrics
- Support Bundles

Observability never interacts with plugins directly.

---

# Report Manager

Responsible for generating execution reports.

Inputs

- Events
- Execution metadata
- Artifacts

Outputs

- HTML
- JSON
- Markdown
- Future PDF

Reports are generated after execution.

---

# Repository Manager

Responsible for reusable platform assets.

Examples

- Workflow definitions
- Plugin packages
- Templates
- Shared configurations

Repositories may be local or remote.

---

# Plugin Layer

Plugins implement business operations.

Examples

- SQL Validation
- SQL Execution
- OpenShift Deployment
- Shell Execution
- Git Operations
- HTTP Requests

Plugins remain completely independent of platform implementation.

---

# Communication Rules

The platform follows strict communication rules.

## Allowed

Application

↓

Runtime Engine

↓

Execution Manager

↓

Plugin Executor

↓

Plugin

---

Plugin

↓

Event Bus

↓

Observability

---

Workflow Execution

↓

Managers

---

## Not Allowed

Plugin

→ Authentication

Plugin

→ Workspace

Plugin

→ Report

Plugin

→ Logger Creation

Plugin

→ Configuration Files

Plugin

→ Other Plugins

All communication occurs through the Execution Context or Event Bus.

---

# Dependency Rules

```
Presentation

↓

Platform

↓

Runtime

↓

Execution

↓

Plugin
```

Reverse dependencies are prohibited.

Plugins must never depend on platform internals.

---

# Component Ownership

| Component | Owns |
|------------|------|
| Application | Platform lifecycle |
| Runtime Engine | Runtime coordination |
| Workflow Manager | Workflow definitions |
| Execution Manager | Workflow executions |
| Plugin Manager | Plugin lifecycle |
| Plugin Executor | Plugin invocation |
| Security Manager | Authentication and authorization |
| Variable Manager | Runtime variables |
| Secret Manager | Runtime secrets |
| Workspace Manager | Execution directories |
| Artifact Manager | Execution artifacts |
| Event Bus | Runtime communication |
| Observability | Execution outputs |
| Report Manager | Reports |
| Repository Manager | Shared assets |

---

# Architectural Principles

## Single Responsibility

Every subsystem owns one responsibility.

---

## Explicit Ownership

Every runtime object has exactly one owner.

---

## Event-Driven Communication

Subsystems communicate through events whenever practical.

---

## Stateless Plugins

Plugins own no platform state.

---

## Isolated Executions

Every execution is independent.

---

## Extensibility

New functionality should be introduced by extending existing managers or creating plugins rather than modifying unrelated components.

---

# Summary

Entropy is structured around a layered architecture with clearly defined ownership boundaries.

The platform prepares and coordinates execution.

The Runtime Engine manages execution state.

Plugins implement business logic.

The Event Bus connects execution with observability.

This separation enables scalability, maintainability, testability, and future expansion without increasing coupling between platform components.
