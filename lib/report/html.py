"""
Render an ExecutionReport as one self-contained HTML file.

The Python implementation is split across html.py, css.py and js.py,
but the generated artifact remains a single report.html.
"""

from __future__ import annotations

import html
import json
from dataclasses import asdict, is_dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from .css import REPORT_CSS
from .js import REPORT_JS
from ..models.report import (
    ActivityReport,
    ExecutionReport,
    ReportTimelineEvent,
    StageReport,
    StepReport,
)


class HtmlReportRenderer:
    """Render an ExecutionReport into one portable HTML document."""

    def render(self, report: ExecutionReport) -> str:
        payload = json.dumps(
            self._serialize(report),
            ensure_ascii=False,
            separators=(",", ":"),
        ).replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")

        return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Entropy — {html.escape(report.workflow)}</title>
<style>
{REPORT_CSS}
</style>
</head>
<body>
<div id="app">
{self._header(report)}
{self._failure(report)}
{self._summary(report)}
{self._steps(report)}
{self._performance(report)}
{self._timeline(report)}
</div>

<div id="result-modal" class="modal-backdrop">
    <div class="modal">
        <div class="modal-head">
            <strong id="result-title">Plugin Result</strong>
            <button id="result-close" class="close" type="button">&times;</button>
        </div>
        <div class="modal-body">
            <div id="result-content"></div>
            <details class="raw">
                <summary>View raw result</summary>
                <pre id="result-raw"></pre>
            </details>
        </div>
    </div>
</div>

<script id="report-data" type="application/json">{payload}</script>
<script>
{REPORT_JS}
</script>
</body>
</html>
"""

    def write(self, report: ExecutionReport, path: Path) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.render(report), encoding="utf-8")
        return path

    @staticmethod
    def _header(report: ExecutionReport) -> str:
        status = report.status.upper()
        css_status = {
            "COMPLETED": "success",
            "SUCCESS": "success",
            "FAILED": "failed",
            "CANCELLED": "cancelled",
            "SKIPPED": "skipped",
            "RUNNING": "running",
        }.get(status, "running")

        return f"""
<header class="header">
    <div>
        <div class="brand">Entropy Execution Report</div>
        <h1>{html.escape(report.workflow)}</h1>
        <div class="meta mono">Execution: {html.escape(report.execution_id)}</div>
        <div class="meta">
            {HtmlReportRenderer._date(report.started_at)}
            → {HtmlReportRenderer._date(report.finished_at)}
            · {HtmlReportRenderer._duration(report.duration_ms)}
        </div>
    </div>
    <div class="status status-{css_status}">{html.escape(status)}</div>
</header>
"""

    @staticmethod
    def _failure(report: ExecutionReport) -> str:
        failed = [step for step in report.steps if step.status == "FAILED"]
        if not failed:
            return ""

        step = failed[0]
        error = HtmlReportRenderer._first_error(step)
        if not error:
            error = "The step reported a failure."

        return f"""
<section class="panel alert">
    <div class="alert-title">Execution failed</div>
    <div><strong>{html.escape(step.name)}</strong></div>
    <div class="meta">{html.escape(step.plugin or "Plugin unavailable")}</div>
    <div style="margin-top:8px">{html.escape(error)}</div>
</section>
"""

    @staticmethod
    def _summary(report: ExecutionReport) -> str:
        s = report.summary
        selected = report.metadata.get("selected_steps", 0)
        not_run = max(selected - s.total_steps, 0)

        metrics = [
            ("Workflow steps", selected or s.total_steps),
            ("Executed", s.total_steps),
            ("Successful", s.successful_steps),
            ("Failed", s.failed_steps),
            ("Not executed", not_run),
            ("Changed", s.changed_steps),
            ("Warnings", s.warning_steps),
            ("Errors", s.error_steps),
        ]

        cards = "".join(
            f'<div class="metric"><div class="metric-label">{label}</div>'
            f'<div class="metric-value">{value}</div></div>'
            for label, value in metrics
        )

        return f"""
<section class="panel">
    <div class="panel-header"><h2>Execution summary</h2></div>
    <div class="panel-body">
        <div class="summary-grid">{cards}</div>
    </div>
</section>
"""

    def _steps(self, report: ExecutionReport) -> str:
        if not report.steps:
            return """
<section class="panel">
    <div class="panel-header"><h2>Execution steps</h2></div>
    <div class="panel-body"><div class="empty">No steps were executed.</div></div>
</section>
"""

        controls = """
<div class="controls">
    <input id="report-search" class="search" placeholder="Search steps, plugins and messages...">
    <button class="filter active" data-filter="all">All</button>
    <button class="filter" data-filter="success">Success</button>
    <button class="filter" data-filter="failed">Failed</button>
    <button class="filter" data-filter="changed">Changed</button>
    <button class="filter" data-filter="warnings">Warnings</button>
    <button class="filter" data-filter="errors">Errors</button>
</div>
"""

        cards = "".join(self._step(index, step) for index, step in enumerate(report.steps))
        return f"""
<section class="panel">
    <div class="panel-header"><h2>Execution steps</h2></div>
    <div class="panel-body">
        {controls}
        {cards}
    </div>
</section>
"""

    def _step(self, index: int, step: StepReport) -> str:
        messages = self._all_messages(step)
        warnings = any(self._level(m.level) == "WARNING" for m in messages)
        errors = any(self._level(m.level) in {"ERROR", "CRITICAL"} for m in messages)
        searchable = " ".join(
            [
                step.name,
                step.plugin,
                step.status,
                *[(m.message or "") for m in messages],
            ]
        ).lower()

        status_class = step.status.lower()
        result_button = (
            f'<button class="action result-button" data-result-index="{index}">View result</button>'
            if step.result
            else ""
        )

        return f"""
<article class="step"
    data-status="{html.escape(step.status)}"
    data-changed="{str(step.changed).lower()}"
    data-warnings="{str(warnings).lower()}"
    data-errors="{str(errors).lower()}"
    data-search="{html.escape(searchable)}">

    <div class="step-head">
        <div class="step-title">
            <div class="step-index">{step.index if step.index is not None else index + 1}</div>
            <div>
                <div class="step-name">{html.escape(step.name)}</div>
                <div class="step-meta">{html.escape(step.plugin or "Plugin unavailable")}</div>
            </div>
        </div>
        <div class="actions">
            <span class="status status-{status_class}">{html.escape(step.status)}</span>
            {result_button}
        </div>
    </div>

    <div class="step-body">
        <div class="info-grid">
            {self._info("Plugin", step.plugin or "—")}
            {self._info("Duration", self._duration(step.duration_ms))}
            {self._info("Changed", "Yes" if step.changed else "No")}
        </div>

        {self._diagnostics(step)}
        {self._execution_tree(step)}
    </div>
</article>
"""

    @staticmethod
    def _info(label: str, value: str) -> str:
        return (
            f'<div class="info-item"><label>{html.escape(label)}</label>'
            f'<strong>{html.escape(value)}</strong></div>'
        )

    def _diagnostics(self, step: StepReport) -> str:
        messages = self._all_messages(step)
        if not messages:
            return ""

        content = "".join(
            f'<div class="message {html.escape(self._level(m.level))}">'
            f'<span class="level">{html.escape(self._level(m.level))}</span>'
            f'{html.escape(m.message or "")}</div>'
            for m in messages
            if m.message
        )

        return f"""
<div style="margin-bottom:15px">
    <h3>Messages</h3>
    {content}
</div>
"""

    def _execution_tree(self, step: StepReport) -> str:
        blocks = []

        for stage in step.stages:
            blocks.append(self._stage(stage))

        for activity in step.activities:
            blocks.append(self._activity(activity))

        if not blocks:
            return ""

        return f"""
<div>
    <h3>Execution details</h3>
    <div class="tree">{''.join(blocks)}</div>
</div>
"""

    def _stage(self, stage: StageReport) -> str:
        children = "".join(self._activity(a) for a in stage.activities)
        return (
            f'<div class="tree-row"><span class="name">{html.escape(stage.name)}</span>'
            f'<span>{html.escape(stage.status)} · {self._duration(stage.duration_ms)}</span></div>'
            f'{children}'
        )

    @staticmethod
    def _activity(activity: ActivityReport) -> str:
        return (
            f'<div class="tree-row"><span class="name">{html.escape(activity.name)}</span>'
            f'<span>{html.escape(activity.status)} · '
            f'{HtmlReportRenderer._duration(activity.duration_ms)}</span></div>'
        )

    @staticmethod
    def _all_messages(step: StepReport) -> list[ReportTimelineEvent]:
        messages = list(step.messages)
        for stage in step.stages:
            messages.extend(stage.messages)
            for activity in stage.activities:
                messages.extend(activity.messages)
        for activity in step.activities:
            messages.extend(activity.messages)
        return messages

    def _performance(self, report: ExecutionReport) -> str:
        return """
<section class="panel">
    <div class="panel-header"><h2>Performance</h2></div>
    <div class="panel-body">
        <div id="performance-chart" class="chart"></div>
    </div>
</section>
"""

    @staticmethod
    def _timeline(report: ExecutionReport) -> str:
        events = "".join(
            f"""
<div class="timeline-item">
    <div class="mono">{html.escape(HtmlReportRenderer._date(event.timestamp))}</div>
    <div><strong>{html.escape(event.event_type)}</strong></div>
    <div>{html.escape(event.message or event.node_name or "")}</div>
</div>
"""
            for event in report.timeline
            if event.message or event.node_name
        )

        return f"""
<section class="panel">
    <div class="panel-header"><h2>Detailed timeline</h2></div>
    <div class="panel-body">
        {events or '<div class="empty">No timeline events.</div>'}
    </div>
</section>
"""

    @staticmethod
    def _first_error(step: StepReport) -> str | None:
        messages = HtmlReportRenderer._all_messages(step)
        for message in messages:
            if HtmlReportRenderer._level(message.level) in {"ERROR", "CRITICAL"}:
                if message.message:
                    return message.message

        result = step.result or {}
        errors = result.get("errors")
        if isinstance(errors, list) and errors:
            first = errors[0]
            if isinstance(first, dict):
                return str(first.get("message") or first.get("error") or first)
            return str(first)

        return None

    @staticmethod
    def _level(value: str | None) -> str:
        return {
            "10": "DEBUG",
            "20": "INFO",
            "30": "WARNING",
            "40": "ERROR",
            "50": "CRITICAL",
        }.get(str(value or "").upper(), str(value or "").upper())

    @staticmethod
    def _duration(ms: int | None) -> str:
        if ms is None:
            return "—"
        if ms < 1000:
            return f"{ms} ms"
        seconds = ms / 1000
        if seconds < 60:
            return f"{seconds:.1f} s"
        minutes = int(seconds // 60)
        return f"{minutes}m {round(seconds % 60):02d}s"

    @staticmethod
    def _date(value: datetime | None) -> str:
        if value is None:
            return "—"
        return value.isoformat(sep=" ", timespec="seconds")

    @staticmethod
    def _serialize(value: Any) -> Any:
        if is_dataclass(value):
            return {key: HtmlReportRenderer._serialize(item) for key, item in asdict(value).items()}
        if isinstance(value, datetime):
            return value.isoformat()
        if isinstance(value, list):
            return [HtmlReportRenderer._serialize(item) for item in value]
        if isinstance(value, dict):
            return {key: HtmlReportRenderer._serialize(item) for key, item in value.items()}
        return value
