"""The pod logs app plugin: time filters, archives, oc commands and the live page."""

from __future__ import annotations

import base64
import gzip
import io
import json
import shutil
import tarfile
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable, Dict, List
from unittest.mock import MagicMock

import pytest

from lib.database.connection import DatabaseConnection
from lib.plugins import contract
from lib.plugins.app import PluginApp, app_definition
from lib.plugins.arguments import PluginArguments
from lib.plugins.contract import read_manifest
from lib.runs.apps import AppStore
from lib.runs.prompts import RUN_MODE_ENV
from resources.plugins.oc.pod_logs import archives
from resources.plugins.oc.pod_logs.exceptions import PodLogsException
from resources.plugins.oc.pod_logs.plugin import CONSOLE_NAME, PodLogsPlugin, _node_id
from resources.plugins.oc.pod_logs.sources import (
    LIST_SCRIPT,
    READ_SCRIPT,
    SEARCH_SCRIPT,
    DemoSource,
    OcSource,
    deployment_of,
)
from resources.plugins.oc.pod_logs.timefilter import Window, filter_lines, line_time, window

PLUGIN_DIR = Path(__file__).resolve().parents[3] / "resources" / "plugins" / "oc" / "pod_logs"
UTC = timezone.utc
NOW = datetime(2026, 11, 8, 12, 0, tzinfo=UTC)


def test_contract_and_app_are_valid() -> None:
    manifest = read_manifest(PLUGIN_DIR)
    assert contract.declared(manifest) is not None
    [browser, _] = app_definition(manifest)["views"]
    assert browser["type"] == "files" and browser["open"] == "open"


# ----------------------------------------------------------------------
# Time filter
# ----------------------------------------------------------------------


@pytest.mark.parametrize(
    "line, expected",
    [
        ("2026-11-08 10:00:00,123 INFO x", datetime(2026, 11, 8, 10, 0, 0, 123000, tzinfo=UTC)),
        ("2026-11-08T10:00:00.5+04:00 x", datetime(2026, 11, 8, 6, 0, 0, 500000, tzinfo=UTC)),
        ("[2026-11-08 10:00:00] x", datetime(2026, 11, 8, 10, 0, tzinfo=UTC)),
        ('1.2.3.4 - - [08/Nov/2026:10:00:00 +0000] "GET /"', datetime(2026, 11, 8, 10, tzinfo=UTC)),
        ("    at com.example.Main(Main.java:1)", None),
    ],
)
def test_line_times(line, expected) -> None:
    moment = line_time(line, UTC)
    assert moment == expected if expected is None else moment is not None and moment == expected


def test_lines_without_a_time_follow_the_line_above() -> None:
    text = "\n".join(
        [
            "2026-11-08 09:00:00 old",
            "    at old.trace",
            "2026-11-08 11:00:00 new ERROR",
            "    at new.trace",
        ]
    )
    shown, kept, total, dated = filter_lines(
        text, Window(datetime(2026, 11, 8, 10, tzinfo=UTC), None), UTC
    )
    assert shown.splitlines() == ["2026-11-08 11:00:00 new ERROR", "    at new.trace"]
    assert (kept, total, dated) == (2, 4, True)


def test_naive_times_use_the_time_zone() -> None:
    dubai = timezone(timedelta(hours=4))
    span = window("Between", "2026-11-08 14:00", "2026-11-08 15:00", dubai)
    assert span.start == datetime(2026, 11, 8, 10, tzinfo=UTC)
    shown, *_ = filter_lines("2026-11-08 14:30:00 inside\n2026-11-08 16:00:00 out", span, dubai)
    assert shown == "2026-11-08 14:30:00 inside"


def test_text_without_timestamps_is_kept_whole() -> None:
    shown, kept, total, dated = filter_lines("a\nb", Window(NOW, None), UTC)
    assert (shown, dated) == ("a\nb", False)


def test_relative_ranges_and_bad_input() -> None:
    assert window("Last hour", "", "", UTC, now=NOW).start == NOW - timedelta(hours=1)
    assert window("Everything", "x", "y", UTC).everything
    with pytest.raises(PodLogsException, match="not a time"):
        window("Between", "yesterday", "", UTC)
    with pytest.raises(PodLogsException, match="later"):
        window("Between", "2026-11-09 00:00", "2026-11-08 00:00", UTC)


# ----------------------------------------------------------------------
# Archives
# ----------------------------------------------------------------------


def _tar(files: Dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as archive:
        for name, data in files.items():
            info = tarfile.TarInfo(name)
            info.size = len(data)
            archive.addfile(info, io.BytesIO(data))
    return buffer.getvalue()


def test_tar_gz_and_zip_members_are_read_without_extracting() -> None:
    tar = _tar({"logs/app.log": b"hello", "../escape.log": b"x"})
    assert [item["name"] for item in archives.members("a.tar.gz", tar)] == [
        "logs/app.log",
        "../escape.log",
    ]
    assert archives.read_member("a.tar.gz", tar, "logs/app.log", 100) == b"hello"

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("x/report.txt", "done")
    assert archives.read_member("r.zip", buffer.getvalue(), "x/report.txt", 100) == b"done"


def test_members_past_the_limit_are_refused() -> None:
    tar = _tar({"big.log": b"x" * 200})
    with pytest.raises(PodLogsException, match="larger"):
        archives.read_member("a.tgz", tar, "big.log", 100)
    with pytest.raises(PodLogsException, match="larger"):
        archives.gunzip("a.log.gz", gzip.compress(b"x" * 200), 100)


def test_archive_kinds() -> None:
    assert archives.is_archive("A.TAR.GZ") and archives.is_archive("x.zip")
    assert archives.is_gzip("app.log.gz") and not archives.is_gzip("a.tar.gz")


# ----------------------------------------------------------------------
# oc
# ----------------------------------------------------------------------


def _result(stdout: str = "", stderr: str = "", code: int = 0) -> SimpleNamespace:
    return SimpleNamespace(success=code == 0, exit_code=code, stdout=stdout, stderr=stderr)


def test_deployment_comes_from_the_owner() -> None:
    replica = {
        "metadata": {
            "name": "api-7c9d8b6f5-x2kqp",
            "labels": {"pod-template-hash": "7c9d8b6f5"},
            "ownerReferences": [{"kind": "ReplicaSet", "name": "api-7c9d8b6f5"}],
        }
    }
    config = {
        "metadata": {
            "name": "web-3-abcde",
            "annotations": {"openshift.io/deployment-config.name": "web"},
        }
    }
    stateful = {
        "metadata": {"name": "db-0", "ownerReferences": [{"kind": "StatefulSet", "name": "db"}]}
    }
    assert [deployment_of(pod) for pod in (replica, config, stateful)] == ["api", "web", "db"]


def test_paths_are_arguments_never_part_of_the_script() -> None:
    calls: List[tuple] = []

    def run(*arguments: str) -> SimpleNamespace:
        calls.append(arguments)
        return _result("@dir\ndirectory|0|1762600000|archive\nregular file|12|1762600000|a b.log")

    listing = OcSource(run).listing("shop", "api-1", "app", "/var/log/$(rm -rf /)")
    assert calls[0][:8] == ("exec", "-n", "shop", "api-1", "-c", "app", "--", "sh")
    assert calls[0][8:] == ("-c", LIST_SCRIPT, "sh", "/var/log/$(rm -rf /)")
    assert [(entry.name, entry.folder) for entry in listing.entries] == [
        ("archive", True),
        ("a b.log", False),
    ]
    assert listing.entries[1].path == "/var/log/$(rm -rf /)/a b.log"


def test_read_decodes_base64_and_reports_a_partial_read() -> None:
    def run(*arguments: str) -> SimpleNamespace:
        assert arguments[-6:] == ("-c", READ_SCRIPT, "sh", "/l/app.log", "4", "tail")
        return _result("10\n" + base64.b64encode(b"tail").decode())

    content = OcSource(run).read("shop", "api-1", "app", "/l/app.log", 4, tail=True)
    assert (content.data, content.size, content.truncated) == (b"tail", 10, True)


def test_an_archive_too_large_says_how_to_open_it() -> None:
    source = OcSource(lambda *arguments: _result("999999999", code=4))
    with pytest.raises(PodLogsException, match="max_read_mb"):
        source.read("shop", "api-1", "app", "/l/a.zip", 10, tail=False)


def test_search_passes_text_and_paths_as_arguments_and_parses_matches() -> None:
    run = MagicMock(
        return_value=_result(
            "/l/a.log:3:ERROR boom\n/l/b:c.log:12:x:y\n/l/old.gz:1:junk\nBinary file /l/z matches"
        )
    )
    found = OcSource(run).search("shop", "api-1", "app", ["/l", "/x y"], "$(rm -rf /)", 5, 50)
    command = run.call_args.args
    assert SEARCH_SCRIPT in command and "$(rm -rf /)" not in SEARCH_SCRIPT
    assert list(command[command.index(SEARCH_SCRIPT) + 1 :]) == [
        "sh",
        "$(rm -rf /)",
        "5",
        "50",
        "/l",
        "/x y",
    ]
    assert [(item.path, item.line, item.text) for item in found] == [
        ("/l/a.log", 3, "ERROR boom"),
        ("/l/b:c.log", 12, "x:y"),
    ]


def test_console_log_uses_since_time_and_tail() -> None:
    calls: List[tuple] = []
    OcSource(lambda *arguments: calls.append(arguments) or _result("x")).console(
        "shop", "api-1", "app", NOW, 500
    )
    assert calls[0] == (
        "logs",
        "-n",
        "shop",
        "api-1",
        "-c",
        "app",
        "--timestamps",
        "--since-time=2026-11-08T12:00:00Z",
        "--tail=500",
    )


# ----------------------------------------------------------------------
# Live page
# ----------------------------------------------------------------------


class FakeOc:
    """Answers oc like a cluster with one pod whose /logs folder holds one file."""

    def __init__(self) -> None:
        self.calls: List[List[str]] = []
        log = "2026-11-08 09:00:00 INFO old\n2026-11-08 11:30:00 ERROR new\n"
        self.files = {"/logs/app.log": log.encode(), "/logs/old/2026-11-01.log": b"rotated\n"}

    def __call__(self, command, timeout=None, env=None) -> SimpleNamespace:
        self.calls.append(command)
        if command[1] == "get":
            pod = {
                "metadata": {
                    "name": "orders-5d9f-abcde",
                    "labels": {"pod-template-hash": "5d9f"},
                    "ownerReferences": [{"kind": "ReplicaSet", "name": "orders-5d9f"}],
                },
                "spec": {"containers": [{"name": "app"}]},
                "status": {"phase": "Running"},
            }
            return _result(json.dumps({"items": [pod]}))
        if command[1] == "exec" and LIST_SCRIPT in command:
            path = command[-1]
            if path == "/logs":
                return _result(
                    "@dir\nregular file|60|1794138300|app.log\ndirectory|0|1762600000|old"
                )
            if path == "/logs/old":
                return _result("@dir\nregular file|8|1762600000|2026-11-01.log")
            return _result("@missing")
        if command[1] == "exec" and SEARCH_SCRIPT in command:
            start = command.index(SEARCH_SCRIPT) + 2
            text, paths = command[start].lower(), command[start + 3 :]
            hits = [
                f"{path}:{number}:{line}"
                for path, data in sorted(self.files.items())
                if any(path.startswith(f"{root}/") or path == root for root in paths)
                for number, line in enumerate(data.decode().splitlines(), 1)
                if text in line.lower()
            ]
            return _result("\n".join(hits))
        if command[1] == "exec" and READ_SCRIPT in command:
            data = self.files[command[-3]]
            return _result(f"{len(data)}\n{base64.b64encode(data).decode()}")
        if command[1] == "logs":
            return _result("2026-11-08T11:00:00.000000000Z started")
        return _result("", "unexpected", 1)


def _page(tmp_path: Path, monkeypatch, mode: str, actions: List[Callable], **arguments: Any):
    monkeypatch.setenv(RUN_MODE_ENV, mode)
    connection = DatabaseConnection(tmp_path / "entropy.db")
    # The run's job, as the server creates it: offered downloads name its execution.
    connection.execute("CREATE TABLE workflow_jobs (id INTEGER PRIMARY KEY, execution_id TEXT)")
    connection.execute("INSERT INTO workflow_jobs VALUES (7, 'exec-7')")
    context = MagicMock()
    context._runtime = SimpleNamespace(
        job_id=7,
        node=SimpleNamespace(name="Pod logs", type=None, parent=None),
        _entropy=SimpleNamespace(database_manager=SimpleNamespace(connection=connection)),
        # What offer() needs to register a download as an artifact.
        database=SimpleNamespace(connection=connection),
        workspace=tmp_path / "workspace",
        user="tester",
        execution=SimpleNamespace(id="exec-1"),
    )
    context.outputs = {}
    context.artifacts = {}
    context.workspace = tmp_path / "workspace"
    context.session_directory = tmp_path / "session"
    context.arguments = PluginArguments(arguments)
    kubeconfig = context.session_directory / ".kube" / "SIT" / "config"
    kubeconfig.parent.mkdir(parents=True)
    kubeconfig.write_text("config")
    context.filesystem.exists.side_effect = lambda path: Path(path).exists()
    context.filesystem.mkdir.side_effect = lambda path: Path(path).mkdir(
        parents=True, exist_ok=True
    )
    context.filesystem.write_text.side_effect = lambda path, text: Path(path).write_text(text)
    context.filesystem.write_bytes.side_effect = lambda path, data: Path(path).write_bytes(data)
    context.filesystem.remove.side_effect = lambda path: (
        shutil.rmtree(path) if Path(path).is_dir() else Path(path).unlink(missing_ok=True)
    )
    context.archive.compress.side_effect = _compress
    oc = FakeOc()
    context.shell.run.side_effect = oc

    plugin = PodLogsPlugin(context)
    store = AppStore(connection)
    pending = list(actions)

    def sleep(_: float) -> None:
        [page] = store.list([7])
        if page["state"] != "running":
            return
        if pending:
            pending.pop(0)(store, page["id"])
        else:
            store.request_stop(page["id"])

    plugin._entropy_app_session = PluginApp(
        context, app_definition(read_manifest(PLUGIN_DIR)), "oc.pod_logs", sleep=sleep
    )
    return plugin, store, context, oc


def _compress(source: Path, archive: Path) -> Path:
    with zipfile.ZipFile(archive, "w") as bundle:
        for file in sorted(source.rglob("*")):
            if file.is_file():
                bundle.write(file, file.relative_to(source))
    return archive


def _press(name: str, *selection: str) -> Callable:
    return lambda store, app_id: store.push_event(app_id, name, {"selection": list(selection)}, "u")


def _inputs(**values: Any) -> Callable:
    return lambda store, app_id: store.set_inputs(app_id, values)


def _browser(store: AppStore) -> Dict[str, Any]:
    [page] = store.list([7])
    return page["views"]["browser"]


POD = "orders-5d9f-abcde"


def test_automated_run_lists_pods_with_their_paths(tmp_path, monkeypatch) -> None:
    plugin, store, context, oc = _page(
        tmp_path,
        monkeypatch,
        "automated",
        [],
        environment="SIT",
        namespace="shop",
        default_paths=["/var/log"],
        log_paths={"orders*": ["/logs"], "other": ["/x"]},
    )

    result = plugin.execute()

    assert result.success, result.errors
    assert result.outputs["pods"] == [
        {"pod": POD, "deployment": "orders", "status": "Running", "paths": ["/var/log", "/logs"]}
    ]
    kubeconfig = str(context.session_directory / ".kube" / "SIT" / "config")
    assert all(call[0] == "oc" for call in oc.calls)
    assert all(
        call.kwargs["env"] == {"KUBECONFIG": kubeconfig}
        for call in context.shell.run.call_args_list
    )
    [node] = _browser(store)["nodes"]
    assert node["name"] == POD and node["kind"] == "group" and "_role" not in node


def test_browse_open_filter_and_save(tmp_path, monkeypatch) -> None:
    pod = _node_id("pod", POD)
    folder = _node_id("path", POD, "app", "/logs")
    log = _node_id("path", POD, "app", "/logs/app.log")
    seen: Dict[str, Any] = {}

    def keep(name: str) -> Callable:
        def capture(store: AppStore, app_id: int) -> None:
            seen[name] = _browser(store)

        return capture

    plugin, store, context, oc = _page(
        tmp_path,
        monkeypatch,
        "interactive",
        [
            _press("open", pod),
            keep("pod"),
            _press("open", folder),
            _press("open", log),
            keep("opened"),
            _inputs(range="Between", **{"from": "2026-11-08 11:00", "to": ""}),
            keep("filtered"),
            _press("save"),
        ],
        environment="SIT",
        namespace="shop",
        default_paths=[],
        log_paths={"orders": ["/logs"]},
    )

    result = plugin.execute()

    assert result.success, result.errors
    names = {node["name"]: node for node in seen["pod"]["nodes"]}
    assert names[CONSOLE_NAME]["parent"] == pod
    assert names["/logs"]["note"] == "configured for orders"
    assert len(seen["opened"]["opened"]["text"].splitlines()) == 2
    filtered = seen["filtered"]["opened"]
    assert filtered["text"] == "2026-11-08 11:30:00 ERROR new"
    assert "1 of 2 lines" in filtered["notice"]
    [saved] = result.outputs["saved"]
    assert saved.startswith(f"pod_logs/{POD}/app/")
    assert (context.workspace / saved).read_text() == "2026-11-08 11:30:00 ERROR new"
    # Downloadable straight away: registered as an artifact, not left for the step's end.
    assert saved not in context.artifacts
    [download] = _browser(store)["downloads"]
    assert download["url"] == f"/api/artifacts/{download['id']}/download"
    assert download["name"] == Path(saved).name
    # Only reads: get, exec (ls/cat through sh), logs.
    assert {call[1] for call in oc.calls} <= {"get", "exec", "logs"}


def test_dry_run_needs_no_session_and_opens_archives(tmp_path, monkeypatch) -> None:
    source = DemoSource(now=NOW)
    pod = "orders-api-7c9d8b6f5-x2kqp"
    archive = _node_id("path", pod, "app", "/var/log/archive/app-old.log.tar.gz")
    member = _node_id("member", archive, "logs/audit.log")
    seen: Dict[str, Any] = {}

    def keep(store: AppStore, app_id: int) -> None:
        seen["browser"] = _browser(store)

    plugin, store, _, oc = _page(
        tmp_path,
        monkeypatch,
        "interactive",
        [
            _press("open", _node_id("pod", pod)),
            _press("open", _node_id("path", pod, "app", "/var/log")),
            _press("open", _node_id("path", pod, "app", "/var/log/archive")),
            _press("open", archive),
            _press("open", member),
            keep,
        ],
        dry_run=True,
    )

    def demo(*_args: Any, **_kwargs: Any) -> DemoSource:
        return source

    monkeypatch.setattr("resources.plugins.oc.pod_logs.plugin.DemoSource", demo)

    result = plugin.execute()

    assert result.success, result.errors
    assert oc.calls == []
    assert result.outputs["namespace"] == "demo"
    nodes = {node["name"] for node in seen["browser"]["nodes"]}
    assert {"app", "proxy", "archive", "app-old.log.tar.gz", "logs", "audit.log"} <= nodes
    assert "INFO" in seen["browser"]["opened"]["text"]


def test_no_session_fails_and_says_how_to_log_in(tmp_path, monkeypatch) -> None:
    plugin, _, context, oc = _page(tmp_path, monkeypatch, "automated", [], environment="PROD")

    result = plugin.execute()

    assert not result.success and "oc.generic" in result.errors[0]["message"]
    assert oc.calls == []


@pytest.mark.parametrize(
    "arguments, message",
    [
        ({"environment": "SIT", "default_paths": ["relative/logs"]}, "absolute"),
        ({"environment": "SIT", "log_paths": {"api": ["/ok", "nope"]}}, "absolute"),
        ({"environment": "SIT", "timezone": "Mars/Base"}, "time zone"),
        ({"environment": "SIT", "namespace": "../x"}, "valid namespace"),
        ({}, "dry_run"),
    ],
)
def test_bad_arguments_never_reach_oc(tmp_path, monkeypatch, arguments, message) -> None:
    plugin, _, _, oc = _page(tmp_path, monkeypatch, "automated", [], **arguments)

    result = plugin.execute()

    assert not result.success and message in result.errors[0]["message"]
    assert oc.calls == []


def _zip(context: Any, download: Dict[str, Any]) -> zipfile.ZipFile:
    return zipfile.ZipFile(context.workspace / "pod_logs" / download["name"])


def test_download_listed_logs_filtered_and_all(tmp_path, monkeypatch) -> None:
    pod = _node_id("pod", POD)
    folder = _node_id("path", POD, "app", "/logs")
    plugin, store, context, oc = _page(
        tmp_path,
        monkeypatch,
        "interactive",
        [
            _press("open", pod),
            _press("open", folder),
            _inputs(range="Between", **{"from": "2026-11-08T11:00", "to": ""}),
            _press("download_filtered"),
            _inputs(range="Everything"),
            _press("download_all"),
        ],
        environment="SIT",
        namespace="shop",
        default_paths=[],
        log_paths={"orders": ["/logs"]},
    )

    result = plugin.execute()

    assert result.success, result.errors
    downloads = _browser(store)["downloads"]
    everything, filtered = downloads
    # One pod: named after it, with the time it was made; its folder carries the same name.
    assert filtered["name"].startswith(f"{POD}-filtered-20")
    assert everything["name"].startswith(f"{POD}-20") and "filtered" not in everything["name"]
    root = filtered["name"][: -len(".zip")]
    with _zip(context, filtered) as bundle:
        names = set(bundle.namelist())
        assert {
            f"{root}/app/console.log",
            f"{root}/app/logs/app.log",
            f"{root}/README.txt",
        } <= names
        assert bundle.read(f"{root}/app/logs/app.log").decode() == "2026-11-08 11:30:00 ERROR new"
        # The subfolder was never expanded; its file was written before the range.
        assert f"{root}/app/logs/old/2026-11-01.log" not in names
    root = everything["name"][: -len(".zip")]
    with _zip(context, everything) as bundle:
        assert bundle.read(f"{root}/app/logs/app.log").decode().count("\n") == 2
        assert bundle.read(f"{root}/app/logs/old/2026-11-01.log") == b"rotated\n"
    assert _browser(store)["progress"] is None
    # The staging folders are gone; only the bundles remain.
    assert sorted(path.name for path in (context.workspace / "pod_logs").iterdir()) == sorted(
        item["name"] for item in downloads
    )


def test_a_ticked_pod_downloads_its_folders_without_expanding_them(tmp_path, monkeypatch) -> None:
    plugin, store, context, oc = _page(
        tmp_path,
        monkeypatch,
        "interactive",
        # The pod is listed but never opened in the tree.
        [_press("download_all", _node_id("pod", POD))],
        environment="SIT",
        namespace="shop",
        default_paths=[],
        log_paths={"orders": ["/logs"]},
    )
    shown: List[Any] = []
    publish = plugin._publish

    def recording() -> None:
        shown.append(plugin._progress)
        publish()

    plugin._publish = recording  # type: ignore[method-assign]

    result = plugin.execute()

    assert result.success, result.errors
    [download] = _browser(store)["downloads"]
    root = download["name"][: -len(".zip")]
    with _zip(context, download) as bundle:
        assert set(bundle.namelist()) == {
            f"{root}/README.txt",
            f"{root}/app/console.log",
            f"{root}/app/logs/app.log",
            f"{root}/app/logs/old/2026-11-01.log",
        }
    labels = [item["label"] for item in shown if item]
    assert labels[0] == "Listing folders..." and "Compressing..." in labels
    reading = [item for item in shown if item and item["label"] == "Reading logs..."]
    assert reading[-1]["done"] == reading[-1]["total"] == 3
    assert shown[-1] is None


def test_a_ticked_folder_downloads_only_that_folder(tmp_path, monkeypatch) -> None:
    pod = _node_id("pod", POD)
    plugin, store, context, oc = _page(
        tmp_path,
        monkeypatch,
        "interactive",
        [
            _press("open", pod),
            _press("download_all", _node_id("path", POD, "app", "/logs"), "gone"),
        ],
        environment="SIT",
        namespace="shop",
        default_paths=[],
        log_paths={"orders": ["/logs"]},
    )

    result = plugin.execute()

    assert result.success, result.errors
    [download] = _browser(store)["downloads"]
    root = download["name"][: -len(".zip")]
    with _zip(context, download) as bundle:
        assert set(bundle.namelist()) == {
            f"{root}/README.txt",
            f"{root}/app/logs/app.log",
            f"{root}/app/logs/old/2026-11-01.log",
        }
        assert "no longer listed" in bundle.read(f"{root}/README.txt").decode()


def _search(text: str, *selection: str) -> Callable:
    return lambda store, app_id: store.push_event(
        app_id, "search_logs", {"selection": list(selection), "values": {"search": text}}, "u"
    )


def test_search_lists_matches_above_the_pods_and_opens_them_highlighted(
    tmp_path, monkeypatch
) -> None:
    seen: Dict[str, Any] = {}

    def keep(name: str) -> Callable:
        def capture(store: AppStore, app_id: int) -> None:
            seen[name] = _browser(store)

        return capture

    result_file = _node_id("search-file", POD, "app", "/logs/app.log")
    plugin, store, context, oc = _page(
        tmp_path,
        monkeypatch,
        "interactive",
        [
            # The pod was never opened: its paths are searched inside the container.
            _search("error"),
            keep("found"),
            _press("open", result_file),
            keep("opened"),
            _search(""),
            keep("cleared"),
        ],
        environment="SIT",
        namespace="shop",
        default_paths=[],
        log_paths={"orders": ["/logs"]},
    )

    result = plugin.execute()

    assert result.success, result.errors
    found = seen["found"]
    first, scope, match = found["nodes"][:3]
    assert first["name"] == "Search: error" and first["parent"] is None
    assert first["note"] == "1 in 1 file(s)"
    assert scope["parent"] == first["id"] and scope["name"] == POD
    assert match["id"] == result_file and match["note"] == "1 match(es)"
    assert found["nodes"][3]["name"] == POD
    assert found["opened"]["text"] == f"{POD}/app  /logs/app.log:2  2026-11-08 11:30:00 ERROR new"
    assert found["opened"]["highlight"] == "error"
    assert found["progress"] is None
    opened = seen["opened"]["opened"]
    assert opened["id"] == result_file and opened["highlight"] == "error"
    assert "ERROR new" in opened["text"]
    assert all(node["name"] != "Search: error" for node in seen["cleared"]["nodes"])
    # Only reads.
    assert {call[1] for call in oc.calls} <= {"get", "exec", "logs"}


def test_dry_run_search_finds_text_in_the_sample_logs(tmp_path, monkeypatch) -> None:
    pod = "billing-6f8d7-ab12c"
    seen: Dict[str, Any] = {}

    def keep(store: AppStore, app_id: int) -> None:
        seen["browser"] = _browser(store)

    plugin, store, _, oc = _page(
        tmp_path,
        monkeypatch,
        "interactive",
        [_search("timed out", _node_id("pod", pod)), keep],
        dry_run=True,
    )

    assert plugin.execute().success
    shown = seen["browser"]["opened"]
    assert shown["id"] == "search" and "SocketTimeoutException" in shown["text"]
    assert all(line.startswith(f"{pod}/billing  /var/log/") for line in shown["text"].splitlines())
    assert "not searched" in shown["notice"]
