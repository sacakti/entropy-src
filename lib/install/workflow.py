"""
Default workflow installation.
"""

from __future__ import annotations

import shutil

from core.context import EntropyContext


class DefaultWorkflowInstaller:
    """
    Installs workflows shipped with Entropy.
    """

    def __init__(
        self,
        context: EntropyContext,
    ) -> None:

        assert context.bootstrap is not None
        assert context.paths is not None

        self._bootstrap = context.bootstrap
        self._paths = context.paths

    # ------------------------------------------------------------------
    # Public
    # ------------------------------------------------------------------

    def install(self) -> None:
        """
        Install the default workflow into the configured workspace.
        """

        source = self._bootstrap.project_root / "lib" / "install" / "default.workflow.json.config"

        destination = self._paths.workspace.workflows / "hello.json"

        destination.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        if destination.exists():
            return

        shutil.copy2(
            source,
            destination,
        )
