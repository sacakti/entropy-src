from __future__ import annotations

import html
import json
from dataclasses import asdict, is_dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from ..models.report import (
    ExecutionReport,
)
from .css import REPORT_CSS
from .js import REPORT_JS


class HtmlReportRenderer:
    """Render the complete execution report as one report.html file."""

    def render(self, report: ExecutionReport) -> str:
        payload = (
            json.dumps(
                self._serialize(report),
                ensure_ascii=False,
                separators=(",", ":"),
            )
            .replace("<", "\\u003c")
            .replace(">", "\\u003e")
            .replace("&", "\\u0026")
        )

        return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Entropy — {html.escape(report.workflow)}</title>
<style>{REPORT_CSS}</style>
</head>
<body>
<div id="app">
{self._header(report)}
{self._failure_summary(report)}
{self._summary(report)}
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
      <div class="result-tabs">
        <button class="result-tab active" data-view="pretty" type="button">Pretty</button>
        <button class="result-tab" data-view="raw" type="button">Raw</button>
      </div>
      <div id="result-pretty"></div>
      <div id="result-raw" class="raw-result">
        <pre id="result-raw-content"></pre>
      </div>
    </div>
  </div>
</div>

<script id="report-data" type="application/json">{payload}</script>
<script>{REPORT_JS}</script>
</body>
</html>"""

    def write(self, report: ExecutionReport, path: Path) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.render(report), encoding="utf-8")
        return path

    @staticmethod
    def _header(report):
        full_name = (report.full_name or "").strip()
        username = (report.username or "").strip()

        if full_name:
            user = (
                f"{html.escape(full_name)} "
                f"<span class=\"identity-id\">({html.escape(username or '—')})</span>"
            )
        else:
            user = html.escape(username or "—")

        workspace = html.escape(report.workspace or "—")

        return f"""
    <header class="page-header">
    <div class="header-main">
        <div class="brand">Entropy</div>

        <h1>{html.escape(report.workflow)}</h1>

        <div class="execution-id">
        Execution: {html.escape(report.execution_id)}
        </div>

        <div class="execution-meta">
        <div class="header-info">
            <span class="header-label">User</span>
            <strong>{user}</strong>
        </div>

        <div class="header-info workspace-info">
            <span class="header-label">Workspace</span>
            <code>{workspace}</code>
        </div>
        </div>

        <div class="muted">
        {HtmlReportRenderer._date(report.started_at)}
        →
        {HtmlReportRenderer._date(report.finished_at)}
        ·
        {HtmlReportRenderer._duration(report.duration_ms)}
        </div>
    </div>

    <div class="status status-{html.escape(report.status.lower())}">
        {html.escape(report.status)}
    </div>
    </header>
    """

    @classmethod
    def _failure_summary(cls, report):
        failed = next(
            (
                s
                for s in report.steps
                if s.status == "FAILED" or (s.result and s.result.get("success") is False)
            ),
            None,
        )
        if not failed:
            return ""
        failure = failed.failure or {}
        message = (
            failure.get("message") or cls._first_error(failed) or "The step reported a failure."
        )
        return f"""
<section class="section">
  <div class="failure">
    <div class="failure-title">Execution failure</div>
    <strong>{html.escape(failed.name)}</strong>
    <div class="muted">{html.escape(failed.plugin or "Plugin unavailable")}</div>
    <div class="failure-message">{html.escape(str(message))}</div>
    <div class="failure-meta">
      <div><label>Failure type</label><strong>{html.escape(str(failure.get("type") or "Failure"))}</strong></div>
      <div><label>Step duration</label><strong>{cls._duration(failed.duration_ms)}</strong></div>
      <div><label>Step</label><strong>{html.escape(failed.name)}</strong></div>
    </div>
    {cls._failure_detail(failed)}
  </div>
</section>"""

    @classmethod
    def _failure_detail(cls, step):
        failure = step.failure or {}
        exception = failure.get("message")
        if not exception:
            return ""
        return f"""
<div class="detail-block">
  <div class="detail-title">Failure details</div>
  <div class="failure-detail">
    <div><strong>Source:</strong> {html.escape(str(failure.get("source") or step.name))}</div>
    <div class="exception" style="margin-top:8px">{html.escape(str(exception))}</div>
  </div>
</div>"""

    @staticmethod
    def _summary(report):
        s = report.summary
        selected = int(report.metadata.get("selected_steps") or s.total_steps)
        not_run = max(selected - s.total_steps, 0)
        values = [
            ("Workflow steps", selected),
            ("Executed", s.total_steps),
            ("Successful", s.successful_steps),
            ("Failed", s.failed_steps),
            ("Not executed", not_run),
            ("Changed", s.changed_steps),
            ("Warnings", s.warning_steps),
            ("Errors", s.error_steps),
        ]
        cards = "".join(
            f'<div class="card"><div class="card-label">{label}</div><div class="card-value">{value}</div></div>'
            for label, value in values
        )
        return f'<section class="section"><div class="section-title"><h2>Execution summary</h2></div><div class="cards">{cards}</div></section>'

    def _step_failure(self, step):
        if not step.failure:
            return ""
        f = step.failure
        return f"""
<div class="detail-block">
  <div class="detail-title">Why this step failed</div>
  <div class="failure-detail">
    <div><strong>Type:</strong> {html.escape(str(f.get("type") or "Failure"))}</div>
    <div><strong>Source:</strong> {html.escape(str(f.get("source") or step.name))}</div>
    <div class="exception" style="margin-top:8px">{html.escape(str(f.get("message") or "Step execution failed."))}</div>
  </div>
</div>"""

    def _messages(self, step):
        messages = self._all_messages(step)

        if not messages:
            return ""

        items = []

        for message in messages:
            if not message.message:
                continue

            level = self._level(message.level)

            items.append(
                f'<div class="message {html.escape(level)}">'
                f'<span class="level">{html.escape(level)}</span>'
                f'<span class="message-text">{html.escape(message.message)}</span>'
                f"</div>"
            )

        if not items:
            return ""

        return '<div style="margin-bottom:15px">' "<h3>Messages</h3>" f'{"".join(items)}' "</div>"

    def _tree(self, step):
        parts = []
        for stage in step.stages:
            acts = "".join(
                f'<div class="activity"><span>{html.escape(a.name)}</span><span>{html.escape(a.status)} · {self._duration(a.duration_ms)}</span></div>'
                for a in stage.activities
            )
            parts.append(
                f'<div class="stage"><div class="stage-header"><strong>{html.escape(stage.name)}</strong><span>{html.escape(stage.status)} · {self._duration(stage.duration_ms)}</span></div>{acts}</div>'
            )
        for activity in step.activities:
            parts.append(
                f'<div class="activity"><span>{html.escape(activity.name)}</span><span>{html.escape(activity.status)} · {self._duration(activity.duration_ms)}</span></div>'
            )
        if not parts:
            return ""
        return f'<div class="detail-block"><div class="detail-title">Execution details</div><div class="tree">{"".join(parts)}</div></div>'

    def _performance(self, report):
        bars = []
        maximum = max((s.duration_ms or 0 for s in report.steps), default=0)

        for step in report.steps:
            if step.duration_ms is None:
                continue

            width = 2 if maximum == 0 else max(2, int(step.duration_ms / maximum * 100))

            bars.append(
                f'<div style="display:grid;grid-template-columns:220px 1fr 70px;'
                f'gap:10px;align-items:center;margin:8px 0;font-size:12px">'
                f"<span>{html.escape(step.name)}</span>"
                f'<span style="height:11px;background:#e9edf1;border-radius:6px">'
                f'<span style="display:block;width:{width}%;height:100%;'
                f'background:#536878;border-radius:6px"></span>'
                f"</span>"
                f"<span>{self._duration(step.duration_ms)}</span>"
                f"</div>"
            )

        chart = "".join(bars)
        if not chart:
            chart = '<div class="chart-empty">No timing data available.</div>'

        return (
            f'<section class="section">'
            f'<div class="section-title"><h2>Performance</h2></div>'
            f'<div class="performance-grid">'
            f'<div class="metric"><span>Total duration</span>'
            f"<strong>{self._duration(report.duration_ms)}</strong></div>"
            f'<div class="metric"><span>Average step</span>'
            f"<strong>{self._duration(report.summary.average_step_duration_ms)}</strong></div>"
            f'<div class="metric"><span>Slowest step</span>'
            f'<strong>{html.escape(report.summary.slowest_step or "—")}</strong></div>'
            f'<div class="metric"><span>Slowest duration</span>'
            f"<strong>{self._duration(report.summary.slowest_step_duration_ms)}</strong></div>"
            f"</div>"
            f'<div class="chart-container"><div class="chart">{chart}</div></div>'
            f"</section>"
        )

    def _timeline(self, report):
        if not report.steps:
            return (
                '<section class="section">'
                '<div class="section-title">'
                '<h2>Execution timeline</h2>'
                '</div>'
                '<div class="muted">No execution steps.</div>'
                '</section>'
            )

        items = []

        for position, step in enumerate(report.steps):
            status = (step.status or "UNKNOWN").lower()

            start = self._date(step.started_at)
            finish = self._date(step.finished_at)
            duration = self._duration(step.duration_ms)

            messages = self._all_messages(step)

            warnings = any(
                self._level(message.level) == "WARNING"
                for message in messages
            )

            errors = any(
                self._level(message.level) in {"ERROR", "CRITICAL"}
                for message in messages
            )

            search = " ".join(
                [
                    step.name,
                    step.plugin,
                    step.status,
                    *(message.message or "" for message in messages),
                ]
            ).lower()

            result_button = (
                f'<button class="action timeline-result" '
                f'data-result-index="{position}" type="button">'
                f'Plugin Result'
                f'</button>'
            )

            body = f"""
            <div class="step-body">
            <div class="step-info">
                <div>
                <span>Plugin</span>
                <strong>{html.escape(step.plugin or "—")}</strong>
                </div>
                <div>
                <span>Duration</span>
                <strong>{html.escape(duration)}</strong>
                </div>
                <div>
                <span>Changed</span>
                <strong>{"Yes" if step.changed else "No"}</strong>
                </div>
            </div>

            {self._step_failure(step)}
            {self._messages(step)}
            {self._tree(step)}
            </div>
            """

            items.append(
                f"""
                <article
                    class="timeline-node step {html.escape(status)}"
                    data-status="{html.escape(step.status)}"
                    data-changed="{str(step.changed).lower()}"
                    data-warnings="{str(warnings).lower()}"
                    data-errors="{str(errors).lower()}"
                    data-search="{html.escape(search)}"
                >
                <div class="timeline-marker">
                    <span class="timeline-dot"></span>
                    {
                        '<span class="timeline-line"></span>'
                        if position < len(report.steps) - 1
                        else ''
                    }
                </div>

                <div class="timeline-card">
                    <div
                        class="timeline-card-header step-header"
                        onclick="toggleStep(this)"
                    >
                    <div class="timeline-step">
                        <span class="timeline-index">
                        {step.index if step.index is not None else position + 1}
                        </span>

                        <div>
                        <strong>{html.escape(step.name)}</strong>

                        <div class="timeline-plugin">
                            {html.escape(step.plugin or "Plugin unavailable")}
                        </div>
                        </div>
                    </div>

                    <div class="timeline-header-actions">
                        <span class="timeline-status">
                        {html.escape(step.status)}
                        </span>

                        {result_button}
                    </div>
                    </div>

                    <div class="timeline-duration">
                    <div class="timeline-metric">
                        <span>Started</span>
                        <strong>{html.escape(start)}</strong>
                    </div>

                    <div class="timeline-duration-value">
                        <span class="timeline-duration-line"></span>
                        <strong>{html.escape(duration)}</strong>
                    </div>

                    <div class="timeline-metric">
                        <span>Finished</span>
                        <strong>{html.escape(finish)}</strong>
                    </div>
                    </div>

                    {body}
                </div>
                </article>
                """
            )

        return (
            '<section class="section">'
            '<div class="section-title">'
            '<h2>Execution timeline</h2>'
            '<div class="filters">'
            '<button class="filter active" data-filter="all">All</button>'
            '<button class="filter" data-filter="success">Success</button>'
            '<button class="filter" data-filter="failed">Failed</button>'
            '<button class="filter" data-filter="skipped">Skipped</button>'
            '<button class="filter" data-filter="running">Running</button>'
            '<button class="filter" data-filter="changed">Changed</button>'
            '<button class="filter" data-filter="warnings">Warnings</button>'
            '<button class="filter" data-filter="errors">Errors</button>'
            '</div>'
            '</div>'
            '<div class="search">'
            '<input id="report-search" type="search" placeholder="Search execution...">'
            '</div>'
            f'<div class="execution-timeline">{"".join(items)}</div>'
            '</section>'
        )

    @staticmethod
    def _all_messages(step):
        messages = list(step.messages)
        for stage in step.stages:
            messages.extend(stage.messages)
            for activity in stage.activities:
                messages.extend(activity.messages)
        for activity in step.activities:
            messages.extend(activity.messages)
        return messages

    @staticmethod
    def _first_error(step):
        for message in HtmlReportRenderer._all_messages(step):
            if (
                HtmlReportRenderer._level(message.level) in {"ERROR", "CRITICAL"}
                and message.message
            ):
                return message.message
        result = step.result or {}
        errors = result.get("errors") or []
        return str(errors[0]) if errors else None

    @staticmethod
    def _level(value):
        return {
            "10": "DEBUG",
            "20": "INFO",
            "25": "NOTICE",
            "30": "WARNING",
            "40": "ERROR",
            "50": "CRITICAL",
        }.get(str(value or "").upper(), str(value or "").upper())

    @staticmethod
    def _duration(ms):
        if ms is None:
            return "—"
        if ms < 1000:
            return f"{ms} ms"
        return f"{ms/1000:.1f} s" if ms < 60000 else f"{ms//60000}m {round((ms%60000)/1000)}s"

    @staticmethod
    def _date(value):
        return "—" if value is None else value.isoformat(sep=" ", timespec="seconds")

    @staticmethod
    def _serialize(value: Any):
        if is_dataclass(value):
            return {k: HtmlReportRenderer._serialize(v) for k, v in asdict(value).items()}
        if isinstance(value, datetime):
            return value.isoformat()
        if isinstance(value, list):
            return [HtmlReportRenderer._serialize(v) for v in value]
        if isinstance(value, dict):
            return {k: HtmlReportRenderer._serialize(v) for k, v in value.items()}
        return value
