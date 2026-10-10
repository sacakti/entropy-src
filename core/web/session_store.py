
"""
Server-side session storage for the Entropy web application.
"""

from __future__ import annotations

import secrets
from datetime import datetime, timedelta
from typing import Optional, Tuple

from core.context import EntropyContext
from lib.models.session import Session
from lib.models.users import User
from lib.users.exceptions import UserNotFoundError


class WebSessionStore:
    """Manage browser sessions independently of CLI sessions."""

    def __init__(self, context: EntropyContext) -> None:
        assert context.authentication is not None
        assert context.configuration is not None
        assert context.executor is not None
        assert context.paths is not None
        assert context.user_repository is not None

        self._context = context
        self._authentication = context.authentication
        self._configuration = context.configuration
        self._executor = context.executor
        self._users = context.user_repository

        self._directory = context.paths.session.directory / "web_sessions"
        self.timeout_seconds = int(
            self._configuration.get("auth.session.timeout", 8)
        ) * 60 * 60

    def login(self, username: str, password: str) -> Tuple[Session, str]:
        """Authenticate credentials and create a separate browser session."""

        user = self._authentication.authenticate(username, password)
        assert user.id is not None

        now = datetime.now()
        token = secrets.token_hex(32)
        csrf_token = secrets.token_hex(32)

        session = Session(
            user_id=user.id,
            username=user.username,
            full_name=user.full_name,
            token=token,
            created_at=now,
            expires_at=now + timedelta(seconds=self.timeout_seconds),
        )

        self._executor.mkdir(
            self._directory,
            parents=True,
            exist_ok=True,
        )

        self._executor.write_json(
            self._session_path(token),
            {
                "session": session.to_dict(),
                "csrf_token": csrf_token,
            },
        )
        self._executor.chmod(self._session_path(token), 0o600)

        self._executor.chmod(self._directory, 0o700)

        return session, csrf_token

    def get(
        self,
        token: Optional[str],
    ) -> Optional[Tuple[Session, str, User]]:
        """Load and validate a browser session and its current user."""

        if not token or len(token) != 64:
            return None

        if any(character not in "0123456789abcdef" for character in token):
            return None

        path = self._session_path(token)

        if not self._executor.exists(path):
            return None

        try:
            data = self._executor.read_json(path)
            session = Session.from_dict(data["session"])
            csrf_token = data["csrf_token"]
        except (KeyError, TypeError, ValueError, OSError):
            self._delete_path(path)
            return None

        if session.token != token or datetime.now() >= session.expires_at:
            self._delete_path(path)
            return None

        try:
            user = self._users.get(session.user_id)
        except UserNotFoundError:
            self._delete_path(path)
            return None

        if not user.is_active:
            self._delete_path(path)
            return None

        # Reflect current account details instead of stale session values.
        session.username = user.username
        session.full_name = user.full_name

        return session, csrf_token, user

    def logout(self, token: Optional[str]) -> None:
        """Delete a browser session without changing the CLI session."""

        if not token or len(token) != 64:
            return

        if any(character not in "0123456789abcdef" for character in token):
            return

        self._delete_path(self._session_path(token))

    def _session_path(self, token: str):
        """Return a validated session file path."""

        return self._directory / "{}.json".format(token)

    def _delete_path(self, path) -> None:
        if self._executor.exists(path):
            self._executor.remove(path)
