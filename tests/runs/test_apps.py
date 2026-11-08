"""App plugins: the app section of plugin.json, the page store and self.app."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from lib.database.connection import DatabaseConnection
from lib.plugins.app import PluginApp, PluginAppError, app_definition, normalize_app
from lib.plugins.contract import ContractError
from lib.runs.apps import AppError, AppStore
from lib.runs.prompts import RUN_MODE_ENV

APP = {
    "title": "Pod monitor",
    "refresh_seconds": 1,
    "inputs": [
        {"name": "filter", "type": "text", "label": "Filter", "default": ""},
        {"name": "namespace", "type": "select", "choices": ["sit", "uat"], "default": "sit"},
        {"name": "follow", "type": "toggle"},
        {"name": "restart", "type": "button", "label": "Restart", "target": "pods"},
    ],
    "views": [
        {
            "name": "pods",
            "type": "table",
            "columns": ["name", {"key": "status", "label": "Status"}],
            "row_key": "name",
            "selectable": True,
        },
        {"name": "summary", "type": "stats"},
        {"name": "events", "type": "log", "max_lines": 3},
    ],
}


@pytest.fixture
def connection(tmp_path: Path) -> DatabaseConnection:
    return DatabaseConnection(tmp_path / "entropy.db")


def _context(connection: DatabaseConnection, job_id: int | None = 7) -> SimpleNamespace:
    runtime = SimpleNamespace(
        job_id=job_id,
        node=SimpleNamespace(name="monitor"),
        _entropy=SimpleNamespace(database_manager=SimpleNamespace(connection=connection)),
    )
    return SimpleNamespace(_runtime=runtime)


def test_app_section_is_normalized() -> None:
    app = normalize_app(APP)

    assert app["refresh_seconds"] == 1.0
    assert app["inputs"][1]["label"] == "Namespace"
    assert app["inputs"][2]["default"] is False  # toggles start off
    assert app["views"][0]["columns"] == [
        {"key": "name", "label": "Name"},
        {"key": "status", "label": "Status"},
    ]
    assert app["views"][0]["filter"] is True
    assert app_definition({"name": "x"}) is None


def test_bad_app_sections_list_every_problem() -> None:
    with pytest.raises(ContractError) as caught:
        normalize_app(
            {
                "refresh_seconds": 0,
                "inputs": [
                    {"name": "pick", "type": "select"},
                    {"name": "go", "type": "button", "target": "missing"},
                    {"name": "bad-name", "type": "slider"},
                ],
                "views": [],
                "colour": "red",
            }
        )
    text = str(caught.value)
    for fragment in (
        "unknown keys colour",
        "refresh_seconds",
        "a select needs",
        "target 'missing'",
        "type must be one of",
        "at least one view",
    ):
        assert fragment in text


def test_store_validates_inputs_and_buttons(connection) -> None:
    store = AppStore(connection)
    app_id = store.start(7, "monitor", "k8s.monitor", normalize_app(APP))

    assert store.inputs(app_id) == {"filter": "", "namespace": "sit", "follow": False}
    store.set_inputs(app_id, {"filter": "pay", "namespace": "uat"})
    assert store.inputs(app_id)["filter"] == "pay"
    for bad in ({"namespace": "prod"}, {"follow": "yes"}, {"nope": 1}, {"restart": True}):
        with pytest.raises(AppError):
            store.set_inputs(app_id, bad)

    store.push_event(app_id, "restart", {"selection": ["pod-a"]}, "alice")
    with pytest.raises(AppError):
        store.push_event(app_id, "filter", {}, "alice")
    assert [event["payload"]["selection"] for event in store.take_events(app_id)] == [["pod-a"]]
    assert store.take_events(app_id) == []

    store.request_stop(app_id)
    assert store.state(app_id) == "stopping"
    with pytest.raises(AppError):
        store.set_inputs(app_id, {"filter": "x"})


def test_live_app_loops_until_stopped(connection, monkeypatch) -> None:
    monkeypatch.setenv(RUN_MODE_ENV, "interactive")
    slept: list = []
    app = PluginApp(_context(connection), normalize_app(APP), "k8s.monitor", sleep=slept.append)
    store = AppStore(connection)

    assert app.running and app.interactive
    [page] = store.list([7])
    assert page["step"] == "monitor" and page["state"] == "running"

    app.table("pods", [{"name": "pod-a", "status": "Running"}])
    app.stats("summary", {"Running": 1})
    app.log("events", "a", "b", "c", "d")
    views = store.list([7])[0]["views"]
    assert views["pods"]["rows"] == [{"name": "pod-a", "status": "Running"}]
    assert views["summary"]["items"] == [{"label": "Running", "value": 1}]
    assert views["events"]["lines"] == ["b", "c", "d"]  # max_lines

    store.set_inputs(page["id"], {"filter": "pay"})
    assert app.input("filter") == "pay"
    store.push_event(page["id"], "restart", {"selection": ["pod-a"]}, "alice")
    [press] = app.events("restart")
    assert press.selection == ["pod-a"] and press.user == "alice"

    app.wait()
    assert sum(slept) == pytest.approx(1.0)  # refresh_seconds, nothing changed
    store.request_stop(page["id"])
    assert app.running is False
    app.close()
    assert store.state(page["id"]) == "finished"


def test_automated_runs_make_one_pass(connection, monkeypatch) -> None:
    monkeypatch.setenv(RUN_MODE_ENV, "automated")
    app = PluginApp(_context(connection), normalize_app(APP), "k8s.monitor", sleep=lambda _: None)

    passes = 0
    while app.running:
        passes += 1
        assert app.input("namespace") == "sit"  # defaults
        assert app.events() == []
        app.table("pods", [{"name": "pod-a", "status": "Running"}])
        app.wait()
    assert passes == 1
    [page] = AppStore(connection).list([7])
    assert page["state"] == "finished" and page["views"]["pods"]["total"] == 1


def test_without_a_run_the_app_runs_once_and_keeps_nothing(connection) -> None:
    app = PluginApp(_context(connection, job_id=None), normalize_app(APP), "k8s.monitor")
    assert [app.running, app.running] == [True, False]
    app.table("pods", [])
    assert AppStore(connection).list([7]) == []


def test_misuse_is_reported(connection) -> None:
    plain = PluginApp(_context(connection), None, "builtin.hello")
    with pytest.raises(PluginAppError, match="not an app"):
        _ = plain.running
    app = PluginApp(_context(connection), normalize_app(APP), "k8s.monitor")
    with pytest.raises(PluginAppError, match="not declared"):
        app.table("nodes", [])
    with pytest.raises(PluginAppError, match="is a stats"):
        app.table("summary", [])


# ----------------------------------------------------------------------
# Charts and row tones
# ----------------------------------------------------------------------

CHART_APP = {
    "views": [
        {"name": "pods", "type": "table", "row_key": "name"},
        {
            "name": "usage",
            "type": "chart",
            "tab_of": "pods",
            "series_label": "pod",
            "max_points": 2,
            "metrics": ["cpu", {"key": "memory", "label": "Memory (MiB)"}],
        },
    ],
}


def test_a_chart_view_is_normalized() -> None:
    usage = normalize_app(CHART_APP)["views"][1]

    assert usage["tab_of"] == "pods" and usage["series_label"] == "pod"
    assert usage["max_points"] == 2
    assert usage["metrics"] == [
        {"key": "cpu", "label": "Cpu"},
        {"key": "memory", "label": "Memory (MiB)"},
    ]


@pytest.mark.parametrize(
    ("view", "problem"),
    [
        ({"name": "usage", "type": "chart"}, "a chart needs metrics"),
        ({"name": "usage", "type": "chart", "metrics": ["cpu"], "tab_of": "nope"}, "not another"),
        ({"name": "usage", "type": "chart", "metrics": ["cpu"], "tab_of": "usage"}, "not another"),
    ],
)
def test_bad_charts_are_refused(view, problem) -> None:
    with pytest.raises(ContractError, match=problem):
        normalize_app({"views": [{"name": "pods", "type": "table"}, view]})


def test_tabs_are_one_level_deep() -> None:
    views = [
        {"name": "pods", "type": "table"},
        {"name": "usage", "type": "chart", "metrics": ["cpu"], "tab_of": "pods"},
        {"name": "more", "type": "chart", "metrics": ["cpu"], "tab_of": "usage"},
    ]
    with pytest.raises(ContractError, match="itself a tab"):
        normalize_app({"views": views})


def test_chart_keeps_the_newest_samples_and_clears_on_request(connection, monkeypatch) -> None:
    monkeypatch.setenv(RUN_MODE_ENV, "automated")
    app = PluginApp(_context(connection), normalize_app(CHART_APP), "k8s.monitor")

    app.chart("usage", {"web-1": {"cpu": 1, "memory": 10}})
    app.chart("usage", {"web-1": {"cpu": 2, "memory": None}})
    app.chart("usage", {"web-1": {"cpu": 3.456, "memory": True, "other": 9}})

    [page] = AppStore(connection).list([7])
    usage = page["views"]["usage"]
    assert usage["series_label"] == "pod"
    # max_points 2; non-numbers are gaps; undeclared metrics are dropped.
    assert [sample["values"] for sample in usage["samples"]] == [
        {"web-1": [2.0, None]},
        {"web-1": [3.46, None]},
    ]

    app.chart("usage", {"api-1": {"cpu": 5}}, clear=True)
    [page] = AppStore(connection).list([7])
    assert [sample["values"] for sample in page["views"]["usage"]["samples"]] == [
        {"api-1": [5.0, None]}
    ]


def test_table_rows_carry_tones_but_not_as_columns(connection, monkeypatch) -> None:
    monkeypatch.setenv(RUN_MODE_ENV, "automated")
    app = PluginApp(_context(connection), normalize_app(CHART_APP), "k8s.monitor")

    app.table("pods", [{"name": "web-1", "_tone": "success", "_tone_column": "name"}])

    [page] = AppStore(connection).list([7])
    assert page["views"]["pods"]["columns"] == [{"key": "name", "label": "Name"}]
    assert page["views"]["pods"]["rows"][0]["_tone"] == "success"
    with pytest.raises(PluginAppError, match="_tone must be one of"):
        app.table("pods", [{"name": "web-1", "_tone": "red"}])
