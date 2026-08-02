"""
Plugin generator.
"""

from core.constants import PluginTemplates
from core.generators.base import (
    BaseGenerator,
    GeneratorMetadata,
)
from core.generators.validators.plugin import PluginValidator


class PluginGenerator(BaseGenerator):

    metadata = GeneratorMetadata(
        name="plugin",
        description="Generate a new plugin.",
    )

    FILES = [
        (PluginTemplates.INIT, "__init__.py"),
        (PluginTemplates.MANIFEST, "plugin.json"),
        (PluginTemplates.PLUGIN, "plugin.py"),
    ]

    def build_context(self, name: str) -> dict:

        return {
            "name": name,
            "version": "1.0.0",
            "description": "",
            "author": "",
            "license": "ENT",
        }

    def generate(self, args) -> None:

        task = self.context.output.progress(f"Generating plugin '{args.name}'...")

        try:

            name = args.name

            context = self.build_context(name)

            plugin_root = self.context.bootstrap.resources.plugins

            PluginValidator.validate(
                name=name,
                plugin_root=self.context.bootstrap.resources.plugins,
            )

            plugin_directory = plugin_root / name
            temp_directory = plugin_root / f".{name}.tmp"

            self.context.executor.mkdir(temp_directory)

            try:
                for template, filename in self.FILES:

                    self.context.template.render(
                        template,
                        temp_directory / filename,
                        context,
                    )

                self.context.executor.move(
                    temp_directory,
                    plugin_directory,
                )

                self.context.output.cli.success(
                    f"Plugin '{name}' created at {plugin_directory}.",
                    task=task,
                )
            except Exception:

                self.context.executor.remove(temp_directory)
                self.context.output.cli.error(
                    f"Plugin '{name}' failed.",
                    task=task,
                )

                raise

        except Exception:

            self.context.output.cli.error(
                f"Plugin '{name}' failed.",
                task=task,
            )

            raise
