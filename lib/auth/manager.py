"""
Session manager.
"""

from __future__ import annotations

import secrets
from datetime import datetime, timedelta
from pathlib import Path

from core.constants import SESSION_DIRECTORY, SESSION_FILE
from core.context import EntropyContext
from lib.auth.exceptions import AuthenticationRequiredError
from lib.auth.session import Session
from lib.executor.linux import LinuxExecutor
from lib.users.manager import UserManager


class SessionManager:

    def __init__(
        self,
        context: EntropyContext,
        session_file: Path = SESSION_FILE,
        session_directory: Path = SESSION_DIRECTORY,
    ) -> None:

        assert context.user_manager is not None
        assert context.executor is not None

        self._now = datetime.now
        self.session_file = session_file
        self.session_directory = session_directory
        self._users: UserManager = context.user_manager
        self._executor: LinuxExecutor = context.executor
        self._log = context.output.auth

    # ------------------------------------------------------------------
    # Save
    # ------------------------------------------------------------------

    def _save(
        self,
        session: Session,
    ) -> None:

        self._executor.mkdir(
            self.session_directory,
        )

        self._executor.write_json(self.session_file, session.to_dict())

        self._executor.chmod(
            self.session_file,
            0o600,
        )

        self._log.debug(f"Session saved for '{session.username}'.")

    # ------------------------------------------------------------------
    # Load
    # ------------------------------------------------------------------

    def _load(
        self,
    ) -> Session | None:

        if not self._executor.exists(
            self.session_file,
        ):
            return None

        data = self._executor.read_json(self.session_file)

        session = Session.from_dict(data)

        self._log.debug(f"Session loaded for '{session.username}'.")

        return session

    # ------------------------------------------------------------------
    # Delete
    # ------------------------------------------------------------------

    def _delete(self) -> None:

        self._executor.remove(
            self.session_file,
        )

        self._log.debug("Session deleted.")

    # ------------------------------------------------------------------
    # Login
    # ------------------------------------------------------------------

    def login(
        self,
        username: str,
        password: str,
    ) -> Session:
        """
        Authenticate a user and create a session.
        """

        user = self._users.authenticate(
            username,
            password,
        )

        now = self._now()

        existing = self.current()

        if existing is not None:
            self._delete()

        assert user.id is not None

        session = Session(
            user_id=user.id,
            username=user.username,
            token=secrets.token_hex(32),
            created_at=now,
            expires_at=now + timedelta(hours=8),
        )

        self._save(session)

        self._log.info(f"User '{user.username}' authenticated.")

        return session

    # ------------------------------------------------------------------
    # Logout
    # ------------------------------------------------------------------

    def logout(
        self,
    ) -> None:
        """
        Destroy the current session.
        """

        session = self.current()

        if session is None:
            return

        self._delete()

        self._log.info(f"User '{session.username}' logged out.")

    # ------------------------------------------------------------------
    # Current
    # ------------------------------------------------------------------

    def current(
        self,
    ) -> Session | None:

        session = self._load()

        if session is None:
            return None

        if self._now() >= session.expires_at:

            self._delete()

            self._log.info(f"Session expired for '{session.username}'.")

            return None

        return session

    # ------------------------------------------------------------------
    # Authenticated
    # ------------------------------------------------------------------

    def authenticated(
        self,
    ) -> bool:

        return self.current() is not None

    # ------------------------------------------------------------------
    # Require
    # ------------------------------------------------------------------

    def require(
        self,
    ) -> Session:

        session = self.current()

        if session is None:
            raise AuthenticationRequiredError()

        return session
