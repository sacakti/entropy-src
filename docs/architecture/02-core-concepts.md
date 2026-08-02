# Core Concepts

Version: 1.0

Status: Draft

---

# Purpose

This document defines the core concepts used throughout the Entropy architecture.

Every component, workflow, plugin, report, and API should use these definitions consistently.

These concepts form the common language of the platform.

---

# Core Design Rule

Every concept in Entropy has exactly one responsibility.

Concepts should never overlap.

When introducing a new feature, it must extend an existing concept or introduce a new concept with a clearly defined responsibility.

---

# Concept Hierarchy

```
Entropy
│
├── Application
│
├── Workflow Definition
│
├── Workflow Execution
│
│   ├── Execution Context
│   ├── Workspace
│   ├── Variables
│   ├── Secrets
│   ├── Logger
│   ├── Event Dispatcher
│   ├── Report
│   └── Artifacts
│
├── Plugin Framework
│
│   ├── Plugin
│   ├── Plugin Manifest
│   └── Plugin Executor
│
├── Observability
│
│   ├── Console
│   ├── Logging
│   ├── Reports
│   └── Support Bundle
│
└── Repository
```

---

# Entropy Application

## Definition

The Application is the entry point of the platform.

It is responsible for bootstrapping the runtime and coordinating high-level services.

The Application exists only for the lifetime of the process.

## Responsibilities

- Load configuration
- Initialize services
- Authenticate user
- Discover plugins
- Load workflow
- Create Workflow Execution
- Shutdown gracefully

## Does NOT

- Execute workflow steps
- Execute plugins
- Produce reports
- Store execution artifacts

---

# Workflow Definition

## Definition

A Workflow Definition is a static document describing an operational process.

It contains no runtime state.

A workflow describes **what should happen**, not **what happened**.

## Contains

- Metadata
- Version
- Variables
- Required integrations
- Steps
- Conditions
- Rollback definitions
- Dependencies

## Characteristics

- Immutable
- Version controlled
- Shareable
- Reusable

---

# Workflow Execution

## Definition

A Workflow Execution is a live instance of a Workflow Definition.

It represents one execution performed by the platform.

Every execution receives its own runtime resources.

## Owns

- Execution ID
- Status
- Workspace
- Logger
- Variables
- Secrets
- Events
- Report
- Artifacts
- Metrics

Everything produced during runtime belongs to the Workflow Execution.

---

# Execution Context

## Definition

Execution Context is the runtime object passed to plugins.

It exposes platform services without exposing internal implementation.

## Contains

- Execution information
- Logger
- Variables
- Secrets
- Workspace
- Configuration
- Event Publisher
- Artifact Manager

Plugins never interact directly with the platform.

They interact only through the Execution Context.

---

# Plugin

## Definition

A Plugin performs one unit of work.

Plugins contain business logic.

The orchestration engine does not.

## Examples

- SQL Validation
- SQL Execution
- Shell Execution
- OpenShift Deployment
- Git Operations
- HTTP Requests

Plugins are independent, reusable, and stateless.

---

# Plugin Manifest

## Definition

A Plugin Manifest describes a plugin.

It contains metadata required by the platform.

## Example

- Name
- Version
- Author
- Required permissions
- Supported inputs
- Outputs
- Configuration schema

The manifest enables plugin discovery and validation.

---

# Plugin Executor

## Definition

The Plugin Executor is responsible for invoking plugins.

It provides the Execution Context and captures results.

It does not implement plugin-specific logic.

---

# Step

## Definition

A Step represents one operation within a workflow.

Every step references exactly one plugin.

Example

```
Validate SQL

↓

Plugin

↓

Result
```

Steps execute sequentially by default.

Future versions may support parallel execution.

---

# Variable

## Definition

Variables provide configurable values used during execution.

Variables are not sensitive.

Examples

- Database Name
- Namespace
- Build Version
- Environment
- Release Number

Variables may originate from

- Workflow
- CLI
- Environment
- Repository

---

# Secret

## Definition

Secrets contain sensitive information.

Examples

- Passwords
- Tokens
- Certificates
- API Keys

Secrets are resolved by the platform.

Plugins receive resolved values only.

Plugins never retrieve secrets directly.

---

# Workspace

## Definition

The Workspace is an isolated execution directory.

Every execution owns one workspace.

Example

```
runtime/

    executions/

        9d73e18b/

            workspace/

            logs/

            reports/

            artifacts/
```

Plugins should store temporary data only inside the workspace.

---

# Artifact

## Definition

Artifacts are files generated during execution.

Examples

- SQL Scripts
- HTML Reports
- CSV Files
- JSON Files
- Validation Output
- Logs

Artifacts belong to exactly one execution.

---

# Event

## Definition

An Event records something that happened during execution.

Examples

- WorkflowStarted
- StepStarted
- PluginStarted
- PluginCompleted
- ValidationFailed
- ExecutionCompleted

Events are immutable.

Events become the source of truth for observability.

---

# Logger

## Definition

The Logger records execution information.

Loggers belong to Workflow Executions.

Plugins never create loggers.

They receive one from the Execution Context.

---

# Report

## Definition

A Report summarizes an execution.

Reports are generated from events.

Reports never parse log files.

Supported formats include

- HTML
- JSON
- Markdown

Future versions may support PDF.

---

# Support Bundle

## Definition

A Support Bundle contains diagnostic information collected from an execution.

Typical contents include

- Execution metadata
- Logs
- Reports
- Environment information
- Plugin versions
- Configuration snapshot
- Exception details

Support Bundles simplify troubleshooting.

---

# Repository

## Definition

The Repository stores reusable platform assets.

Examples

- Workflow Definitions
- Plugins
- Templates
- Shared Configuration

Repositories may be local or remote.

---

# Relationship Summary

| Concept | Owns | Lifetime |
|----------|------|----------|
| Application | Platform Services | Process |
| Workflow Definition | Static Configuration | Permanent |
| Workflow Execution | Runtime State | Execution |
| Execution Context | Platform Interface | Step |
| Plugin | Business Logic | Permanent |
| Step | Plugin Invocation | Execution |
| Workspace | Runtime Files | Execution |
| Event | Execution Record | Permanent |
| Artifact | Generated Files | Execution |
| Report | Execution Summary | Permanent |

---

# Guiding Principle

The platform is built around ownership.

Every object has one owner.

Ownership determines

- Lifetime
- Visibility
- Responsibility
- Storage
- Cleanup

When ownership is clear, architecture remains simple.
