"""
Base command.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from argparse import ArgumentParser, Namespace
from dataclasses import dataclass

from lib.models.session import Session


@dataclass(frozen=True)
class CommandMetadata:

    name: str

    description: str

    aliases: tuple[str, ...] = ()

    hidden: bool = False

    authentication_required: bool = True


class BaseCommand(ABC):

    metadata: CommandMetadata

    def __init__(
        self,
        context,
    ) -> None:

        self.context = context

    # ------------------------------------------------------------------
    # Authentication
    # ------------------------------------------------------------------

    def _require_authentication(
        self,
    ) -> Session:
        """
        Require an authenticated session.
        """

        assert self.context.session_manager is not None

        return self.context.session_manager.require()

    # ------------------------------------------------------------------
    # Authorization
    # ------------------------------------------------------------------

    def _require_permission(
        self,
        permission: str,
    ) -> Session:
        """
        Require authentication and a specific permission.

        Returns
        -------
        Session
            The authenticated user session.

        Raises
        ------
        AuthenticationRequiredError
            If no authenticated session exists.

        AuthorizationRequiredError
            If the authenticated user lacks the permission.
        """

        session = self._require_authentication()

        assert self.context.authorization is not None

        self.context.authorization.require(
            session,
            permission,
        )

        return session

    # ------------------------------------------------------------------
    # Command
    # ------------------------------------------------------------------

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
