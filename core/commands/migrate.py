"""
Database migration command.
"""

from argparse import (
    ArgumentParser,
    Namespace,
)

from core.commands.base import (
    BaseCommand,
    CommandMetadata,
)


class MigrateCommand(BaseCommand):
    """
    Apply pending database migrations.
    """

    metadata = CommandMetadata(
        name="migrate",
        description="Apply pending database migrations.",
        authentication_required=False,
        aliases=("mig",),
    )

    # ------------------------------------------------------------------
    # Configure
    # ------------------------------------------------------------------

    def configure(
        self,
        parser: ArgumentParser,
    ) -> None:
        """
        Configure command-line arguments.
        """

        pass

    # ------------------------------------------------------------------
    # Execute
    # ------------------------------------------------------------------

    def execute(
        self,
        args: Namespace,
    ) -> None:
        """
        Apply pending database migrations.
        """

        assert self.context.migration_manager is not None

        self.context.migration_manager.migrate()
