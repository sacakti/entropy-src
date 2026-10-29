"""
The plan of a workflow run: which steps run, on which node, and how they
depend on each other.

A run may select steps explicitly, filter them by tags, and send steps to
different nodes. Steps still run one after another in workflow order;
consecutive steps on the same node form a *segment*. Each segment runs as
an ordinary job with a trimmed definition: only its steps, with references
to outputs of earlier segments (`${steps.<step>.outputs.<key>}`) replaced
by the values those steps produced.
"""

from __future__ import annotations

import dataclasses
import re
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set, Tuple

# An argument is a step output reference only as a whole value.
STEP_REFERENCE = re.compile(r"^\$\{steps\.([^.}]+)\.outputs\.([^}]+)\}$")


class PlanError(ValueError):
    """The requested selection cannot run; the message is shown to users."""


def _walk(value: Any) -> Iterable[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, list):
        for item in value:
            yield from _walk(item)
    elif isinstance(value, dict):
        for item in value.values():
            yield from _walk(item)


def step_references(arguments: Dict[str, Any]) -> List[Tuple[str, str]]:
    """(step, output path) pairs a step's arguments read, in order, unique."""

    found: List[Tuple[str, str]] = []
    for text in _walk(arguments or {}):
        match = STEP_REFERENCE.fullmatch(text)
        if match and (match.group(1), match.group(2)) not in found:
            found.append((match.group(1), match.group(2)))
    return found


@dataclasses.dataclass
class RunPlan:
    """Steps of one run, in workflow order."""

    default_node: str
    tags: List[str]
    steps: List[Dict[str, Any]]

    @property
    def selected(self) -> List[str]:
        return [step["name"] for step in self.steps if step["selected"]]

    @property
    def skipped(self) -> List[str]:
        return [step["name"] for step in self.steps if not step["selected"]]

    @property
    def segments(self) -> List[Dict[str, Any]]:
        """Consecutive selected steps sharing a node."""

        segments: List[Dict[str, Any]] = []
        for step in self.steps:
            if not step["selected"]:
                continue
            if segments and segments[-1]["node"] == step["node"]:
                segments[-1]["steps"].append(step["name"])
            else:
                segments.append({"node": step["node"], "steps": [step["name"]]})
        return segments

    @property
    def nodes(self) -> List[str]:
        return list(dict.fromkeys(segment["node"] for segment in self.segments))

    @property
    def trivial(self) -> bool:
        """Every enabled step, on the default node: a plain run."""

        return all(
            step["selected"] == step["enabled"] and step["node"] == self.default_node
            for step in self.steps
        )

    def snapshot(self, variables: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """What the run records about itself (no variable values)."""

        return {
            "default_node": self.default_node,
            "tags": self.tags,
            "selected": self.selected,
            "skipped": self.skipped,
            "nodes": self.nodes,
            "segments": self.segments,
            "variables": sorted((variables or {}).keys()),
            "steps": self.steps,
        }


def build_plan(
    workflow: Any,
    *,
    default_node: str = "local",
    steps: Optional[Sequence[str]] = None,
    tags: Optional[Sequence[str]] = None,
    step_nodes: Optional[Dict[str, str]] = None,
) -> RunPlan:
    """
    Select steps (all enabled ones, narrowed by `steps` and `tags`), assign
    nodes, and check that every selected step's inputs will exist.

    A step disabled in the workflow runs only when `steps` names it.
    """

    names = [step.name for step in workflow.steps]
    wanted = set(steps) if steps is not None else None
    tag_filter = [tag for tag in (tags or []) if tag]
    nodes = {name: node for name, node in (step_nodes or {}).items() if node}

    unknown = sorted((wanted or set()) - set(names)) + sorted(set(nodes) - set(names))
    if unknown:
        raise PlanError(f"Unknown step(s): {', '.join(dict.fromkeys(unknown))}.")

    entries: List[Dict[str, Any]] = []
    for step in workflow.steps:
        step_tags = list(step.tags or [])
        if not step.enabled and (wanted is None or step.name not in wanted):
            selected, reason = False, "disabled"
        elif tag_filter and not set(step_tags) & set(tag_filter):
            selected, reason = False, "tag filter"
        elif wanted is not None and step.name not in wanted:
            selected, reason = False, "not selected"
        else:
            selected, reason = True, None
        entries.append(
            {
                "name": step.name,
                "plugin": step.plugin,
                "tags": step_tags,
                "enabled": bool(step.enabled),
                "selected": selected,
                "skip_reason": reason,
                "node": nodes.get(step.name, default_node),
                "depends_on": [
                    {"step": source, "output": output}
                    for source, output in step_references(step.arguments)
                ],
            }
        )

    plan = RunPlan(default_node=default_node, tags=tag_filter, steps=entries)

    if not plan.selected:
        raise PlanError("No steps are selected to run.")

    selected: Set[str] = set(plan.selected)
    for entry in entries:
        if not entry["selected"]:
            continue
        for dependency in entry["depends_on"]:
            if dependency["step"] not in selected:
                raise PlanError(
                    f"Step '{entry['name']}' uses the output of step "
                    f"'{dependency['step']}', which is not selected to run."
                )

    return plan


def _substitute(value: Any, outputs: Dict[str, Dict[str, Any]], local: Set[str]) -> Any:
    if isinstance(value, str):
        match = STEP_REFERENCE.fullmatch(value)
        if not match or match.group(1) in local:
            return value
        source, path = match.group(1), match.group(2)
        if source not in outputs:
            raise PlanError(f"Step '{source}' produced no outputs for '{value}'.")
        current: Any = outputs[source]
        for key in path.split("."):
            if not isinstance(current, dict) or key not in current:
                raise PlanError(f"Step '{source}' has no output '{path}' for '{value}'.")
            current = current[key]
        return current
    if isinstance(value, list):
        return [_substitute(item, outputs, local) for item in value]
    if isinstance(value, dict):
        return {key: _substitute(item, outputs, local) for key, item in value.items()}
    return value


def segment_workflow(
    workflow: Any,
    step_names: Sequence[str],
    outputs: Optional[Dict[str, Dict[str, Any]]] = None,
) -> Any:
    """
    The workflow reduced to `step_names` (enabled, in order), with outputs of
    steps outside it filled in from `outputs` (step name → outputs dict).
    """

    chosen = set(step_names)
    steps = []
    for step in workflow.steps:
        if step.name not in chosen:
            continue
        arguments = _substitute(dict(step.arguments or {}), outputs or {}, chosen)
        steps.append(dataclasses.replace(step, enabled=True, arguments=arguments))
    return dataclasses.replace(workflow, steps=steps)
