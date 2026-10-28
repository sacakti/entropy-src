---
paths:
  - "**/*.py"
---

# Python rules

## Python 3.9 compatibility
- Most modules start with `from __future__ import annotations`. That makes
  `X | None` and `list[str]` safe in annotations only.
- At runtime (`isinstance`, type aliases, `cast`, dataclass defaults evaluated at
  import, pydantic/FastAPI models) use `Optional[...]`, `Union[...]`, `List[...]`, `Dict[...]`.
- Do not use 3.10+ features: `match`, parenthesized context managers,
  `zip(strict=)`, `typing.Self`/`TypeAlias`/`ParamSpec`, `ExceptionGroup`, `tomllib`.
- Ruff ignores UP006/UP035/UP045 for 3.9 compatibility. Do not "modernize" typing imports.

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
