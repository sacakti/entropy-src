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
        *,
        username: str | None = None,
        password: str | None = None,
        full_name: str = "Administrator",
        interactive: bool = True,
    ) -> None:

        assert context.user_manager is not None

        self._users = context.user_manager
        self._username = username
        self._password = password
        self._full_name = full_name or "Administrator"
        self._interactive = interactive

    # ------------------------------------------------------------------
    # Public
    # ------------------------------------------------------------------

    def install(self) -> User | None:

        if self._users.any():
            return None

        print()
        print("Bootstrap Administrator")
        print("-----------------------")

        username = self._username
        if not username:
            if not self._interactive:
                username = "admin"
            else:
                username = input("Username [admin]: ").strip() or "admin"
        print(f"Username: {username}")

        while True:

            password = self._password
            self._password = None

            if password is None:

                if not self._interactive:
                    raise RuntimeError(
                        "A bootstrap administrator password is required "
                        "(set ENTROPY_ADMIN_PASSWORD or use --admin-password-file)."
                    )

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
                    full_name=self._full_name,
                )

                break

            except WeakPasswordError as exc:

                print(exc)

                if not self._interactive:
                    raise

                continue

        print()
        print("Administrator account created.")

        return user
