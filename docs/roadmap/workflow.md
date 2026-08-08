# Workflow Engine Roadmap

## Overview

This document outlines the planned evolution of the Entropy Workflow Engine.

The primary design principle is **backward compatibility**. Future workflow capabilities must not require changes to existing plugins. All enhancements should be implemented within the workflow engine, allowing plugins to continue interacting with the stable Plugin SDK.

---

# Design Goals

- Preserve Plugin SDK compatibility.
- Keep workflow execution deterministic.
- Separate workflow orchestration from plugin implementation.
- Support enterprise deployment scenarios.
- Provide clear execution planning and diagnostics.
- Introduce advanced features incrementally without breaking existing workflows.

---

# Phase 1 — Execution Filtering

Focus on improving workflow usability without changing execution semantics.

## Workflow Tags

Allow workflow steps to be categorized using one or more tags.

Example:

```json
{
    "steps": [
        {
            "name": "Validate Scripts",
            "plugin": "oracle.validate",
            "tags": [
                "validate",
                "database"
            ]
        }
    ]
}
```

### Execute by Tag

```bash
ent workflow run deploy.json --tags validate
```

### Execute Multiple Tags

```bash
ent workflow run deploy.json --tags validate,database
```

---

## Skip Tags

Exclude one or more tagged steps.

```bash
ent workflow run deploy.json --skip-tags cleanup
```

---

## Workflow Information

Display workflow metadata without execution.

```bash
ent workflow show deploy.json
```

Displays:

- Workflow metadata
- Variables
- Steps
- Plugins
- Tags
- Arguments

---

## Execution Plan

Display the execution plan without running plugins.

```bash
ent workflow run deploy.json --show
```

Supports:

- `--tags`
- `--skip-tags`

This command allows users to verify exactly what will execute.

---

## Dry Run

Validate workflow execution without invoking plugins.

```bash
ent workflow run deploy.json --dry-run
```

Performs:

- Workflow validation
- Variable resolution
- Expression evaluation
- Tag filtering
- Plugin validation
- Dependency validation
- Argument validation

Stops immediately before plugin execution.

---

# Phase 2 — Selective Execution

Focus on partial workflow execution.

## Execute Specific Steps

```bash
ent workflow run deploy.json --steps Validate
```

Multiple steps:

```bash
ent workflow run deploy.json --steps Validate,Deploy
```

---

## Execute From Step

```bash
ent workflow run deploy.json --from-step Validate
```

Runs from the specified step until completion.

---

## Execute To Step

```bash
ent workflow run deploy.json --to-step Deploy
```

Runs from the beginning until the specified step.

---

## Execute Step Range

```bash
ent workflow run deploy.json \
    --from-step Validate \
    --to-step Cleanup
```

---

## Conditional Execution

Execute steps only when conditions evaluate to true.

Example:

```json
{
    "when": "${environment == 'prod'}"
}
```

Initially supports simple expression evaluation.

---

## Retry Policy

```json
{
    "retry": {
        "count": 3,
        "delay": 5
    }
}
```

Future enhancements may include retry strategies such as exponential backoff.

---

# Phase 3 — Advanced Workflow Features

Introduce richer workflow capabilities while maintaining a stable Plugin SDK.

---

## Variable Resolution

Support runtime variable substitution.

Examples:

```text
${variables.database}

${workspace}

${user}

${artifacts.report}
```

---

## Expression Evaluation

Resolve expressions before plugin execution.

Example:

```text
${workspace}/output

${environment == "DEV"}
```

---

## Loop Execution

Execute a step for each item in a collection.

Example:

```json
{
    "foreach": "${scripts}"
}
```

or

```json
{
    "foreach": [
        "script1.sql",
        "script2.sql"
    ]
}
```

---

## Matrix Execution

Execute a workflow across multiple parameter combinations.

Example:

```json
{
    "matrix": {
        "database": [
            "DEV",
            "QA",
            "PROD"
        ]
    }
}
```

---

## Enhanced Continue-On-Error

Extend the existing `continue_on_error` capability with configurable policies.

Possible future options:

- Continue
- Retry
- Ignore
- Abort workflow

---

# Deferred Features

These capabilities are intentionally postponed until the workflow engine matures.

## Parallel Execution

Parallel execution affects nearly every subsystem:

- Runtime tree
- Observability
- Console presentation
- Progress rendering
- Logging
- Artifact management
- Variable synchronization
- Output ordering

For this reason, it will be introduced only after the sequential execution model is fully stabilized.

---

# Compatibility Principles

The Plugin SDK is considered a stable contract.

Workflow engine enhancements must remain transparent to plugins.

For example:

Today:

```json
{
    "arguments": {
        "directory": "./scripts"
    }
}
```

Future:

```json
{
    "arguments": {
        "directory": "${variables.script_directory}"
    }
}
```

The plugin should always receive the resolved value:

```python
self.arguments["directory"]
```

Plugins should never need to know whether values originated from literals, variables, expressions, loops, or matrices.

---

# Long-Term Vision

The Workflow Engine should evolve into a declarative orchestration platform capable of:

- Selective execution
- Conditional execution
- Variable interpolation
- Expression evaluation
- Loop execution
- Matrix execution
- Retry policies
- Execution planning
- Rich diagnostics

while preserving a simple and stable Plugin SDK for plugin authors.
