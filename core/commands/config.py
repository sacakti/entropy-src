"""
Command line preferences: `ent config set output table`.
"""

from __future__ import annotations

import os
from argparse import ArgumentParser, Namespace

from core.commands.base import BaseCommand, CommandMetadata
from core.commands.output_mode import Preferences
from lib.remote_cli.contract import CONFIG_KEYS, OUTPUT_ENV, OUTPUT_MODES, resolve_output, resource


class ConfigCommand(BaseCommand):
    """
    Show and save CLI preferences (the same as the ent client's).
    """

    metadata = CommandMetadata(
        name="config",
        description="Command line preferences (output mode).",
    )

    def configure(
        self,
        parser: ArgumentParser,
    ) -> None:

        item = resource("config")
        assert item is not None

        actions = parser.add_subparsers(
            dest="action",
            required=True,
        )

        for verb in item.verbs:

            action = actions.add_parser(
                verb.name,
                aliases=list(verb.aliases),
                help=verb.help,
            )

            action.add_argument(
                "key",
                nargs="?" if verb.name == "view" else None,
                choices=sorted(CONFIG_KEYS),
                help="Setting.",
            )

            if verb.name == "set":

                action.add_argument(
                    "value",
                    choices=OUTPUT_MODES,
                    help="Output mode.",
                )

            action.set_defaults(
                config_action=verb.name,
            )

    def execute(
        self,
        args: Namespace,
    ) -> None:

        session = self._require_authentication()
        preferences = Preferences(self.context)

        if args.config_action == "set":
            preferences.set(session.user_id, args.key, args.value)
            self.context.ui.success(f"{args.key} set to {args.value}.")
            return

        if args.config_action == "unset":
            preferences.set(session.user_id, args.key, None)
            self.context.ui.success(f"Forgot {args.key}; using {resolve_output(None, None)}.")
            return

        saved = preferences.get(session.user_id, "output")
        source = OUTPUT_ENV if os.environ.get(OUTPUT_ENV) else "saved" if saved else "default"
        self.context.ui.info(f"output: {resolve_output(None, saved)} ({source})")
