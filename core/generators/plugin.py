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
        ("plugin/commands.py.j2", "commands.py"),
        ("plugin/exceptions.py.j2", "exceptions.py"),
    )

    metadata = GeneratorMetadata(
        name="plugin",
        description="Generate a new plugin.",
    )

    TEMPLATE = "plugin"

    # ------------------------------------------------------------------
    # Public
    # ------------------------------------------------------------------

    def generate(
        self,
        args,
        context,
    ) -> None:
        """
        Generate a plugin.
        """

        self.logger = context.observability.emitter(
            "generator",
        )

        namespace = (
            args.namespace
            or
            "custom"
        )

        self.logger.debug(f"Generating plugin: namespace={namespace}, name={args.name}")

        name = args.name

        root = (
            self._context.bootstrap.resources.plugins
        )

        self.logger.debug(f"Validating plugin")

        PluginValidator.validate(
            namespace=namespace,
            name=name,
            root=root,
        )

        self.logger.debug(f"Plugin validated")

        destination = PluginValidator.directory(
            root=root,
            namespace=namespace,
            name=name,
        )

        self.logger.debug(f"Plugin Generation Destination: {destination}")

        temporary = destination.with_name(
            f".{name}.tmp",
        )

        self.logger.debug(f"Plugin Generation Destination(temporary): {temporary}")

        context = self._build_context(
            namespace,
            name,
        )

        #
        # Create temporary directory.
        #

        self.logger.debug(f"Creating Plugin Generation Destination(temporary): {temporary}")

        self._context.executor.mkdir(
            temporary,
        )

        try:

            self.logger.debug(f"Render: {context}")
            self._render(
                temporary,
                context,
            )

            self.logger.debug(f"Creating migration folder")

            self._context.executor.mkdir(
                temporary /
                "migrations",
            )

            self.logger.debug(f"Moving to original templates folder")
            self._context.executor.move(
                temporary,
                destination,
            )
            self.logger.info(f"Plugin '{name}' generated.")
            self.logger.info(f"Plugin directory: {destination}")
            return destination

        except Exception as e:

            self.logger.error(f"Plugin template generation failed. Unknow error occured. Error: {e}")

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

        self.logger.debug(f"Rending plugin templates to {destination}")
        for template, filename in self.FILES:

            self.logger.debug(f"Rendering {template} to {filename}")

            self._context.template.render(
                template,
                destination / filename,
                context,
            )
            self.logger.debug(f"Rendered {template} to {filename}")

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
