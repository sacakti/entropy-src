"""
Where pod logs come from: OpenShift through oc, or built-in sample pods for a dry run.

Both answer the same questions: the pods of a namespace, what is in a path of a
container, a file's bytes, and a container's console log.
"""

from __future__ import annotations

import base64
import binascii
import gzip
import io
import json
import re
import tarfile
import zipfile
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, List, Optional, Tuple

from .exceptions import PodLogsException

# What a path holds: one line "@dir", "@file" or "@missing", then "type|size|mtime|name"
# per entry. The path is an argument ($1), never part of the script.
LIST_SCRIPT = (
    'if [ -d "$1" ]; then echo "@dir"; cd -- "$1" || exit 3; '
    'for f in * .[!.]* ..?*; do [ -e "$f" ] || continue; '
    'stat -L -c "%F|%s|%Y|%n" -- "$f"; done; '
    'elif [ -e "$1" ]; then echo "@file"; stat -L -c "%F|%s|%Y|%n" -- "$1"; '
    'else echo "@missing"; fi'
)
# A file's size on the first line, then its bytes in base64: the newest $2 bytes
# when $3 is "tail", else the whole file (refused past $2 bytes).
READ_SCRIPT = (
    'size=$(stat -L -c %s -- "$1") || exit 3; echo "$size"; '
    'if [ "$size" -le "$2" ]; then base64 < "$1"; '
    'elif [ "$3" = "tail" ]; then tail -c "$2" < "$1" | base64; '
    "else exit 4; fi"
)
TOO_LARGE_EXIT = 4
# Lines holding $1 (plain text, any case) in the files under the paths after $3, as
# "path:line:text": at most $2 per file and $3 in all, each cut to 1000 characters.
SEARCH_SCRIPT = (
    'p="$1"; m="$2"; t="$3"; shift 3; '
    'grep -rHniF -m "$m" -e "$p" -- "$@" 2>/dev/null | head -n "$t" | cut -c 1-1000; exit 0'
)
SEARCH_LINE = re.compile(r"^(/.*?):(\d+):(.*)$")
# Files grep cannot read as text; they are opened in the tree instead.
UNSEARCHABLE = (".gz", ".tgz", ".zip", ".tar")


@dataclass
class Pod:
    name: str
    deployment: str
    status: str
    containers: List[str] = field(default_factory=list)


@dataclass
class Entry:
    name: str
    path: str
    folder: bool
    size: int = 0
    modified: Optional[int] = None


@dataclass
class Match:
    """One line holding the searched text."""

    path: str
    line: int
    text: str


@dataclass
class Listing:
    """What a path holds: a folder's entries, a file, or nothing."""

    kind: str  # "folder", "file" or "missing"
    entries: List[Entry] = field(default_factory=list)


@dataclass
class Content:
    data: bytes
    size: int
    truncated: bool


def deployment_of(pod: Dict[str, Any]) -> str:
    """The deployment (or other owner) a pod belongs to, from its metadata."""

    metadata = pod.get("metadata") or {}
    labels = metadata.get("labels") or {}
    annotations = metadata.get("annotations") or {}
    name = str(metadata.get("name") or "")
    configured = annotations.get("openshift.io/deployment-config.name") or labels.get(
        "deploymentconfig"
    )
    if configured:
        return str(configured)
    for owner in metadata.get("ownerReferences") or []:
        owner_name = str(owner.get("name") or "")
        if not owner_name:
            continue
        if owner.get("kind") == "ReplicaSet":
            suffix = labels.get("pod-template-hash")
            if suffix and owner_name.endswith(f"-{suffix}"):
                return owner_name[: -len(suffix) - 1]
            return owner_name.rsplit("-", 1)[0]
        return owner_name
    return str(labels.get("app") or name)


def _join(folder: str, name: str) -> str:
    return f"{folder.rstrip('/')}/{name}" if folder != "/" else f"/{name}"


# ----------------------------------------------------------------------
# OpenShift
# ----------------------------------------------------------------------


class OcSource:
    """Reads through `oc`; `run(*arguments)` runs one oc command and returns its result."""

    def __init__(self, run: Callable[..., Any]) -> None:
        self._run = run

    def _checked(self, what: str, *arguments: str) -> str:
        result = self._run(*arguments)
        if not result.success:
            detail = (result.stderr or result.stdout or "").strip()
            raise PodLogsException(f"{what} failed: {detail or 'no details'}")
        return str(result.stdout or "")

    def current_project(self) -> str:
        project = self._checked("oc project", "project", "-q").strip()
        if not project:
            raise PodLogsException("The session has no current project: set 'namespace'.")
        return project

    def pods(self, namespace: str) -> List[Pod]:
        text = self._checked("oc get pods", "get", "pods", "-n", namespace, "-o", "json")
        try:
            document = json.loads(text or "{}")
        except ValueError as exc:
            raise PodLogsException(f"oc get pods did not return JSON: {exc}") from exc
        pods = []
        for item in document.get("items") or []:
            metadata = item.get("metadata") or {}
            containers = [
                str(container.get("name"))
                for container in (item.get("spec") or {}).get("containers") or []
                if container.get("name")
            ]
            if not metadata.get("name") or not containers:
                continue
            pods.append(
                Pod(
                    name=str(metadata["name"]),
                    deployment=deployment_of(item),
                    status=str((item.get("status") or {}).get("phase") or "Unknown"),
                    containers=containers,
                )
            )
        return sorted(pods, key=lambda pod: pod.name)

    def _exec(self, namespace: str, pod: str, container: str, *command: str) -> Any:
        return self._run("exec", "-n", namespace, pod, "-c", container, "--", *command)

    def listing(self, namespace: str, pod: str, container: str, path: str) -> Listing:
        result = self._exec(namespace, pod, container, "sh", "-c", LIST_SCRIPT, "sh", path)
        lines = str(result.stdout or "").splitlines()
        if not result.success and not lines:
            detail = (result.stderr or "").strip()
            raise PodLogsException(f"Unable to list {path} in {pod}: {detail or 'no details'}")
        if not lines or lines[0] == "@missing":
            return Listing("missing")
        entries = []
        for line in lines[1:]:
            parts = line.split("|", 3)
            if len(parts) != 4 or not parts[1].isdigit():
                continue
            kind, size, modified, name = parts
            if kind == "directory":
                folder = True
            elif kind.startswith("regular"):
                folder = False
            else:
                continue
            entries.append(
                Entry(
                    name=name.rsplit("/", 1)[-1],
                    path=path if lines[0] == "@file" else _join(path, name),
                    folder=folder,
                    size=int(size),
                    modified=int(modified) if modified.isdigit() else None,
                )
            )
        if lines[0] == "@file":
            return Listing("file", entries[:1])
        return Listing("folder", sorted(entries, key=lambda entry: (not entry.folder, entry.name)))

    def read(
        self, namespace: str, pod: str, container: str, path: str, limit: int, tail: bool
    ) -> Content:
        result = self._exec(
            namespace,
            pod,
            container,
            "sh",
            "-c",
            READ_SCRIPT,
            "sh",
            path,
            str(limit),
            "tail" if tail else "whole",
        )
        lines = str(result.stdout or "").splitlines()
        if getattr(result, "exit_code", None) == TOO_LARGE_EXIT:
            raise PodLogsException(
                f"{path} is larger than {limit // (1024 * 1024)} MB; "
                "raise 'max_read_mb' to open it."
            )
        if not result.success or not lines or not lines[0].strip().isdigit():
            detail = (result.stderr or "").strip()
            raise PodLogsException(f"Unable to read {path} in {pod}: {detail or 'no details'}")
        size = int(lines[0])
        try:
            data = base64.b64decode("".join(lines[1:]), validate=False)
        except (binascii.Error, ValueError) as exc:
            raise PodLogsException(f"Unable to read {path} in {pod}: {exc}") from exc
        return Content(data=data, size=size, truncated=size > len(data))

    def console(
        self,
        namespace: str,
        pod: str,
        container: str,
        since: Optional[datetime],
        max_lines: int,
    ) -> str:
        arguments = ["logs", "-n", namespace, pod, "-c", container, "--timestamps"]
        if since is not None:
            stamp = since.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            arguments.append(f"--since-time={stamp}")
        arguments.append(f"--tail={max_lines}")
        return self._checked("oc logs", *arguments)

    def search(
        self,
        namespace: str,
        pod: str,
        container: str,
        paths: List[str],
        text: str,
        per_file: int,
        limit: int,
    ) -> List[Match]:
        """Lines holding `text` in the files under `paths`, searched inside the container."""

        result = self._exec(
            namespace,
            pod,
            container,
            "sh",
            "-c",
            SEARCH_SCRIPT,
            "sh",
            text,
            str(per_file),
            str(limit),
            *paths,
        )
        if not result.success:
            detail = (result.stderr or "").strip()
            raise PodLogsException(f"Unable to search {pod}/{container}: {detail or 'no details'}")
        found = []
        for line in str(result.stdout or "").splitlines():
            match = SEARCH_LINE.match(line)
            if match and not match.group(1).lower().endswith(UNSEARCHABLE):
                found.append(Match(match.group(1), int(match.group(2)), match.group(3)))
        return found[:limit]


# ----------------------------------------------------------------------
# Dry run
# ----------------------------------------------------------------------


def _sample_log(service: str, now: datetime, hours: int = 30, step_minutes: int = 20) -> str:
    """A log with a line every few minutes over the last `hours`, and a stack trace."""

    lines = []
    moment = now - timedelta(hours=hours)
    count = 0
    while moment <= now:
        stamp = moment.strftime("%Y-%m-%d %H:%M:%S,") + f"{count % 1000:03d}"
        if count % 9 == 4:
            lines.append(f"{stamp} ERROR [{service}] Request failed: timeout calling db")
            lines.append("java.net.SocketTimeoutException: Read timed out")
            lines.append("    at com.example.db.Client.query(Client.java:42)")
        elif count % 5 == 2:
            lines.append(f"{stamp} WARN  [{service}] Slow response: {800 + count} ms")
        else:
            lines.append(
                f"{stamp} INFO  [{service}] Handled request {count} in {20 + count % 70} ms"
            )
        moment += timedelta(minutes=step_minutes)
        count += 1
    return "\n".join(lines) + "\n"


def _tar_gz(files: Dict[str, bytes], mtime: int) -> bytes:
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as archive:
        for name, data in files.items():
            info = tarfile.TarInfo(name)
            info.size = len(data)
            info.mtime = mtime
            archive.addfile(info, io.BytesIO(data))
    return buffer.getvalue()


def _zip(files: Dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, data in files.items():
            archive.writestr(name, data)
    return buffer.getvalue()


class DemoSource:
    """
    Sample pods with log folders, a .tar.gz and a .zip, for trying the plugin
    without a cluster (`dry_run`). Nothing is read from OpenShift.
    """

    NAMESPACE = "demo"

    def __init__(self, now: Optional[datetime] = None) -> None:
        self._now = now or datetime.now(timezone.utc)
        self._files: Dict[str, Dict[str, Tuple[bytes, int]]] = {}
        stamp = int(self._now.timestamp())
        old = int((self._now - timedelta(days=3)).timestamp())
        for pod, service in (
            ("orders-api-7c9d8b6f5-x2kqp", "orders"),
            ("billing-6f8d7-ab12c", "billing"),
        ):
            log = _sample_log(service, self._now).encode()
            yesterday = _sample_log(service, self._now - timedelta(days=1), hours=6).encode()
            self._files[pod] = {
                "/var/log/app.log": (log, stamp),
                "/var/log/gc.log": (b"[0.004s][info][gc] Using G1\n", stamp),
                "/var/log/archive/app-old.log.tar.gz": (
                    _tar_gz({"app-old.log": yesterday, "logs/audit.log": log[:2000]}, old),
                    old,
                ),
                "/var/log/archive/reports.zip": (
                    _zip({"report.txt": b"All jobs finished.\n", "jobs/run-1.log": yesterday}),
                    old,
                ),
                "/var/log/archive/app-1.log.gz": (gzip.compress(yesterday, mtime=0), old),
                f"/opt/{service}/logs/{service}.log": (log, stamp),
            }

    def current_project(self) -> str:
        return self.NAMESPACE

    def pods(self, namespace: str) -> List[Pod]:
        return [
            Pod("billing-6f8d7-ab12c", "billing", "Running", ["billing"]),
            Pod("orders-api-7c9d8b6f5-x2kqp", "orders-api", "Running", ["app", "proxy"]),
        ]

    def listing(self, namespace: str, pod: str, container: str, path: str) -> Listing:
        files = self._files.get(pod, {})
        path = path.rstrip("/") or "/"
        if path in files:
            data, modified = files[path]
            return Listing(
                "file", [Entry(path.rsplit("/", 1)[-1], path, False, len(data), modified)]
            )
        prefix = "" if path == "/" else path
        seen: Dict[str, Entry] = {}
        for name, (data, modified) in files.items():
            if not name.startswith(prefix + "/"):
                continue
            rest = name[len(prefix) + 1 :]
            head = rest.split("/", 1)[0]
            folder = "/" in rest
            seen.setdefault(
                head,
                Entry(head, _join(path, head), folder, 0 if folder else len(data), modified),
            )
        if not seen:
            return Listing("missing")
        return Listing(
            "folder", sorted(seen.values(), key=lambda entry: (not entry.folder, entry.name))
        )

    def read(
        self, namespace: str, pod: str, container: str, path: str, limit: int, tail: bool
    ) -> Content:
        found = self._files.get(pod, {}).get(path)
        if found is None:
            raise PodLogsException(f"Unable to read {path} in {pod}: no such file")
        data = found[0]
        if len(data) > limit:
            if not tail:
                raise PodLogsException(f"{path} is larger than {limit // (1024 * 1024)} MB.")
            return Content(data[-limit:], len(data), True)
        return Content(data, len(data), False)

    def console(
        self,
        namespace: str,
        pod: str,
        container: str,
        since: Optional[datetime],
        max_lines: int,
    ) -> str:
        lines = []
        moment = self._now - timedelta(hours=12)
        count = 0
        while moment <= self._now:
            if since is None or moment >= since:
                stamp = moment.strftime("%Y-%m-%dT%H:%M:%S.%f000Z")
                lines.append(f"{stamp} [{container}] heartbeat {count}: ok")
            moment += timedelta(minutes=10)
            count += 1
        return "\n".join(lines[-max_lines:])

    def search(
        self,
        namespace: str,
        pod: str,
        container: str,
        paths: List[str],
        text: str,
        per_file: int,
        limit: int,
    ) -> List[Match]:
        needle = text.casefold()
        found: List[Match] = []
        for name, (data, _modified) in sorted(self._files.get(pod, {}).items()):
            inside = any(name == path or name.startswith(path.rstrip("/") + "/") for path in paths)
            if not inside or name.lower().endswith(UNSEARCHABLE):
                continue
            hits = 0
            for number, line in enumerate(data.decode("utf-8", "replace").splitlines(), 1):
                if needle in line.casefold():
                    found.append(Match(name, number, line[:1000]))
                    hits += 1
                    if hits >= per_file or len(found) >= limit:
                        break
            if len(found) >= limit:
                break
        return found
