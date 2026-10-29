"""
Image references, selection rules, and the images of OpenShift workloads.

Patterns are shell globs (`app-finance-*`, `*-1.2.0*`), or regular
expressions when prefixed with `re:` (`re:^app-(finance|hr)-`).
"""

from __future__ import annotations

import fnmatch
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

from .exceptions import SkopeoRuleError

# Workload kind as `oc get` names it -> the kind of the object owning its pods.
WORKLOAD_KINDS = {
    "deployment": ("Deployment", "ReplicaSet"),
    "deploymentconfig": ("DeploymentConfig", "ReplicationController"),
    "statefulset": ("StatefulSet", None),
    "daemonset": ("DaemonSet", None),
}

DEFAULT_REGISTRY = "docker.io"


def matches(pattern: str, value: str) -> bool:
    """
    Whether `value` matches a glob, or a regular expression given as `re:...`.
    """

    if pattern.startswith("re:"):
        return re.search(pattern[3:], value) is not None
    return fnmatch.fnmatchcase(value, pattern)


def patterns(value: Any, what: str) -> List[str]:
    """
    A pattern or list of patterns, checked.
    """

    if value is None or value == "":
        return []
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, list) or not all(isinstance(item, str) and item for item in value):
        raise SkopeoRuleError(f"{what} must be a pattern or a list of patterns.")
    for pattern in value:
        if pattern.startswith("re:"):
            try:
                re.compile(pattern[3:])
            except re.error as exc:
                raise SkopeoRuleError(
                    f"{what}: invalid regular expression '{pattern}': {exc}."
                ) from None
    return list(value)


# ----------------------------------------------------------------------
# Image references
# ----------------------------------------------------------------------


@dataclass(frozen=True)
class ImageReference:
    """
    `registry/repository[:tag][@digest]`, e.g.
    `quay.example.com/finance/app-finance-api:1.2.0`.
    """

    registry: str
    repository: str
    tag: Optional[str]
    digest: Optional[str]

    @classmethod
    def parse(cls, reference: str) -> ImageReference:
        text = reference.strip()
        for prefix in ("docker://", "docker-pullable://"):
            if text.startswith(prefix):
                text = text[len(prefix) :]
        if not text:
            raise SkopeoRuleError("Empty image reference.")

        name, _, digest = text.partition("@")
        first, slash, rest = name.partition("/")
        if slash and ("." in first or ":" in first or first == "localhost"):
            registry, path = first, rest
        else:
            registry, path = DEFAULT_REGISTRY, name
            if "/" not in path:
                path = f"library/{path}"

        tag: Optional[str] = None
        last = path.rsplit("/", 1)[-1]
        if ":" in last:
            path, _, tag = path.rpartition(":")
        return cls(registry, path, tag or None, digest or None)

    @property
    def name(self) -> str:
        """`registry/repository`."""

        return f"{self.registry}/{self.repository}"

    @property
    def tagged(self) -> str:
        """The full image with its registry and tag (`latest` when none)."""

        return f"{self.name}:{self.tag or 'latest'}"

    def pinned(self, digest: Optional[str]) -> Optional[str]:
        """`registry/repository@digest`."""

        return f"{self.name}@{digest}" if digest else None


def digest_of(image_id: Optional[str]) -> Optional[str]:
    """
    The digest in a container status imageID (`...@sha256:...` or `sha256:...`).
    """

    if not image_id:
        return None
    candidate = image_id.rsplit("@", 1)[-1]
    if candidate.startswith("docker://"):
        candidate = candidate[len("docker://") :]
    return candidate if re.fullmatch(r"sha(256|512):[0-9a-f]{32,128}", candidate) else None


# ----------------------------------------------------------------------
# Selection rules
# ----------------------------------------------------------------------


@dataclass(frozen=True)
class Rule:
    """
    Every given pattern list must match (an empty one matches anything).
    """

    deployments: List[str] = field(default_factory=list)
    tags: List[str] = field(default_factory=list)
    containers: List[str] = field(default_factory=list)

    def wants_workload(self, name: str) -> bool:
        return not self.deployments or any(matches(p, name) for p in self.deployments)

    def wants(self, workload: Optional[str], container: Optional[str], tag: Optional[str]) -> bool:
        if workload is not None and not self.wants_workload(workload):
            return False
        if (
            container is not None
            and self.containers
            and not any(matches(p, container) for p in self.containers)
        ):
            return False
        return not self.tags or any(matches(p, tag or "latest") for p in self.tags)


def parse_rules(
    rules: Optional[Sequence[Any]],
    deployments: Any = None,
    tags: Any = None,
    containers: Any = None,
) -> List[Rule]:
    """
    The `rules` argument, plus the shorthand `deployments`/`tags`/`containers`
    arguments as one more rule. No rules select everything.
    """

    parsed: List[Rule] = []
    for index, raw in enumerate(rules or [], start=1):
        if not isinstance(raw, dict):
            raise SkopeoRuleError(f"Rule {index} must be an object.")
        unknown = set(raw) - {"deployments", "tags", "containers"}
        if unknown:
            raise SkopeoRuleError(f"Rule {index}: unknown field(s) {', '.join(sorted(unknown))}.")
        rule = Rule(
            patterns(raw.get("deployments"), f"Rule {index}: 'deployments'"),
            patterns(raw.get("tags"), f"Rule {index}: 'tags'"),
            patterns(raw.get("containers"), f"Rule {index}: 'containers'"),
        )
        if not (rule.deployments or rule.tags or rule.containers):
            raise SkopeoRuleError(f"Rule {index} needs deployments, tags or containers.")
        parsed.append(rule)

    shorthand = Rule(
        patterns(deployments, "'deployments'"),
        patterns(tags, "'tags'"),
        patterns(containers, "'containers'"),
    )
    if shorthand.deployments or shorthand.tags or shorthand.containers:
        parsed.append(shorthand)
    return parsed


def selected(
    rules: Sequence[Rule],
    workload: Optional[str],
    container: Optional[str],
    tag: Optional[str],
) -> bool:
    return not rules or any(rule.wants(workload, container, tag) for rule in rules)


def workload_selected(rules: Sequence[Rule], exclude: Sequence[str], name: str) -> bool:
    """
    Whether any rule could select images of this workload (by name only).
    """

    if any(matches(pattern, name) for pattern in exclude):
        return False
    return not rules or any(rule.wants_workload(name) for rule in rules)


# ----------------------------------------------------------------------
# Workloads and their running pods
# ----------------------------------------------------------------------


@dataclass
class Container:
    name: str
    image: str
    init: bool = False


@dataclass
class Workload:
    kind: str
    name: str
    namespace: str
    containers: List[Container]
    # (pod, container, spec image, imageID) of each running container
    running: List[Tuple[str, str, str, Optional[str]]] = field(default_factory=list)


def _containers(spec: Dict[str, Any], include_init: bool) -> List[Container]:
    found = [Container(c["name"], c.get("image", "")) for c in spec.get("containers") or []]
    if include_init:
        found += [
            Container(c["name"], c.get("image", ""), init=True)
            for c in spec.get("initContainers") or []
        ]
    return found


def _owner(item: Dict[str, Any]) -> Optional[Tuple[str, str]]:
    for reference in item.get("metadata", {}).get("ownerReferences") or []:
        if reference.get("controller", True):
            return reference.get("kind", ""), reference.get("name", "")
    return None


def workloads(
    items: Sequence[Dict[str, Any]],
    kinds: Sequence[str],
    *,
    include_init: bool = False,
) -> List[Workload]:
    """
    The workloads of `kinds` in an `oc get ... -o json` list, each with the
    images of its running pods (through ReplicaSet/ReplicationController owners).
    """

    wanted = {WORKLOAD_KINDS[kind][0]: kind for kind in kinds}
    found: Dict[Tuple[str, str, str], Workload] = {}
    controllers: Dict[Tuple[str, str, str], Tuple[str, str]] = {}
    pods: List[Dict[str, Any]] = []

    for item in items:
        kind = item.get("kind", "")
        metadata = item.get("metadata", {})
        namespace = metadata.get("namespace", "")
        if kind in wanted:
            template = item.get("spec", {}).get("template", {}).get("spec", {})
            found[(kind, namespace, metadata.get("name", ""))] = Workload(
                kind=wanted[kind],
                name=metadata.get("name", ""),
                namespace=namespace,
                containers=_containers(template, include_init),
            )
        elif kind in ("ReplicaSet", "ReplicationController"):
            owner = _owner(item)
            if owner:
                controllers[(kind, namespace, metadata.get("name", ""))] = owner
        elif kind == "Pod":
            pods.append(item)

    for pod in pods:
        metadata = pod.get("metadata", {})
        namespace = metadata.get("namespace", "")
        if pod.get("status", {}).get("phase") != "Running" or metadata.get("deletionTimestamp"):
            continue
        owner = _owner(pod)
        if owner and owner[0] in ("ReplicaSet", "ReplicationController"):
            owner = controllers.get((owner[0], namespace, owner[1]))
        workload = found.get((owner[0], namespace, owner[1])) if owner else None
        if workload is None:
            continue
        spec_images = {c.name: c.image for c in _containers(pod.get("spec", {}), include_init=True)}
        statuses = [
            *(pod.get("status", {}).get("containerStatuses") or []),
            *(pod.get("status", {}).get("initContainerStatuses") or []),
        ]
        names = {c.name for c in workload.containers}
        for status in statuses:
            name = status.get("name", "")
            if name in names:
                workload.running.append(
                    (
                        metadata.get("name", ""),
                        name,
                        spec_images.get(name) or status.get("image", ""),
                        status.get("imageID"),
                    )
                )

    return sorted(found.values(), key=lambda workload: (workload.namespace, workload.name))
