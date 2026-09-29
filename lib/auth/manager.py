"""
Session manager.
"""

from __future__ import annotations

import secrets
from datetime import datetime, timedelta

from core.context import EntropyContext
from lib.auth.exceptions import AuthenticationRequiredError, SessionNotFoundError
from lib.auth.service import AuthenticationService
from lib.models.session import Session
from lib.executor.linux import LinuxExecutor


class SessionManager:
    """
    Manages authenticated sessions.

    Multiple authenticated sessions may exist at the same time.
    The current session represents the identity currently selected
    by the shell.
    """

    def __init__(
        self,
        context: EntropyContext,
    ) -> None:

        assert context.authentication is not None
        assert context.configuration is not None
        assert context.executor is not None
        assert context.paths is not None
        assert context.observability is not None

        self._authentication: AuthenticationService = context.authentication

        self._executor: LinuxExecutor = context.executor

        self._session_file = context.paths.session.current

        self._session_directory = context.paths.session.directory

        self._sessions_directory = (
            self._session_directory / "sessions"
        )

        self._session_timeout = context.configuration.get(
            "auth.session.timeout",
            8,
        )

        self._events = context.observability.emitter(
            "auth",
        )

        self._now = datetime.now

    # ------------------------------------------------------------------
    # Login
    # ------------------------------------------------------------------

    def login(
        self,
        username: str,
        password: str,
    ) -> Session:

        existing = self.find(
            username,
        )

        if existing is not None:

            self._set_current(
                existing,
            )

            self._events.log.info(
                f"Already authenticated as '{existing.username}'.",
            )

            return existing

        user = self._authentication.authenticate(
            username,
            password,
        )

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
            full_name=user.full_name,
        )

        self._save(
            session,
        )

        self._set_current(
            session,
        )

        self._events.log.success(
            f"User '{session.username}' authenticated successfully.",
        )

        return session

    # ------------------------------------------------------------------
    # Logout
    # ------------------------------------------------------------------

    def logout(
        self,
    ) -> None:
        """
        Log out the currently selected session.

        Other authenticated sessions remain untouched.
        """

        session = self.current()

        if session is None:

            self._events.log.warning(
                "No active session.",
            )

            return

        self._delete_session(
            session,
        )

        self._clear_current()

        self._events.log.success(
            f"User '{session.username}' logged out successfully.",
        )

    # ------------------------------------------------------------------
    # Current
    # ------------------------------------------------------------------

    def current(
        self,
    ) -> Session | None:
        """
        Return the currently selected authenticated session.
        """

        token = self._load_current_token()

        if token is None:

            return None

        session = self._load_session(
            token,
        )

        if session is None:

            self._clear_current()

            return None

        if self._now() >= session.expires_at:

            self._delete_session(
                session,
            )

            self._clear_current()

            self._events.log.warning(
                f"Session for '{session.username}' expired.",
            )

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
        """
        Save an individual session.
        """

        self._executor.mkdir(
            self._session_directory,
            parents=True,
            exist_ok=True,
        )

        self._executor.mkdir(
            self._sessions_directory,
            parents=True,
            exist_ok=True,
        )

        session_file = self._session_path(
            session.token,
        )

        self._executor.write_json(
            session_file,
            session.to_dict(),
        )

        self._executor.chmod(
            session_file,
            0o600,
        )

    def _load_session(
        self,
        token: str,
    ) -> Session | None:
        """
        Load a session by token.
        """

        session_file = self._session_path(
            token,
        )

        if not self._executor.exists(
            session_file,
        ):

            return None

        return Session.from_dict(
            self._executor.read_json(
                session_file,
            ),
        )

    def _delete_session(
        self,
        session: Session,
    ) -> None:
        """
        Delete an individual session.
        """

        session_file = self._session_path(
            session.token,
        )

        if self._executor.exists(
            session_file,
        ):

            self._executor.remove(
                session_file,
            )

    def _session_path(
        self,
        token: str,
    ):
        """
        Return the storage path for a session.
        """

        return self._sessions_directory / f"{token}.json"

    # ------------------------------------------------------------------
    # Current session
    # ------------------------------------------------------------------

    def _set_current(
        self,
        session: Session,
    ) -> None:
        """
        Select a session as the current shell session.
        """

        self._executor.mkdir(
            self._session_directory,
            parents=True,
            exist_ok=True,
        )

        self._executor.write_json(
            self._session_file,
            {
                "token": session.token,
            },
        )

        self._executor.chmod(
            self._session_file,
            0o600,
        )

    def _load_current_token(
        self,
    ) -> str | None:
        """
        Return the token of the currently selected session.

        Supports the old single-session format temporarily so an
        existing session can be migrated automatically.
        """

        if not self._executor.exists(
            self._session_file,
        ):

            return None

        data = self._executor.read_json(
            self._session_file,
        )

        token = data.get(
            "token",
        )

        if isinstance(
            token,
            str,
        ) and token.strip():

            return token

        # ----------------------------------------------------------
        # Backward compatibility with the old session format.
        #
        # The old current.json contained the complete Session.
        # Migrate it into the new per-session storage.
        # ----------------------------------------------------------

        if all(
            key in data
            for key in (
                "user_id",
                "username",
                "token",
                "created_at",
                "expires_at",
            )
        ):

            session = Session.from_dict(
                data,
            )

            self._save(
                session,
            )

            self._set_current(
                session,
            )

            return session.token

        return None

    def _clear_current(
        self,
    ) -> None:
        """
        Clear the currently selected session.
        """

        if self._executor.exists(
            self._session_file,
        ):

            self._executor.remove(
                self._session_file,
        )

    # Manage multiple sessions
    def find(
        self,
        username: str,
    ) -> Session | None:
        """
        Return a valid authenticated session for a user.
        """

        sessions = self.list()

        username = username.strip()

        for session in sessions:

            if session.username == username:

                return session

        return None

    def switch(
        self,
        username: str,
    ) -> Session:
        """
        Switch the current shell session to an existing
        authenticated session.
        """

        session = self.find(
            username,
        )

        if session is None:

            raise SessionNotFoundError(
                username,
            )

        current = self.current()

        if (
            current is not None
            and current.token == session.token
        ):

            self._events.log.info(
                f"Already authenticated as '{session.username}'.",
            )

            return session

        self._set_current(
            session,
        )

        self._events.log.success(
            f"Switched to user '{session.username}'.",
        )

        return session

    def list(
        self,
    ) -> list[Session]:
        """
        Return all valid authenticated sessions.
        """

        sessions: list[Session] = []

        for session_file in self._executor.find(
            self._sessions_directory,
            "*.json",
            recursive=False,
        ):

            try:

                session = Session.from_dict(
                    self._executor.read_json(
                        session_file,
                    ),
                )

            except (
                KeyError,
                TypeError,
                ValueError,
            ):

                self._events.log.warning(
                    f"Ignoring invalid session file '{session_file}'.",
                )

                continue

            if self._now() >= session.expires_at:

                self._executor.remove(
                    session_file,
                )

                continue

            sessions.append(
                session,
            )

        return sessions
