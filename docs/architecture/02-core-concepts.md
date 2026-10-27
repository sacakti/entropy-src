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

## Contract

Every plugin declares, in `plugin.json`, what it takes and what it publishes:

```json
"arguments": [
    {"name": "host", "type": "string", "required": true, "description": "Server to reach"},
    {"name": "port", "type": "integer", "default": 22, "minimum": 1, "maximum": 65535},
    {"name": "mode", "choices": ["get", "put"], "default": "get"},
    {"name": "password", "secret": true},
    {"name": "source", "type": "path", "path": "file"}
],
"outputs": [
    {"name": "transferred", "type": "integer", "description": "Files copied"}
]
```

- Types: `string`, `boolean`, `integer`, `number`, `path`, `list`, `dictionary`, `any`.
  Arguments are optional unless `required`; a required argument has no default.
- `secret` arguments are typed in masked fields; `choices` become a list to pick
  from (matched without case); `path` says whether a file or a directory is meant.
- Installing a plugin is refused when it declares no contract, when the contract
  is malformed, or when its source reads an argument or publishes an output it
  does not declare. "Generate contract" in the plugin editor fills both lists in
  from the source.
- At run time, undeclared arguments are refused, required ones must be given,
  values are checked (and text from forms read as numbers or flags), defaults are
  filled in, and outputs the plugin did not declare fail the step.
- Plugins installed before contracts existed keep running; their arguments are
  inferred from the source until they are saved again.

## Lifecycle

A plugin run goes through `validate()`, `prepare()`, `execute()` and `cleanup()`.
Only `execute()` is required; `cleanup()` always runs, also when an earlier step
failed. `execute()` returns a `PluginResult`.

## Automated and interactive runs

A run is started in one of two modes:

- **Automated** (the default; schedules always): nobody is asked anything.
  `self.ask(...)` returns its `default`, or the step fails when there is none.
- **Interactive**: a plugin may ask while it runs —
  `self.ask("One-time code", secret=True)`, or with `choices=[...]`, `default=...`.
  The question appears on the run screen; the run's starter (or anyone who may
  run workflows in the project) answers it there. Before the plugin starts,
  the run also asks for the arguments left empty: required ones, ones declared
  `"prompt": true`, and optional single values without a default (an empty
  answer skips those). Answers may be JSON for objects and lists, or a vault
  reference such as `${entv:prod/sftp}`.
  Secret answers are stored encrypted with the vault key, deleted as soon as the
  plugin reads them, and never logged. Unanswered questions fail the step after
  an hour. Interactive runs execute on the Entropy server (the local node).
- `ent` runs plugins in the terminal and asks there.

## Two ways to build a plugin

- **Source code**: Python in the plugin editor, with the whole Plugin SDK.
- **Visual builder (no code)**: chosen when the plugin is created. Methods are
  boxes of blocks (print, set output, set variable, condition, loop, switch,
  ask the user, run a command, call a method, fail); the side panel defines
  inputs (type, mandatory, default, secret, choices, ask at run time), outputs
  and dependencies (extensions and other plugins). The model is kept in
  `builder.json`; Entropy writes `plugin.py` and `plugin.json` from it, so the
  plugin follows the contract and lifecycle like any other. Expressions are
  small Python expressions over inputs and variables, checked before any code
  is written (no imports, files or other calls than a short allow-list).
  Deleting `builder.json` turns the plugin into a source-code plugin for good.

## Vault values in plugins

- **As arguments (preferred):** any argument may be `${entv:namespace/key}`
  (`${entvfile:...}` for a file's path). The run resolves it with the vault
  access of the user it belongs to; a vault entry holding a JSON object arrives
  as an object, e.g. SFTP credentials
  `{"host": ..., "port": 22, "user": ..., "password": ...}` for `sftp`.
  The run dialog has a vault picker next to every argument; the workflow
  builder offers vault entries among its references.
- **In plugin code:** `self.vault("namespace/key")` (the visual builder's
  "Read from vault" block) reads an entry the same way.
- Values read from the vault are masked in the run's messages: plain string
  entries as a whole, and fields of objects whose names look secret
  (password, token, key, ...).

## Git repositories from Tools

An argument may declare `"picker": "git_repository"`: forms show the managed
repositories (Tools -> Git repositories) the user may use in the project, and
the plugin calls `self.git_repository(name_or_id)` to get a working copy in the
run's workspace (committed as the run user). `builtin.git` takes one as
`git_repository`, instead of a `repository` path.

## Paths on the server

Path arguments have a browse button in the run dialog and in the workflow
builder: it lists folders and files on the Entropy server (starting in the
workspace) for users who may run plugins or workflows in the project.

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
