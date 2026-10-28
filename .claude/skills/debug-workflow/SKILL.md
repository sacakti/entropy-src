---
name: debug-workflow
description: Diagnose a failing or misbehaving Entropy workflow run (load, validation, step execution, plugin dispatch, outputs/variables passing). Use when a workflow, step, or run fails or produces unexpected results.
argument-hint: "<error text, run id, or workflow file>"
---

# Debug a workflow

Problem: $ARGUMENTS

Diagnose first. Do not change code until the root cause is confirmed **and** the user
asked for a fix (or clearly authorized one).

1. **Understand / reproduce.** Capture the exact error, the step, and the workflow
   definition. Reproduce with the smallest test or command available, preferably an
   existing test in `tests/workflow/` or `tests/runs/`. Never run real deployments.
2. **Trace only the relevant stage**, following the error:
   - load/parse: `lib/workflow/loader.py`, `lib/workflow/codec/`
   - validation: `lib/workflow/validator.py`
   - variables/arguments/overrides: `lib/workflow/variables/`, `arguments.py`, `overrides.py`
   - execution: `lib/workflow/runner.py`, `core/runtime/` (workflow, stage, step, scope)
   - plugin dispatch: `lib/plugins/manager.py`, `runner.py`, `loader.py`, `contract.py`
   - plugin itself: `resources/plugins/<ns>/<name>/plugin.py`
   Stop reading once the evidence explains the failure.
3. **Root cause.** Report it as:
   - Confirmed: the evidence, with `file:line`, test output, or values.
   - Hypotheses: what is still unproven and how to check it.
4. **Fix (only if authorized).** Make the minimal change at the root cause. No broad
   refactors and no defensive patches over symptoms.
5. **Verify.** Add a regression test if feasible. Run the targeted tests, then
   `tests/workflow` and `tests/plugins/test_runner.py` if the runner or engine changed.
   Compare against the pre-existing baseline failures.
6. **Report:** cause, fix (if any), commands with results, and remaining risk.
