"""
Retention policy: which tags of a repository are kept and which are deleted.

Tags are ranked newest first (by Quay's `start_ts`). A tag is either
protected, claimed by the first custom rule whose tag and repository
patterns match, or left to the default rule; each rule keeps its own
newest `keep` tags. Patterns are shell globs (`release-*`), or regular
expressions when prefixed with `re:` (`re:^v\\d+\\.\\d+$`).
"""

from __future__ import annotations

import fnmatch
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence

from .exceptions import QuayRuleError

SECONDS_PER_DAY = 86_400


def matches(pattern: str, value: str) -> bool:
    """
    Whether `value` matches a glob, or a regular expression given as `re:...`.
    """

    if pattern.startswith("re:"):
        return re.search(pattern[3:], value) is not None
    return fnmatch.fnmatchcase(value, pattern)


def _patterns(value: Any, what: str) -> List[str]:
    if value is None:
        return []
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, list) or not all(isinstance(item, str) and item for item in value):
        raise QuayRuleError(f"{what} must be a pattern or a list of patterns.")
    for pattern in value:
        if pattern.startswith("re:"):
            try:
                re.compile(pattern[3:])
            except re.error as exc:
                raise QuayRuleError(
                    f"{what}: invalid regular expression '{pattern}': {exc}."
                ) from None
    return list(value)


@dataclass(frozen=True)
class Rule:
    """
    Keep the newest `keep` tags matching `tags` (all of them when `keep` is None).
    """

    name: str
    tags: List[str]
    keep: Optional[int]
    repositories: List[str] = field(default_factory=list)
    min_age_days: Optional[int] = None

    def applies(self, repository: str, tag: str) -> bool:
        if self.repositories and not any(matches(p, repository) for p in self.repositories):
            return False
        return any(matches(pattern, tag) for pattern in self.tags)


def parse_rules(rules: Optional[Sequence[Any]]) -> List[Rule]:
    """
    Rules from the `rules` argument, e.g.
    `{"tags": "pr-*", "keep": 0}` or `{"tags": ["release-*"], "keep": 12,
    "repositories": ["payments-*"], "min_age_days": 30}`. Without `keep`,
    matching tags are never deleted.
    """

    parsed: List[Rule] = []
    for index, raw in enumerate(rules or [], start=1):
        if not isinstance(raw, dict):
            raise QuayRuleError(f"Rule {index} must be an object with 'tags'.")
        unknown = set(raw) - {"name", "tags", "keep", "repositories", "min_age_days"}
        if unknown:
            raise QuayRuleError(f"Rule {index}: unknown field(s) {', '.join(sorted(unknown))}.")
        name = str(raw.get("name") or f"rule {index}")
        tags = _patterns(raw.get("tags"), f"{name}: 'tags'")
        if not tags:
            raise QuayRuleError(f"{name}: 'tags' is required.")
        keep = raw.get("keep")
        if keep is not None and (isinstance(keep, bool) or not isinstance(keep, int) or keep < 0):
            raise QuayRuleError(f"{name}: 'keep' must be a whole number of 0 or more.")
        age = raw.get("min_age_days")
        if age is not None and (isinstance(age, bool) or not isinstance(age, int) or age < 0):
            raise QuayRuleError(f"{name}: 'min_age_days' must be a whole number of 0 or more.")
        parsed.append(
            Rule(
                name=name,
                tags=tags,
                keep=keep,
                repositories=_patterns(raw.get("repositories"), f"{name}: 'repositories'"),
                min_age_days=age,
            )
        )
    return parsed


@dataclass
class Decision:
    """
    The outcome for one tag.
    """

    tag: str
    keep: bool
    reason: str
    rule: str
    start_ts: Optional[int] = None
    manifest_digest: Optional[str] = None
    size: Optional[int] = None

    def as_dict(self) -> Dict[str, Any]:
        return {
            "tag": self.tag,
            "action": "keep" if self.keep else "delete",
            "reason": self.reason,
            "rule": self.rule,
            "start_ts": self.start_ts,
            "manifest_digest": self.manifest_digest,
            "size": self.size,
        }


def plan_repository(
    repository: str,
    tags: Sequence[Dict[str, Any]],
    *,
    keep: int,
    rules: Sequence[Rule] = (),
    protect: Sequence[str] = (),
    min_age_days: int = 0,
    now: float,
) -> List[Decision]:
    """
    Decide, newest first, which tags of `repository` are kept.
    """

    ranked = sorted(tags, key=lambda tag: int(tag.get("start_ts") or 0), reverse=True)
    kept: Dict[str, int] = {}
    decisions: List[Decision] = []

    for tag in ranked:
        name = str(tag["name"])
        decision = Decision(
            tag=name,
            keep=True,
            reason="",
            rule="default",
            start_ts=tag.get("start_ts"),
            manifest_digest=tag.get("manifest_digest"),
            size=tag.get("size"),
        )
        decisions.append(decision)

        if any(matches(pattern, name) for pattern in protect):
            decision.rule = "protect"
            decision.reason = "protected"
            continue

        rule = next((rule for rule in rules if rule.applies(repository, name)), None)
        limit = keep if rule is None else rule.keep
        if rule is not None:
            decision.rule = rule.name
        if limit is None:
            decision.reason = "kept by rule"
            continue

        rank = kept.get(decision.rule, 0)
        if rank < limit:
            kept[decision.rule] = rank + 1
            decision.reason = f"newest {limit}"
            continue

        age_limit = min_age_days if rule is None or rule.min_age_days is None else rule.min_age_days
        started = tag.get("start_ts")
        if age_limit and (started is None or now - int(started) < age_limit * SECONDS_PER_DAY):
            decision.reason = f"younger than {age_limit} days"
            continue

        decision.keep = False
        decision.reason = f"beyond newest {limit}"

    return decisions
