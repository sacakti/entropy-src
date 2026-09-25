"""
HTML report rendering utilities.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from html import escape
from pathlib import Path
from typing import Iterable


@dataclass(frozen=True)
class HtmlReportObject:
    """
    Invalid database object.
    """

    name: str
    object_type: str
    status: str
    errors: tuple[str, ...] = ()


@dataclass(frozen=True)
class HtmlReportSchema:
    """
    Schema report data.
    """

    name: str
    status: str
    invalid_objects: tuple[HtmlReportObject, ...] = ()
    error_type: str | None = None
    error_message: str | None = None
    stderr: str | None = None


class InvalidObjectsHtmlReport:
    """
    Render the invalid-objects report.
    """

    def render(
        self,
        *,
        report_name: str,
        generated_at: datetime,
        generated_by: str,
        host: str,
        port: int,
        sid: str,
        schemas: Iterable[HtmlReportSchema],
    ) -> str:
        schema_list = list(schemas)

        clean = [
            schema
            for schema in schema_list
            if schema.status == "clean"
        ]

        attention = [
            schema
            for schema in schema_list
            if schema.status == "attention"
        ]

        errors = [
            schema
            for schema in schema_list
            if schema.status == "error"
        ]

        invalid_count = sum(
            len(schema.invalid_objects)
            for schema in schema_list
        )

        default_schema = (
            attention[0]
            if attention
            else errors[0]
            if errors
            else clean[0]
            if clean
            else None
        )

        schema_options = self._schema_options(
            schema_list,
        )

        schema_sections = "\n".join(
            self._schema_section(
                schema,
                active=(
                    default_schema is not None
                    and schema.name == default_schema.name
                ),
            )
            for schema in schema_list
        )

        return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{escape(report_name)}</title>

<style>
:root {{
    --bg: #f5f7fb;
    --surface: #ffffff;
    --surface-soft: #f8fafc;
    --border: #e5e7eb;
    --text: #172033;
    --muted: #667085;
    --clean: #15803d;
    --clean-bg: #ecfdf3;
    --attention: #b45309;
    --attention-bg: #fffbeb;
    --error: #b42318;
    --error-bg: #fef3f2;
    --accent: #4f46e5;
    --shadow: 0 10px 30px rgba(15, 23, 42, 0.06);
    --radius: 16px;
}}

* {{
    box-sizing: border-box;
}}

body {{
    margin: 0;
    background: var(--bg);
    color: var(--text);
    font-family:
        Inter, ui-sans-serif, system-ui, -apple-system,
        BlinkMacSystemFont, "Segoe UI", sans-serif;
    line-height: 1.5;
}}

.container {{
    width: min(1400px, calc(100% - 32px));
    margin: 0 auto;
    padding: 32px 0 56px;
}}

.hero {{
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 24px;
    padding: 28px;
    box-shadow: var(--shadow);
}}

.hero h1 {{
    margin: 0 0 8px;
    font-size: clamp(1.6rem, 3vw, 2.25rem);
}}

.subtitle {{
    color: var(--muted);
    margin-bottom: 24px;
}}

.meta {{
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
    gap: 12px;
}}

.meta-item {{
    background: var(--surface-soft);
    border: 1px solid var(--border);
    border-radius: 12px;
    padding: 14px 16px;
}}

.meta-label {{
    color: var(--muted);
    font-size: .78rem;
    text-transform: uppercase;
    letter-spacing: .05em;
}}

.meta-value {{
    margin-top: 3px;
    font-weight: 600;
    overflow-wrap: anywhere;
}}

.section {{
    margin-top: 20px;
}}

.section-title {{
    font-size: 1.05rem;
    font-weight: 700;
    margin: 0 0 12px;
}}

.summary {{
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
    gap: 14px;
}}

.card {{
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    padding: 20px;
    box-shadow: var(--shadow);
}}

.metric-value {{
    font-size: 2rem;
    font-weight: 750;
}}

.metric-label {{
    color: var(--muted);
    margin-top: 2px;
}}

.metric-clean .metric-value {{
    color: var(--clean);
}}

.metric-attention .metric-value {{
    color: var(--attention);
}}

.metric-error .metric-value {{
    color: var(--error);
}}

.connection {{
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
    gap: 12px;
}}

.schema-summary {{
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    overflow: hidden;
    box-shadow: var(--shadow);
}}

.schema-summary summary {{
    cursor: pointer;
    padding: 18px 20px;
    font-weight: 700;
}}

.schema-list {{
    border-top: 1px solid var(--border);
    padding: 8px;
}}

.schema-row {{
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 12px;
    padding: 12px;
    border-radius: 10px;
}}

.schema-row:hover {{
    background: var(--surface-soft);
}}

.badge {{
    display: inline-flex;
    align-items: center;
    border-radius: 999px;
    padding: 4px 10px;
    font-size: .78rem;
    font-weight: 700;
    white-space: nowrap;
}}

.badge-clean {{
    color: var(--clean);
    background: var(--clean-bg);
}}

.badge-attention {{
    color: var(--attention);
    background: var(--attention-bg);
}}

.badge-error {{
    color: var(--error);
    background: var(--error-bg);
}}

.selector {{
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 12px;
    margin-bottom: 16px;
}}

.selector label {{
    font-weight: 700;
}}

select {{
    min-width: min(420px, 100%);
    border: 1px solid var(--border);
    border-radius: 10px;
    background: var(--surface);
    color: var(--text);
    padding: 10px 14px;
    font: inherit;
}}

.schema-panel {{
    display: none;
}}

.schema-panel.active {{
    display: block;
}}

.panel {{
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    padding: 22px;
    box-shadow: var(--shadow);
}}

.panel-header {{
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    justify-content: space-between;
    gap: 12px;
    margin-bottom: 18px;
}}

.panel-header h2 {{
    margin: 0;
    font-size: 1.3rem;
}}

.object {{
    border: 1px solid var(--border);
    border-radius: 12px;
    margin-top: 10px;
    overflow: hidden;
}}

.object summary {{
    cursor: pointer;
    padding: 14px 16px;
    list-style: none;
}}

.object summary::-webkit-details-marker {{
    display: none;
}}

.object summary::after {{
    content: "+";
    float: right;
    color: var(--muted);
}}

.object[open] summary::after {{
    content: "−";
}}

.object-name {{
    font-weight: 700;
}}

.object-type {{
    color: var(--muted);
    margin-left: 8px;
}}

.object-body {{
    border-top: 1px solid var(--border);
    padding: 16px;
    background: var(--surface-soft);
}}

.error-list {{
    margin: 0;
    padding-left: 20px;
}}

.error-list li {{
    margin: 5px 0;
    font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
    font-size: .88rem;
}}

.empty {{
    color: var(--muted);
    padding: 20px 0 4px;
}}

.schema-error {{
    border: 1px solid #fecaca;
    background: var(--error-bg);
    color: var(--error);
    border-radius: 12px;
    padding: 16px;
}}

pre {{
    overflow-x: auto;
    white-space: pre-wrap;
    overflow-wrap: anywhere;
}}

@media (max-width: 640px) {{
    .container {{
        width: min(100% - 20px, 1400px);
        padding-top: 16px;
    }}

    .hero,
    .panel,
    .card {{
        border-radius: 14px;
    }}
}}
</style>
</head>

<body>
<div class="container">

    <section class="hero">
        <h1>Invalid Objects Report</h1>
        <div class="subtitle">
            Oracle invalid-object inspection
        </div>

        <div class="meta">
            <div class="meta-item">
                <div class="meta-label">Report Name</div>
                <div class="meta-value">{escape(report_name)}</div>
            </div>

            <div class="meta-item">
                <div class="meta-label">Generated</div>
                <div class="meta-value">{escape(generated_at.astimezone().strftime("%d %b %Y, %H:%M:%S %Z"))}</div>
            </div>

            <div class="meta-item">
                <div class="meta-label">Generated By</div>
                <div class="meta-value">{escape(generated_by)}</div>
            </div>
        </div>
    </section>

    <section class="section">
        <h2 class="section-title">Database Connection</h2>

        <div class="connection">
            <div class="card">
                <div class="meta-label">Host</div>
                <div class="meta-value">{escape(host)}</div>
            </div>

            <div class="card">
                <div class="meta-label">Port</div>
                <div class="meta-value">{port}</div>
            </div>

            <div class="card">
                <div class="meta-label">SID</div>
                <div class="meta-value">{escape(sid)}</div>
            </div>
        </div>
    </section>

    <section class="section">
        <h2 class="section-title">Overall Summary</h2>

        <div class="summary">
            <div class="card metric-clean">
                <div class="metric-value">{len(clean)}</div>
                <div class="metric-label">Clean</div>
            </div>

            <div class="card metric-attention">
                <div class="metric-value">{len(attention)}</div>
                <div class="metric-label">Attention Required</div>
            </div>

            <div class="card metric-error">
                <div class="metric-value">{len(errors)}</div>
                <div class="metric-label">Errors</div>
            </div>

            <div class="card">
                <div class="metric-value">{len(schema_list)}</div>
                <div class="metric-label">Schemas Checked</div>
            </div>

            <div class="card">
                <div class="metric-value">{invalid_count}</div>
                <div class="metric-label">Invalid Objects</div>
            </div>
        </div>
    </section>

    <section class="section">
        <details class="schema-summary">
            <summary>Schemas · {len(schema_list)}</summary>

            <div class="schema-list">
                {schema_options}
            </div>
        </details>
    </section>

    <section class="section">
        <div class="selector">
            <label for="schema-selector">Schema</label>

            <select id="schema-selector"
                    onchange="selectSchema(this.value)">
                {"".join(
                    f'<option value="{escape(schema.name, quote=True)}" '
                    f'{"selected" if default_schema is not None and schema.name == default_schema.name else ""}>'
                    f'{escape(schema.name)} — {escape(self._status_label(schema.status))}'
                    f'</option>'
                    for schema in schema_list
                )}
            </select>
        </div>

        {schema_sections}
    </section>

</div>

<script>
function selectSchema(name) {{
    document.querySelectorAll(".schema-panel").forEach(function(panel) {{
        panel.classList.toggle(
            "active",
            panel.dataset.schema === name
        );
    }});
}}
</script>

</body>
</html>
"""

    @staticmethod
    def _status_label(
        status: str,
    ) -> str:
        return {
            "clean": "Clean",
            "attention": "Attention Required",
            "error": "Error",
        }.get(status, status)

    def _schema_options(
        self,
        schemas: list[HtmlReportSchema],
    ) -> str:
        rows: list[str] = []

        for schema in schemas:
            status = schema.status
            count = len(schema.invalid_objects)

            if status == "clean":
                detail = "Clean"
            elif status == "attention":
                detail = f"{count} Invalid Object{'s' if count != 1 else ''}"
            else:
                detail = "Information gathering failed"

            rows.append(
                f"""
                <div class="schema-row">
                    <span>{escape(schema.name)}</span>
                    <span class="badge badge-{escape(status)}">
                        {escape(self._status_label(status))}
                        · {escape(detail)}
                    </span>
                </div>
                """
            )

        return "\n".join(rows)

    def _schema_section(
        self,
        schema: HtmlReportSchema,
        *,
        active: bool,
    ) -> str:
        badge = (
            f"badge-{schema.status}"
        )

        if schema.status == "attention":
            count = len(schema.invalid_objects)
            subtitle = (
                f"{count} invalid object"
                f"{'s' if count != 1 else ''}"
            )
        elif schema.status == "clean":
            subtitle = "No invalid objects found."
        else:
            subtitle = "Unable to gather invalid-object information."

        objects = ""

        for obj in schema.invalid_objects:
            errors = ""

            if obj.errors:
                errors = (
                    '<div class="object-body">'
                    "<strong>Oracle Errors</strong>"
                    '<ul class="error-list">'
                    + "".join(
                        f"<li>{escape(error)}</li>"
                        for error in obj.errors
                    )
                    + "</ul>"
                    "</div>"
                )
            else:
                errors = (
                    '<div class="object-body">'
                    '<div class="empty">'
                    "Oracle error details are not available."
                    "</div>"
                    "</div>"
                )

            objects += f"""
            <details class="object">
                <summary>
                    <span class="object-name">{escape(obj.name)}</span>
                    <span class="object-type">{escape(obj.object_type)}</span>
                    <span class="badge badge-attention">
                        {escape(obj.status)}
                    </span>
                </summary>
                {errors}
            </details>
            """

        error_html = ""

        if schema.status == "error":
            error_html = f"""
            <div class="schema-error">
                <strong>{escape(schema.error_type or "Oracle error")}</strong>
                <div>{escape(schema.error_message or "Unable to gather information.")}</div>
            """

            if schema.stderr:
                error_html += f"""
                <details style="margin-top:12px;">
                    <summary>SQLPlus diagnostic output</summary>
                    <pre>{escape(schema.stderr)}</pre>
                </details>
                """

            error_html += "</div>"

        return f"""
        <section
            class="schema-panel {'active' if active else ''}"
            data-schema="{escape(schema.name, quote=True)}"
        >
            <div class="panel">
                <div class="panel-header">
                    <div>
                        <h2>{escape(schema.name)}</h2>
                        <div class="subtitle">{escape(subtitle)}</div>
                    </div>

                    <span class="badge {badge}">
                        {escape(self._status_label(schema.status))}
                    </span>
                </div>

                {error_html}

                {objects if objects else '<div class="empty">No invalid objects found.</div>'}
            </div>
        </section>
        """
