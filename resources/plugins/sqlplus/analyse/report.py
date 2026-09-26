"""
HTML report generation for Oracle SQL script analysis.
"""

from __future__ import annotations

from collections import Counter
from html import escape
from pathlib import Path

from .model import AnalyseFinding, AnalyseObject, AnalyseResult


class AnalyseReportBuilder:
    """
    Build an HTML report from SQL analysis results.
    """

    def build(
        self,
        result: AnalyseResult,
        output: Path,
    ) -> Path:
        """
        Build and write the HTML analysis report.
        """

        output.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        html = self._render(
            result,
        )

        output.write_text(
            html,
            encoding="utf-8",
        )

        return output

    # ------------------------------------------------------------------
    # Rendering
    # ------------------------------------------------------------------

    def _render(
        self,
        result: AnalyseResult,
    ) -> str:
        """
        Render the complete HTML document.
        """

        objects = sorted(
            result.objects,
            key=self._object_sort_key,
        )

        findings = sorted(
            result.findings,
            key=self._finding_sort_key,
        )

        object_counts = Counter(
            obj.category.upper()
            for obj in objects
        )

        severity_counts = Counter(
            finding.severity.upper()
            for finding in findings
        )

        return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Oracle SQL Analysis Report</title>
<style>
    :root {{
        --background: #f5f7fa;
        --surface: #ffffff;
        --border: #d9dee7;
        --text: #1f2937;
        --muted: #6b7280;
        --primary: #2563eb;
        --warning: #b45309;
        --error: #b91c1c;
        --stop: #7f1d1d;
        --success: #166534;
    }}

    * {{
        box-sizing: border-box;
    }}

    body {{
        margin: 0;
        padding: 0;
        background: var(--background);
        color: var(--text);
        font-family:
            -apple-system,
            BlinkMacSystemFont,
            "Segoe UI",
            sans-serif;
        line-height: 1.5;
    }}

    .container {{
        max-width: 1500px;
        margin: 0 auto;
        padding: 32px;
    }}

    header {{
        margin-bottom: 28px;
    }}

    h1 {{
        margin: 0 0 8px;
        font-size: 30px;
    }}

    h2 {{
        margin: 0 0 16px;
        font-size: 21px;
    }}

    .subtitle {{
        color: var(--muted);
    }}

    .status {{
        display: inline-block;
        margin-top: 14px;
        padding: 6px 12px;
        border-radius: 6px;
        font-size: 13px;
        font-weight: 700;
        background: {"#fee2e2" if result.stopped else "#dcfce7"};
        color: {"var(--stop)" if result.stopped else "var(--success)"};
    }}

    .summary {{
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
        gap: 14px;
        margin-bottom: 32px;
    }}

    .card {{
        background: var(--surface);
        border: 1px solid var(--border);
        border-radius: 8px;
        padding: 18px;
    }}

    .card-label {{
        color: var(--muted);
        font-size: 13px;
        margin-bottom: 5px;
    }}

    .card-value {{
        font-size: 26px;
        font-weight: 700;
    }}

    section {{
        background: var(--surface);
        border: 1px solid var(--border);
        border-radius: 8px;
        margin-bottom: 24px;
        overflow: hidden;
    }}

    section > .section-header {{
        padding: 18px 20px;
        border-bottom: 1px solid var(--border);
    }}

    .table-wrapper {{
        overflow-x: auto;
    }}

    table {{
        width: 100%;
        border-collapse: collapse;
        font-size: 14px;
    }}

    th,
    td {{
        padding: 11px 14px;
        text-align: left;
        vertical-align: top;
        border-bottom: 1px solid var(--border);
    }}

    th {{
        background: #f8fafc;
        color: #374151;
        font-size: 12px;
        text-transform: uppercase;
        letter-spacing: 0.04em;
        white-space: nowrap;
    }}

    tr:last-child td {{
        border-bottom: 0;
    }}

    code {{
        font-family:
            "SFMono-Regular",
            Consolas,
            "Liberation Mono",
            monospace;
        font-size: 13px;
    }}

    .badge {{
        display: inline-block;
        padding: 3px 8px;
        border-radius: 5px;
        font-size: 11px;
        font-weight: 700;
        text-transform: uppercase;
    }}

    .badge-ddl {{
        background: #dbeafe;
        color: #1e40af;
    }}

    .badge-dml {{
        background: #fef3c7;
        color: #92400e;
    }}

    .badge-dql {{
        background: #dcfce7;
        color: #166534;
    }}

    .severity-warning {{
        background: #fef3c7;
        color: var(--warning);
    }}

    .severity-error {{
        background: #fee2e2;
        color: var(--error);
    }}

    .severity-stop {{
        background: #fecaca;
        color: var(--stop);
    }}

    .severity-info {{
        background: #e0e7ff;
        color: #3730a3;
    }}

    .empty {{
        padding: 24px;
        color: var(--muted);
        text-align: center;
    }}

    .finding-message {{
        max-width: 700px;
        white-space: normal;
    }}

    footer {{
        color: var(--muted);
        font-size: 12px;
        padding: 8px 0 24px;
    }}

    @media (max-width: 700px) {{
        .container {{
            padding: 16px;
        }}

        h1 {{
            font-size: 24px;
        }}

        th,
        td {{
            padding: 9px 10px;
        }}
    }}
</style>
</head>

<body>
<div class="container">

<header>
    <h1>Oracle SQL Analysis Report</h1>
    <div class="subtitle">
        Static analysis of Oracle SQL and SQLPlus scripts
    </div>
    <div class="status">
        {"STOP POLICY DETECTED" if result.stopped else "ANALYSIS COMPLETED"}
    </div>
</header>

<div class="summary">
    {self._card("Files Scanned", result.files_scanned)}
    {self._card("Objects", len(objects))}
    {self._card("DDL", object_counts.get("DDL", 0))}
    {self._card("DML", object_counts.get("DML", 0))}
    {self._card("DQL", object_counts.get("DQL", 0))}
    {self._card("Warnings", severity_counts.get("WARNING", 0))}
    {self._card("Errors", severity_counts.get("ERROR", 0))}
    {self._card("Stops", severity_counts.get("STOP", 0))}
</div>

<section>
    <div class="section-header">
        <h2>Database Objects</h2>
    </div>

    {self._render_objects(objects)}
</section>

<section>
    <div class="section-header">
        <h2>Policy Findings</h2>
    </div>

    {self._render_findings(findings)}
</section>

<footer>
    Generated by Entropy Oracle SQL analysis.
</footer>

</div>
</body>
</html>
"""

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------

    @staticmethod
    def _card(
        label: str,
        value: int,
    ) -> str:
        """
        Render a summary card.
        """

        return f"""
<div class="card">
    <div class="card-label">{escape(label)}</div>
    <div class="card-value">{value}</div>
</div>
"""

    # ------------------------------------------------------------------
    # Objects
    # ------------------------------------------------------------------

    def _render_objects(
        self,
        objects: list[AnalyseObject],
    ) -> str:
        """
        Render the database object table.
        """

        if not objects:
            return """
<div class="empty">
    No database objects were discovered.
</div>
"""

        rows = []

        for obj in objects:
            category_class = (
                f"badge-{escape(obj.category.casefold())}"
            )

            rows.append(
                f"""
<tr>
    <td><code>{escape(obj.name)}</code></td>
    <td>{escape(obj.object_type)}</td>
    <td>{escape(obj.operation)}</td>
    <td>
        <span class="badge {category_class}">
            {escape(obj.category)}
        </span>
    </td>
    <td><code>{escape(obj.file.name)}</code></td>
    <td>{obj.line}:{obj.column or 1}</td>
</tr>
""",
            )

        return f"""
<div class="table-wrapper">
<table>
    <thead>
        <tr>
            <th>Name</th>
            <th>Type</th>
            <th>Operation</th>
            <th>Script</th>
            <th>File</th>
            <th>Location</th>
        </tr>
    </thead>
    <tbody>
        {"".join(rows)}
    </tbody>
</table>
</div>
"""

    # ------------------------------------------------------------------
    # Findings
    # ------------------------------------------------------------------

    def _render_findings(
        self,
        findings: list[AnalyseFinding],
    ) -> str:
        """
        Render the policy findings table.
        """

        if not findings:
            return """
<div class="empty">
    No policy violations detected.
</div>
"""

        rows = []

        for finding in findings:
            severity = finding.severity.upper()
            severity_class = (
                f"severity-{severity.casefold()}"
            )

            rows.append(
                f"""
<tr>
    <td>
        <span class="badge {severity_class}">
            {escape(severity)}
        </span>
    </td>
    <td><code>{escape(finding.rule)}</code></td>
    <td><code>{escape(finding.file.name)}</code></td>
    <td>{finding.line}:{finding.column or 1}</td>
    <td class="finding-message">
        {escape(finding.message)}
    </td>
</tr>
""",
            )

        return f"""
<div class="table-wrapper">
<table>
    <thead>
        <tr>
            <th>Severity</th>
            <th>Rule</th>
            <th>File</th>
            <th>Location</th>
            <th>Message</th>
        </tr>
    </thead>
    <tbody>
        {"".join(rows)}
    </tbody>
</table>
</div>
"""

    # ------------------------------------------------------------------
    # Sorting
    # ------------------------------------------------------------------

    @staticmethod
    def _object_sort_key(
        obj: AnalyseObject,
    ) -> tuple[str, int, int]:
        """
        Sort objects by file and source location.
        """

        return (
            str(obj.file).casefold(),
            obj.line,
            obj.column or 0,
        )

    @staticmethod
    def _finding_sort_key(
        finding: AnalyseFinding,
    ) -> tuple[str, int, int, str]:
        """
        Sort findings by file and source location.
        """

        return (
            str(finding.file).casefold(),
            finding.line,
            finding.column or 0,
            finding.rule.casefold(),
        )
