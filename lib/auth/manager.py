"""
Session manager.
"""

from __future__ import annotations

import secrets
from datetime import datetime, timedelta

from core.context import EntropyContext
from lib.auth.exceptions import AuthenticationRequiredError
from lib.auth.service import AuthenticationService
from lib.auth.session import Session
from lib.executor.linux import LinuxExecutor


class SessionManager:
    """
    Manages authenticated sessions.
    """

    def __init__(
        self,
        context: EntropyContext,
    ) -> None:

        assert context.authentication is not None
        assert context.configuration is not None
        assert context.executor is not None
        assert context.paths is not None
        # assert context.observability is not None
        assert context.diagnostics is not None

        self._authentication: AuthenticationService = context.authentication

        self._executor: LinuxExecutor = context.executor

        self._session_file = context.paths.session.current

        self._session_directory = context.paths.session.directory

        self._session_timeout = context.configuration.get(
            "auth.session.timeout",
            8,
        )

        self._now = datetime.now

        self._log = context.diagnostics.logger(
            "auth",
        )

    # ------------------------------------------------------------------
    # Login
    # ------------------------------------------------------------------

    def login(
        self,
        username: str,
        password: str,
    ) -> Session:

        user = self._authentication.authenticate(
            username,
            password,
        )

        existing = self.current()

        if existing is not None:

            self._delete()

        now = self._now()

        assert user.id is not None

        session = Session(
            user_id=user.id,
            username=user.username,
            token=secrets.token_hex(32),
            created_at=now,
            expires_at=now
            + timedelta(
                hours=self._session_timeout,
            ),
        )

        self._save(
            session,
        )

        self._log.info(f"User '{user.username}' logged in.")

        return session

    # ------------------------------------------------------------------
    # Logout
    # ------------------------------------------------------------------

    def logout(
        self,
    ) -> None:

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
    # Status
    # ------------------------------------------------------------------

    def authenticated(
        self,
    ) -> bool:

        return self.current() is not None

    def require(
        self,
    ) -> Session:

        session = self.current()

        if session is None:

            raise AuthenticationRequiredError()

        return session

    # ------------------------------------------------------------------
    # Storage
    # ------------------------------------------------------------------

    def _save(
        self,
        session: Session,
    ) -> None:

        self._executor.mkdir(
            self._session_directory,
            parents=True,
            exist_ok=True,
        )

        self._executor.write_json(
            self._session_file,
            session.to_dict(),
        )

        self._executor.chmod(
            self._session_file,
            0o600,
        )

    def _load(
        self,
    ) -> Session | None:

        if not self._executor.exists(
            self._session_file,
        ):
            return None

        return Session.from_dict(
            self._executor.read_json(
                self._session_file,
            )
        )

    def _delete(
        self,
    ) -> None:

        if self._executor.exists(
            self._session_file,
        ):

            self._executor.remove(
                self._session_file,
            )
