"""
Execution nodes and their resource metrics.

The server Entropy is installed on is always registered as the 'local'
node. Metrics are read from the operating system without third-party
packages (Linux /proc first, POSIX fallbacks elsewhere) and can be
rendered in the Prometheus text exposition format for any TSDB.
"""

from __future__ import annotations

import json
import os
import platform
import re
import socket
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from lib.database.connection import DatabaseConnection

from .store import LOCAL_NODE, ensure_run_schema, utcnow

# Samples older than this are pruned.
METRICS_RETENTION = timedelta(days=7)

# A node not seen for this long is reported as down.
AGENT_STALE_AFTER = timedelta(minutes=2)

_NODE_NAME = re.compile(r"^[a-z0-9][a-z0-9._-]{0,62}$")


# ----------------------------------------------------------------------
# Local metrics
# ----------------------------------------------------------------------


def _read(path: str) -> Optional[str]:
    try:
        return Path(path).read_text(encoding="utf-8")
    except OSError:
        return None


def _cpu_times() -> Optional[tuple]:
    text = _read("/proc/stat")
    if not text:
        return None
    fields = [int(value) for value in text.splitlines()[0].split()[1:]]
    idle = fields[3] + (fields[4] if len(fields) > 4 else 0)
    return sum(fields), idle


class LocalMetrics:
    """Reads resource usage of the machine this process runs on."""

    def __init__(self, disk_path: Path) -> None:
        self._disk_path = disk_path
        self._last_cpu = _cpu_times()

    def cpu_percent(self) -> Optional[float]:
        current = _cpu_times()
        previous, self._last_cpu = self._last_cpu, current

        if current is None:
            # No /proc: approximate from load average.
            try:
                return min(100.0, os.getloadavg()[0] / (os.cpu_count() or 1) * 100)
            except OSError:
                return None

        if previous is None or current[0] == previous[0]:
            # First reading: sample over a short window.
            time.sleep(0.1)
            previous, current = current, _cpu_times()
            self._last_cpu = current

        assert current is not None and previous is not None
        total = current[0] - previous[0]
        idle = current[1] - previous[1]
        return round(100.0 * (total - idle) / total, 2) if total > 0 else 0.0

    @staticmethod
    def memory() -> Dict[str, Optional[float]]:
        text = _read("/proc/meminfo")
        if text:
            values = {}
            for line in text.splitlines():
                key, _, rest = line.partition(":")
                parts = rest.split()
                if parts:
                    values[key] = int(parts[0]) * 1024
            total = values.get("MemTotal")
            available = values.get("MemAvailable", values.get("MemFree"))
            if total:
                used = total - (available or 0)
                return {
                    "total": total,
                    "used": used,
                    "percent": round(100.0 * used / total, 2),
                }

        try:
            total = os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES")
            return {"total": total, "used": None, "percent": None}
        except (ValueError, OSError, AttributeError):
            return {"total": None, "used": None, "percent": None}

    def disk(self) -> Dict[str, Optional[float]]:
        try:
            stats = os.statvfs(str(self._disk_path))
        except OSError:
            return {"total": None, "used": None, "percent": None, "path": str(self._disk_path)}

        total = stats.f_blocks * stats.f_frsize
        free = stats.f_bavail * stats.f_frsize
        used = total - stats.f_bfree * stats.f_frsize
        usable = used + free
        return {
            "total": total,
            "used": used,
            "free": free,
            "percent": round(100.0 * used / usable, 2) if usable else None,
            "path": str(self._disk_path),
        }

    @staticmethod
    def uptime() -> Optional[float]:
        text = _read("/proc/uptime")
        if text:
            return float(text.split()[0])
        return None

    def collect(self) -> Dict[str, Any]:
        try:
            load = list(os.getloadavg())
        except OSError:
            load = [None, None, None]

        return {
            "cpu": {"percent": self.cpu_percent(), "count": os.cpu_count()},
            "memory": self.memory(),
            "disk": self.disk(),
            "load": load,
            "uptime_seconds": self.uptime(),
        }


def local_info() -> Dict[str, Any]:
    return {
        "hostname": socket.gethostname(),
        "os": platform.system(),
        "release": platform.release(),
        "arch": platform.machine(),
        "python": platform.python_version(),
        "python_executable": sys.executable,
    }


# ----------------------------------------------------------------------
# Prometheus exposition
# ----------------------------------------------------------------------


def _label(value: Any) -> str:
    return str(value).replace("\\", "\\\\").replace("\n", "\\n").replace('"', '\\"')


def exposition(nodes: List[Dict[str, Any]]) -> str:
    """
    Render node metrics in the Prometheus text format (version 0.0.4),
    ready for Prometheus, VictoriaMetrics, Mimir or any compatible TSDB.
    """

    families = (
        (
            "entropy_node_up",
            "gauge",
            "1 when the node agent is runnable.",
            lambda m: m.get("agent_up"),
        ),
        (
            "entropy_node_cpu_usage_percent",
            "gauge",
            "CPU utilisation in percent.",
            lambda m: m["cpu"].get("percent"),
        ),
        ("entropy_node_cpu_count", "gauge", "Logical CPUs.", lambda m: m["cpu"].get("count")),
        (
            "entropy_node_memory_total_bytes",
            "gauge",
            "Physical memory.",
            lambda m: m["memory"].get("total"),
        ),
        (
            "entropy_node_memory_used_bytes",
            "gauge",
            "Memory in use.",
            lambda m: m["memory"].get("used"),
        ),
        (
            "entropy_node_memory_usage_percent",
            "gauge",
            "Memory utilisation in percent.",
            lambda m: m["memory"].get("percent"),
        ),
        (
            "entropy_node_disk_total_bytes",
            "gauge",
            "Size of the Entropy data filesystem.",
            lambda m: m["disk"].get("total"),
        ),
        (
            "entropy_node_disk_used_bytes",
            "gauge",
            "Used space on the Entropy data filesystem.",
            lambda m: m["disk"].get("used"),
        ),
        (
            "entropy_node_disk_usage_percent",
            "gauge",
            "Disk utilisation in percent.",
            lambda m: m["disk"].get("percent"),
        ),
        ("entropy_node_load1", "gauge", "1-minute load average.", lambda m: m["load"][0]),
        ("entropy_node_load5", "gauge", "5-minute load average.", lambda m: m["load"][1]),
        ("entropy_node_load15", "gauge", "15-minute load average.", lambda m: m["load"][2]),
        (
            "entropy_node_uptime_seconds",
            "counter",
            "Seconds since the node booted.",
            lambda m: m.get("uptime_seconds"),
        ),
        (
            "entropy_node_running_jobs",
            "gauge",
            "Workflow runs active on the node.",
            lambda m: m.get("running_jobs"),
        ),
    )

    lines: List[str] = []
    for name, kind, help_text, read in families:
        samples = []
        for node in nodes:
            metrics = node.get("metrics")
            if not metrics:
                continue
            try:
                value = read(metrics)
            except (KeyError, IndexError, TypeError):
                value = None
            if value is None:
                continue
            labels = f'node="{_label(node["name"])}",kind="{_label(node["kind"])}"'
            samples.append(f"{name}{{{labels}}} {float(value):g}")
        if samples:
            lines.append(f"# HELP {name} {help_text}")
            lines.append(f"# TYPE {name} {kind}")
            lines.extend(samples)

    return "\n".join(lines) + "\n"


# ----------------------------------------------------------------------
# Store
# ----------------------------------------------------------------------


def _node_payload(row: Any) -> Dict[str, Any]:
    try:
        info = json.loads(row["info"]) if row["info"] else {}
    except ValueError:
        info = {}

    return {
        "id": row["id"],
        "name": row["name"],
        "kind": row["kind"],
        "host": row["host"],
        "description": row["description"],
        "enabled": bool(row["enabled"]),
        "info": info,
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "last_seen_at": row["last_seen_at"],
    }


def valid_node_name(name: str) -> bool:
    return bool(_NODE_NAME.match(name or ""))


class NodeStore:
    """Persists nodes and metric samples."""

    def __init__(self, connection: DatabaseConnection) -> None:
        ensure_run_schema(connection)
        self.connection = connection
        self.ensure_local()

    def ensure_local(self) -> None:
        if getattr(self.connection, "_entropy_local_node_ready", False):
            return

        now = utcnow()
        info = json.dumps(local_info())

        with self.connection.transaction():
            self.connection.execute(
                """
                INSERT OR IGNORE INTO nodes
                (name, kind, host, description, enabled, info, created_at, updated_at, last_seen_at)
                VALUES (?, 'local', ?, 'The Entropy server.', 1, ?, ?, ?, ?)
                """,
                (LOCAL_NODE, socket.gethostname(), info, now, now, now),
            )
            self.connection.execute(
                "UPDATE nodes SET host = ?, info = ?, updated_at = ? WHERE name = ?",
                (socket.gethostname(), info, now, LOCAL_NODE),
            )

        self.connection._entropy_local_node_ready = True

    def list(self) -> List[Dict[str, Any]]:
        rows = self.connection.fetchall(
            "SELECT * FROM nodes ORDER BY kind = 'local' DESC, name",
        )
        return [_node_payload(row) for row in rows]

    def get(self, name: str) -> Optional[Dict[str, Any]]:
        row = self.connection.fetchone(
            "SELECT * FROM nodes WHERE name = ?",
            (name,),
        )
        return _node_payload(row) if row is not None else None

    def update(
        self,
        name: str,
        *,
        description: Optional[str] = None,
        enabled: Optional[bool] = None,
    ) -> Optional[Dict[str, Any]]:
        node = self.get(name)
        if node is None:
            return None

        with self.connection.transaction():
            self.connection.execute(
                "UPDATE nodes SET description = ?, enabled = ?, updated_at = ? WHERE name = ?",
                (
                    node["description"] if description is None else description.strip()[:500],
                    int(node["enabled"] if enabled is None else enabled),
                    utcnow(),
                    name,
                ),
            )
        return self.get(name)

    def touch(self, name: str) -> None:
        with self.connection.transaction():
            self.connection.execute(
                "UPDATE nodes SET last_seen_at = ? WHERE name = ?",
                (utcnow(), name),
            )

    # ------------------------------------------------------------------
    # Samples
    # ------------------------------------------------------------------

    def add_sample(self, name: str, metrics: Dict[str, Any]) -> None:
        with self.connection.transaction():
            self.connection.execute(
                """
                INSERT INTO node_metrics
                (node, sampled_at, cpu_percent, memory_percent, disk_percent,
                 load1, running_jobs, agent_up)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    name,
                    utcnow(),
                    metrics["cpu"].get("percent"),
                    metrics["memory"].get("percent"),
                    metrics["disk"].get("percent"),
                    metrics["load"][0],
                    int(metrics.get("running_jobs") or 0),
                    int(bool(metrics.get("agent_up"))),
                ),
            )
            self.connection.execute(
                "DELETE FROM node_metrics WHERE sampled_at < ?",
                ((datetime.now(timezone.utc) - METRICS_RETENTION).isoformat(),),
            )

    def history(self, name: str, hours: float = 1) -> List[Dict[str, Any]]:
        since = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
        rows = self.connection.fetchall(
            """
            SELECT sampled_at, cpu_percent, memory_percent, disk_percent,
                   load1, running_jobs, agent_up
            FROM node_metrics
            WHERE node = ? AND sampled_at >= ?
            ORDER BY sampled_at
            """,
            (name, since),
        )
        return [dict(row) for row in rows]


def agent_up(node: Dict[str, Any]) -> bool:
    """A node is runnable when enabled and recently seen."""

    if not node["enabled"]:
        return False

    if node["kind"] == "local":
        return True

    seen = node.get("last_seen_at")
    if not seen:
        return False

    last = datetime.fromisoformat(seen)
    if last.tzinfo is None:
        last = last.replace(tzinfo=timezone.utc)
    return datetime.now(timezone.utc) - last < AGENT_STALE_AFTER
