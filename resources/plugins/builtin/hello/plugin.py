"""
Hello plugin.

Demonstrates the Entropy Plugin SDK.
"""

from __future__ import annotations

from time import sleep

from lib.plugins.base import BasePlugin
from lib.models.plugin import PluginResult

class HelloPlugin(BasePlugin):
    """
    Plugin implementation.
    """

    def execute(
        self,
    ) -> PluginResult:
        """
        Execute the plugin.
        """

        self.message.info(
            "Starting plugin execution."
        )

        with self.activity(
            "hello"
        ):

            self._execute()

        self.message.success(
            "Plugin completed successfully."
        )

        return PluginResult(
            success=True,
            changed=True,
            outputs=dict(
                self.outputs,
            ),
            metadata={
                "artifacts": {
                    name: str(path)
                    for name, path in self.artifacts.items()
                },
            },
        )

    # ------------------------------------------------------------------
    # Implementation
    # ------------------------------------------------------------------

    def _execute(
        self,
    ) -> None:

        #
        # Introduction
        #

        self.message.info(
            "Hello Entropy!"
        )

        self.message.info(
            f"Workspace : {self.workspace}"
        )

        self.message.info(
            f"Current User : {self.user}"
        )

        #
        # Filesystem
        #

        output = self.workspace / "hello.txt"

        with self.activity(
            "Create sample file",
        ):

            self.filesystem.write_text(
                output,
                "Hello from Entropy!",
            )

            sleep(1)

        self.outputs["message"] = "Hello"

        self.artifacts["hello"] = output

        self.message.success(
            f"Created '{output.name}'."
        )

        #
        # Shell
        #

        self.message.info(
            "Collecting system information."
        )

        with self.activity(
            "Execute uname -a",
        ):

            result = self.shell.run(
                [
                    "uname",
                    "-a",
                ]
            )

            sleep(1)

        self.ui.panel(
            "System Information",
            [
                result.stdout,
            ],
        )

        #
        # Summary
        #

        self.ui.table(
            title="Execution Summary",
            columns=[
                "Item",
                "Value",
            ],
            rows=[
                [
                    "User",
                    self.user,
                ],
                [
                    "Workspace",
                    str(self.workspace),
                ],
                [
                    "Artifact",
                    self.artifacts["hello"].name,
                ],
            ],
        )
