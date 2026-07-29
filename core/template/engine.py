"""
Jinja2 template rendering engine.
"""

from __future__ import annotations

from pathlib import Path

from jinja2 import (
    Environment,
    FileSystemLoader,
    TemplateNotFound,
)

from core.constants import TEMPLATE_DIR

from .exceptions import TemplateNotFoundError


class TemplateEngine:

    def __init__(
        self,
        context,
    ):

        self.context = context

        # template_directory = (
        #     Path(__file__).resolve().parents[2]
        #     / "templates"
        # )

        self._environment = Environment(
            loader=FileSystemLoader(TEMPLATE_DIR),
            autoescape=False,
            keep_trailing_newline=True,
            trim_blocks=True,
            lstrip_blocks=True,
        )

    # ------------------------------------------------------------------
    # Render
    # ------------------------------------------------------------------

    def render(
        self,
        template: str,
        destination: Path,
        context: dict | None = None,
    ) -> Path:

        context = context or {}

        try:

            tpl = self._environment.get_template(
                template,
            )

        except TemplateNotFound as ex:

            raise TemplateNotFoundError(
                template,
            ) from ex

        content = tpl.render(**context)

        self.context.executor.write_text(
            destination,
            content,
        )

        return destination
