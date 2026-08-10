"""
Plugin generator.
"""

from __future__ import annotations

from pathlib import Path

from core.generators.base import (
    BaseGenerator,
    GeneratorMetadata,
)
from core.generators.validators.plugin import PluginValidator


class PluginGenerator(
    BaseGenerator,
):
    """
    Generates plugin skeletons.
    """

    FILES = (
        ("plugin/__init__.py.j2", "__init__.py"),
        ("plugin/plugin.py.j2", "plugin.py"),
        ("plugin/plugin.json.j2", "plugin.json"),
        ("plugin/README.md.j2", "README.md"),
        ("plugin/workflow.json.j2", "workflow.json"),
        ("plugin/requirements.txt.j2", "requirements.txt"),
    )

    DIRECTORIES = ("migrations",)

    metadata = GeneratorMetadata(
        name="plugin",
        description="Generate a new plugin.",
    )

    def generate(
        self,
        args,
        context,
    ) -> Path:

        assert context.ui is not None
        assert context.observability is not None

        ui = context.ui

        events = context.observability.emitter(
            "generator",
        )

        namespace = args.namespace or "custom"

        name = args.name

        ui.rule(
            f"Generate Plugin : {namespace}.{name}",
        )

        root = self._context.bootstrap.resources.plugins

        events.log.info(
            "Validating plugin.",
        )

        PluginValidator.validate(
            namespace=namespace,
            name=name,
            root=root,
        )

        destination = PluginValidator.directory(
            root=root,
            namespace=namespace,
            name=name,
        )

        temporary = destination.with_name(
            f".{name}.tmp",
        )

        render_context = self._build_context(
            namespace,
            name,
        )

        events.log.info(
            "Creating temporary workspace.",
        )

        self._context.executor.mkdir(
            temporary,
        )

        try:

            events.log.info(
                "Rendering templates.",
            )

            self._render(
                temporary,
                render_context,
            )

            events.log.info(
                "Creating plugin directories.",
            )

            self._create_directories(
                temporary,
            )

            events.log.info(
                "Finalizing plugin.",
            )

            self._context.executor.move(
                temporary,
                destination,
            )

            events.log.success(
                f"Plugin '{namespace}.{name}' generated successfully.",
            )

            ui.print()

            ui.table(
                title="Plugin",
                columns=[
                    "Property",
                    "Value",
                ],
                rows=[
                    [
                        "Name",
                        f"{namespace}.{name}",
                    ],
                    [
                        "Plugin Directory",
                        str(destination),
                    ],
                ],
            )

            return destination

        except Exception:

            self._context.executor.remove(
                temporary,
            )

            raise

    def _render(
        self,
        destination: Path,
        context: dict,
    ) -> None:

        for template, filename in self.FILES:

            self._context.template.render(
                template,
                destination / filename,
                context,
            )

    def _create_directories(
        self,
        root: Path,
    ) -> None:

        for directory in self.DIRECTORIES:

            self._context.executor.mkdir(
                root / directory,
            )

    def _build_context(
        self,
        namespace: str,
        name: str,
    ) -> dict:

        return {
            "namespace": namespace,
            "name": name,
            "class_name": self._class_name(
                name,
            ),
            "version": "1.0.0",
            "description": "",
            "author": "",
            "license": "",
        }

    @staticmethod
    def _class_name(
        name: str,
    ) -> str:

        return (
            "".join(
                part.capitalize()
                for part in name.split(
                    "_",
                )
            )
            + "Plugin"
        )
