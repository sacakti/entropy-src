# Entropy — Project Instructions

Modular Python deployment automation framework with a FastAPI web layer and a
React/TypeScript frontend (`frontend/`). Usage guide for this config: `.claude/README.md`.

## Architecture
- Preserve the existing architecture, public interfaces, and established patterns.
- Flow: CLI (`entropy.py`, `core/application.py`) -> Application -> EntropyContext
  (`core/context.py`) -> Workflow Engine (`lib/workflow/`, `core/runtime/`) ->
  Plugin Manager (`lib/plugins/manager.py`) -> Plugins (`resources/plugins/`) ->
  LinuxExecutor (`lib/executor/`).
- Plugins must not call other plugins directly unless user explicitly defines
- Plugins reach the executor only through the context facades on `BasePlugin`
  (`self.filesystem`, `self.shell`, `self.archive`, `self.environment`,
  `self.information`, `self.path`). There is no `self.executor` attribute.
- LinuxExecutor must not print or log; the output subsystem owns reporting
  (plugins use `self.message` / `self.log` / `self.ui`).
- Preserve the existing output subsystem.
- Check the relevant source before assuming a rule applies to a component.
  Detailed rules load automatically from `.claude/rules/` for matching files.

## Compatibility
- Python 3.9 (`requires-python >=3.9`, black/ruff/mypy target py39).
- Avoid unnecessary dependencies and abstractions; reuse existing implementations first.

## Implementation
- Inspect relevant files and nearby tests before editing; do not audit the whole repo.
- Keep changes limited to the requested scope. Do not refactor unrelated code.
- Frontend: follow existing React/TypeScript patterns, `frontend/src/api/*.api.ts`
  services, navigation, and CSS tokens (`frontend/src/styles/theme.css`).
- Do not invent APIs, files, or commands. State uncertainty instead.

## Working efficiently
- Read only the files you need; reuse findings already established in this task.
- Plan briefly for non-trivial changes; skip plans for trivial ones.
- Use subagents (`.claude/agents/`) only when isolated context, parallelism, or an
  independent review justifies the cost. Never spawn several for a small task.
- Handoffs carry: objective, paths/symbols, confirmed findings, required behavior,
  constraints, allowed actions, expected deliverable. No transcripts.
- Validate delegated findings against the source before acting on them.
- Show only the relevant failing lines of test output, not whole logs.

## Verification
- Commands (use `venv/bin/` if the venv is not active):
  - focused: `pytest tests/<area>/test_<x>.py -q` (optionally `-k <name>`)
  - lint/format/types: `ruff check <paths>`, `black --check <paths>`, `mypy <paths>`
  - full gate: `make check`; frontend: `npm run lint` / `npm run build` in `frontend/`
- Run focused tests first; broaden when shared interfaces or execution paths change.
- Some suites currently fail or error before any change (e.g. `tests/plugins`
  collection errors). Compare against the baseline instead of assuming your change caused them.
- Inspect the final diff for regressions and unrelated modifications.
- Never claim a test passed unless it actually ran and passed.
- Report: changed files, commands run with results, skipped checks, unresolved risks.
