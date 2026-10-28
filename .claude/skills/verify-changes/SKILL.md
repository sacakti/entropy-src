---
name: verify-changes
description: Verify the current Entropy changes with the repository's real test, lint, and type commands, focused first and broadened when shared code changed. Use before reporting a change as done.
argument-hint: "[paths or area to focus on]"
---

# Verify changes

Focus: $ARGUMENTS

1. **Diff.** Run `git status --short` and `git diff --stat`, then read the diff of the changed files.
2. **Map impact.** For each changed module, find its tests (`tests/<area>/`) and, if a
   public interface changed, its callers (grep the symbol).
3. **Focused run** (use `venv/bin/` binaries):
   - `pytest <specific test files> -q`
   - `ruff check <changed .py files>` and `black --check <changed .py files>`
   - `mypy <changed .py files>` when types or signatures changed
   - frontend changes: `npm run lint` and `npm run build` in `frontend/`
4. **Broaden** when shared interfaces or execution paths changed
   (`lib/executor/`, `lib/plugins/{base,context,runner,manager}.py`, `lib/workflow/`,
   `core/runtime/`, `core/context.py`): run the whole related test directories,
   e.g. `pytest tests/workflow tests/plugins tests/executor -q`.
5. **Baseline.** If failures look unrelated, confirm by running the same tests with
   your changes stashed (`git stash` / `git stash pop`), but only with the user's OK,
   or by checking whether the failing test touches changed code.
6. **3.9 check** when relevant: the venv is Python 3.9, so a passing import or test
   run there counts as evidence. Otherwise grep the changed lines for 3.10+ syntax.

## Report
- The exact commands run, with pass/fail/error counts. Show only the failing test
  names and the key assertion lines.
- Checks skipped and why.
- Pre-existing failures vs failures introduced by the change.
- Unresolved risks. Never say "passes" for something that was not run.
