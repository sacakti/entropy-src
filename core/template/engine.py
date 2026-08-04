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

from .exceptions import TemplateNotFoundError


class TemplateEngine:

    def __init__(
        self,
        context,
    ):

        self.context = context

        self._environment = Environment(
            loader=FileSystemLoader(self.context.bootstrap.resources.templates),
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

        # print(f"Inside render: template={template}, destination={destination}, context={context}")
        try:

            # print(f"Getting template: {template}")
            tpl = self._environment.get_template(
                template,
            )

        except TemplateNotFound as ex:

            # print(f"Template not found: {template}")

            raise TemplateNotFoundError(
                template,
            ) from ex

        # print(f"Rendering template: {template} to destination: {destination}")

        content = tpl.render(**context)

        # print(f"Writing render content to destination: {destination}")
        self.context.executor.write_text(
            destination,
            content,
        )
        # print(f"Render complete: {template} to destination: {destination}")

        return destination
