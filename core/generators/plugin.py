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

    DIRECTORIES = (
        "migrations",
    )

    metadata = GeneratorMetadata(
        name="plugin",
        description="Generate a new plugin.",
    )

    # ------------------------------------------------------------------
    # Generate
    # ------------------------------------------------------------------

    def generate(
        self,
        args,
        context,
    ) -> Path:
        """
        Generate a plugin.
        """

        ui = context.ui

        namespace = (
            args.namespace
            or "custom"
        )

        name = args.name

        ui.rule(
            f"Generate Plugin : {namespace}.{name}",
        )

        root = (
            self._context.bootstrap.resources.plugins
        )

        #
        # Validate
        #

        ui.info("Validating plugin...")

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

        #
        # Prepare
        #

        ui.info("Creating temporary workspace...")

        self._context.executor.mkdir(
            temporary,
        )

        try:

            #
            # Render
            #

            ui.info("Rendering templates...")

            self._render(
                temporary,
                render_context,
            )

            #
            # Directories
            #

            ui.info("Creating plugin directories...")

            self._create_directories(
                temporary,
            )

            #
            # Finalize
            #

            ui.info("Finalizing plugin...")

            self._context.executor.move(
                temporary,
                destination,
            )
            ui.print()
            ui.success(
                f"Plugin '{namespace}.{name}' generated successfully."
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

    # ------------------------------------------------------------------
    # Rendering
    # ------------------------------------------------------------------

    def _render(
        self,
        destination: Path,
        context: dict,
    ) -> None:
        """
        Render plugin templates.
        """

        for template, filename in self.FILES:

            self._context.template.render(
                template,
                destination / filename,
                context,
            )

    # ------------------------------------------------------------------
    # Directories
    # ------------------------------------------------------------------

    def _create_directories(
        self,
        root: Path,
    ) -> None:
        """
        Create plugin directories.
        """

        for directory in self.DIRECTORIES:

            self._context.executor.mkdir(
                root / directory,
            )

    # ------------------------------------------------------------------
    # Context
    # ------------------------------------------------------------------

    def _build_context(
        self,
        namespace: str,
        name: str,
    ) -> dict:
        """
        Build template context.
        """

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

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _class_name(
        name: str,
    ) -> str:
        """
        Convert a plugin name into a class name.
        """

        return (
            "".join(
                part.capitalize()
                for part in name.split(
                    "_",
                )
            )
            + "Plugin"
        )
