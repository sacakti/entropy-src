"""
Plugin generator.
"""

from core.constants import PLUGIN_DIR, PluginTemplates
from core.generators.base import (
    BaseGenerator,
    GeneratorMetadata,
)


class PluginGenerator(BaseGenerator):

    metadata = GeneratorMetadata(
        name="plugin",
        description="Generate a new plugin.",
    )

    def generate(self, args) -> None:

        self.context.output.cli.info(
            f"Generating plugin '{args.name}'..."
        )

        name = args.name

        plugin_directory = PLUGIN_DIR / name

        self.context.executor.mkdir(plugin_directory)

        self.context.template.render(
            PluginTemplates.INIT,
            plugin_directory / "__init__.py",
            {
                "name": name,
            },
        )

        self.context.template.render(
            PluginTemplates.MANIFEST,
            plugin_directory / "plugin.json",
            {
                "name": name,
            },
        )

        self.context.output.cli.success(
            f"Plugin '{name}' created."
        )