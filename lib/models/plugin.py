from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Plugin:

    name: str

    version: str

    path: Path

    namespace: str

    manifest: Path

    description: str

    author: str

    license: str

    commands: list[type] = field(default_factory=list)

    generators: list[type] = field(default_factory=list)

    hooks: list[type] = field(default_factory=list)

    @property
    def package(self) -> str:
        return f"plugins.{self.namespace}"

    @property
    def module(self) -> str:
        return f"{self.package}.{self.name}.plugin"

    @property
    def plugin_file(self) -> Path:

        return self.path / "plugin.py"

    @property
    def init_file(self) -> Path:

        return self.path / "__init__.py"

    @property
    def templates(self) -> Path:

        return self.path / "templates"

    @property
    def resources(self) -> Path:

        return self.path / "resources"
