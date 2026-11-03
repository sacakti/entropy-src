"""
A run's report: the run page as a file to keep or send, as a web page or a PDF.

It shows what the page shows, including step results and console output, so it deserves the
care that page does. Anyone who can see the run can download it.
"""

from __future__ import annotations

from .html_report import render_html
from .model import build_report, collect_events, read_console, resolve_zone
from .pdf_report import render_pdf

__all__ = [
    "build_report",
    "collect_events",
    "read_console",
    "render_html",
    "render_pdf",
    "resolve_zone",
]
