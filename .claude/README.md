# Claude Code configuration for Entropy

Written for Claude Code 2.1.x (configured on 2.1.303). Nothing here changes application code.

## Files

| File | Loaded | Purpose |
|---|---|---|
| `CLAUDE.md` | Every session | Core architecture, compatibility, workflow, verification rules |
| `rules/python.md` | Only when working on `**/*.py` | 3.9 typing, exceptions, dependencies, tests |
| `rules/plugins.md` | Only for `lib/plugins/**`, `resources/plugins/**`, `tests/plugins/**` | Plugin layout, boundaries, executor facades, results |
| `skills/*/SKILL.md` | Description always; body only when invoked | Repeatable procedures |
| `agents/*.md` | Description always; runs in its own context when delegated | Specialist subagents |

## Skills

| Skill | Invoke | Use when |
|---|---|---|
| `implement-plugin` | `/implement-plugin <ns/name> <change>`, or automatic | Adding or changing plugin behavior |
| `debug-workflow` | `/debug-workflow <error/run/file>`, or automatic | A workflow, step, or run fails or misbehaves |
| `verify-changes` | `/verify-changes [area]`, or automatic | Before reporting work as done |
| `review-code` | `/review-code [range/paths]`, manual only | Independent review. Runs forked in the `code-reviewer` agent |

## Agents

| Agent | Tools | Delegate when |
|---|---|---|
| `codebase-researcher` | Read, Grep, Glob (Sonnet) | You need a multi-file search or path trace and only the conclusion matters |
| `code-reviewer` | Read, Grep, Glob, Bash (read-only git by instruction) | Non-trivial diff touching shared code, the executor, workflow engine, plugin runtime, or web/auth |
| `test-analyst` | Read, Grep, Glob, Bash (pytest by instruction) (Sonnet) | Picking a test selection for a wide change, or triaging many failures |

Don't delegate tasks that touch only a few files with known locations. Doing them inline is cheaper.

## Handoff template (main agent -> subagent)

```
Objective: <one sentence>
Files/symbols: <path:line, ...>
Confirmed so far: <facts already verified>
Required behavior: <what must be true>
Constraints: Python 3.9; no plugin-to-plugin calls; executor facades only; <task-specific>
Allowed actions: read-only | may run pytest on <paths>
Deliverable: <format, e.g. findings list, path trace, test commands>
```
Don't paste the transcript. The main agent checks returned findings against the source before acting on them.

## Workflows

**Simple change**
> Add a `timeout` argument to docker/build and pass it to the shell call. Use /implement-plugin.

Inline: inspect -> implement -> focused test -> `/verify-changes`.

**Complex debugging**
> /debug-workflow Step "deploy" fails with KeyError 'image' after the build step. Workflow: deployment-wf.json. Diagnose only.

If the trace spans many modules:
> Use codebase-researcher: trace how a step's outputs become the next step's variables, from lib/workflow/runner.py to PluginContext. Return the path with file:line.

Fix only after the root cause is confirmed and you approve it.

**Independent review**
> /review-code

or
> Use code-reviewer on `git diff main...HEAD`, focusing on lib/plugins/runner.py changes.

Fix the confirmed findings, then run `/verify-changes`.

## Measuring cost and quality
- Tokens/cost: `/cost` (API billing) or `/status` / `/usage` (subscription) at the end of a task. Compare the same task with and without delegation.
- Context size: `/context` shows what is loaded (CLAUDE.md, rules, skill descriptions, agents).
- Latency: wall-clock per task. Subagent results show their own token and duration totals.
- Quality: review findings per change, tests added, and rework loops. Track these over a handful of comparable tasks. No savings figure has been measured.

## Validating the config
- `/memory` lists the loaded CLAUDE.md and rules. Open a `.py` file to confirm path-scoped rules attach.
- `/agents` lists the agents (frontmatter errors show here). The `/` menu lists the skills.
- Frontmatter parse check:
  `venv/bin/python -c "import yaml,glob;[yaml.safe_load(open(f).read().split('---')[1]) for f in glob.glob('.claude/**/*.md',recursive=True) if open(f).read().startswith('---')];print('ok')"`

## Known limitations
- `.claude/` is listed in `.gitignore` (uncommitted change at setup time), so this config is
  not version-controlled or shared until that line is removed.
- Agent `tools` limits which tools an agent has, not which commands it runs. Bash restrictions for
  `code-reviewer` and `test-analyst` are instructions, enforced in practice by your
  permission mode and prompts. For strict enforcement, add `permissions.deny` rules in settings.
- Baseline failures at setup: `pytest tests/plugins` has 11 collection errors
  (`cm_secret_update` / `xl_generator` imports, an absolute path on a dev machine in
  `sql_analyse`). `pytest tests/workflow` has 5 failing tests. A bare `pytest` therefore fails,
  so use path-scoped runs.
- `context: fork`/`agent`, `disable-model-invocation`, and `paths` rule frontmatter require
  a recent Claude Code 2.x. On older versions they may be ignored.
- `model: sonnet` on two agents trades some depth for cost. Remove the line to inherit the session model.
