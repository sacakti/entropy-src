"""
Base command.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from argparse import ArgumentParser, Namespace


@dataclass(frozen=True)
class CommandMetadata:

    name: str

    description: str

    aliases: tuple[str, ...] = ()

    hidden: bool = False

    requires_admin: bool = False

    authentication_required: bool = True


class BaseCommand(ABC):

    metadata: CommandMetadata

    def __init__(self, context):

        self.context = context

    @abstractmethod
    def configure(
        self,
        parser: ArgumentParser,
    ) -> None:
        """
        Configure command arguments.
        """

    @abstractmethod
    def execute(
        self,
        args: Namespace,
    ) -> None:
        """
        Execute command.
        """