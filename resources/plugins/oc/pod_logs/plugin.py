"""
OpenShift pod logs plugin.

An app plugin: browse the log files of a namespace's pods like a file explorer, open one
in a read-only viewer, narrow it to a time range, and save it as an artifact. Each pod
shows its containers' console logs, the default log paths and the paths configured for
its deployment. It only reads, through the login session of oc.generic; `dry_run` uses
built-in sample pods instead, for trying it without a cluster.
"""

from __future__ import annotations

import fnmatch
import hashlib
import re
import subprocess  # nosec B404 - only for the timeout raised by the executor
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from lib.models.plugin import PluginResult
from lib.plugins.app import PluginAppError
from lib.plugins.base import BasePlugin

from .archives import gunzip, is_archive, is_gzip, members, read_member
from .exceptions import PodLogsException
from .sources import DemoSource, Listing, OcSource, Pod
from .timefilter import EVERYTHING, Window, filter_lines, window

NAMESPACE = re.compile(r"^[a-z0-9]([-a-z0-9.]{0,251}[a-z0-9])?$")
ENVIRONMENT = re.compile(r"^[A-Za-z0-9._-]+$")
OC_TIMEOUT_SECONDS = 60
BROWSER = "browser"
ACTIVITY = "activity"
CONSOLE_NAME = "Console log (oc logs)"
# Bytes that are not text: shown as a notice instead of garbage.
BINARY_SAMPLE = 8192

Source = Union[OcSource, DemoSource]


def _node_id(*parts: str) -> str:
    """Stable across refreshes, so the page keeps what is open and expanded."""

    return hashlib.sha1("\x1f".join(parts).encode("utf-8"), usedforsecurity=False).hexdigest()[:16]


def _safe_parts(path: str) -> List[str]:
    """A path's names, without ones that could leave the folder they are written in."""

    return [part for part in path.replace("\\", "/").split("/") if part not in ("", ".", "..")]


def _size(size: int) -> str:
    amount = float(size)
    for unit in ("B", "KB", "MB"):
        if amount < 1024:
            return f"{amount:.0f} {unit}" if unit == "B" else f"{amount:.1f} {unit}"
        amount /= 1024
    return f"{amount:.1f} GB"


class PodLogsPlugin(
    BasePlugin,
):
    """
    Browse, view and save the logs of an OpenShift namespace's pods.
    """

    KUBECONFIG_DIRECTORY = ".kube"
    KUBECONFIG_FILENAME = "config"
    SAVE_DIRECTORY = "pod_logs"
    # Archives read this run, newest last; older ones are read again when needed.
    ARCHIVE_CACHE = 3

    def execute(
        self,
    ) -> PluginResult:
        """
        Keep the log browser up to date until the app is stopped.
        """

        try:
            self._browse()
        except PodLogsException as error:
            self.message.error(str(error))
            return PluginResult(success=False, errors=[{"message": str(error)}])

        return PluginResult(
            success=True,
            changed=bool(self.outputs.get("saved")),
            outputs=dict(self.outputs),
        )

    # ------------------------------------------------------------------
    # Settings
    # ------------------------------------------------------------------

    def _settings(
        self,
    ) -> Dict[str, Any]:
        dry_run = bool(self.arguments.boolean("dry_run", False))
        environment = (self.arguments.string("environment", "") or "").strip()
        if not dry_run and not ENVIRONMENT.match(environment):
            raise PodLogsException(
                "Argument 'environment' is required: the oc.generic environment that is "
                "logged in (or set 'dry_run' to try the plugin with sample pods).",
            )
        zone_name = (self.arguments.string("timezone", "UTC") or "UTC").strip()
        try:
            zone = ZoneInfo(zone_name)
        except (ZoneInfoNotFoundError, ValueError):
            raise PodLogsException(
                f"Argument 'timezone' '{zone_name}' is not a time zone such as UTC or Asia/Dubai."
            ) from None
        return {
            "dry_run": dry_run,
            "environment": environment,
            "namespace": (self.arguments.string("namespace", "") or "").strip(),
            "default_paths": self._paths(
                self.arguments.list("default_paths", ["/var/log"]), "'default_paths'"
            ),
            "log_paths": self._log_paths(self.arguments.dictionary("log_paths", {}) or {}),
            "zone": zone,
            "max_read": (self.arguments.integer("max_read_mb", 20, minimum=1, maximum=200) or 20)
            * 1024
            * 1024,
            "max_lines": self.arguments.integer("max_lines", 20000, minimum=100, maximum=200000)
            or 20000,
            "max_bundle": (
                self.arguments.integer("max_bundle_mb", 200, minimum=1, maximum=2000) or 200
            )
            * 1024
            * 1024,
        }

    @staticmethod
    def _paths(
        value: Any,
        label: str,
    ) -> List[str]:
        items = [value] if isinstance(value, str) else value
        if not isinstance(items, list):
            raise PodLogsException(f"{label} must be a list of absolute paths.")
        paths = []
        for item in items:
            if (
                not isinstance(item, str)
                or not item.strip().startswith("/")
                or any(char in item for char in "\n\r\0")
            ):
                raise PodLogsException(f"{label}: {item!r} is not an absolute path.")
            path = item.strip().rstrip("/") or "/"
            if path not in paths:
                paths.append(path)
        return paths

    @classmethod
    def _log_paths(
        cls,
        value: Dict[str, Any],
    ) -> Dict[str, List[str]]:
        """Deployment name (or pattern, e.g. api-*) to its log paths."""

        if not isinstance(value, dict):
            raise PodLogsException("'log_paths' must map deployment names to lists of paths.")
        return {
            str(key).strip(): cls._paths(paths, f"'log_paths.{key}'")
            for key, paths in value.items()
            if str(key).strip()
        }

    # ------------------------------------------------------------------
    # App loop
    # ------------------------------------------------------------------

    def _browse(
        self,
    ) -> None:
        settings = self._settings()
        self._zone = settings["zone"]
        self._max_read = settings["max_read"]
        self._max_lines = settings["max_lines"]
        self._max_bundle = settings["max_bundle"]
        self._default_paths = settings["default_paths"]
        self._deployment_paths = settings["log_paths"]
        self._source: Source
        if settings["dry_run"]:
            self._source = DemoSource()
            self.message.warning("Dry run: sample pods; nothing is read from OpenShift.")
        else:
            kubeconfig = self._kubeconfig(settings["environment"])
            self._source = OcSource(lambda *arguments: self._oc(kubeconfig, *arguments))

        self._nodes: Dict[str, Dict[str, Any]] = {}
        self._pods: Dict[str, Pod] = {}
        self._archives: Dict[str, bytes] = {}
        self._opened: Optional[Dict[str, Any]] = None
        self._shown: Optional[Dict[str, Any]] = None
        self._opened_titles: List[str] = []
        self._saved: List[str] = []
        self._downloads: List[Dict[str, Any]] = []
        self._namespace: Optional[str] = None
        self._span = Window()
        session_project: Optional[str] = None
        shown_error: Optional[str] = None

        if self.app.interactive:
            self.message.info("Live page open: use the App tab, and Stop app to finish.")
        self.app.log(ACTIVITY, "Pod logs started.")

        while self.app.running:
            try:
                namespace = str(self.app.input("namespace", "") or settings["namespace"]).strip()
                if not namespace:
                    session_project = session_project or self._source.current_project()
                    namespace = session_project
                if not NAMESPACE.match(namespace):
                    raise PodLogsException(f"'{namespace}' is not a valid namespace name.")
                if namespace != self._namespace:
                    self._reset(namespace)

                span = window(
                    str(self.app.input("range", EVERYTHING)),
                    str(self.app.input("from", "") or ""),
                    str(self.app.input("to", "") or ""),
                    self._zone,
                )
                if span != self._span:
                    self._span = span
                    if self._opened is not None:
                        self._show(self._opened["id"], fetch=self._opened["console"])

                self._refresh_pods(namespace)
                self._handle_events()
            except PodLogsException as error:
                # A one-off run has nothing to show; a live page keeps what it has.
                if not self.app.interactive:
                    raise
                if str(error) != shown_error:
                    self.app.log(ACTIVITY, f"Error: {error}")
                    shown_error = str(error)
            else:
                if shown_error:
                    self.app.log(ACTIVITY, "Working again.")
                    shown_error = None
            self._publish()
            self.app.wait()

        self.app.log(ACTIVITY, "Pod logs stopped.")
        self.message.success(
            f"Pod logs finished: {len(self._opened_titles)} opened, {len(self._saved)} saved."
        )

    def _reset(
        self,
        namespace: str,
    ) -> None:
        self._namespace = namespace
        self._nodes.clear()
        self._pods.clear()
        self._archives.clear()
        self._opened = None
        self._shown = None
        self.app.log(ACTIVITY, f"Namespace {namespace}.")

    def _handle_events(
        self,
    ) -> None:
        for press in self.app.events("open"):
            for node_id in press.selection[:1]:
                self._click(str(node_id))
        for _press in self.app.events("reload"):
            if self._opened is not None:
                self._show(self._opened["id"], fetch=True)
        for _press in self.app.events("save"):
            self._save()
        for _press in self.app.events("download_filtered"):
            self._bundle(filtered=True)
        for _press in self.app.events("download_all"):
            self._bundle(filtered=False)

    def _publish(
        self,
    ) -> None:
        self.app.files(
            BROWSER,
            [
                {key: value for key, value in node.items() if not key.startswith("_")}
                for node in self._nodes.values()
            ],
            opened=self._shown,
            downloads=self._downloads,
        )
        self.outputs.update(
            {
                "namespace": self._namespace,
                "pods": [
                    {
                        "pod": pod.name,
                        "deployment": pod.deployment,
                        "status": pod.status,
                        "paths": self._pod_paths(pod)[0],
                    }
                    for pod in self._pods.values()
                ],
                "opened": list(self._opened_titles),
                "saved": list(self._saved),
            },
        )

    # ------------------------------------------------------------------
    # Tree
    # ------------------------------------------------------------------

    def _add(
        self,
        node_id: str,
        name: str,
        kind: str,
        parent: Optional[str],
        **extra: Any,
    ) -> Dict[str, Any]:
        node = {"id": node_id, "name": name, "kind": kind, "parent": parent, **extra}
        previous = self._nodes.get(node_id)
        if previous is not None and previous.get("loaded"):
            # Refreshing a pod keeps what was already opened under it.
            node["loaded"] = True
        self._nodes[node_id] = node
        return node

    def _remove_children(
        self,
        parent: str,
    ) -> None:
        children = [node_id for node_id, node in self._nodes.items() if node["parent"] == parent]
        for child in children:
            self._remove_children(child)
            self._nodes.pop(child, None)
            self._archives.pop(child, None)

    def _refresh_pods(
        self,
        namespace: str,
    ) -> None:
        wanted = str(self.app.input("pod_filter", "") or "").strip().lower()
        pods = [
            pod
            for pod in self._source.pods(namespace)
            if not wanted or wanted in pod.name.lower() or wanted in pod.deployment.lower()
        ]
        current = {pod.name: pod for pod in pods}
        for name in set(self._pods) - set(current):
            node_id = _node_id("pod", name)
            self._remove_children(node_id)
            self._nodes.pop(node_id, None)
        self._pods = current
        for pod in pods:
            self._add(
                _node_id("pod", pod.name),
                pod.name,
                "group",
                None,
                note=f"{pod.deployment} · {pod.status}",
                loaded=False,
                _role="pod",
                _pod=pod.name,
            )

    def _pod_paths(
        self,
        pod: Pod,
    ) -> Tuple[List[str], Dict[str, str]]:
        """The pod's paths (default first, then its deployment's), and why each is there."""

        paths: List[str] = []
        notes: Dict[str, str] = {}
        for path in self._default_paths:
            paths.append(path)
            notes[path] = "default"
        for pattern, configured in self._deployment_paths.items():
            if not fnmatch.fnmatchcase(pod.deployment, pattern):
                continue
            for path in configured:
                if path not in paths:
                    paths.append(path)
                    notes[path] = f"configured for {pattern}"
                elif "configured" not in notes[path]:
                    notes[path] += f", configured for {pattern}"
        return paths, notes

    def _load_pod(
        self,
        node: Dict[str, Any],
    ) -> None:
        pod = self._pods.get(node["_pod"])
        if pod is None:
            raise PodLogsException(f"Pod {node['_pod']} is no longer listed.")
        self._remove_children(node["id"])
        paths, notes = self._pod_paths(pod)
        for container in pod.containers:
            # One container needs no level of its own.
            parent = node["id"]
            if len(pod.containers) > 1:
                parent = _node_id("container", pod.name, container)
                self._add(parent, container, "group", node["id"], note="container", loaded=True)
            self._add(
                _node_id("console", pod.name, container),
                CONSOLE_NAME,
                "file",
                parent,
                note="stdout and stderr",
                _role="console",
                _pod=pod.name,
                _container=container,
                _path=CONSOLE_NAME,
            )
            for path in paths:
                self._add(
                    _node_id("path", pod.name, container, path),
                    path,
                    "folder",
                    parent,
                    note=notes[path],
                    loaded=False,
                    _role="folder",
                    _pod=pod.name,
                    _container=container,
                    _path=path,
                )
        node["loaded"] = True
        self.app.log(
            ACTIVITY,
            f"{pod.name} ({pod.deployment}): {len(paths)} path(s) in "
            f"{len(pod.containers)} container(s).",
        )

    def _load_folder(
        self,
        node: Dict[str, Any],
    ) -> None:
        assert self._namespace is not None
        listing: Listing = self._source.listing(
            self._namespace, node["_pod"], node["_container"], node["_path"]
        )
        self._remove_children(node["id"])
        node["loaded"] = True
        if listing.kind == "missing":
            node["note"] = "not found in this container"
            return
        if listing.kind == "file":
            # A configured path may name one file: it opens like any other.
            entry = listing.entries[0] if listing.entries else None
            node.update(
                kind="archive" if is_archive(node["_path"]) else "file",
                loaded=False,
                _role="file",
                size=entry.size if entry else None,
            )
            self._click(node["id"])
            return
        hidden = 0
        start = self._span.start
        for entry in listing.entries:
            modified = (
                datetime.fromtimestamp(entry.modified, timezone.utc) if entry.modified else None
            )
            # Nothing in a file last written before the range can be inside it.
            if not entry.folder and start and modified and modified < start:
                hidden += 1
                continue
            kind = "folder" if entry.folder else "archive" if is_archive(entry.name) else "file"
            self._add(
                _node_id("path", node["_pod"], node["_container"], entry.path),
                entry.name,
                kind,
                node["id"],
                size=None if entry.folder else entry.size,
                modified=(
                    modified.astimezone(self._zone).strftime("%Y-%m-%d %H:%M") if modified else None
                ),
                loaded=False,
                _role="folder" if entry.folder else "file",
                _pod=node["_pod"],
                _container=node["_container"],
                _path=entry.path,
            )
        node["note"] = f"{hidden} file(s) last written before the range hidden" if hidden else None

    def _load_archive(
        self,
        node: Dict[str, Any],
    ) -> None:
        data = self._archive_bytes(node)
        self._remove_children(node["id"])
        folders: Dict[str, str] = {}

        def folder_of(path: str) -> str:
            if not path:
                return str(node["id"])
            if path not in folders:
                parent = folder_of(path.rsplit("/", 1)[0] if "/" in path else "")
                folders[path] = _node_id("member-folder", node["id"], path)
                self._add(folders[path], path.rsplit("/", 1)[-1], "folder", parent, loaded=True)
            return folders[path]

        found = members(node["_path"], data)
        for member in found:
            name = member["name"].strip("/")
            directory = name.rsplit("/", 1)[0] if "/" in name else ""
            self._add(
                _node_id("member", node["id"], member["name"]),
                name.rsplit("/", 1)[-1],
                "file",
                folder_of(directory),
                size=member["size"],
                note="encrypted" if member["encrypted"] else None,
                _role="member",
                _archive=node["id"],
                _member=member["name"],
                _pod=node["_pod"],
                _container=node["_container"],
                _path=f"{node['_path']}!/{member['name']}",
            )
        node["loaded"] = True
        node["note"] = f"{len(found)} file(s)"

    def _archive_bytes(
        self,
        node: Dict[str, Any],
    ) -> bytes:
        if node["id"] in self._archives:
            return self._archives[node["id"]]
        assert self._namespace is not None
        content = self._source.read(
            self._namespace,
            node["_pod"],
            node["_container"],
            node["_path"],
            self._max_read,
            tail=False,
        )
        self._archives[node["id"]] = content.data
        while len(self._archives) > self.ARCHIVE_CACHE:
            self._archives.pop(next(iter(self._archives)))
        return content.data

    # ------------------------------------------------------------------
    # Opening
    # ------------------------------------------------------------------

    def _click(
        self,
        node_id: str,
    ) -> None:
        node = self._nodes.get(node_id)
        if node is None:
            self.app.log(ACTIVITY, "That entry is no longer listed; it was refreshed.")
            return
        role = node.get("_role")
        if role == "pod":
            if not node.get("loaded"):
                self._load_pod(node)
        elif role == "folder":
            # Clicking a folder again reads it again: logs keep changing.
            self._load_folder(node)
        elif node["kind"] == "archive":
            if not node.get("loaded"):
                self._load_archive(node)
        elif role in ("console", "file", "member"):
            self._show(node_id, fetch=True)

    def _show(
        self,
        node_id: str,
        fetch: bool,
    ) -> None:
        """Open a file in the viewer; without `fetch` only the time range is applied again."""

        node = self._nodes.get(node_id)
        if node is None:
            return
        console = node["_role"] == "console"
        if fetch or self._opened is None or self._opened["id"] != node_id:
            raw, notes = self._read_text(node)
            self._opened = {"id": node_id, "raw": raw, "notes": notes, "console": console}
            title = f"{node['_pod']}/{node['_container']}: {node['_path']}"
            if title not in self._opened_titles:
                self._opened_titles.append(title)
        raw = self._opened["raw"]
        notes = list(self._opened["notes"])
        text, kept, total, dated = filter_lines(raw, self._span, self._zone)
        if not self._span.everything:
            if dated:
                notes.append(
                    f"{kept} of {total} lines in {self._span.describe(self._zone)} "
                    f"({self._zone})."
                )
            else:
                notes.append("No timestamps found, so all lines are shown.")
        lines = text.split("\n")
        if len(lines) > self._max_lines:
            text = "\n".join(lines[-self._max_lines :])
            notes.append(f"Only the newest {self._max_lines} lines are shown.")
        self._opened["text"] = text
        name = node["name"] if not console else f"{node['_container']}-console.log"
        self._shown = {
            "id": node_id,
            "title": f"{node['_pod']} / {node['_container']}: {node['_path']}",
            "text": text,
            "notice": " ".join(notes) or None,
            "download_name": f"{node['_pod']}-{name}",
        }

    def _read_text(
        self,
        node: Dict[str, Any],
    ) -> Tuple[str, List[str]]:
        assert self._namespace is not None
        notes: List[str] = []
        role = node["_role"]
        if role == "console":
            text = self._source.console(
                self._namespace,
                node["_pod"],
                node["_container"],
                self._span.start,
                self._max_lines,
            )
            return text, notes
        if role == "member":
            archive = self._nodes.get(node["_archive"])
            if archive is None:
                raise PodLogsException("The archive is no longer listed.")
            data = read_member(
                archive["_path"], self._archive_bytes(archive), node["_member"], self._max_read
            )
        else:
            content = self._source.read(
                self._namespace,
                node["_pod"],
                node["_container"],
                node["_path"],
                self._max_read,
                tail=not is_gzip(node["_path"]),
            )
            data = content.data
            if content.truncated:
                notes.append(
                    f"The file is {_size(content.size)}: the newest {_size(len(data))} were read."
                )
        if is_gzip(node["_path"]):
            data = gunzip(node["_path"], data, self._max_read)
        if b"\0" in data[:BINARY_SAMPLE]:
            return "", [f"{node['name']} is not a text file, so it is not shown."]
        return data.decode("utf-8", errors="replace"), notes

    def _save(
        self,
    ) -> None:
        """The opened file, as narrowed by the time range, as an artifact of the run."""

        if self._opened is None or self._shown is None:
            self.app.log(ACTIVITY, "Save: open a file first.")
            return
        node = self._nodes.get(self._opened["id"])
        if node is None:
            return
        text, _kept, _total, _dated = filter_lines(self._opened["raw"], self._span, self._zone)
        folder = Path(self.workspace) / self.SAVE_DIRECTORY / node["_pod"] / node["_container"]
        self.filesystem.mkdir(folder)
        stem = re.sub(r"[^A-Za-z0-9._-]+", "_", self._shown["download_name"]).strip("_")
        if not self._span.everything:
            stem += datetime.now(timezone.utc).strftime("-%Y%m%dT%H%M%S")
        target = folder / (stem if stem.endswith((".log", ".txt")) else f"{stem}.log")
        self.filesystem.write_text(target, text)
        self._deliver(target)

    def _deliver(
        self,
        target: Path,
    ) -> None:
        """Offer a written file for download now; without a live run, keep it as an artifact."""

        relative = str(target.relative_to(Path(self.workspace)))
        try:
            offered = self.app.offer(target)
        except PluginAppError as error:
            # Still kept: the run's artifacts list it once the step ends.
            self.app.log(ACTIVITY, f"Download not available now: {error}")
            offered = None
        if offered is None:
            self.artifacts[relative] = target
        else:
            self._downloads = [item for item in self._downloads if item["name"] != offered["name"]]
            self._downloads.insert(0, offered)
            del self._downloads[10:]
        if relative not in self._saved:
            self._saved.append(relative)
        self.app.log(
            ACTIVITY,
            (
                f"Saved {relative} ({_size(offered['size'])}); download it above the tree."
                if offered
                else f"Saved {relative}; it is in the run's artifacts once the step ends."
            ),
        )

    # ------------------------------------------------------------------
    # Download all listed logs
    # ------------------------------------------------------------------

    def _bundle(
        self,
        filtered: bool,
    ) -> None:
        """
        One .zip of every log listed: the console log of each listed pod's containers,
        and the files in the folders opened so far. Filtered, text is narrowed to the
        time range and archives that were opened give their files; otherwise files are
        taken as they are.
        """

        assert self._namespace is not None
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
        scope = "filtered" if filtered and not self._span.everything else "all"
        root = Path(self.workspace) / self.SAVE_DIRECTORY
        staging = root / f".bundle-{stamp}"
        target = root / f"{self._namespace}-logs-{scope}-{stamp}.zip"
        notes: List[str] = [
            f"Namespace: {self._namespace}",
            f"Time range: {self._span.describe(self._zone) if filtered else 'everything'}"
            f" ({self._zone})",
            "",
        ]
        total = 0
        count = 0
        self.app.log(ACTIVITY, f"Preparing a download of the listed logs ({scope})...")

        def add(parts: List[str], data: bytes) -> None:
            nonlocal total, count
            if total + len(data) > self._max_bundle:
                notes.append(f"Left out (over max_bundle_mb): {'/'.join(parts)}")
                return
            path = staging.joinpath(*parts)
            self.filesystem.mkdir(path.parent)
            self.filesystem.write_bytes(path, data)
            total += len(data)
            count += 1

        try:
            for pod in self._pods.values():
                for container in pod.containers:
                    try:
                        text = self._source.console(
                            self._namespace,
                            pod.name,
                            container,
                            self._span.start if filtered else None,
                            self._max_lines,
                        )
                        if filtered:
                            text = filter_lines(text, self._span, self._zone)[0]
                        add([pod.name, container, "console.log"], text.encode("utf-8"))
                    except PodLogsException as error:
                        notes.append(f"Not read: {pod.name}/{container} console log: {error}")
            for node in list(self._nodes.values()):
                if node.get("_role") != "file" or node["_pod"] not in self._pods:
                    continue
                label = f"{node['_pod']}/{node['_container']}: {node['_path']}"
                try:
                    self._bundle_file(node, filtered, add, notes)
                except PodLogsException as error:
                    notes.append(f"Not read: {label}: {error}")
            files = count
            add(["README.txt"], ("\n".join(notes) + "\n").encode("utf-8"))
            self.filesystem.remove(target)
            self.archive.compress(staging, target)
        finally:
            self.filesystem.remove(staging)
        self.app.log(ACTIVITY, f"{files} log(s) in {target.name}.")
        self._deliver(target)

    def _bundle_file(
        self,
        node: Dict[str, Any],
        filtered: bool,
        add: Any,
        notes: List[str],
    ) -> None:
        assert self._namespace is not None
        folder = [node["_pod"], node["_container"], *_safe_parts(node["_path"])]
        archive = node["kind"] == "archive"
        if archive and filtered and node.get("loaded"):
            data = self._archive_bytes(node)
            for member in members(node["_path"], data):
                if member["encrypted"]:
                    notes.append(f"Left out (encrypted): {node['_path']}!/{member['name']}")
                    continue
                content = read_member(node["_path"], data, member["name"], self._max_read)
                text = filter_lines(
                    content.decode("utf-8", errors="replace"), self._span, self._zone
                )[0]
                add(
                    [*folder[:-1], f"{folder[-1]}.contents", *_safe_parts(member["name"])],
                    text.encode("utf-8"),
                )
            return
        content = self._source.read(
            self._namespace,
            node["_pod"],
            node["_container"],
            node["_path"],
            self._max_read,
            tail=not archive and not is_gzip(node["_path"]),
        )
        if content.truncated:
            notes.append(
                f"Newest {_size(len(content.data))} of {_size(content.size)}: "
                f"{node['_pod']}/{node['_container']}: {node['_path']}"
            )
        data = content.data
        if filtered and not archive and not self._span.everything:
            if is_gzip(node["_path"]):
                data = gunzip(node["_path"], data, self._max_read)
                folder[-1] = folder[-1][: -len(".gz")]
            if b"\0" not in data[:BINARY_SAMPLE]:
                data = filter_lines(data.decode("utf-8", errors="replace"), self._span, self._zone)[
                    0
                ].encode("utf-8")
        add(folder, data)

    # ------------------------------------------------------------------
    # OpenShift
    # ------------------------------------------------------------------

    def _kubeconfig(
        self,
        environment: str,
    ) -> Path:
        """The oc.generic login session of `environment` (never created here)."""

        path = (
            self.session_directory
            / self.KUBECONFIG_DIRECTORY
            / environment
            / self.KUBECONFIG_FILENAME
        )
        if not self.filesystem.exists(path):
            raise PodLogsException(
                f"No OpenShift session for environment '{environment}'. "
                "Log in first with oc.generic (operation 'login').",
            )
        return path

    def _oc(
        self,
        kubeconfig: Path,
        *arguments: str,
    ) -> Any:
        command = ["oc", *arguments]
        try:
            return self.shell.run(
                command,
                timeout=OC_TIMEOUT_SECONDS,
                env={"KUBECONFIG": str(kubeconfig)},
            )
        except FileNotFoundError as exc:
            raise PodLogsException(
                "'oc' was not found; install it and make sure it is in PATH.",
            ) from exc
        except subprocess.TimeoutExpired as exc:
            raise PodLogsException(
                f"'oc {arguments[0]}' did not answer in {OC_TIMEOUT_SECONDS} seconds.",
            ) from exc
        except UnicodeDecodeError as exc:
            raise PodLogsException(f"'oc {arguments[0]}' returned text that is not UTF-8.") from exc
        except OSError as exc:
            raise PodLogsException(f"Unable to run oc: {exc}") from exc
