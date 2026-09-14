"""
Bootstrap administrator.
"""

from __future__ import annotations

import getpass

from core.context import EntropyContext
from lib.models.users import User
from lib.users.exceptions import WeakPasswordError


class BootstrapInstaller:
    """
    Creates the bootstrap administrator.
    """

    def __init__(
        self,
        context: EntropyContext,
    ) -> None:

        assert context.user_manager is not None

        self._users = context.user_manager

    # ------------------------------------------------------------------
    # Public
    # ------------------------------------------------------------------

    def install(self) -> User | None:

        if self._users.any():
            return None

        username = "admin"

        print()
        print("Bootstrap Administrator")
        print("-----------------------")
        print(f"Username: {username}")

        while True:

            password = getpass.getpass("Password: ")
            confirm = getpass.getpass("Confirm Password: ")

            if password != confirm:

                print("Passwords do not match.")
                print()

                continue

            try:

                user = self._users.create(
                    username=username,
                    password=password,
                    full_name="Administrator",
                )

                break

            except WeakPasswordError as exc:

                print(exc)

                continue

        print()
        print("Administrator account created.")

        return user
