"""
Web server command.
"""

from __future__ import annotations

from argparse import ArgumentParser, Namespace

from core.commands.base import (
    BaseCommand,
    CommandMetadata,
)


class WebCommand(BaseCommand):
    """
    Start, stop and inspect the Entropy web server.
    """

    metadata = CommandMetadata(
        name="web",
        description="Start, stop or inspect the Entropy web server.",
        authentication_required=False,
    )

    def __init__(
        self,
        context,
    ) -> None:

        super().__init__(
            context,
        )

        assert context.ui is not None

        self._ui = context.ui

    def configure(
        self,
        parser: ArgumentParser,
    ) -> None:

        parser.add_argument(
            "action",
            choices=("start", "stop", "restart", "status", "run"),
            nargs="?",
            default="status",
            help="start | stop | restart | status | run (foreground).",
        )

    def execute(
        self,
        args: Namespace,
    ) -> None:

        from lib.system import web

        if args.action == "run":
            from core.web.__main__ import main

            main()
            return

        action = {
            "start": web.start,
            "stop": web.stop,
            "restart": web.restart,
            "status": web.status,
        }[args.action]
        state = action()

        if state["running"]:
            health = "healthy" if state["healthy"] else "starting"
            self._ui.print(f"Entropy web server is running ({health}) at {state['url']}")
        else:
            self._ui.print("Entropy web server is stopped.")
        self._ui.print(f"Supervisor: {state['supervisor']}  Log: {state['log']}")
