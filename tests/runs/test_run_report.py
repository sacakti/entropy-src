"""Plugin runs can be run again, and any run can be downloaded as the page shows it."""

from __future__ import annotations

import re
import zlib
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from core.web.routes import runs as routes
from lib.runs.report import (
    build_report,
    collect_events,
    model,
    read_console,
    render_html,
    render_pdf,
    resolve_zone,
)
from lib.runs.report.icons import ICONS
from lib.runs.report.pdf_report import Canvas
from lib.runs.service import RunService

NOW = datetime(2026, 11, 3, 12, 0, tzinfo=timezone.utc)


def _run(**extra):
    return {
        "id": 197,
        "target": "sqlplus.analyse",
        "workflow": "plugin.sqlplus.analyse",
        "kind": "plugin",
        "state": "failed",
        "execution_id": "plugin.sqlplus.analyse_a8039191",
        "username": "aravinthan",
        "full_name": "Aravinthan Selvaraj",
        "trigger": "manual",
        "node": "local",
        "started_at": "2026-11-03T17:30:47Z",
        "created_at": "2026-11-03T17:30:47Z",
        "finished_at": "2026-11-03T17:30:47.034Z",
        "exit_code": 1,
        **extra,
    }


def _event(number, kind="message", message="", level="20", **extra):
    return {
        "id": number,
        "type": kind,
        "level": level,
        "message": message,
        "node_type": extra.pop("node_type", "activity"),
        "node_name": extra.pop("node_name", None),
        "payload": extra.pop("payload", None),
        "created_at": "2026-11-03T17:30:47Z",
        **extra,
    }


def _started(number=1, name="sqlplus.analyse"):
    return _event(
        number,
        "step.started",
        node_type="step",
        node_name=name,
        payload={"metadata": {"plugin": "sqlplus.analyse"}},
    )


def _failed(number=3, name="sqlplus.analyse"):
    return _event(
        number,
        "step.failed",
        node_type="step",
        node_name=name,
        payload={"duration_ms": 26, "metadata": {"exception": "'path' must be a string."}},
    )


PLAN = [{"name": "sqlplus.analyse", "plugin": "sqlplus.analyse", "enabled": True}]
STEPS = [
    {"id": "s1", "name": "sqlplus.analyse", "status": "failed", "duration_ms": 26},
]
EVENTS = [
    _started(),
    _event(2, message="Starting SQL script analysis."),
    _failed(),
    _event(
        4,
        "execution.failed",
        node_type="workflow",
        payload={"duration_ms": 29, "metadata": {"exception": "'path' must be a string."}},
    ),
]


def _report(run=None, plan=PLAN, steps=STEPS, events=EVENTS, **extra):
    return build_report(run or _run(), plan, steps, events, now=NOW, version="3.3.0", **extra)


def _pdf_text(pdf: bytes) -> str:
    """The text a PDF draws, from its compressed page streams."""

    drawn = []
    for stream in re.findall(rb"stream\n(.*?)\nendstream", pdf, re.S):
        for part in re.findall(r"<([0-9a-f]*)> Tj", zlib.decompress(stream).decode("ascii")):
            drawn.append(bytes.fromhex(part).decode("cp1252"))
    return "\n".join(drawn)


# ----------------------------------------------------------------------
# It shows what the page shows
# ----------------------------------------------------------------------


def test_the_header_reads_like_the_page() -> None:
    zone, name = resolve_zone("Asia/Kolkata")
    report = _report(zone=zone, zone_name=name)

    assert report["title"] == "sqlplus.analyse"
    assert report["subtitle"] == ("Run #197 · Plugin test run · plugin.sqlplus.analyse_a8039191")
    assert report["meta"] == [
        ("Executed by", "Aravinthan Selvaraj"),
        ("Trigger", "Manual"),
        ("Node", "local"),
        ("Started", "Nov 3, 2026, 11:00:47 PM"),
        ("Duration", "34 ms"),
        ("Steps", "0 / 1"),
    ]
    assert report["alert"] == {
        "kind": "danger",
        "text": "Run failed in 29 ms: 'path' must be a string.",
    }
    assert "times in Asia/Kolkata" in report["footer"]


def test_a_step_card_holds_its_lines_as_the_page_words_them() -> None:
    zone, _ = resolve_zone("Asia/Kolkata")
    [card] = _report(zone=zone)["cards"]

    assert (card["index"], card["name"], card["plugin"]) == (
        1,
        "sqlplus.analyse",
        "sqlplus.analyse",
    )
    assert (card["status"], card["label"], card["duration"]) == ("failed", "Failed", "26 ms")
    assert [(line["time"], line["text"], line["tone"]) for line in card["lines"]] == [
        ("11:00:47 PM", "Step 'sqlplus.analyse' started (sqlplus.analyse)", "meta"),
        ("11:00:47 PM", "Starting SQL script analysis.", "info"),
        (
            "11:00:47 PM",
            "Step 'sqlplus.analyse' failed in 26 ms: 'path' must be a string.",
            "error",
        ),
    ]


def test_step_results_and_artifacts_are_on_the_card() -> None:
    result = _event(
        3,
        "plugin_result",
        payload={"result": {"success": True, "outputs": {"rows": 2}}},
    )
    events = [_started(), result]
    artifacts = [
        {"name": "a.zip", "size_bytes": 2048, "step_name": "sqlplus.analyse", "available": True},
        {"name": "gone.zip", "size_bytes": 1, "step_name": "sqlplus.analyse", "available": False},
    ]

    [card] = _report(events=events, artifacts=artifacts)["cards"]

    assert '"rows": 2' in card["result"]
    assert card["lines"][-1]["text"] == 'Result: success · outputs {"rows":2}'
    assert card["artifacts"] == [
        {"name": "a.zip", "size": "2.0 KB"},
        {"name": "gone.zip", "size": "no longer available"},
    ]


@pytest.mark.parametrize(
    ("state", "recorded", "expected"),
    [
        ("completed", None, "skipped"),
        ("failed", None, "cancelled"),
        ("running", None, "pending"),
        ("running", "started", "running"),
        ("failed", "started", "failed"),
        ("cancelled", "failed", "cancelled"),
        ("completed", "completed", "completed"),
    ],
)
def test_a_card_status_follows_the_page(state, recorded, expected) -> None:
    steps = [{"name": "sqlplus.analyse", "status": recorded}] if recorded else []
    [card] = _report(_run(state=state), steps=steps, events=[])["cards"]

    assert card["status"] == expected


def test_only_finished_or_skipped_steps_count_as_done() -> None:
    plan = [{"name": name, "plugin": "p", "enabled": True} for name in "abcd"]
    steps = [{"name": "a", "status": "completed"}, {"name": "b", "status": "failed"}]

    report = _report(plan=plan, steps=steps, events=[])

    assert dict(report["meta"])["Steps"] == "1 / 4"
    assert report["progress"] == 25


def test_a_stopped_run_says_so() -> None:
    report = _report(_run(state="cancelled"), events=[])

    assert report["alert"]["kind"] == "warning"
    assert "Steps after the interrupted one did not run." in report["alert"]["text"]


def test_a_running_run_counts_its_time_up_to_now() -> None:
    run = _run(state="running", started_at="2026-11-03T11:59:00Z", finished_at=None)

    assert dict(_report(run, events=[])["meta"])["Duration"] == "1m 0s"


def test_what_a_run_was_started_with_lists_input_names_only() -> None:
    options = {
        "nodes": ["local", "n2"],
        "tags": ["db"],
        "selected": ["a"],
        "skipped": ["b"],
        "segments": [{"node": "local"}, {"node": "n2"}],
        "variables": ["password"],
        "steps": [{"name": "b", "skip_reason": "not selected"}],
    }

    rows = dict(_report(_run(options=options))["options"])

    assert rows["Tags"] == ["db"] and rows["Steps"] == ["a"]
    assert rows["Skipped"] == ["b (deselected)"]
    assert rows["Nodes"] == ["local → n2"]
    assert rows["Inputs"] == ["password"]


def test_the_live_log_names_steps_and_console_output_is_kept() -> None:
    report = _report(console="\x1b[31mboom\x1b[0m\n")

    assert report["log"][0]["step"] == "sqlplus.analyse"
    assert report["log"][1]["step"] == ""
    assert report["console"] == "\x1b[31mboom\x1b[0m\n"


def test_debug_messages_only_appear_for_a_debug_run() -> None:
    store = _Store([_event(1, message="detail", level="10"), _event(2, message="kept")])

    assert [item["id"] for item in collect_events(store, 1, _run())[0]] == [2]
    assert [item["id"] for item in collect_events(store, 1, _run(debug=True))[0]] == [1, 2]


class _Store:
    def __init__(self, items) -> None:
        self.items = items

    def job_ids(self, job_id):
        return [job_id]

    def events(self, job_ids, after, limit, archived=False):
        return [item for item in self.items if item["id"] > (after or 0)][:limit]


def test_a_long_run_keeps_its_end_and_every_step_event(monkeypatch) -> None:
    monkeypatch.setattr(model, "MAX_EVENTS", 3)
    monkeypatch.setattr(model, "_PAGE_OF_EVENTS", 4)
    items = [_started(1)] + [_event(n, message=str(n)) for n in range(2, 12)]
    items.append(_failed(12))

    events, omitted = collect_events(_Store(items), 1, _run())

    assert omitted == 7
    assert [item["id"] for item in events] == [1, 9, 10, 11, 12]


def test_the_console_is_read_to_its_end_and_keeps_its_tail(monkeypatch) -> None:
    monkeypatch.setattr(model, "MAX_CONSOLE_CHARS", 5)
    parts = [
        {"offset": 4, "text": "abcd"},
        {"offset": 8, "text": "efgh"},
        {"offset": 8, "text": ""},
    ]
    service = SimpleNamespace(log=lambda job, offset: parts.pop(0))

    assert read_console(service, 1, _run()) == ("defgh", True)
    assert read_console(service, 1, _run(archived=True)) == ("", False)


def test_an_app_page_is_shown_as_last_published() -> None:
    app = {
        "step": "metrics",
        "state": "finished",
        "definition": {
            "title": "Pods",
            "inputs": [
                {"name": "ns", "type": "text", "label": "Namespace"},
                {"name": "go", "type": "button", "label": "Go"},
            ],
            "views": [
                {"name": "t", "type": "table", "label": "Table"},
                {"name": "s", "type": "stats", "label": "Stats"},
            ],
        },
        "inputs": {"ns": "prod"},
        "views": {
            "t": {
                "columns": [{"key": "pod", "label": "Pod"}],
                "rows": [{"pod": "a-1"}],
                "total": 3,
            },
            "s": {"items": [{"label": "CPU", "value": 12}]},
        },
    }

    [shown] = _report(apps=[app])["apps"]

    assert shown["title"] == "Pods" and shown["inputs"] == [("Namespace", "prod")]
    assert shown["views"][0]["rows"] == [["a-1"]] and shown["views"][0]["total"] == 3
    assert shown["views"][1]["items"] == [("CPU", "12")]


# ----------------------------------------------------------------------
# Look and zone
# ----------------------------------------------------------------------


@pytest.mark.parametrize("name", ["", None, "Not/AZone", "../../etc/passwd", "a" * 64])
def test_an_unknown_zone_falls_back_to_utc(name) -> None:
    assert resolve_zone(name) == (timezone.utc, "UTC")


def test_the_report_uses_the_persons_theme_and_accent() -> None:
    colors = _report(theme="light", accent="#3366ff")["colors"]

    assert colors["surface"] == "#ffffff" and colors["accent"] == "#3366ff"
    assert colors["accent_text"] == "#ffffff"


def test_the_default_accent_is_not_forced_on_the_light_theme() -> None:
    assert _report(theme="light", accent="#d7ff63")["colors"]["accent"] == "#658a12"
    assert _report(theme="dark", accent="#d7ff63")["colors"]["accent"] == "#d7ff63"
    assert _report(theme="dark", accent="red;}")["colors"]["accent"] == "#d7ff63"


# ----------------------------------------------------------------------
# The diagram
# ----------------------------------------------------------------------


def _diagram_report(count=3, **extra):
    plan = [
        {"name": f"step{n}", "plugin": "p", "enabled": True, "node": "local", **extra}
        for n in range(count)
    ]
    return _report(
        _run(state="running"),
        plan=plan,
        steps=[{"name": "step0", "status": "completed"}],
        events=[],
    )


def test_the_diagram_places_every_step_within_its_canvas() -> None:
    layout = model.layout_diagram(_diagram_report(9), 1000)

    assert len(layout["bubbles"]) == 9 and len(layout["sequence"]) == 8
    for bubble in layout["bubbles"]:
        assert 0 <= bubble["x"] <= 1000 - model.BUBBLE_W
        assert 0 <= bubble["y"] <= layout["height"] - model.BUBBLE_H
    assert layout["bubbles"][0]["status"] == "completed"
    assert layout["bubbles"][1]["status"] == "pending"


def test_a_single_step_diagram_is_centred_and_has_no_arrows() -> None:
    layout = model.layout_diagram(_report(), 1000)

    assert len(layout["bubbles"]) == 1 and layout["sequence"] == []


def test_output_dependencies_are_drawn_and_unknown_ones_ignored() -> None:
    plan = [
        {"name": "a", "plugin": "p", "enabled": True},
        {
            "name": "b",
            "plugin": "p",
            "enabled": True,
            "depends_on": [
                {"step": "a", "output": "path"},
                {"step": "gone", "output": "x"},
            ],
        },
    ]

    layout = model.layout_diagram(_report(plan=plan, steps=[], events=[]), 1000)

    assert [item["label"] for item in layout["dependencies"]] == ["outputs.path"]


# ----------------------------------------------------------------------
# HTML
# ----------------------------------------------------------------------


def test_html_escapes_everything_from_the_run() -> None:
    attack = "<script>alert(1)</script>"
    plan = [{"name": attack, "plugin": attack, "enabled": True, "tags": [attack]}]
    events = [
        _started(1, attack),
        _event(2, message=attack),
        _event(3, "render", payload={"title": attack, "lines": [attack]}),
    ]
    app = {
        "step": attack,
        "definition": {
            "title": attack,
            "views": [{"name": "v", "type": "text", "label": attack}],
        },
        "views": {"v": {"text": attack}},
    }

    page = render_html(
        _report(
            _run(target=attack, full_name=attack),
            plan=plan,
            steps=[],
            events=events,
            console=attack,
            apps=[app],
            artifacts=[{"name": attack, "step_name": attack, "available": False}],
        )
    ).decode()

    assert "<script" not in page
    assert "&lt;script&gt;" in page


def test_html_stands_alone_with_the_tabs_of_the_page() -> None:
    page = render_html(_report()).decode()

    assert page.startswith("<!DOCTYPE html>")
    assert "default-src 'none'" in page
    assert not re.search(r"(?:src|href)=", page)
    for label in ("Progress", "Diagram", "Live log", "Steps", "Console"):
        assert f"{label}</label>" in page


def test_html_leaves_out_the_page_controls() -> None:
    page = render_html(_report()).decode()

    for control in ("Run again", "Follow", "Debug messages", "Reset layout", ">Report<"):
        assert control not in page


def test_the_app_tab_only_appears_for_app_runs() -> None:
    assert "t-app" not in render_html(_report()).decode().split("<style>")[1].split("</style>")[1]
    app = {"step": "s", "definition": {"title": "Pods"}, "views": {}}
    assert 'id="t-app"' in render_html(_report(apps=[app])).decode()


# ----------------------------------------------------------------------
# PDF
# ----------------------------------------------------------------------


def test_the_pdf_cross_reference_table_points_at_its_objects() -> None:
    pdf = render_pdf(_report())

    assert pdf.startswith(b"%PDF-1.4") and pdf.endswith(b"%%EOF\n")
    start = int(re.search(rb"startxref\n(\d+)", pdf)[1])
    assert pdf[start:].startswith(b"xref")
    offsets = re.findall(rb"(\d{10}) 00000 n ", pdf[start:])
    for number, offset in enumerate(offsets, start=1):
        assert pdf[int(offset) :].startswith(f"{number} 0 obj".encode())


def test_the_pdf_shows_every_tab() -> None:
    text = _pdf_text(render_pdf(_report(console="console line")))

    for expected in (
        "sqlplus.analyse",
        "EXECUTED BY",
        "Run failed in 29 ms: 'path' must be a string.",
        "Progress",
        "Diagram",
        "Live log · Steps",
        "Live log · Console",
        "console line",
        "Starting SQL script analysis.",
    ):
        assert expected in text, expected


def test_a_long_log_flows_over_numbered_pages() -> None:
    events = [_started(), *(_event(n, message=f"line {n}") for n in range(2, 500))]
    pdf = render_pdf(_report(events=events))
    text = _pdf_text(pdf)
    pages = int(re.search(rb"/Count (\d+)", pdf)[1])

    assert pages > 1
    assert f"Page {pages} of {pages}" in text
    assert "line 2\n" in text and "line 499" in text


def test_long_lines_wrap_without_losing_text() -> None:
    text = _pdf_text(render_pdf(_report(console="~" * 700)))

    assert text.count("~") == 700


def test_characters_the_fonts_lack_do_not_break_the_pdf() -> None:
    text = _pdf_text(render_pdf(_report(console="Café 日本語 €5 (ok) \\ end")))

    assert "Café ??? €5 (ok) \\ end" in text


def test_every_icon_can_be_drawn() -> None:
    canvas = Canvas(_report()["colors"])

    for name in ICONS:
        canvas.icon(name, 0, 0, 16, "#ffffff")

    assert len(canvas.pages[0]) == len(ICONS) + 1


def test_a_card_taller_than_a_page_continues_on_the_next() -> None:
    events = [_started(), *(_event(n, message="x") for n in range(2, 300))]

    assert int(re.search(rb"/Count (\d+)", render_pdf(_report(events=events)))[1]) >= 2


# ----------------------------------------------------------------------
# Routes
# ----------------------------------------------------------------------


@pytest.fixture
def world(monkeypatch) -> SimpleNamespace:
    store = MagicMock()
    store.get.return_value = _run()
    store.job_ids.return_value = [197]
    store.events.return_value = []
    store.steps.return_value = []
    store.rerun_config.return_value = {"arguments": {"a": 1}, "node": "local"}
    denied = set()

    def require(request, user, permission, project=None):
        if permission in denied:
            raise routes.HTTPException(status_code=403, detail="Permission denied.")

    service = SimpleNamespace(store=store, log=lambda job, offset: {"offset": 0, "text": ""})
    monkeypatch.setattr(routes, "_require_permission", require)
    monkeypatch.setattr(routes, "_run_project", lambda request, job_id: 1)
    monkeypatch.setattr(routes, "_service", lambda request: service)
    monkeypatch.setattr(
        routes,
        "_report_extras",
        lambda request, user, job_id, project: {"theme": "dark", "accent": None},
    )
    return SimpleNamespace(
        store=store,
        denied=denied,
        request=SimpleNamespace(),
        record=("session", "token", SimpleNamespace(id=1, username="me")),
    )


def _download(world, kind="html", tz=None):
    return routes.run_report(197, world.request, kind, tz, world.record)


@pytest.mark.parametrize(
    ("kind", "media", "start"),
    [("html", "text/html", b"<!DOCTYPE html>"), ("pdf", "application/pdf", b"%PDF-")],
)
def test_the_report_is_downloaded_as_a_file(world, kind, media, start) -> None:
    response = _download(world, kind)

    assert response.media_type.startswith(media) and response.body.startswith(start)
    assert (
        response.headers["content-disposition"]
        == f'attachment; filename="run-197-sqlplus.analyse.{kind}"'
    )
    assert response.headers["cache-control"] == "no-store"


def test_times_follow_the_browsers_zone(world) -> None:
    body = _download(world, tz="Asia/Kolkata").body.decode()

    assert "Nov 3, 2026, 11:00:47 PM" in body and "times in Asia/Kolkata" in body


def test_a_hostile_target_cannot_reach_the_download_header(world) -> None:
    world.store.get.return_value = _run(target='x"; evil=\r\nSet-Cookie: a=b')

    assert (
        _download(world)
        .headers["content-disposition"]
        .endswith('filename="run-197-x-evil-Set-Cookie-a-b.html"')
    )


def test_a_report_needs_access_to_the_run(world) -> None:
    world.denied.add("workflows.read")

    with pytest.raises(routes.HTTPException) as caught:
        _download(world, "pdf")
    assert caught.value.status_code == 403


def test_a_missing_run_is_not_found(world) -> None:
    world.store.get.return_value = None

    with pytest.raises(routes.HTTPException) as caught:
        _download(world)
    assert caught.value.status_code == 404


def _extras_request(allowed):
    connection = MagicMock()
    connection.fetchone.return_value = {
        "user_id": 1,
        "theme": "light",
        "accent_color": "#3366ff",
    }
    context = SimpleNamespace(
        database_manager=SimpleNamespace(connection=connection),
        authorization=SimpleNamespace(has_permission=lambda user, permission, project: allowed),
    )
    return SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(entropy_context=context)))


@pytest.mark.parametrize(("allowed", "artifacts"), [(True, ["a"]), (False, [])])
def test_artifacts_are_only_listed_for_who_may_read_them(monkeypatch, allowed, artifacts) -> None:
    repository = MagicMock()
    repository.return_value.get.return_value = {"theme": "light", "accent_color": "#3366ff"}
    monkeypatch.setattr(
        "lib.database.repositories.user_preferences.UserPreferencesRepository", repository
    )
    monkeypatch.setattr(routes, "_artifact_items", lambda request, job_id, project: ["a"])
    monkeypatch.setattr(routes, "_app_store", lambda request: SimpleNamespace(list=lambda ids: []))
    monkeypatch.setattr(
        routes,
        "_service",
        lambda request: SimpleNamespace(store=SimpleNamespace(job_ids=lambda job: [job])),
    )

    extras = routes._report_extras(_extras_request(allowed), SimpleNamespace(id=1), 197, 1)

    assert extras["artifacts"] == artifacts
    assert (extras["theme"], extras["accent"]) == ("light", "#3366ff")


def _config(world):
    return routes.get_rerun_config(197, world.request, MagicMock(headers={}), world.record)


def test_a_plugin_run_returns_its_saved_inputs_to_who_may_run_plugins(world) -> None:
    world.denied.add("workflows.execute")

    assert _config(world)["config"]["arguments"] == {"a": 1}

    world.denied.add("plugins.execute")
    with pytest.raises(routes.HTTPException) as caught:
        _config(world)
    assert caught.value.status_code == 403


def test_a_workflow_run_still_needs_workflow_access(world) -> None:
    world.store.get.return_value = _run(kind="workflow")
    world.denied.add("workflows.execute")

    with pytest.raises(routes.HTTPException) as caught:
        _config(world)
    assert caught.value.status_code == 403


def test_an_older_plugin_run_says_it_has_no_saved_inputs(world) -> None:
    world.store.rerun_config.return_value = None

    with pytest.raises(routes.HTTPException) as caught:
        _config(world)
    assert caught.value.status_code == 409
    assert "Start it from the plugin" in caught.value.detail


# ----------------------------------------------------------------------
# A plugin run saves what it needs to run again
# ----------------------------------------------------------------------


def test_starting_a_plugin_saves_its_inputs(tmp_path: Path) -> None:
    service = RunService.__new__(RunService)
    service._context = SimpleNamespace(plugin_manager=SimpleNamespace(exists=lambda name: True))
    service.store = MagicMock()
    service.store.get.return_value = {"id": 5}
    service._executable_node = lambda node, project: {"name": node, "kind": "local"}
    service.plugin_run_directory = lambda: tmp_path
    service._start = lambda user, file, debug: SimpleNamespace(require_id=lambda: 5)

    service.start_plugin(
        SimpleNamespace(id=1),
        "oc.deployment",
        node="local",
        arguments={"namespace": "prod"},
        debug=True,
        mode="interactive",
    )

    assert service.store.record.call_args.kwargs["rerun_config"] == {
        "arguments": {"namespace": "prod"},
        "node": "local",
        "debug": True,
        "mode": "interactive",
    }
