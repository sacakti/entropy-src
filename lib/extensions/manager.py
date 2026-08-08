"""
Extension manager.
"""

from __future__ import annotations
from pathlib import Path

from core.context import EntropyContext

from lib.database.repositories.extensions import ExtensionRepository
from lib.extensions.downloader import ExtensionDownloader
from lib.extensions.installer import OfflineInstaller
from lib.extensions.validator import ExtensionValidator
from lib.models.extensions import Extension, ExtensionManifest

from .exceptions import (
    ExtensionAlreadyInstalledError,
    ExtensionNotFoundError,
    ExtensionWheelNotFoundError,
)


class ExtensionManager:
    """
    Extension subsystem.

    Responsible for orchestrating extension lifecycle.
    """

    def __init__(
        self,
        context: EntropyContext,
    ) -> None:

        self._context = context

        # ------------------------------------------------------------------
        # Database
        # ------------------------------------------------------------------

        assert context.database_manager is not None

        self._repository = ExtensionRepository(
            context.database_manager.connection,
        )

        # ------------------------------------------------------------------
        # Services
        # ------------------------------------------------------------------

        self._validator = ExtensionValidator(
            context,
            self._repository,
        )

        self._installer = OfflineInstaller(
            context,
        )

        self._downloader = ExtensionDownloader(
            context,
        )

        # ------------------------------------------------------------------
        # Observability
        # ------------------------------------------------------------------

        assert context.observability is not None

        self._events = context.observability.emitter(
            "extensions",
        )

    # ------------------------------------------------------------------
    # Query
    # ------------------------------------------------------------------

    def exists(
        self,
        name: str,
    ) -> bool:
        """
        Return True if an extension is installed.
        """

        return self._repository.exists(
            name,
        )

    def list(
        self,
    ) -> list[Extension]:
        """
        Return installed extensions.
        """

        return self._repository.list()

    # ------------------------------------------------------------------
    # Installation
    # ------------------------------------------------------------------

    def install(
        self,
        manifest: ExtensionManifest,
    ) -> Extension:
        """
        Install an extension.
        """

        self._events.log.info(
            f"Installing extension '{manifest.name}'.",
        )

        if self._repository.exists(
            manifest.name,
        ):

            raise ExtensionAlreadyInstalledError(
                manifest.name,
            )

        wheel = self._validator.wheel(
            manifest.name,
        )

        if wheel is None:

            raise ExtensionWheelNotFoundError(
                manifest.name,
            )

        extension = self._installer.install(
            manifest,
            wheel,
        )

        self._repository.create(
            extension,
        )

        self._events.log.success(
            f"Extension '{extension.name}' installed.",
        )

        return extension

    # ------------------------------------------------------------------
    # Removal
    # ------------------------------------------------------------------

    def uninstall(
        self,
        name: str,
    ) -> None:
        """
        Uninstall an extension.
        """

        if not self._repository.exists(
            name,
        ):

            raise ExtensionNotFoundError(
                name,
            )

        extension = self._repository.get_by_name(
            name,
        )

        self._installer.uninstall(
            extension,
        )

        self._repository.delete(
            name,
        )

        self._events.log.success(
            f"Extension '{name}' uninstalled.",
        )

    # ------------------------------------------------------------------
    # Verification
    # ------------------------------------------------------------------

    def verify(
        self,
        name: str,
    ) -> None:
        """
        Verify an extension installation.
        """

        self._events.log.info(
            f"Verifying extension '{name}'.",
        )

        if not self._repository.exists(
            name,
        ):

            raise ExtensionNotFoundError(
                name,
            )

        extension = self._repository.get_by_name(
            name,
        )

        self._installer.verify(
            extension,
        )

        self._events.log.success(
            f"Extension '{name}' verified successfully.",
        )

    def repair(
        self,
        name: str,
    ) -> None:
        """
        Repair an extension installation.
        """

        self._events.log.info(
            f"Repairing extension '{name}'.",
        )

        if not self._repository.exists(
            name,
        ):

            raise ExtensionNotFoundError(
                name,
            )

        extension = self._repository.get_by_name(
            name,
        )

        wheel = (
            self._context.paths.extensions.wheels /
            extension.wheel
        )

        if not wheel.exists():

            raise ExtensionWheelNotFoundError(
                name,
            )

        repaired = self._installer.repair(
            extension,
            wheel,
        )

        self._repository.update(
            repaired,
        )

        self._installer.verify(
            repaired,
        )

        self._events.log.success(
            f"Extension '{name}' repaired successfully.",
        )

    def wheels(
        self,
    ) -> list[Path]:
        """
        Return locally available extension wheels.
        """

        return self._validator.wheels()

    # ------------------------------------------------------------------
    # Download
    # ------------------------------------------------------------------

    def download(
        self,
        manifest: ExtensionManifest,
    ) -> None:
        """
        Download an extension wheel.
        """

        self._events.log.info(
            f"Downloading extension '{manifest.name}'.",
        )

        self._downloader.download(
            manifest,
        )

        self._events.log.success(
            f"Extension '{manifest.name}' downloaded.",
        )
