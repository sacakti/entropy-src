---
name: review-code
description: Independent read-only review of the current diff (or a given commit range/paths) for defects, security, architecture, and Python 3.9 issues. Invoke manually with /review-code.
argument-hint: "[git range or paths; default: uncommitted changes]"
disable-model-invocation: true
context: fork
agent: code-reviewer
---

# Review code (read-only)

Scope: $ARGUMENTS (if empty: `git diff HEAD` plus untracked files from `git status`).

Do not modify any file. Do not restate the implementation.

1. Get the diff with read-only git commands. Read surrounding code only where a
   finding depends on it (callers, interfaces, tests).
2. Check, in priority order:
   1. Functional defects and wrong return contracts (`PluginResult`, `ExecutionResult`)
   2. Error handling: swallowed exceptions, wrong exception types, `success` flags
   3. Security: command/shell injection through executor calls, path traversal,
      secrets in logs/outputs, missing authz on web endpoints (`core/web/`)
   4. Architecture: plugin-to-plugin calls, filesystem/process access that bypasses
      the executor facades, printing/logging in `lib/executor/`, bypassing the output subsystem
   5. Python 3.9 incompatibilities (runtime `X | Y`, `match`, 3.10+ stdlib)
   6. Regression risks for other callers of changed interfaces
   7. Missing tests for important new or changed behavior
3. Skip style-only remarks unless they affect correctness or maintainability.

## Output
Findings ordered by severity (Critical / High / Medium / Low), each with:
`severity | file:line | issue | impact | recommended fix`.
Mark anything uncertain as "unverified". If there are no findings, say so in one line.
