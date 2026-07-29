from abc import ABC, abstractmethod


class BaseMigration(ABC):

    VERSION: int = 0
    DESCRIPTION: str = ""

    def validate(self) -> None:  # noqa: B027
        """Optional validation before upgrade."""

    @abstractmethod
    def upgrade(self, connection) -> None: ...

    def dispose(self) -> None:  # noqa: B027
        """Optional cleanup after upgrade."""
