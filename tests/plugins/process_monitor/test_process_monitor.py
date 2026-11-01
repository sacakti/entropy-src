"""The process monitor app plugin, with the shell mocked."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

from process_monitor.plugin import ProcessMonitorPlugin

from lib.database.connection import DatabaseConnection
from lib.plugins.app import PluginApp, app_definition
from lib.plugins.contract import read_manifest
from lib.runs.apps import AppStore
from lib.runs.prompts import RUN_MODE_ENV

PLUGIN_DIR = (
    Path(__file__).resolve().parents[3] / "resources" / "plugins" / "builtin" / "process_monitor"
)
PS = (
    "  101 alice  12.5  1.0 python3\n"
    "  202 root    0.5  3.0 nginx\n"
    "  303 alice   1.0  0.5 bash\n"
    "garbage line\n"
)


def _plugin(tmp_path: Path, monkeypatch, mode: str) -> tuple:
    monkeypatch.setenv(RUN_MODE_ENV, mode)
    connection = DatabaseConnection(tmp_path / "entropy.db")
    runtime = SimpleNamespace(
        job_id=5,
        node=SimpleNamespace(name="Process monitor"),
        _entropy=SimpleNamespace(database_manager=SimpleNamespace(connection=connection)),
    )
    context = MagicMock()
    context._runtime = runtime
    context.outputs = {}
    context.arguments.integer.return_value = 200
    context.environment.getenv.return_value = "alice"
    context.shell.run.side_effect = lambda command: SimpleNamespace(
        success=True,
        exit_code=0,
        stderr="",
        stdout=PS if "-eo" in command else "  101 python3 /srv/app.py --serve\n",
    )
    plugin = ProcessMonitorPlugin(context)
    store = AppStore(connection)
    stops = {"after": 2}

    def sleep(_: float) -> None:
        # Stop the live page after a couple of refreshes.
        stops["after"] -= 1
        if stops["after"] <= 0:
            for page in store.list([5]):
                if page["state"] == "running":
                    store.request_stop(page["id"])

    plugin._entropy_app_session = PluginApp(
        context, app_definition(read_manifest(PLUGIN_DIR)), "builtin.process_monitor", sleep=sleep
    )
    return plugin, store, context


def test_automated_run_publishes_one_snapshot(tmp_path, monkeypatch) -> None:
    plugin, store, _ = _plugin(tmp_path, monkeypatch, "automated")

    result = plugin.execute()

    assert result.success and result.outputs["process_count"] == 3
    [page] = store.list([5])
    rows = page["views"]["processes"]["rows"]
    assert [row["pid"] for row in rows] == [101, 303, 202]  # CPU, highest first
    assert page["views"]["summary"]["items"][0] == {"label": "Processes", "value": 3}
    assert page["state"] == "finished"


def test_live_run_follows_inputs_and_buttons_until_stopped(tmp_path, monkeypatch) -> None:
    plugin, store, _ = _plugin(tmp_path, monkeypatch, "interactive")
    # Inputs and a button press are waiting when the page opens.
    app = plugin.app
    assert app.running  # opens the page
    page_id = store.list([5])[0]["id"]
    store.set_inputs(page_id, {"filter": "ALICE", "sort": "Name", "only_mine": True})
    store.push_event(page_id, "inspect", {"selection": [101, "x"]}, "bob")
    app._passes = 0  # let execute() start the loop afresh

    result = plugin.execute()

    assert result.success and result.outputs["process_count"] == 2
    [page] = store.list([5])
    assert [row["command"] for row in page["views"]["processes"]["rows"]] == ["bash", "python3"]
    log = page["views"]["activity"]["lines"]
    assert "Inspect requested by bob:" in log
    assert "101 python3 /srv/app.py --serve" in log
    assert log[-1] == "Monitoring stopped."
