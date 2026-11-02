---
paths:
  - "**/*.py"
---

# Python rules

## Python versions
- The server (`core/`, `lib/`, plugins, the release and container) runs on **Python 3.13**
  (`requires-python >=3.13`, black/ruff/mypy target py313).
- **Exception: `lib/remote_cli/`** is the `ent` client people run on their own Python,
  so it stays **Python 3.9 compatible** (standard library only; no `match`, `X | Y` at
  runtime, `typing.Self`, `tomllib`, ...). `tests/remote_cli` checks it parses as 3.9.
- Existing code uses `Optional[...]`/`List[...]` typing. Ruff ignores UP006/UP035/UP045 so
  it does not churn; match the surrounding file rather than mass-modernizing.
- `datetime.utcnow()` is deprecated: use `datetime.now(timezone.utc)` (keep stored
  values naive or aware as the surrounding code already does).

## Conventions
- Match the surrounding file's style: docstrings on public classes and methods,
  section dividers (`# ----`), and one argument per line in multi-line calls.
- Formatting: black and ruff with a line length of 100, isort profile black.
- Exceptions derive from the module's existing base (`core/exceptions.py`
  `EntropyException`, `lib/<area>/exceptions.py`). Do not raise bare `Exception`.
- Never swallow exceptions silently. Convert them at the boundary that owns
  reporting, as the existing code does.

## Dependencies
- Runtime dependencies are `fastapi` and `uvicorn` (pyproject.toml). Do not add a
  dependency without explicit approval. Prefer the stdlib or existing `lib/` helpers.

## Interfaces and contracts
- Preserve public signatures, return types, and result objects
  (`ExecutionResult`, `PluginResult`) unless the task requires a change.
- When a shared interface must change, find all callers first (grep) and update the tests.

## Tests
- pytest; tests live in `tests/<area>/test_*.py` and use shared `conftest.py` fixtures.
- `filterwarnings = error`: new warnings fail tests.
- Add or update focused tests for changed behavior. Reuse existing fixtures and mocks.
