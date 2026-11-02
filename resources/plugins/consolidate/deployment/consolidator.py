"""
Consolidate Deployment changes from several releases.

Input documents (in release order) are the ones a release ships:

- entropy/v1 DeploymentUpdate: `target: {kind, name}` and `operations`
  (add / update / delete of image, env, mounts, mountvolume);
- apps/v1 Deployment: a complete resource.

oc.deployment is strict: `add` fails when the item exists, `update` and `delete`
fail when it is missing. So changes to one item (the image of a container, one
env variable, one mount, one volume) reduce to their net operation:

    earlier  later   net
    add      update  add (later value)
    add      delete  nothing
    update   update  update (later value)
    update   delete  delete
    delete   add     update (later value)

Any other pair would fail when applied one by one, whatever the Deployment holds,
so it fails here too, naming both releases. Image operations only set a value, so
the later one wins.

Different items do not affect each other, so the operations of one Deployment can
be applied in any order.

No I/O happens here; the plugin reads the releases and writes the result.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from .exceptions import ConsolidationDefinitionError

API_VERSION = "entropy/v1"
UPDATE_KIND = "DeploymentUpdate"
TARGET_KIND = "Deployment"
NATIVE_API_VERSION = "apps/v1"
ACTIONS = ("add", "update", "delete")
FIELDS = ("image", "env", "mounts", "mountvolume")

# (field, container, item name); the image of a container has no item name.
Key = Tuple[str, Optional[str], Optional[str]]


# ----------------------------------------------------------------------
# Model
# ----------------------------------------------------------------------


@dataclass
class Source:
    """Where a change came from."""

    release: str
    file: str


@dataclass
class _Change:
    """The net operation on one item; `action` None means nothing is left to do."""

    action: Optional[str]
    value: Any
    release: str


@dataclass
class Target:
    """Everything the releases do to one Deployment."""

    name: str
    sources: List[Source] = field(default_factory=list)
    changes: Dict[Key, _Change] = field(default_factory=dict)
    # The complete resource of the latest release that ships one.
    native: Optional[Dict[str, Any]] = None
    native_releases: List[str] = field(default_factory=list)

    def document(self) -> Optional[Dict[str, Any]]:
        """The consolidated DeploymentUpdate; None when no operation is left."""

        operations = [
            _operation(key, change) for key, change in self.changes.items() if change.action
        ]

        if not operations:
            return None

        return {
            "apiVersion": API_VERSION,
            "kind": UPDATE_KIND,
            "target": {"kind": TARGET_KIND, "name": self.name},
            "operations": operations,
        }

    def keys(self) -> Dict[str, str]:
        """Item label -> the release that last changed it, for items still changed."""

        return {
            _label(key): change.release for key, change in self.changes.items() if change.action
        }

    def cancelled(self) -> List[str]:
        """Items added and deleted again by the releases, so left out of the result."""

        return [_label(key) for key, change in self.changes.items() if not change.action]


# ----------------------------------------------------------------------
# Consolidator
# ----------------------------------------------------------------------


class Consolidator:
    """Collects documents in release order and consolidates them per Deployment."""

    def __init__(self) -> None:
        self._targets: Dict[str, Target] = {}
        self.ignored = 0

    @property
    def targets(self) -> List[Target]:
        return list(self._targets.values())

    def add(self, document: Any, source: Source) -> bool:
        """
        Add one YAML document; False when it is not a Deployment change
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

        if api_version == NATIVE_API_VERSION and kind == TARGET_KIND:
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
                f"{_where(source)}: Deployment needs a non-empty metadata.name."
            )
        target = self._target(name.strip(), source)
        target.native = deepcopy(document)
        target.native_releases.append(source.release)

    # -- updates --------------------------------------------------------

    def _add_update(self, document: Dict[str, Any], source: Source) -> None:
        where = _where(source)
        reference = document.get("target")
        if not isinstance(reference, dict):
            raise ConsolidationDefinitionError(f"{where}: 'target' must be a mapping.")
        kind = reference.get("kind")
        name = reference.get("name")
        if kind != TARGET_KIND:
            raise ConsolidationDefinitionError(
                f"{where}: target kind must be {TARGET_KIND}, not '{kind}'."
            )
        if not isinstance(name, str) or not name.strip():
            raise ConsolidationDefinitionError(
                f"{where}: target 'name' must be a non-empty string."
            )
        operations = document.get("operations")
        if not isinstance(operations, list) or not operations:
            raise ConsolidationDefinitionError(f"{where}: 'operations' must be a non-empty list.")

        target = self._target(name.strip(), source)
        for operation in operations:
            self._operation(target, operation, source)

    def _operation(self, target: Target, operation: Any, source: Source) -> None:
        where = _where(source)
        if not isinstance(operation, dict):
            raise ConsolidationDefinitionError(f"{where}: each operation must be a mapping.")

        action = str(operation.get("action") or "").strip().lower()
        if action not in ACTIONS:
            raise ConsolidationDefinitionError(
                f"{where}: unsupported operation '{action}' (add, update or delete)."
            )

        field_name = str(operation.get("field") or "").strip().lower()
        if field_name not in FIELDS:
            raise ConsolidationDefinitionError(
                f"{where}: unsupported Deployment field '{field_name}' "
                f"({', '.join(sorted(FIELDS))})."
            )

        key = _key(field_name, action, operation, where)
        value = deepcopy(operation["value"])
        if field_name == "image":
            value = value.strip()

        target.changes[key] = _net(key, target.changes.get(key), action, value, source)

    # -- helpers ----------------------------------------------------------

    def _target(self, name: str, source: Source) -> Target:
        target = self._targets.setdefault(name, Target(name=name))
        if not target.sources or target.sources[-1] != source:
            target.sources.append(source)
        return target


# ----------------------------------------------------------------------
# Net operation
# ----------------------------------------------------------------------


def _net(
    key: Key,
    earlier: Optional[_Change],
    action: str,
    value: Any,
    source: Source,
) -> _Change:
    """The net operation of an item after `action`, given what came before."""

    if earlier is None or key[0] == "image":
        return _Change(action, value, source.release)

    if earlier.action == "add":
        if action == "update":
            return _Change("add", value, source.release)
        if action == "delete":
            return _Change(None, None, source.release)

    elif earlier.action == "update":
        if action == "update":
            return _Change("update", value, source.release)
        if action == "delete":
            return _Change("delete", value, source.release)

    elif earlier.action == "delete":
        if action == "add":
            return _Change("update", value, source.release)

    elif action == "add":
        # Added and deleted again: the item is known to be absent.
        return _Change("add", value, source.release)

    state = "was deleted" if earlier.action in ("delete", None) else "already exists"
    raise ConsolidationDefinitionError(
        f"{_where(source)}: cannot {action} {_label(key)}: it {state} after release "
        f"{earlier.release}, so applying the releases in order would fail."
    )


# ----------------------------------------------------------------------
# Operations
# ----------------------------------------------------------------------


def _key(field_name: str, action: str, operation: Dict[str, Any], where: str) -> Key:
    """Validate an operation as oc.deployment does, and name the item it changes."""

    container = operation.get("container")
    value = operation.get("value")

    if field_name == "mountvolume":
        if container is not None:
            raise ConsolidationDefinitionError(
                f"{where}: field 'mountvolume' does not support 'container'."
            )
    else:
        if not isinstance(container, str) or not container.strip():
            raise ConsolidationDefinitionError(
                f"{where}: field '{field_name}' needs a non-empty 'container'."
            )
        container = container.strip()

    if field_name == "image":
        if action == "delete":
            raise ConsolidationDefinitionError(
                f"{where}: deleting the image of container '{container}' is not supported."
            )
        if not isinstance(value, str) or not value.strip():
            raise ConsolidationDefinitionError(
                f"{where}: field 'image' needs a non-empty string 'value'."
            )
        return (field_name, container, None)

    if not isinstance(value, dict) or not value:
        raise ConsolidationDefinitionError(
            f"{where}: field '{field_name}' needs a non-empty mapping 'value'."
        )

    name = value.get("name")
    if not isinstance(name, str) or not name.strip():
        raise ConsolidationDefinitionError(
            f"{where}: field '{field_name}' needs a non-empty 'value.name'."
        )

    return (field_name, container, name.strip())


def _operation(key: Key, change: _Change) -> Dict[str, Any]:
    field_name, container, _ = key
    operation: Dict[str, Any] = {"action": change.action, "field": field_name}
    if container is not None:
        operation["container"] = container
    operation["value"] = deepcopy(change.value)
    return operation


def _label(key: Key) -> str:
    """image/app, env/app/APP_MODE, mounts/app/logs or mountvolume/logs."""

    return "/".join(part for part in key if part)


def _where(source: Source) -> str:
    return f"{source.release}/{source.file}"
