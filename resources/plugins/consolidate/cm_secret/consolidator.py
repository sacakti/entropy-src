"""
Consolidate ConfigMap/Secret changes from several releases.

Input documents (in release order) are the ones oc.cm_secret_update reads:

- entropy/v1 ConfigMapSecretUpdate: `target: {kind, name}` and `operations`
  (add / update / delete, with an optional `format`: properties, yaml, json);
- v1 ConfigMap or Secret: a native resource whose keys are merged.

cm_secret_update applies every document of one target in order, so the
consolidated result is that same sequence, made as short as possible:

- adjacent native resources merge into one (later keys win);
- adjacent update definitions merge into one, key by key:
  - a plain value (no format) or a delete of the whole key replaces
    everything earlier for that key;
  - structured changes (same format, one after another) merge by path:
    a later write cancels an earlier delete of that path and vice versa.
    Writes and deletes then never overlap, so writing the deletes first
    gives the same result as applying the releases one by one.

No I/O happens here; the plugin reads the releases and writes the result.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from .exceptions import ConsolidationDefinitionError

API_VERSION = "entropy/v1"
UPDATE_KIND = "ConfigMapSecretUpdate"
NATIVE_API_VERSION = "v1"
KINDS = ("ConfigMap", "Secret")
ACTIONS = ("add", "update", "delete")
FORMATS = ("properties", "yaml", "json")

Path_ = Tuple[str, ...]


# ----------------------------------------------------------------------
# Model
# ----------------------------------------------------------------------


@dataclass
class Source:
    """Where a change came from."""

    release: str
    file: str


@dataclass
class _Structured:
    """Consecutive structured changes of one key, merged by path."""

    format: str
    action: str
    writes: Dict[Path_, Any] = field(default_factory=dict)
    deletes: List[Path_] = field(default_factory=list)

    def write(self, entries: Dict[str, Any]) -> None:
        for path, value in _leaves(entries, nested=self.format != "properties"):
            # The write wins over earlier deletes of this path or below it.
            self.deletes = [item for item in self.deletes if not _within(item, path)]
            for written in list(self.writes):
                if _within(written, path):
                    # An earlier value at or below this path is replaced.
                    del self.writes[written]
                elif _within(path, written):
                    # An earlier plain value above it is replaced by a mapping:
                    # remove it first, as applying it in sequence would.
                    del self.writes[written]
                    self._delete(written)
            self.writes[path] = value

    def delete(self, entries: List[str]) -> None:
        for entry in entries:
            path = (entry,) if self.format == "properties" else _dotted(entry)
            if not path:
                continue
            for written in list(self.writes):
                if _within(written, path):
                    del self.writes[written]
            self._delete(path)

    def _delete(self, path: Path_) -> None:
        if path not in self.deletes:
            self.deletes.append(path)

    def operations(self, key: str) -> List[Dict[str, Any]]:
        found: List[Dict[str, Any]] = []
        if self.deletes:
            found.append(
                {
                    "action": "delete",
                    "key": key,
                    "format": self.format,
                    "entries": [
                        path[0] if self.format == "properties" else ".".join(path)
                        for path in self.deletes
                    ],
                }
            )
        if self.writes:
            found.append(
                {
                    "action": self.action,
                    "key": key,
                    "format": self.format,
                    "entries": _unflatten(self.writes),
                }
            )
        return found


@dataclass
class _Segment:
    """A run of documents of one type for a target: native or update."""

    native: bool
    document: Dict[str, Any] = field(default_factory=dict)
    # Update segments: key -> its operations in order (plain dicts or _Structured).
    keys: Dict[str, List[Any]] = field(default_factory=dict)


@dataclass
class Target:
    kind: str
    name: str
    sources: List[Source] = field(default_factory=list)
    segments: List[_Segment] = field(default_factory=list)
    # key -> release that last changed it, for the report.
    last_changed: Dict[str, str] = field(default_factory=dict)

    def documents(self) -> List[Dict[str, Any]]:
        """The consolidated documents, in the order they must be applied."""

        documents: List[Dict[str, Any]] = []
        for segment in self.segments:
            if segment.native:
                documents.append(segment.document)
                continue
            operations: List[Dict[str, Any]] = []
            for key, items in segment.keys.items():
                for item in items:
                    if isinstance(item, _Structured):
                        operations.extend(item.operations(key))
                    else:
                        operations.append(item)
            if operations:
                documents.append(
                    {
                        "apiVersion": API_VERSION,
                        "kind": UPDATE_KIND,
                        "target": {"kind": self.kind, "name": self.name},
                        "operations": operations,
                    }
                )
        return documents


# ----------------------------------------------------------------------
# Consolidator
# ----------------------------------------------------------------------


class Consolidator:
    """Collects documents in release order and consolidates them per target."""

    def __init__(self) -> None:
        self._targets: Dict[Tuple[str, str], Target] = {}
        self.ignored = 0

    @property
    def targets(self) -> List[Target]:
        return list(self._targets.values())

    def add(self, document: Any, source: Source) -> bool:
        """
        Add one YAML document; False when it is not a ConfigMap/Secret change
        (other resources belong to the other consolidation plugins).
        """

        if not isinstance(document, dict):
            self.ignored += 1
            return False

        api_version = document.get("apiVersion")
        kind = document.get("kind")

        if api_version == API_VERSION and kind == UPDATE_KIND:
            self._add_update(document, source)
            return True

        if api_version == NATIVE_API_VERSION and kind in KINDS:
            self._add_native(document, source)
            return True

        self.ignored += 1
        return False

    # -- native ---------------------------------------------------------

    def _add_native(self, document: Dict[str, Any], source: Source) -> None:
        metadata = document.get("metadata")
        name = metadata.get("name") if isinstance(metadata, dict) else None
        if not isinstance(name, str) or not name.strip():
            raise ConsolidationDefinitionError(
                f"{_where(source)}: {document['kind']} needs a non-empty metadata.name."
            )
        for section in ("data", "stringData"):
            if document.get(section) is not None and not isinstance(document[section], dict):
                raise ConsolidationDefinitionError(
                    f"{_where(source)}: {document['kind']} '{name}' {section} must be a mapping."
                )

        target = self._target(document["kind"], name.strip(), source)
        segment = target.segments[-1] if target.segments else None

        if segment is None or not segment.native:
            target.segments.append(_Segment(native=True, document=deepcopy(document)))
        else:
            merged = segment.document
            for field_name, value in document.items():
                if field_name in ("data", "stringData") and isinstance(value, dict):
                    merged.setdefault(field_name, {})
                    merged[field_name] = {**(merged[field_name] or {}), **deepcopy(value)}
                else:
                    merged[field_name] = deepcopy(value)

        for section in ("data", "stringData"):
            for key in document.get(section) or {}:
                target.last_changed[key] = source.release

    # -- updates --------------------------------------------------------

    def _add_update(self, document: Dict[str, Any], source: Source) -> None:
        reference = document.get("target")
        if not isinstance(reference, dict):
            raise ConsolidationDefinitionError(f"{_where(source)}: 'target' must be a mapping.")
        kind = reference.get("kind")
        name = reference.get("name")
        if kind not in KINDS:
            raise ConsolidationDefinitionError(
                f"{_where(source)}: target kind must be ConfigMap or Secret, not '{kind}'."
            )
        if not isinstance(name, str) or not name.strip():
            raise ConsolidationDefinitionError(
                f"{_where(source)}: target 'name' must be a non-empty string."
            )
        operations = document.get("operations")
        if not isinstance(operations, list) or not operations:
            raise ConsolidationDefinitionError(
                f"{_where(source)}: 'operations' must be a non-empty list."
            )

        target = self._target(kind, name.strip(), source)
        segment = target.segments[-1] if target.segments else None
        if segment is None or segment.native:
            segment = _Segment(native=False)
            target.segments.append(segment)

        for operation in operations:
            self._operation(segment, operation, source)
            target.last_changed[str(operation["key"]).strip()] = source.release

    @staticmethod
    def _operation(segment: _Segment, operation: Any, source: Source) -> None:
        where = _where(source)
        if not isinstance(operation, dict):
            raise ConsolidationDefinitionError(f"{where}: each operation must be a mapping.")
        action = str(operation.get("action") or "").strip().lower()
        key = operation.get("key")
        if action not in ACTIONS:
            raise ConsolidationDefinitionError(
                f"{where}: unsupported operation '{action}' (add, update or delete)."
            )
        if not isinstance(key, str) or not key.strip():
            raise ConsolidationDefinitionError(f"{where}: operation 'key' must be a string.")
        key = key.strip()
        operation["key"] = key
        format_ = operation.get("format")
        format_ = str(format_).strip().lower() if format_ is not None else None
        if format_ is not None and format_ not in FORMATS:
            raise ConsolidationDefinitionError(
                f"{where}: key '{key}' has unsupported format '{format_}'."
            )

        items = segment.keys.setdefault(key, [])

        if format_ is None:
            if action != "delete" and "value" not in operation:
                raise ConsolidationDefinitionError(f"{where}: key '{key}' needs a 'value'.")
            # A whole value (or deleting the key) replaces everything before it.
            items[:] = [
                (
                    {"action": "delete", "key": key}
                    if action == "delete"
                    else {"action": action, "key": key, "value": deepcopy(operation["value"])}
                )
            ]
            return

        entries = operation.get("entries")
        last = items[-1] if items else None
        if not (isinstance(last, _Structured) and last.format == format_):
            last = _Structured(format=format_, action="update")
            items.append(last)

        if action == "delete":
            if not isinstance(entries, list) or not all(isinstance(e, str) for e in entries):
                raise ConsolidationDefinitionError(
                    f"{where}: deleting from '{key}' needs 'entries' as a list of names."
                )
            last.delete(entries)
        else:
            if not isinstance(entries, dict):
                raise ConsolidationDefinitionError(
                    f"{where}: '{key}' ({format_}) needs 'entries' as a mapping."
                )
            last.action = action
            last.write(entries)

    # -- helpers ----------------------------------------------------------

    def _target(self, kind: str, name: str, source: Source) -> Target:
        target = self._targets.setdefault((kind, name), Target(kind=kind, name=name))
        if not target.sources or target.sources[-1] != source:
            target.sources.append(source)
        return target


# ----------------------------------------------------------------------
# Paths
# ----------------------------------------------------------------------


def _where(source: Source) -> str:
    return f"{source.release}/{source.file}"


def _dotted(text: str) -> Path_:
    return tuple(part.strip() for part in text.split(".") if part.strip())


def _within(path: Path_, ancestor: Path_) -> bool:
    """True when `path` is `ancestor` or below it."""

    return path[: len(ancestor)] == ancestor


def _leaves(entries: Dict[str, Any], *, nested: bool, prefix: Path_ = ()) -> List[tuple]:
    """(path, value) for each value; mappings are walked when `nested`."""

    found: List[tuple] = []
    for key, value in entries.items():
        path = prefix + (str(key),)
        if nested and isinstance(value, dict) and value:
            found.extend(_leaves(value, nested=True, prefix=path))
        else:
            found.append((path, deepcopy(value)))
    return found


def _unflatten(writes: Dict[Path_, Any]) -> Dict[str, Any]:
    result: Dict[str, Any] = {}
    for path, value in writes.items():
        current: Dict[str, Any] = result
        for part in path[:-1]:
            nested: Optional[Any] = current.get(part)
            if not isinstance(nested, dict):
                nested = {}
                current[part] = nested
            current = nested
        current[path[-1]] = deepcopy(value)
    return result
