"""
Application runtime environment.
"""

from __future__ import annotations

from core.paths.manager import RuntimePathManager
from lib.executor import LinuxExecutor


class Environment:
    """
    Prepares the application runtime environment.

    This class is responsible only for creating the directory
    structure required by the application.
    """

    def __init__(
        self,
        executor: LinuxExecutor,
    ) -> None:

        self._executor = executor

    # ------------------------------------------------------------------
    # Public
    # ------------------------------------------------------------------

    def prepare(
        self,
        paths: RuntimePathManager,
    ) -> None:
        """
        Prepare the runtime environment.
        """

        self._create_directories(paths)

    # ------------------------------------------------------------------
    # Directories
    # ------------------------------------------------------------------

    def _create_directories(
        self,
        paths: RuntimePathManager,
    ) -> None:
        """
        Create all runtime directories.
        """

        directories = (
            paths.database.directory,

            paths.logs.root,

            paths.runtime.root,
            paths.runtime.pid,
            paths.runtime.state,
            paths.runtime.lock,

            paths.session.directory,

            paths.python.packages,

            #
            # Extensions
            #
            paths.extensions.root,
            paths.extensions.wheels,
            paths.extensions.site_packages,
            # paths.extensions.metadata,
            paths.extensions.cache,
            paths.extensions.downloads,
        )

        for directory in directories:

            self._executor.mkdir(
                directory,
                parents=True,
                exist_ok=True,
            )
