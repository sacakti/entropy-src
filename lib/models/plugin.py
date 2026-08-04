from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


@dataclass
class Plugin:

    id: int | None = None

    namespace: str

    name: str

    version: str

    path: Path

    enabled: bool = True

    installed_at: datetime | None = None

    @property
    def qualified_name(self) -> str:

        return f"{self.namespace}.{self.name}"

    @property
    def module_file(
        self,
    ) -> Path:
        """
        Plugin implementation.
        """

        return self.path / "plugin.py"
