"""The pod metrics app plugin, with oc mocked."""

from __future__ import annotations

import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock

import pytest

from lib.database.connection import DatabaseConnection
from lib.plugins import contract
from lib.plugins.app import PluginApp, app_definition
from lib.plugins.arguments import PluginArguments
from lib.plugins.contract import read_manifest
from lib.runs.apps import AppStore
from lib.runs.prompts import RUN_MODE_ENV
from resources.plugins.oc.pod_metrics.metrics import (
    cpu_millicores,
    display_row,
    format_age,
    memory_mib,
    pod_rows,
)
from resources.plugins.oc.pod_metrics.plugin import PodMetricsPlugin

PLUGIN_DIR = Path(__file__).resolve().parents[3] / "resources" / "plugins" / "oc" / "pod_metrics"


def _pod(
    name: str,
    *,
    phase: str = "Running",
    ready: bool = True,
    restarts: int = 0,
    limits: Optional[Dict[str, str]] = None,
    waiting: Optional[str] = None,
    env: Optional[List[Dict[str, str]]] = None,
) -> Dict[str, Any]:
    state = {"waiting": {"reason": waiting}} if waiting else {"running": {}}
    return {
        "metadata": {"name": name, "creationTimestamp": "2026-01-01T00:00:00Z"},
        "spec": {
            "nodeName": "worker-1",
            "containers": [
                {"name": "app", "resources": {"limits": limits or {}}, "env": env or []},
            ],
        },
        "status": {
            "phase": phase,
            "startTime": "2026-01-01T00:00:00Z",
            "containerStatuses": [
                {"name": "app", "ready": ready, "restartCount": restarts, "state": state}
            ],
        },
    }


def _metric(name: str, cpu: str, memory: str) -> Dict[str, Any]:
    return {
        "metadata": {"name": name},
        "containers": [{"name": "app", "usage": {"cpu": cpu, "memory": memory}}],
    }


PODS = {
    "items": [
        _pod("web", limits={"cpu": "1", "memory": "1Gi"}),
        _pod("api", restarts=3, limits={"cpu": "500m", "memory": "512Mi"}),
        _pod("crash", ready=False, restarts=9, waiting="CrashLoopBackOff"),
    ]
}
METRICS = {
    "items": [
        _metric("web", "100m", "256Mi"),
        _metric("api", "400m", "128Mi"),
    ]
}


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("250m", 250),
        ("1", 1000),
        ("1.5", 1500),
        ("123456000n", 123.456),
        ("5000u", 5),
        (None, None),
    ],
)
def test_cpu_quantities(value, expected) -> None:
    assert cpu_millicores(value) == pytest.approx(expected) if expected else value is None


@pytest.mark.parametrize(
    ("value", "expected"),
    [("512Mi", 512), ("1Gi", 1024), ("1024Ki", 1), ("1048576", 1), ("2097152000m", 2)],
)
def test_memory_quantities(value, expected) -> None:
    assert memory_mib(value) == pytest.approx(expected)


@pytest.mark.parametrize("value", [None, "", "abc", "1Xi", "1.2.3"])
def test_unreadable_quantities_are_none(value) -> None:
    assert memory_mib(value) is None and cpu_millicores(value) is None


@pytest.mark.parametrize(
    ("seconds", "expected"), [(5, "5s"), (120, "2m"), (7200, "2h"), (172800, "2d")]
)
def test_age(seconds, expected) -> None:
    now = datetime.fromtimestamp(1_000_000 + seconds, timezone.utc)
    started = datetime.fromtimestamp(1_000_000, timezone.utc).isoformat()

    assert format_age(started, now) == expected


def test_rows_combine_status_usage_and_limits() -> None:
    rows = {row["pod"]: row for row in pod_rows(PODS, METRICS)}

    assert rows["web"]["cpu"] == 100 and rows["web"]["cpu_percent"] == 10
    assert rows["web"]["memory"] == 256 and rows["web"]["memory_percent"] == 25
    assert rows["web"]["ready"] == "1/1" and not rows["web"]["attention"]
    assert rows["api"]["restarts"] == 3 and rows["api"]["cpu_percent"] == 80
    # A waiting reason wins over the phase, and no sample or limit gives no value.
    assert rows["crash"]["status"] == "CrashLoopBackOff" and rows["crash"]["attention"]
    assert rows["crash"]["cpu"] is None and rows["crash"]["cpu_percent"] is None


def test_finished_pods_do_not_need_attention() -> None:
    [row] = pod_rows({"items": [_pod("job", phase="Succeeded", ready=False)]}, None)

    assert row["status"] == "Succeeded" and not row["attention"]


def test_a_terminating_pod_says_so() -> None:
    pod = _pod("old")
    pod["metadata"]["deletionTimestamp"] = "2026-01-02T00:00:00Z"

    assert pod_rows({"items": [pod]}, None)[0]["status"] == "Terminating"


def test_a_limit_on_only_some_containers_gives_no_percent() -> None:
    pod = _pod("two", limits={"cpu": "1"})
    pod["spec"]["containers"].append({"name": "side", "resources": {}})
    metric = _metric("two", "100m", "10Mi")

    [row] = pod_rows({"items": [pod]}, {"items": [metric]})

    assert row["cpu_limit"] is None and row["cpu_percent"] is None and row["cpu"] == 100


def test_env_values_never_reach_a_row() -> None:
    pod = _pod("secret", env=[{"name": "PASSWORD", "value": "hunter2"}])

    [row] = pod_rows({"items": [pod]}, None)

    assert "hunter2" not in json.dumps(row) and "hunter2" not in json.dumps(display_row(row))


def test_display_row_has_only_table_values() -> None:
    [row] = pod_rows({"items": [_pod("a")]}, None)

    shown = display_row(row)

    assert shown["cpu"] == "—" and "attention" not in shown and "containers" not in shown


def test_contract_and_app_are_valid() -> None:
    declared = contract.declared(read_manifest(PLUGIN_DIR))

    assert declared is not None
    assert contract.check_source(PLUGIN_DIR, declared) == []
    assert app_definition(read_manifest(PLUGIN_DIR))["refresh_seconds"] == 5


# ----------------------------------------------------------------------
# The plugin
# ----------------------------------------------------------------------


class FakeOc:
    def __init__(self) -> None:
        self.calls: List[Dict[str, Any]] = []
        self.pods: Any = PODS
        self.metrics: Any = METRICS
        self.project = "from-session"
        self.pods_error: Optional[str] = None
        self.metrics_error: Optional[str] = None
        self.raises: Optional[Exception] = None

    def __call__(self, command, timeout=None, env=None) -> SimpleNamespace:
        self.calls.append({"command": command, "timeout": timeout, "env": env})
        if self.raises:
            raise self.raises
        if command[1] == "project":
            return self._result(self.project)
        if "--raw" in command:
            if self.metrics_error:
                return self._result("", self.metrics_error)
            return self._result(json.dumps(self.metrics))
        if self.pods_error:
            return self._result("", self.pods_error)
        return self._result(json.dumps(self.pods))

    @staticmethod
    def _result(stdout: str, error: Optional[str] = None) -> SimpleNamespace:
        return SimpleNamespace(success=error is None, stdout=stdout, stderr=error or "")


def _plugin(tmp_path: Path, monkeypatch, mode: str, **arguments: Any) -> tuple:
    monkeypatch.setenv(RUN_MODE_ENV, mode)
    connection = DatabaseConnection(tmp_path / "entropy.db")
    context = MagicMock()
    context._runtime = SimpleNamespace(
        job_id=5,
        node=SimpleNamespace(name="Pod metrics"),
        _entropy=SimpleNamespace(database_manager=SimpleNamespace(connection=connection)),
    )
    context.outputs = {}
    context.session_directory = tmp_path / "session"
    context.arguments = PluginArguments({"environment": "SIT", **arguments})
    kubeconfig = context.session_directory / ".kube" / "SIT" / "config"
    kubeconfig.parent.mkdir(parents=True)
    kubeconfig.write_text("config")
    context.filesystem.exists.side_effect = lambda path: Path(path).exists()
    oc = FakeOc()
    context.shell.run.side_effect = oc

    plugin = PodMetricsPlugin(context)
    store = AppStore(connection)
    stops = {"after": 2}

    def sleep(_: float) -> None:
        stops["after"] -= 1
        if stops["after"] <= 0:
            for page in store.list([5]):
                if page["state"] == "running":
                    store.request_stop(page["id"])

    plugin._entropy_app_session = PluginApp(
        context, app_definition(read_manifest(PLUGIN_DIR)), "oc.pod_metrics", sleep=sleep
    )
    return plugin, store, context, oc


def _stats(page: Dict[str, Any]) -> Dict[str, Any]:
    return {item["label"]: item["value"] for item in page["views"]["summary"]["items"]}


def test_automated_run_reports_one_pass(tmp_path, monkeypatch) -> None:
    plugin, store, _, oc = _plugin(tmp_path, monkeypatch, "automated", namespace="shop")

    result = plugin.execute()

    assert result.success
    assert result.outputs["namespace"] == "shop" and result.outputs["pod_count"] == 3
    assert result.outputs["attention_count"] == 1 and result.outputs["metrics_available"] is True
    assert result.outputs["cpu_millicores"] == 500 and result.outputs["memory_mib"] == 384

    [page] = store.list([5])
    rows = page["views"]["pods"]["rows"]
    # CPU, highest first; a pod with no usage last.
    assert [row["pod"] for row in rows] == ["api", "web", "crash"]
    assert rows[2]["cpu"] == "—"
    assert _stats(page)["Need attention"] == 1 and _stats(page)["Restarts"] == 12
    assert page["state"] == "finished"


def test_oc_uses_the_session_and_a_timeout_and_only_reads(tmp_path, monkeypatch) -> None:
    plugin, _, context, oc = _plugin(tmp_path, monkeypatch, "automated", namespace="shop")

    assert plugin.execute().success

    kubeconfig = str(context.session_directory / ".kube" / "SIT" / "config")
    assert all(call["env"] == {"KUBECONFIG": kubeconfig} for call in oc.calls)
    assert all(call["timeout"] for call in oc.calls)
    assert all(call["command"][:2] == ["oc", "get"] for call in oc.calls)
    assert any(
        "/apis/metrics.k8s.io/v1beta1/namespaces/shop/pods" in call["command"] for call in oc.calls
    )


def test_the_session_project_is_used_without_a_namespace(tmp_path, monkeypatch) -> None:
    plugin, _, _, oc = _plugin(tmp_path, monkeypatch, "automated")

    result = plugin.execute()

    assert result.outputs["namespace"] == "from-session"
    assert oc.calls[0]["command"] == ["oc", "project", "-q"]


def test_no_session_fails_and_says_how_to_log_in(tmp_path, monkeypatch) -> None:
    plugin, _, _, oc = _plugin(tmp_path, monkeypatch, "automated")
    plugin._context.arguments = PluginArguments({"environment": "PROD"})

    result = plugin.execute()

    assert not result.success and "oc.generic" in result.errors[0]["message"]
    assert oc.calls == []


@pytest.mark.parametrize("environment", ["", "../etc", "a b"])
def test_a_bad_environment_is_refused(tmp_path, monkeypatch, environment) -> None:
    plugin, _, _, oc = _plugin(tmp_path, monkeypatch, "automated")
    plugin._context.arguments = PluginArguments({"environment": environment})

    assert not plugin.execute().success
    assert oc.calls == []


def test_a_bad_namespace_never_reaches_oc(tmp_path, monkeypatch) -> None:
    plugin, _, _, oc = _plugin(tmp_path, monkeypatch, "automated", namespace="../../secrets")

    result = plugin.execute()

    assert not result.success and "not a valid namespace" in result.errors[0]["message"]
    assert oc.calls == []


def test_metrics_unavailable_still_shows_status(tmp_path, monkeypatch) -> None:
    plugin, store, _, oc = _plugin(tmp_path, monkeypatch, "automated", namespace="shop")
    oc.metrics_error = "Error from server (Forbidden): pods.metrics.k8s.io is forbidden"

    result = plugin.execute()

    assert result.success and result.outputs["metrics_available"] is False
    assert result.outputs["pod_count"] == 3
    [page] = store.list([5])
    source = {item["key"]: item["value"] for item in page["views"]["source"]["items"]}
    assert "Forbidden" in source["Metrics"]
    assert any("Forbidden" in line for line in page["views"]["activity"]["lines"])


@pytest.mark.parametrize(
    "failure",
    [FileNotFoundError("oc"), subprocess.TimeoutExpired("oc", 30), OSError("broken")],
)
def test_oc_problems_fail_an_automated_run(tmp_path, monkeypatch, failure) -> None:
    plugin, _, _, oc = _plugin(tmp_path, monkeypatch, "automated", namespace="shop")
    oc.raises = failure

    result = plugin.execute()

    assert not result.success and result.errors


def test_a_failed_pods_read_fails_an_automated_run(tmp_path, monkeypatch) -> None:
    plugin, _, _, oc = _plugin(tmp_path, monkeypatch, "automated", namespace="shop")
    oc.pods_error = "forbidden"

    result = plugin.execute()

    assert not result.success and "forbidden" in result.errors[0]["message"]


def test_live_page_follows_inputs_and_buttons_until_stopped(tmp_path, monkeypatch) -> None:
    plugin, store, _, oc = _plugin(tmp_path, monkeypatch, "interactive", namespace="shop")
    app = plugin.app
    assert app.running
    page_id = store.list([5])[0]["id"]
    store.set_inputs(
        page_id,
        {"namespace": "other", "filter": "", "sort": "Restarts", "only_attention": False},
    )
    store.push_event(page_id, "details", {"selection": ["api", "gone"]}, "bob")
    app._passes = 0

    result = plugin.execute()

    assert result.success and result.outputs["namespace"] == "other"
    [page] = store.list([5])
    assert [row["pod"] for row in page["views"]["pods"]["rows"]] == ["crash", "api", "web"]
    log = page["views"]["activity"]["lines"]
    assert any(line.startswith("api (Running") for line in log)
    assert "  app: CPU 400.0m, memory 128.0 MiB" in log
    assert log[-1] == "Monitoring stopped."


def test_live_filter_and_attention_toggle(tmp_path, monkeypatch) -> None:
    plugin, store, _, _ = _plugin(tmp_path, monkeypatch, "interactive", namespace="shop")
    app = plugin.app
    assert app.running
    page_id = store.list([5])[0]["id"]
    store.set_inputs(page_id, {"only_attention": True})
    app._passes = 0

    assert plugin.execute().success

    [page] = store.list([5])
    assert [row["pod"] for row in page["views"]["pods"]["rows"]] == ["crash"]
    # The summary still describes the whole namespace.
    assert _stats(page)["Pods"] == 3


def test_a_live_page_survives_a_failed_refresh_and_keeps_its_rows(tmp_path, monkeypatch) -> None:
    plugin, store, _, oc = _plugin(tmp_path, monkeypatch, "interactive", namespace="shop")
    real_wait = plugin.app.wait
    passes = {"count": 0}

    def wait(seconds=None) -> None:
        passes["count"] += 1
        # First refresh works, the second fails, the third works again.
        oc.pods_error = "connection refused" if passes["count"] == 1 else None
        real_wait(seconds)

    plugin.app.wait = wait
    plugin._entropy_app_session._sleep = _stop_after(store, 3)

    result = plugin.execute()

    assert result.success and result.outputs["pod_count"] == 3
    [page] = store.list([5])
    log = page["views"]["activity"]["lines"]
    assert sum("connection refused" in line for line in log) == 1
    assert "Refreshing again." in log
    assert len(page["views"]["pods"]["rows"]) == 3


def _stop_after(store: AppStore, refreshes: int) -> Any:
    state = {"seen": 0}

    def sleep(_: float) -> None:
        state["seen"] += 1
        # wait() sleeps in 0.25 steps over 5 seconds: 20 per refresh.
        if state["seen"] >= refreshes * 20:
            for page in store.list([5]):
                if page["state"] == "running":
                    store.request_stop(page["id"])

    return sleep
