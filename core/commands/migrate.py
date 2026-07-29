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

    metadata = CommandMetadata(
        name="migrate",
        description="Execute pending database migrations.",
        authentication_required=True,
    )

    def configure(
        self,
        parser: ArgumentParser,
    ) -> None:
        """
        Configure command arguments.
        """

        #
        # No arguments required.
        #

    def execute(
        self,
        args: Namespace,
    ) -> None:
        """
        Execute pending migrations.
        """

        self.context.database_manager.migrate()