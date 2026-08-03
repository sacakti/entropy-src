"""
Extension downloader.
"""

from __future__ import annotations

import sys

from core.context import EntropyContext

from lib.extensions.exceptions import ExtensionDownloadError
from lib.models.extensions import ExtensionManifest


class ExtensionDownloader:
    """
    Downloads extension wheels into the offline repository.
    """

    def __init__(
        self,
        context: EntropyContext,
    ) -> None:

        assert context.executor is not None
        assert context.paths is not None

        self._executor = context.executor
        self._paths = context.paths.extensions

    # ------------------------------------------------------------------
    # Public
    # ------------------------------------------------------------------

    def download(
        self,
        manifest: ExtensionManifest,
    ) -> None:
        """
        Download an extension wheel without installing it.
        """

        package = manifest.name

        if manifest.version:

            package = f"{package}=={manifest.version}"

        result = self._executor.run(
            [
                sys.executable,
                "-m",
                "pip",
                "download",
                "--disable-pip-version-check",
                "--dest",
                str(
                    self._paths.wheels,
                ),
                package,
            ],
        )

        if result.exit_code != 0:

            raise ExtensionDownloadError(
                result.stderr or result.stdout,
            )
