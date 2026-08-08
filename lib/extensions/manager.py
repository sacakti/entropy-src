"""
Extension manager.
"""

from __future__ import annotations

from core.context import EntropyContext
from lib.extensions.downloader import ExtensionDownloader

from .exceptions import (
    ExtensionAlreadyInstalledError,
    ExtensionNotFoundError,
    ExtensionWheelNotFoundError,
)
from lib.extensions.installer import OfflineInstaller
from lib.extensions.metadata import ExtensionMetadata
from lib.models.extensions import Extension, ExtensionManifest
from lib.extensions.validator import ExtensionValidator


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

        self._metadata = ExtensionMetadata(
            context,
        )

        self._validator = ExtensionValidator(
            context,
            self._metadata,
        )

        self._installer = OfflineInstaller(
            context,
        )

        self._downloader = ExtensionDownloader(
            context,
        )

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

        return self._validator.exists(
            name,
        )

    def list(
        self,
    ) -> list[Extension]:
        """
        Return installed extensions.
        """

        return self._metadata.list()

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

        if self._validator.exists(
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

        self._metadata.register(
            extension,
        )

        # self._events.log.info(
        #     f"Extension '{extension.name}' installed.",
        # )

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

        if not self._validator.exists(
            name,
        ):

            raise ExtensionNotFoundError(
                name,
            )

        extension = self._metadata.get(
            name,
        )

        self._installer.uninstall(
            extension,
        )

        self._metadata.unregister(
            name,
        )

        # self._events.log.info(
        #     f"Extension '{name}' uninstalled.",
        # )

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

        self._validator.verify(
            name,
        )

    def repair(
        self,
        name: str,
    ) -> None:
        """
        Repair an extension installation.
        """

        raise NotImplementedError()

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
