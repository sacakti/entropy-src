"""
HTML report generation for SQLPlus post-validation.
"""

from __future__ import annotations

import base64
import html
from pathlib import Path
from typing import Any

from .model import (
    OperationCount,
    ValidationAssociateResult,
    ValidationFileResult,
    ValidationResult,
)


class PostValidationReportBuilder:
    """
    Build the post-validation HTML dashboard.
    """

    def build(
        self,
        *,
        result: ValidationResult,
        output: Path,
        embed_log: bool = True,
    ) -> Path:
        """
        Render the validation result as an HTML dashboard.
        """

        output.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        document = self._render(
            result=result,
            embed_log=embed_log,
        )

        output.write_text(
            document,
            encoding="utf-8",
        )

        return output

    def build_log_analysis(
        self,
        *,
        log_path: Path,
        analysis: dict[str, Any],
        output: Path,
        release: str,
        embed_log: bool = True,
    ) -> Path:
        """
        Build an HTML report from deployment-log analysis only.

        No expected operation counts are inferred in this mode.
        """

        output.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        document = self._render_log_analysis(
            log_path=log_path,
            analysis=analysis,
            release=release,
            embed_log=embed_log,
        )

        output.write_text(
            document,
            encoding="utf-8",
        )

        return output

    # ------------------------------------------------------------------
    # Document
    # ------------------------------------------------------------------

    def _render(
        self,
        *,
        result: ValidationResult,
        embed_log: bool,
    ) -> str:
        associates = "\n".join(
            self._render_associate(
                associate,
            )
            for associate in result.associates
        )

        embedded_log = self._render_log(
            result.log_path,
        ) if embed_log else ""

        status = (
            "PASS"
            if result.success
            else "FAIL"
        )

        return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport"
      content="width=device-width, initial-scale=1">
<title>
    {self._escape(result.release)}
    - Post Validation Dashboard
</title>

<style>
    * {{
        box-sizing: border-box;
    }}

    body {{
        margin: 0;
        padding: 0;
        background: #f4f6f8;
        color: #202124;
        font-family:
            -apple-system,
            BlinkMacSystemFont,
            "Segoe UI",
            Roboto,
            Arial,
            sans-serif;
    }}

    .container {{
        width: min(1500px, 96%);
        margin: 0 auto;
        padding: 24px 0 48px;
    }}

    .header {{
        display: flex;
        justify-content: space-between;
        align-items: flex-start;
        gap: 24px;
        margin-bottom: 24px;
    }}

    .title {{
        margin: 0;
        font-size: 28px;
        font-weight: 700;
    }}

    .subtitle {{
        margin-top: 6px;
        color: #667085;
        font-size: 14px;
    }}

    .status {{
        border-radius: 999px;
        padding: 8px 16px;
        font-weight: 700;
        font-size: 13px;
    }}

    .status.pass {{
        background: #dcfce7;
        color: #166534;
    }}

    .status.fail {{
        background: #fee2e2;
        color: #991b1b;
    }}

    .cards {{
        display: grid;
        grid-template-columns:
            repeat(auto-fit, minmax(150px, 1fr));
        gap: 12px;
        margin-bottom: 24px;
    }}

    .card {{
        background: white;
        border: 1px solid #e4e7ec;
        border-radius: 10px;
        padding: 16px;
    }}

    .card-label {{
        color: #667085;
        font-size: 12px;
        text-transform: uppercase;
        letter-spacing: .04em;
    }}

    .card-value {{
        margin-top: 6px;
        font-size: 26px;
        font-weight: 700;
    }}

    .panel {{
        background: white;
        border: 1px solid #e4e7ec;
        border-radius: 10px;
        margin-bottom: 16px;
        overflow: hidden;
    }}

    .panel-header {{
        padding: 16px 18px;
        border-bottom: 1px solid #e4e7ec;
        font-size: 16px;
        font-weight: 700;
    }}

    .associate {{
        border-bottom: 1px solid #e4e7ec;
    }}

    .associate:last-child {{
        border-bottom: 0;
    }}

    .associate-summary {{
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 16px;
        padding: 14px 18px;
        cursor: pointer;
    }}

    .associate-name {{
        font-weight: 700;
    }}

    .associate-meta {{
        color: #667085;
        font-size: 12px;
        margin-top: 4px;
    }}

    .badge {{
        display: inline-block;
        border-radius: 999px;
        padding: 4px 9px;
        font-size: 11px;
        font-weight: 700;
        text-transform: uppercase;
    }}

    .badge.pass {{
        background: #dcfce7;
        color: #166534;
    }}

    .badge.fail {{
        background: #fee2e2;
        color: #991b1b;
    }}

    .badge.partial {{
        background: #fef3c7;
        color: #92400e;
    }}

    .badge.notrun {{
        background: #e5e7eb;
        color: #374151;
    }}

    .associate-body {{
        padding: 0 18px 18px;
    }}

    table {{
        width: 100%;
        border-collapse: collapse;
        font-size: 13px;
    }}

    th {{
        background: #f8fafc;
        color: #475467;
        text-align: left;
        font-weight: 600;
    }}

    th,
    td {{
        border-bottom: 1px solid #eaecf0;
        padding: 9px 8px;
        vertical-align: top;
    }}

    tr:last-child td {{
        border-bottom: 0;
    }}

    .muted {{
        color: #667085;
    }}

    .error {{
        color: #991b1b;
    }}

    .warning {{
        color: #92400e;
    }}

    .ok {{
        color: #166534;
    }}

    .section-title {{
        margin: 18px 0 8px;
        font-size: 14px;
        font-weight: 700;
    }}

    .empty {{
        padding: 12px 0;
        color: #667085;
        font-size: 13px;
    }}

    .log {{
        background: #101828;
        color: #e5e7eb;
        border-radius: 8px;
        padding: 16px;
        overflow: auto;
        max-height: 650px;
        white-space: pre;
        font: 12px/1.5
            ui-monospace,
            SFMono-Regular,
            Menlo,
            Monaco,
            Consolas,
            monospace;
    }}

    @media (max-width: 800px) {{
        .header {{
            flex-direction: column;
        }}

        .associate-summary {{
            align-items: flex-start;
            flex-direction: column;
        }}

        table {{
            display: block;
            overflow-x: auto;
        }}
    }}
</style>
</head>

<body>
<div class="container">

    <div class="header">
        <div>
            <h1 class="title">
                Post Validation Dashboard
            </h1>

            <div class="subtitle">
                Release:
                <strong>{self._escape(result.release)}</strong>
                <br>
                Log:
                {self._escape(result.log_path.name)}
            </div>
        </div>

        <div class="status {status.lower()}">
            {status}
        </div>
    </div>

    {self._render_summary(result)}

    <div class="panel">
        <div class="panel-header">
            Associate Validation
        </div>

        {associates}
    </div>

    {embedded_log}

</div>
</body>
</html>
"""

    # ------------------------------------------------------------------
    # Log-only analysis
    # ------------------------------------------------------------------

    def _render_log_analysis(
        self,
        *,
        log_path: Path,
        analysis: dict[str, Any],
        release: str,
        embed_log: bool,
    ) -> str:
        per_file = analysis.get(
            "per_file",
            {},
        )

        errors = analysis.get(
            "errors",
            [],
        )

        notes = analysis.get(
            "notes",
            [],
        )

        files_scanned = len(per_file)

        status = (
            "FAIL"
            if errors
            else "ANALYZED"
        )

        file_rows = "\n".join(
            self._render_log_analysis_file(
                file_name=file_name,
                data=data,
            )
            for file_name, data in sorted(
                per_file.items(),
                key=lambda item: str(item[0]).casefold(),
            )
        )

        embedded_log = (
            self._render_log(
                log_path,
            )
            if embed_log
            else ""
        )

        error_section = self._render_log_analysis_messages(
            title="Errors",
            messages=errors,
            css_class="error",
        )

        note_section = self._render_log_analysis_messages(
            title="Advisory Notes",
            messages=notes,
            css_class="warning",
        )

        return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport"
      content="width=device-width, initial-scale=1">

<title>
    {self._escape(release)}
    - Post Validation Log Analysis
</title>

<style>
    * {{
        box-sizing: border-box;
    }}

    body {{
        margin: 0;
        padding: 0;
        background: #f4f6f8;
        color: #202124;
        font-family:
            -apple-system,
            BlinkMacSystemFont,
            "Segoe UI",
            Roboto,
            Arial,
            sans-serif;
    }}

    .container {{
        width: min(1500px, 96%);
        margin: 0 auto;
        padding: 24px 0 48px;
    }}

    .header {{
        display: flex;
        justify-content: space-between;
        align-items: flex-start;
        gap: 24px;
        margin-bottom: 24px;
    }}

    .title {{
        margin: 0;
        font-size: 28px;
        font-weight: 700;
    }}

    .subtitle {{
        margin-top: 6px;
        color: #667085;
        font-size: 14px;
    }}

    .status {{
        border-radius: 999px;
        padding: 8px 16px;
        font-weight: 700;
        font-size: 13px;
    }}

    .status.analyzed {{
        background: #e0f2fe;
        color: #075985;
    }}

    .status.fail {{
        background: #fee2e2;
        color: #991b1b;
    }}

    .cards {{
        display: grid;
        grid-template-columns:
            repeat(auto-fit, minmax(160px, 1fr));
        gap: 12px;
        margin-bottom: 24px;
    }}

    .card {{
        background: white;
        border: 1px solid #e4e7ec;
        border-radius: 10px;
        padding: 16px;
    }}

    .card-label {{
        color: #667085;
        font-size: 12px;
        text-transform: uppercase;
        letter-spacing: .04em;
    }}

    .card-value {{
        margin-top: 6px;
        font-size: 26px;
        font-weight: 700;
    }}

    .panel {{
        background: white;
        border: 1px solid #e4e7ec;
        border-radius: 10px;
        margin-bottom: 16px;
        overflow: hidden;
    }}

    .panel-header {{
        padding: 16px 18px;
        border-bottom: 1px solid #e4e7ec;
        font-size: 16px;
        font-weight: 700;
    }}

    .panel-body {{
        padding: 18px;
    }}

    table {{
        width: 100%;
        border-collapse: collapse;
        font-size: 13px;
    }}

    th {{
        background: #f8fafc;
        color: #475467;
        text-align: left;
        font-weight: 600;
    }}

    th,
    td {{
        border-bottom: 1px solid #eaecf0;
        padding: 9px 8px;
        vertical-align: top;
    }}

    tr:last-child td {{
        border-bottom: 0;
    }}

    .muted {{
        color: #667085;
    }}

    .error {{
        color: #991b1b;
    }}

    .warning {{
        color: #92400e;
    }}

    .ok {{
        color: #166534;
    }}

    .section-title {{
        margin: 18px 0 8px;
        font-size: 14px;
        font-weight: 700;
    }}

    .empty {{
        padding: 12px 0;
        color: #667085;
        font-size: 13px;
    }}

    .log {{
        background: #101828;
        color: #e5e7eb;
        border-radius: 8px;
        padding: 16px;
        overflow: auto;
        max-height: 650px;
        white-space: pre;
        font: 12px/1.5
            ui-monospace,
            SFMono-Regular,
            Menlo,
            Monaco,
            Consolas,
            monospace;
    }}

    @media (max-width: 800px) {{
        .header {{
            flex-direction: column;
        }}

        table {{
            display: block;
            overflow-x: auto;
        }}
    }}
</style>
</head>

<body>
<div class="container">

    <div class="header">
        <div>
            <h1 class="title">
                Post Validation Log Analysis
            </h1>

            <div class="subtitle">
                Application:
                <strong>{self._escape(release)}</strong>
                <br>
                Log:
                {self._escape(log_path.name)}
                <br>
                Mode:
                <strong>Log-only analysis</strong>
            </div>
        </div>

        <div class="status {status.lower()}">
            {status}
        </div>
    </div>

    <div class="cards">
        {self._card(
            "Files Analyzed",
            files_scanned,
        )}

        {self._card(
            "Errors",
            len(errors),
        )}

        {self._card(
            "Advisory Notes",
            len(notes),
        )}
    </div>

    <div class="panel">
        <div class="panel-header">
            Script Analysis
        </div>

        <div class="panel-body">

            {
                f'''
                <table>
                    <thead>
                        <tr>
                            <th>File</th>
                            <th>DML</th>
                            <th>DDL</th>
                            <th>Blocks</th>
                            <th>Success</th>
                        </tr>
                    </thead>
                    <tbody>
                        {file_rows}
                    </tbody>
                </table>
                '''
                if file_rows
                else '<div class="empty">No script activity found in the log.</div>'
            }

            {error_section}

            {note_section}

        </div>
    </div>

    {embedded_log}

</div>
</body>
</html>
"""

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------

    def _render_summary(
        self,
        result: ValidationResult,
    ) -> str:
        return f"""
<div class="cards">

    {self._card(
        "Associates",
        len(result.associates),
    )}

    {self._card(
        "Passed",
        result.passed,
    )}

    {self._card(
        "Failed",
        result.failed,
    )}

    {self._card(
        "Partial",
        result.partial,
    )}

    {self._card(
        "Not Run",
        result.notrun,
    )}

    {self._card(
        "Errors",
        result.error_lines,
    )}

    {self._card(
        "Mismatches",
        result.count_mismatches,
    )}

</div>
"""

    @staticmethod
    def _card(
        label: str,
        value: int,
    ) -> str:
        return f"""
<div class="card">
    <div class="card-label">
        {html.escape(label)}
    </div>
    <div class="card-value">
        {value}
    </div>
</div>
"""

    # ------------------------------------------------------------------
    # Associate
    # ------------------------------------------------------------------

    def _render_associate(
        self,
        associate: ValidationAssociateResult,
    ) -> str:
        files = "\n".join(
            self._render_file(
                file,
            )
            for file in associate.files
        )

        errors = self._render_errors(
            associate,
        )

        notes = self._render_notes(
            associate,
        )

        return f"""
<details class="associate" open>
    <summary class="associate-summary">
        <div>
            <div class="associate-name">
                {self._escape(associate.name)}
            </div>

            <div class="associate-meta">
                Files:
                {len(associate.files)}
                &nbsp;·&nbsp;
                Errors:
                {len(associate.errors)}
                &nbsp;·&nbsp;
                Mismatches:
                {len(associate.mismatches)}
            </div>
        </div>

        <span class="badge {associate.status}">
            {self._escape(associate.status)}
        </span>
    </summary>

    <div class="associate-body">

        <div class="section-title">
            Files
        </div>

        {
            f'''
            <table>
                <thead>
                    <tr>
                        <th>File</th>
                        <th>JIRA</th>
                        <th>Schema</th>
                        <th>DML</th>
                        <th>DDL</th>
                        <th>Blocks</th>
                        <th>Status</th>
                    </tr>
                </thead>
                <tbody>
                    {files}
                </tbody>
            </table>
            '''
            if files
            else '<div class="empty">No files found.</div>'
        }

        {errors}

        {notes}

    </div>
</details>
"""

    # ------------------------------------------------------------------
    # File
    # ------------------------------------------------------------------

    def _render_file(
        self,
        file: ValidationFileResult,
    ) -> str:
        dml = self._format_counts(
            file.dml,
        )

        ddl = self._format_counts(
            file.ddl,
        )

        blocks = (
            f"{file.blocks_completed}/"
            f"{file.blocks_expected}"
        )

        if file.blocks_expected:
            blocks += (
                f" "
                f"(clean: {file.blocks_clean})"
            )

        status_class = file.status

        return f"""
<tr>
    <td>
        {self._escape(file.file)}
        <div class="muted">
            {self._escape(file.folder)}
        </div>
    </td>

    <td>
        {self._escape(file.jira)}
    </td>

    <td>
        {self._escape(file.schema)}
    </td>

    <td>
        {dml}
    </td>

    <td>
        {ddl}
    </td>

    <td>
        {self._escape(blocks)}
    </td>

    <td>
        <span class="badge {status_class}">
            {self._escape(file.status)}
        </span>
    </td>
</tr>
"""

    # ------------------------------------------------------------------
    # Errors / notes
    # ------------------------------------------------------------------

    def _render_errors(
        self,
        associate: ValidationAssociateResult,
    ) -> str:
        if not associate.errors:
            return ""

        rows = "\n".join(
            f"""
<li class="error">
    {self._escape(error.file)}
    :
    line {error.line}
    —
    {self._escape(error.message)}
</li>
"""
            for error in associate.errors
        )

        return f"""
<div class="section-title">
    Errors
</div>

<ul>
    {rows}
</ul>
"""

    def _render_notes(
        self,
        associate: ValidationAssociateResult,
    ) -> str:
        if not associate.notes:
            return ""

        rows = "\n".join(
            f"""
<li class="warning">
    {self._escape(note.file)}
    :
    line {note.line}
    —
    {self._escape(note.message)}
</li>
"""
            for note in associate.notes
        )

        return f"""
<div class="section-title">
    Advisory Notes
</div>

<ul>
    {rows}
</ul>
"""

    # ------------------------------------------------------------------
    # Raw log
    # ------------------------------------------------------------------

    def _render_log(
        self,
        path: Path,
    ) -> str:
        try:
            content = path.read_text(
                encoding="utf-8",
                errors="replace",
            )
        except OSError as exc:
            return f"""
<div class="panel">
    <div class="panel-header">
        Raw Deployment Log
    </div>

    <div class="associate-body">
        <div class="error">
            Unable to embed log:
            {self._escape(str(exc))}
        </div>
    </div>
</div>
"""

        encoded = base64.b64encode(
            content.encode(
                "utf-8",
            ),
        ).decode(
            "ascii",
        )

        escaped = self._escape(
            content,
        )

        return f"""
<div class="panel">
    <div class="panel-header">
        Raw Deployment Log
    </div>

    <div class="associate-body">

        <p>
            <a
                download="{self._escape(path.name)}"
                href="data:text/plain;base64,{encoded}"
            >
                Download log
            </a>
        </p>

        <details>
            <summary>
                Show embedded log
            </summary>

            <pre class="log">{escaped}</pre>
        </details>

    </div>
</div>
"""

    # ------------------------------------------------------------------
    # Formatting
    # ------------------------------------------------------------------

    @staticmethod
    def _format_counts(
        counts: tuple[OperationCount, ...],
    ) -> str:
        if not counts:
            return '<span class="muted">—</span>'

        values: list[str] = []

        for count in counts:

            text = (
                f"{count.operation}: "
                f"{count.actual}/"
                f"{count.expected}"
            )

            if count.expected > count.actual:
                values.append(
                    f'<span class="error">'
                    f'{html.escape(text)}'
                    f'</span>',
                )

            else:
                values.append(
                    f'<span class="ok">'
                    f'{html.escape(text)}'
                    f'</span>',
                )

        return "<br>".join(values)

    @staticmethod
    def _escape(
        value: object,
    ) -> str:
        return html.escape(
            str(value),
            quote=True,
        )

    def _render_log_analysis_file(
        self,
        *,
        file_name: str,
        data: dict[str, Any],
    ) -> str:
        dml = self._format_log_counts(
            data.get("dml"),
        )

        ddl = self._format_log_counts(
            data.get("ddl"),
        )

        blocks_completed = data.get(
            "blocks_ok",
            0,
        )

        blocks_clean = data.get(
            "blocks_clean",
            0,
        )

        success = data.get(
            "success",
            0,
        )

        blocks = str(
            blocks_completed,
        )

        if blocks_completed:
            blocks += (
                f" "
                f"(clean: {blocks_clean})"
            )

        return f"""
<tr>
    <td>
        {self._escape(file_name)}
    </td>

    <td>
        {dml}
    </td>

    <td>
        {ddl}
    </td>

    <td>
        {self._escape(blocks)}
    </td>

    <td>
        {
            '<span class="ok">Yes</span>'
            if success
            else '<span class="muted">—</span>'
        }
    </td>
</tr>
"""

    @staticmethod
    def _format_log_counts(
        counts: Any,
    ) -> str:
        if not counts:
            return '<span class="muted">—</span>'

        if hasattr(
            counts,
            "items",
        ):
            values = counts.items()
        else:
            values = counts

        rendered: list[str] = []

        for operation, count in values:
            rendered.append(
                f"{html.escape(str(operation))}: "
                f"{html.escape(str(count))}"
            )

        return "<br>".join(rendered)

    def _render_log_analysis_messages(
        self,
        *,
        title: str,
        messages: Any,
        css_class: str,
    ) -> str:
        if not messages:
            return ""

        rows: list[str] = []

        for message in messages:
            if hasattr(
                message,
                "file",
            ):
                file_name = message.file
                line = message.line
                text = message.message

                rows.append(
                    f"""
<li class="{css_class}">
    {self._escape(file_name)}
    :
    line {line}
    —
    {self._escape(text)}
</li>
"""
                )

            else:
                rows.append(
                    f"""
<li class="{css_class}">
    {self._escape(message)}
</li>
"""
                )

        return f"""
<div class="section-title">
    {self._escape(title)}
</div>

<ul>
    {"".join(rows)}
</ul>
"""
