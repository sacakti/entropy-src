---
name: implement-plugin
description: Implement or change an Entropy plugin under resources/plugins/ (or the plugin framework in lib/plugins/) with focused tests. Use when asked to add, extend, or fix plugin behavior.
argument-hint: "<namespace/plugin> <what to change>"
---

# Implement a plugin change

Target: $ARGUMENTS

Plugin rules in `.claude/rules/plugins.md` apply. Do not repeat them here.

1. **Inspect.** Read the target plugin's `plugin.json`, `plugin.py`, and `exceptions.py`.
   Read one comparable plugin in the same namespace (e.g. `resources/plugins/docker/build/`).
   Skip files that are not relevant.
2. **Identify.** List what the change touches: arguments/outputs contract
   (`lib/plugins/contract.py` if declared), registration/manifest fields, executor
   methods needed (grep `lib/executor/` before writing new ones), and existing tests
   in `tests/plugins/<plugin>/`. If something essential is unclear, ask instead of guessing.
3. **Implement.** Make the smallest complete change. Use executor facades, the plugin's own
   exceptions, and a `PluginResult` return. Bump the `plugin.json` version for behavior changes.
4. **Test.** Add or update focused tests next to the existing ones, mocking the executor.
5. **Verify.** Run `venv/bin/pytest tests/plugins/<plugin> -q` and
   `venv/bin/ruff check <changed paths>`, then read `git diff`. If tests were already
   failing before the change, say so and show the baseline.
6. **Report** (short): changed files, commands with pass/fail counts, and unresolved risks
   or unverified behavior.
