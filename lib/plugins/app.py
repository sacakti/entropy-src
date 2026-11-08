"""
App plugins: a live page on the run screen.

A plugin.json may declare an "app": inputs the user sets while the plugin
runs, and views the plugin keeps up to date. Entropy draws the page; the
plugin runs a loop with `self.app`:

    while self.app.running:
        pods = self._pods(self.app.input("namespace"))
        wanted = self.app.input("filter", "")
        self.app.table("pods", [pod for pod in pods if wanted in pod["name"]])
        self.app.stats("summary", {"Pods": len(pods)})
        self.app.chart("usage", {pod["name"]: {"cpu": pod["cpu"]} for pod in pods})
        for press in self.app.events("restart"):
            self._restart(press.selection)
        self.app.wait()

Interactive runs loop until the user stops the app. Automated runs (and
`ent`) make one pass: `running` is True once, so the plugin still produces
its views and outputs.
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Optional, Sequence

from lib.plugins.contract import NAME, ContractError

if TYPE_CHECKING:
    from lib.plugins.context import PluginContext

INPUT_TYPES = ("text", "number", "select", "toggle", "button")
VIEW_TYPES = ("table", "stats", "log", "keyvalue", "text", "chart")
INPUT_KEYS = {"name", "type", "label", "description", "placeholder", "default", "choices", "target"}
VIEW_KEYS = {
    "name",
    "type",
    "title",
    "description",
    "columns",
    "row_key",
    "selectable",
    "filter",
    "max_lines",
    "metrics",
    "series_label",
    "max_points",
    "tab_of",
}
APP_KEYS = {"title", "description", "refresh_seconds", "inputs", "views"}
DEFAULT_REFRESH = 2.0
MAX_TABLE_ROWS = 5000
DEFAULT_LOG_LINES = 500
DEFAULT_CHART_POINTS = 120
MAX_CHART_POINTS = 1000
MAX_CHART_SERIES = 200
# A table row may carry these keys: the row (or one cell) is coloured, never shown as a column.
ROW_TONE = "_tone"
ROW_TONE_COLUMN = "_tone_column"
ROW_TONES = ("success", "warning", "danger", "info")


# ----------------------------------------------------------------------
# Manifest
# ----------------------------------------------------------------------


def normalize_app(data: Any) -> Dict[str, Any]:
    """A well-formed "app" section of plugin.json; ContractError lists what is wrong."""

    problems: List[str] = []
    if not isinstance(data, dict):
        raise ContractError(['"app" must be an object with "inputs" and "views"'])
    unknown = set(data) - APP_KEYS
    if unknown:
        problems.append(f'"app": unknown keys {", ".join(sorted(unknown))}')

    refresh = data.get("refresh_seconds", DEFAULT_REFRESH)
    if (
        isinstance(refresh, bool)
        or not isinstance(refresh, (int, float))
        or not 0.5 <= refresh <= 300
    ):
        problems.append('"app.refresh_seconds" must be a number from 0.5 to 300')
        refresh = DEFAULT_REFRESH

    names: set = set()
    inputs: List[Dict[str, Any]] = []
    raw_inputs = data.get("inputs", [])
    if not isinstance(raw_inputs, list):
        problems.append('"app.inputs" must be a list')
        raw_inputs = []
    for index, item in enumerate(raw_inputs):
        entry = _named(item, f"app input {index + 1}", INPUT_KEYS, INPUT_TYPES, names, problems)
        if entry is None:
            continue
        label = entry["label"]
        if entry["type"] == "select":
            choices = item.get("choices")
            if (
                not isinstance(choices, list)
                or not choices
                or not all(isinstance(choice, str) for choice in choices)
            ):
                problems.append(
                    f"app input '{entry['name']}': a select needs a list of text choices"
                )
                choices = []
            entry["choices"] = choices
        if "default" in item:
            entry["default"] = item["default"]
        elif entry["type"] == "toggle":
            entry["default"] = False
        for extra in ("placeholder", "target"):
            if isinstance(item.get(extra), str):
                entry[extra] = item[extra]
        entry["label"] = label
        inputs.append(entry)

    views: List[Dict[str, Any]] = []
    raw_views = data.get("views")
    if not isinstance(raw_views, list) or not raw_views:
        problems.append('"app.views" must list at least one view')
        raw_views = []
    view_names: set = set()
    for index, item in enumerate(raw_views):
        entry = _named(item, f"app view {index + 1}", VIEW_KEYS, VIEW_TYPES, view_names, problems)
        if entry is None:
            continue
        if isinstance(item.get("title"), str):
            entry["title"] = item["title"]
        if entry["type"] == "table":
            columns = item.get("columns")
            if columns is not None:
                parsed = _columns(columns)
                if parsed is None:
                    problems.append(
                        f"app view '{entry['name']}': "
                        "columns must be names or {key, label} objects"
                    )
                else:
                    entry["columns"] = parsed
            if isinstance(item.get("row_key"), str):
                entry["row_key"] = item["row_key"]
            entry["selectable"] = bool(item.get("selectable", False))
            entry["filter"] = bool(item.get("filter", True))
        if entry["type"] == "log":
            lines = item.get("max_lines", DEFAULT_LOG_LINES)
            entry["max_lines"] = (
                lines if isinstance(lines, int) and 1 <= lines <= 5000 else DEFAULT_LOG_LINES
            )
        if entry["type"] == "chart":
            metrics = _columns(item.get("metrics"))
            if not metrics:
                problems.append(
                    f"app view '{entry['name']}': a chart needs metrics, "
                    "as names or {key, label} objects"
                )
                metrics = []
            entry["metrics"] = metrics
            label = item.get("series_label", "series")
            entry["series_label"] = label if isinstance(label, str) and label else "series"
            points = item.get("max_points", DEFAULT_CHART_POINTS)
            entry["max_points"] = (
                points
                if isinstance(points, int)
                and not isinstance(points, bool)
                and 2 <= points <= MAX_CHART_POINTS
                else DEFAULT_CHART_POINTS
            )
        if isinstance(item.get("tab_of"), str):
            entry["tab_of"] = item["tab_of"]
        views.append(entry)

    # A view may show as a tab of another (a table's graph); one level only.
    by_name = {entry["name"]: entry for entry in views}
    for entry in views:
        host = entry.get("tab_of")
        if host is None:
            continue
        if host == entry["name"] or host not in by_name:
            problems.append(f"app view '{entry['name']}': tab_of '{host}' is not another view")
        elif "tab_of" in by_name[host]:
            problems.append(
                f"app view '{entry['name']}': tab_of '{host}' is itself a tab of another view"
            )

    for entry in inputs:
        target = entry.get("target")
        if target is not None and target not in view_names:
            problems.append(f"app input '{entry['name']}': target '{target}' is not a view")

    if problems:
        raise ContractError(problems)
    result: Dict[str, Any] = {"refresh_seconds": float(refresh), "inputs": inputs, "views": views}
    for key in ("title", "description"):
        if isinstance(data.get(key), str):
            result[key] = data[key]
    return result


def app_definition(manifest: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """The plugin's app, or None when it is not an app plugin."""

    if "app" not in manifest or manifest["app"] in (None, False):
        return None
    return normalize_app(manifest["app"])


def _named(
    item: Any, where: str, keys: set, types: Sequence[str], seen: set, problems: List[str]
) -> Optional[Dict[str, Any]]:
    if not isinstance(item, dict) or not isinstance(item.get("name"), str):
        problems.append(f"{where} needs a name")
        return None
    name = item["name"]
    if not NAME.match(name):
        problems.append(f"{where} '{name}': the name must be a Python-style identifier")
    if name in seen:
        problems.append(f"{where} '{name}' is declared twice")
    seen.add(name)
    unknown = set(item) - keys
    if unknown:
        problems.append(f"{where} '{name}': unknown keys {', '.join(sorted(unknown))}")
    kind = item.get("type")
    if kind not in types:
        problems.append(f"{where} '{name}': type must be one of {', '.join(types)}")
        return None
    label = item.get("label") or item.get("title") or name.replace("_", " ").capitalize()
    entry: Dict[str, Any] = {"name": name, "type": kind, "label": str(label)}
    if isinstance(item.get("description"), str):
        entry["description"] = item["description"]
    return entry


def _columns(columns: Any) -> Optional[List[Dict[str, str]]]:
    if not isinstance(columns, list):
        return None
    parsed = []
    for column in columns:
        if isinstance(column, str):
            parsed.append({"key": column, "label": column.replace("_", " ").capitalize()})
        elif isinstance(column, dict) and isinstance(column.get("key"), str):
            parsed.append(
                {"key": column["key"], "label": str(column.get("label") or column["key"])}
            )
        else:
            return None
    return parsed


# ----------------------------------------------------------------------
# SDK
# ----------------------------------------------------------------------


@dataclass
class AppEvent:
    """A button press: the button, who pressed it, and the rows selected then."""

    name: str
    user: Optional[str] = None
    selection: List[Any] = field(default_factory=list)
    values: Dict[str, Any] = field(default_factory=dict)


class PluginAppError(RuntimeError):
    """Misuse of `self.app`: the plugin is not an app, or a view is not declared."""


class PluginApp:
    """
    The live page of an app plugin (`self.app`).

    Read inputs with `input()`/`inputs`, publish views with `table()`,
    `stats()`, `log()`, `keyvalue()`, `text()` and `chart()`, handle buttons
    with `events()`, and pace the loop with `wait()`.
    """

    def __init__(
        self,
        context: PluginContext,
        definition: Optional[Dict[str, Any]],
        plugin: str,
        *,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._context = context
        self._definition = definition
        self._plugin = plugin
        self._sleep = sleep
        self._store: Any = None
        self._app_id: Optional[int] = None
        self._views: Dict[str, Any] = {}
        self._passes = 0
        self._stopped = False
        self._live = False
        self._opened = False

    # -- lifecycle ------------------------------------------------------

    @property
    def definition(self) -> Dict[str, Any]:
        if self._definition is None:
            raise PluginAppError(
                f"Plugin '{self._plugin}' is not an app: declare \"app\" in its plugin.json."
            )
        return self._definition

    @property
    def interactive(self) -> bool:
        """True when the page is live and the loop runs until the user stops it."""

        self._open()
        return self._live

    @property
    def running(self) -> bool:
        """
        Whether the loop should go on. Live pages run until the user stops
        them; otherwise the first check is True and later ones False.
        """

        self._open()
        self._passes += 1
        if self._stopped:
            return False
        if not self._live:
            return self._passes == 1
        if self._store.state(self._app_id) != "running":
            self._stopped = True
            return False
        return True

    def stop(self) -> None:
        """End the loop from the plugin (the next `running` is False)."""

        self._stopped = True

    def close(self) -> None:
        """Mark the page finished; the runner calls this when the plugin ends."""

        if self._live and self._app_id is not None:
            self._store.finish(self._app_id)

    def wait(self, seconds: Optional[float] = None) -> None:
        """
        Pause between loops (the app's refresh_seconds by default); a
        change on the page (input, button, stop) ends the pause early.
        """

        self._open()
        if not self._live:
            return
        remaining = self.definition["refresh_seconds"] if seconds is None else max(0.0, seconds)
        marker = self._store.marker(self._app_id)
        while remaining > 0:
            step = min(0.25, remaining)
            self._sleep(step)
            remaining -= step
            if self._store.marker(self._app_id) != marker:
                return

    # -- inputs ---------------------------------------------------------

    @property
    def inputs(self) -> Dict[str, Any]:
        """Current values of the inputs (defaults until the user changes them)."""

        self._open()
        defaults = {
            item["name"]: item.get("default")
            for item in self.definition["inputs"]
            if item["type"] != "button"
        }
        if not self._live:
            return defaults
        return {**defaults, **self._store.inputs(self._app_id)}

    def input(self, name: str, default: Any = None) -> Any:
        value = self.inputs.get(name)
        return default if value is None or value == "" else value

    def events(self, name: Optional[str] = None) -> List[AppEvent]:
        """Button presses since the last call (of one button, or all)."""

        self._open()
        if name is not None:
            self._input(name, "button")
        if not self._live:
            return []
        return [
            AppEvent(
                name=item["name"],
                user=item.get("user"),
                selection=list(item["payload"].get("selection") or []),
                values=dict(item["payload"].get("values") or {}),
            )
            for item in self._store.take_events(self._app_id, name)
        ]

    # -- views ----------------------------------------------------------

    def table(
        self, name: str, rows: Sequence[Dict[str, Any]], columns: Optional[Sequence[Any]] = None
    ) -> None:
        """
        Rows (dicts) for a table view; columns default to the declared or first row's keys.

        A row may set `_tone` (success, warning, danger or info) to colour it, and
        `_tone_column` to colour only that cell instead of the whole row.
        """

        view = self._view(name, "table")
        rows = [dict(row) for row in list(rows)[:MAX_TABLE_ROWS]]
        for row in rows:
            tone = row.get(ROW_TONE)
            if tone is not None and tone not in ROW_TONES:
                raise PluginAppError(
                    f"Table '{name}': {ROW_TONE} must be one of {', '.join(ROW_TONES)}."
                )
        if columns is not None:
            parsed = _columns(list(columns))
            if parsed is None:
                raise PluginAppError(
                    f"Table '{name}': columns must be names or {{key, label}} dicts."
                )
        else:
            parsed = view.get("columns") or [
                {"key": key, "label": key.replace("_", " ").capitalize()}
                for key in (rows[0] if rows else {})
                if not key.startswith("_")
            ]
        self._publish(name, {"columns": parsed, "rows": rows, "total": len(rows)})

    def stats(self, name: str, values: Dict[str, Any]) -> None:
        """Headline numbers, e.g. {"Running": 12, "Failing": 1}."""

        self._view(name, "stats")
        self._publish(
            name, {"items": [{"label": str(key), "value": value} for key, value in values.items()]}
        )

    def keyvalue(self, name: str, values: Dict[str, Any]) -> None:
        self._view(name, "keyvalue")
        self._publish(
            name, {"items": [{"key": str(key), "value": value} for key, value in values.items()]}
        )

    def text(self, name: str, text: str) -> None:
        self._view(name, "text")
        self._publish(name, {"text": str(text)})

    def log(self, name: str, *lines: str, clear: bool = False) -> None:
        """Append lines to a log view (it keeps the newest max_lines)."""

        view = self._view(name, "log")
        kept = [] if clear else list(self._views.get(name, {}).get("lines", []))
        kept.extend(str(line) for line in lines)
        self._publish(name, {"lines": kept[-view.get("max_lines", DEFAULT_LOG_LINES) :]})

    # -- internals ------------------------------------------------------

    def _open(self) -> None:
        if self._opened:
            return
        definition = self.definition
        self._opened = True
        runtime = self._context._runtime
        job_id = getattr(runtime, "job_id", None)
        from lib.runs.prompts import RUN_MODE_ENV

        self._live = job_id is not None and os.environ.get(RUN_MODE_ENV) == "interactive"
        if job_id is None:
            self._store = _NoStore()
            return
        from lib.runs.apps import AppStore

        node = runtime.node
        manager: Any = runtime._entropy.database_manager
        self._store = AppStore(manager.connection)
        self._app_id = self._store.start(
            int(job_id), getattr(node, "name", None) or self._plugin, self._plugin, definition
        )
        if not self._live:
            # Automated runs still show their one pass; the page is not live.
            self._store.finish(self._app_id)

    def _input(self, name: str, kind: str) -> Dict[str, Any]:
        item: Dict[str, Any]
        for item in self.definition["inputs"]:
            if item["name"] == name:
                if item["type"] != kind:
                    raise PluginAppError(f"App input '{name}' is a {item['type']}, not a {kind}.")
                return item
        raise PluginAppError(f"App input '{name}' is not declared in plugin.json.")

    def _view(self, name: str, kind: str) -> Dict[str, Any]:
        self._open()
        item: Dict[str, Any]
        for item in self.definition["views"]:
            if item["name"] == name:
                if item["type"] != kind:
                    raise PluginAppError(f"App view '{name}' is a {item['type']}, not a {kind}.")
                return item
        raise PluginAppError(f"App view '{name}' is not declared in plugin.json.")

    def chart(
        self,
        name: str,
        values: Dict[str, Dict[str, Any]],
        *,
        clear: bool = False,
        at: Optional[datetime] = None,
    ) -> None:
        """
        Add one sample to a chart view: {series: {metric: number}}, e.g.
        {"web-1": {"cpu": 12.5, "memory": 300}}. The chart keeps the newest
        max_points samples of at most MAX_CHART_SERIES series; `clear` starts
        again (say, another namespace). A value that is not a number is a gap.

        Published as {"metrics", "series_label", "samples": [{"at", "values":
        {series: [value per metric, in declared order]}}]}.
        """

        view = self._view(name, "chart")
        metrics = [item["key"] for item in view["metrics"]]
        # Compact: one list per series, in the order of the declared metrics.
        sample: Dict[str, List[Optional[float]]] = {}
        for series, numbers in list(values.items())[:MAX_CHART_SERIES]:
            sample[str(series)] = [_number(numbers.get(metric)) for metric in metrics]
        moment = (at or datetime.now(timezone.utc)).astimezone(timezone.utc)
        kept_samples = [] if clear else list(self._views.get(name, {}).get("samples", []))
        kept_samples.append({"at": moment.isoformat(timespec="seconds"), "values": sample})
        self._publish(
            name,
            {
                "metrics": view["metrics"],
                "series_label": view["series_label"],
                "samples": kept_samples[-view["max_points"] :],
            },
        )

    def _publish(self, name: str, data: Dict[str, Any]) -> None:
        self._views[name] = data
        if self._app_id is not None:
            self._store.set_views(self._app_id, self._views)


def _number(value: Any) -> Optional[float]:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return round(float(value), 2)


class _NoStore:
    """Without a run (e.g. `ent plugin run`) there is no page to keep."""

    def state(self, app_id: Any) -> str:
        return "finished"
