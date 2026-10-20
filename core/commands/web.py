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
            choices=("start", "stop", "restart", "status", "run", "config"),
            nargs="?",
            default="status",
            help="start | stop | restart | status | run (foreground) | config.",
        )

        parser.add_argument(
            "--host",
            help="config: address to listen on (0.0.0.0 = every network interface, "
            "so nodes and other machines can connect; 127.0.0.1 = this machine only).",
        )

        parser.add_argument(
            "--port",
            type=int,
            help="config: port to listen on.",
        )

    def execute(
        self,
        args: Namespace,
    ) -> None:

        from lib.system import web

        if args.action == "config":
            self._config(args)
            return

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

    def _config(self, args: Namespace) -> None:
        """Show or change where the web server listens."""

        from lib.system import install, web

        record = install.load()
        current = record["web"]

        if args.host is None and args.port is None:
            self._ui.print(f"Listening on {current['host']}:{current['port']} ({web.url(record)})")
            return

        if not install.record_path().exists():
            # Writing an install record would make a checkout look installed.
            raise ValueError(
                "This Entropy runs from a source checkout. Start it with "
                "ENTROPY_WEB_HOST=0.0.0.0 ENTROPY_WEB_PORT=8000 python -m core.web instead."
            )

        if args.port is not None and not 1 <= args.port <= 65535:
            raise ValueError("Port must be between 1 and 65535.")

        if args.host is not None:
            current["host"] = args.host.strip()
        if args.port is not None:
            current["port"] = args.port
        install.save(record)

        # A systemd unit carries the address in its environment.
        if current.get("service") == "systemd" and web.service_file().exists():
            import subprocess

            web.service_file().write_text(web.unit(record), encoding="utf-8")
            subprocess.run(["systemctl", "--user", "daemon-reload"], check=False)

        self._ui.success(f"The web server will listen on {current['host']}:{current['port']}.")
        if web.status()["running"]:
            self._ui.print("Run 'ent web restart' to apply it.")
