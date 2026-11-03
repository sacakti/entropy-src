"""
Turn the JSON of `oc get pods` and the metrics API into one row per pod.

Only the fields below are kept: a pod's spec can hold environment values, and rows are
shown on the run screen.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

_QUANTITY = re.compile(r"^([0-9.]+)([A-Za-z]*)$")

# In cores.
_CPU_UNITS = {"": 1.0, "m": 1e-3, "u": 1e-6, "n": 1e-9, "k": 1e3, "M": 1e6}

# In bytes.
_MEMORY_UNITS = {
    "": 1.0,
    "m": 1e-3,
    "k": 1e3,
    "M": 1e6,
    "G": 1e9,
    "T": 1e12,
    "P": 1e15,
    "E": 1e18,
    "Ki": 2.0**10,
    "Mi": 2.0**20,
    "Gi": 2.0**30,
    "Ti": 2.0**40,
    "Pi": 2.0**50,
    "Ei": 2.0**60,
}

MIB = 2.0**20


def _quantity(value: Any, units: Dict[str, float]) -> Optional[float]:
    match = _QUANTITY.match(str(value).strip()) if value is not None else None
    if match is None or match.group(2) not in units:
        return None
    try:
        return float(match.group(1)) * units[match.group(2)]
    except ValueError:
        return None


def cpu_millicores(value: Any) -> Optional[float]:
    """Kubernetes CPU quantity ('250m', '1.5', '123456n') in millicores."""

    cores = _quantity(value, _CPU_UNITS)
    return None if cores is None else cores * 1000


def memory_mib(value: Any) -> Optional[float]:
    """Kubernetes memory quantity ('512Mi', '1G', '1048576') in MiB."""

    size = _quantity(value, _MEMORY_UNITS)
    return None if size is None else size / MIB


def format_age(started: Optional[str], now: datetime) -> str:
    """'45s', '12m', '3h', '6d', like `oc get pods`."""

    if not started:
        return "—"
    try:
        then = datetime.fromisoformat(started.replace("Z", "+00:00"))
    except ValueError:
        return "—"
    seconds = int((now - then).total_seconds())
    if seconds < 0:
        return "0s"
    for size, unit in ((86400, "d"), (3600, "h"), (60, "m")):
        if seconds >= size:
            return f"{seconds // size}{unit}"
    return f"{seconds}s"


def _status(pod: Dict[str, Any], statuses: List[Dict[str, Any]]) -> str:
    """What `oc get pods` shows: a container's problem first, else the phase."""

    if (pod.get("metadata") or {}).get("deletionTimestamp"):
        return "Terminating"
    for container in statuses:
        state = container.get("state") or {}
        for kind in ("waiting", "terminated"):
            reason = (state.get(kind) or {}).get("reason")
            if reason and reason != "Completed":
                return str(reason)
    return str((pod.get("status") or {}).get("phase") or "Unknown")


def _sum_resources(containers: List[Dict[str, Any]], section: str, name: str, parse: Any) -> Any:
    """A pod's total, or None unless every container sets it: a partial total misleads."""

    total = 0.0
    for container in containers:
        value = parse(((container.get("resources") or {}).get(section) or {}).get(name))
        if value is None:
            return None
        total += value
    return total if containers else None


def _usage(metric: Optional[Dict[str, Any]]) -> Dict[str, Dict[str, Optional[float]]]:
    usage: Dict[str, Dict[str, Optional[float]]] = {}
    for container in (metric or {}).get("containers") or []:
        values = container.get("usage") or {}
        usage[str(container.get("name"))] = {
            "cpu": cpu_millicores(values.get("cpu")),
            "memory": memory_mib(values.get("memory")),
        }
    return usage


def _total(usage: Dict[str, Dict[str, Optional[float]]], name: str) -> Optional[float]:
    values = [value for value in (item[name] for item in usage.values()) if value is not None]
    return sum(values) if values else None


def _percent(used: Optional[float], limit: Optional[float]) -> Optional[float]:
    return round(used / limit * 100, 1) if used is not None and limit else None


def pod_rows(
    pods: Dict[str, Any], metrics: Optional[Dict[str, Any]], now: Optional[datetime] = None
) -> List[Dict[str, Any]]:
    """One row per pod; usage is None where the metrics API has no sample for it."""

    now = now or datetime.now(timezone.utc)
    samples = {
        (item.get("metadata") or {}).get("name"): item
        for item in (metrics or {}).get("items") or []
    }
    rows: List[Dict[str, Any]] = []

    for pod in pods.get("items") or []:
        metadata = pod.get("metadata") or {}
        spec = pod.get("spec") or {}
        status = pod.get("status") or {}
        containers = spec.get("containers") or []
        statuses = status.get("containerStatuses") or []
        usage = _usage(samples.get(metadata.get("name")))

        cpu = _total(usage, "cpu")
        memory = _total(usage, "memory")
        cpu_limit = _sum_resources(containers, "limits", "cpu", cpu_millicores)
        memory_limit = _sum_resources(containers, "limits", "memory", memory_mib)

        ready = sum(1 for item in statuses if item.get("ready"))
        phase = _status(pod, statuses)

        rows.append(
            {
                "pod": str(metadata.get("name")),
                "status": phase,
                "ready": f"{ready}/{len(containers)}",
                "restarts": sum(int(item.get("restartCount") or 0) for item in statuses),
                "cpu": None if cpu is None else round(cpu, 1),
                "cpu_limit": None if cpu_limit is None else round(cpu_limit, 1),
                "cpu_percent": _percent(cpu, cpu_limit),
                "memory": None if memory is None else round(memory, 1),
                "memory_limit": None if memory_limit is None else round(memory_limit, 1),
                "memory_percent": _percent(memory, memory_limit),
                "node": str(spec.get("nodeName") or "—"),
                "age": format_age(
                    status.get("startTime") or metadata.get("creationTimestamp"), now
                ),
                # Finished pods are fine; anything else not fully ready needs a look.
                "attention": phase != "Succeeded"
                and (phase != "Running" or ready < len(containers)),
                "containers": {
                    str(item.get("name")): usage.get(str(item.get("name")), {})
                    for item in containers
                },
            }
        )

    return rows


def display_row(row: Dict[str, Any]) -> Dict[str, Any]:
    """A row for the table: no internals, and a dash where there is no value."""

    return {
        key: ("—" if value is None else value)
        for key, value in row.items()
        if key not in ("attention", "containers")
    }
