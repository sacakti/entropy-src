"""
What changed between two versions of an OpenShift resource.

Lists of named items (containers, env, volumes, ports) are matched by name,
so a reorder is not a change. ConfigMap and Secret data is compared key by
key; Secret values are never returned, only that a key changed.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence

# Fields OpenShift changes on its own; they are not configuration changes.
DEFAULT_IGNORED = (
    "status",
    "metadata.resourceVersion",
    "metadata.uid",
    "metadata.generation",
    "metadata.creationTimestamp",
    "metadata.managedFields",
    "metadata.selfLink",
    'metadata.annotations["kubectl.kubernetes.io/last-applied-configuration"]',
    'metadata.annotations["deployment.kubernetes.io/revision"]',
)

DATA_FIELDS = ("data", "binaryData", "stringData")

Change = Dict[str, Any]


def _key(path: str, key: Any) -> str:
    text = str(key)
    if any(char in text for char in "./[] ") or not text:
        return f'{path}["{text}"]'
    return f"{path}.{text}" if path else text


def _ignored(path: str, ignored: Sequence[str]) -> bool:
    return any(path == item or path.startswith((f"{item}.", f"{item}[")) for item in ignored)


def _named(items: Any) -> bool:
    return (
        isinstance(items, list)
        and bool(items)
        and all(isinstance(item, dict) and isinstance(item.get("name"), str) for item in items)
    )


def diff(
    old: Any, new: Any, path: str = "", ignored: Sequence[str] = DEFAULT_IGNORED
) -> List[Change]:
    """Field-level changes from `old` to `new`, with dotted paths."""

    if path and _ignored(path, ignored):
        return []
    if isinstance(old, dict) and isinstance(new, dict):
        changes: List[Change] = []
        for key in sorted(set(old) | set(new), key=str):
            child = _key(path, key)
            if _ignored(child, ignored):
                continue
            if key not in old:
                changes.append(
                    {"path": child, "change": "added", "before": None, "after": new[key]}
                )
            elif key not in new:
                changes.append(
                    {"path": child, "change": "removed", "before": old[key], "after": None}
                )
            else:
                changes += diff(old[key], new[key], child, ignored)
        return changes
    if (
        _named(old)
        and _named(new)
        and len({i["name"] for i in old}) == len(old)
        and len({i["name"] for i in new}) == len(new)
    ):
        before = {item["name"]: item for item in old}
        after = {item["name"]: item for item in new}
        changes = []
        for name in list(before) + [name for name in after if name not in before]:
            child = f"{path}[{name}]"
            if name not in after:
                changes.append(
                    {"path": child, "change": "removed", "before": before[name], "after": None}
                )
            elif name not in before:
                changes.append(
                    {"path": child, "change": "added", "before": None, "after": after[name]}
                )
            else:
                changes += diff(before[name], after[name], child, ignored)
        return changes
    if isinstance(old, list) and isinstance(new, list) and len(old) == len(new):
        changes = []
        for index, (left, right) in enumerate(zip(old, new)):
            changes += diff(left, right, f"{path}[{index}]", ignored)
        return changes
    if old != new:
        return [{"path": path or "(document)", "change": "changed", "before": old, "after": new}]
    return []


def _data(document: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    merged: Dict[str, Any] = {}
    for field in DATA_FIELDS:
        value = (document or {}).get(field)
        if isinstance(value, dict):
            merged.update(value)
    return merged


def data_changes(
    old: Optional[Dict[str, Any]], new: Optional[Dict[str, Any]], secret: bool
) -> List[Change]:
    """Key-by-key changes of ConfigMap or Secret data; Secret values are withheld."""

    before, after = _data(old), _data(new)
    changes: List[Change] = []
    for key in sorted(set(before) | set(after)):
        if key not in before:
            change = "added"
        elif key not in after:
            change = "removed"
        elif before[key] != after[key]:
            change = "changed"
        else:
            continue
        changes.append(
            {
                "key": key,
                "change": change,
                "before": None if secret else before.get(key),
                "after": None if secret else after.get(key),
                "hidden": secret,
            }
        )
    return changes


def identity(document: Optional[Dict[str, Any]], fallback: str) -> Dict[str, str]:
    metadata = (document or {}).get("metadata")
    name = metadata.get("name") if isinstance(metadata, dict) else None
    return {"kind": str((document or {}).get("kind") or "Resource"), "name": str(name or fallback)}


def compare(
    old: Optional[Dict[str, Any]],
    new: Optional[Dict[str, Any]],
    file: str,
    ignored: Sequence[str] = DEFAULT_IGNORED,
) -> Optional[Dict[str, Any]]:
    """
    One resource's audit entry: added, removed or modified with its changes;
    None when only ignored fields changed.
    """

    document = new if new is not None else old
    who = identity(document, file)
    kind = who["kind"]
    status = "added" if old is None else "removed" if new is None else "modified"
    # Added and removed resources are summarised (their keys listed), not diffed key by key.
    data = (
        data_changes(old, new, kind == "Secret")
        if kind in ("ConfigMap", "Secret") and status == "modified"
        else []
    )
    if kind in ("ConfigMap", "Secret"):
        old = (
            {k: v for k, v in (old or {}).items() if k not in DATA_FIELDS}
            if old is not None
            else None
        )
        new = (
            {k: v for k, v in (new or {}).items() if k not in DATA_FIELDS}
            if new is not None
            else None
        )
    fields = diff(old, new, "", ignored) if status == "modified" else []
    if status == "modified" and not fields and not data:
        return None
    return {
        **who,
        "file": file,
        "status": status,
        "fields": fields,
        "data": data,
        "summary": _summary(document, kind),
    }


def _summary(document: Optional[Dict[str, Any]], kind: str) -> List[str]:
    """A few facts shown for added and removed resources."""

    facts: List[str] = []
    spec = (document or {}).get("spec") or {}
    template = ((spec.get("template") or {}).get("spec") or {}) if isinstance(spec, dict) else {}
    for container in template.get("containers") or []:
        if isinstance(container, dict):
            facts.append(f"container {container.get('name')}: {container.get('image')}")
    if kind in ("ConfigMap", "Secret"):
        keys = sorted(_data(document))
        if keys:
            facts.append(
                f"{len(keys)} key{'s' if len(keys) != 1 else ''}: "
                f"{', '.join(keys[:20])}{' …' if len(keys) > 20 else ''}"
            )
    if isinstance(spec, dict) and spec.get("replicas") is not None:
        facts.append(f"replicas: {spec['replicas']}")
    return facts
