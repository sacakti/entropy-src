
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
        # Browser sessions end after this long without activity (0: never).
        self.idle_seconds = max(
            0, int(self._configuration.get("auth.session.idle_minutes", 15)) * 60
        )

    @property
    def cli_timeout_seconds(self) -> int:
        """Lifetime of command line tokens (hours in auth.cli.timeout, default a week)."""

        return int(self._configuration.get("auth.cli.timeout", 168)) * 60 * 60

    def login(
        self,
        username: str,
        password: str,
        *,
        seconds: Optional[int] = None,
        browser: bool = True,
        address: Optional[str] = None,
    ) -> Tuple[Session, str]:
        """Authenticate credentials; a sign-in (browser or `ent login`) is remembered."""

        from lib.auth.external import sign_in

        # Local accounts check their password here; LDAP accounts the directory.
        user = sign_in(self._context, username, password)
        return self.issue(
            user,
            seconds=seconds,
            browser=browser,
            address=address,
            login_source="web" if browser else "cli",
        )

    def issue(
        self,
        user: User,
        *,
        seconds: Optional[int] = None,
        browser: bool = True,
        address: Optional[str] = None,
        login_source: Optional[str] = None,
    ) -> Tuple[Session, str]:
        """
        A new session for an already authenticated user. Browser sessions
        end after `idle_seconds` without activity; command line tokens
        (browser=False) do not. A sign-in (`login_source`, browser sessions
        by default) is remembered as the user's last sign-in; a token made
        from an existing browser session is not a sign-in.
        """

        if login_source is None and browser:
            login_source = "web"
        # The sign-in before this one, kept with the session (shown as "previous sign-in").
        previous = self._latest_login(user.id) if browser else None

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
            expires_at=now + timedelta(seconds=seconds or self.timeout_seconds),
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
                "browser": browser,
                "last_activity": now.isoformat(),
                "previous_login": previous,
            },
        )
        self._executor.chmod(self._session_path(token), 0o600)

        self._executor.chmod(self._directory, 0o700)

        if login_source is not None:
            self._record_login(user.id, address, login_source)

        return session, csrf_token

    def previous_login(self, token: Optional[str]) -> Optional[dict]:
        """The sign-in before this browser session started (None: first sign-in)."""

        data = self._read(token)
        if data is None:
            return None
        if "previous_login" in data:
            previous = data["previous_login"]
            return previous if isinstance(previous, dict) else None
        # Sessions from before the snapshot: the sign-in before the latest one.
        manager = self._context.database_manager
        if manager is None or not data.get("session"):
            return None
        from lib.database.repositories.user_logins import UserLoginsRepository

        return UserLoginsRepository(manager.connection).previous(int(data["session"]["user_id"]))

    # ------------------------------------------------------------------
    # Inactivity
    # ------------------------------------------------------------------

    def idle_deadline(self, token: Optional[str]) -> Optional[datetime]:
        """When the browser session ends unless it is used (None: no idle limit)."""

        data = self._read(token)
        if data is None:
            return None
        return self._deadline(data)

    def touch(self, token: Optional[str]) -> Optional[datetime]:
        """
        The user is active: restart the inactivity timer. Only explicit
        keepalives do this, so background polling never keeps an
        abandoned browser signed in.
        """

        data = self._read(token)
        if data is None or self.get(token) is None:
            return None
        data["last_activity"] = datetime.now().isoformat()
        path = self._session_path(str(token))
        self._executor.write_json(path, data)
        self._executor.chmod(path, 0o600)
        return self._deadline(data)

    def _deadline(self, data: dict) -> Optional[datetime]:
        if not data.get("browser") or not self.idle_seconds:
            return None
        try:
            last = datetime.fromisoformat(data["last_activity"])
        except (KeyError, TypeError, ValueError):
            # Sessions from before the idle limit count from their creation.
            last = datetime.fromisoformat(data["session"]["created_at"])
        return last + timedelta(seconds=self.idle_seconds)

    def _read(self, token: Optional[str]) -> Optional[dict]:
        if not token or len(token) != 64 or any(c not in "0123456789abcdef" for c in token):
            return None
        path = self._session_path(token)
        if not self._executor.exists(path):
            return None
        try:
            data = self._executor.read_json(path)
        except (TypeError, ValueError, OSError):
            return None
        return data if isinstance(data, dict) else None

    def _latest_login(self, user_id: Optional[int]) -> Optional[dict]:
        manager = self._context.database_manager
        if manager is None or user_id is None:
            return None
        from lib.database.repositories.user_logins import UserLoginsRepository

        return UserLoginsRepository(manager.connection).latest_entry(user_id)

    def _record_login(self, user_id: Optional[int], address: Optional[str], source: str) -> None:
        """Remember the sign-in (shown as the last sign-in, in Users and the profile)."""

        manager = self._context.database_manager
        if manager is None or user_id is None:
            return
        from lib.database.repositories.user_logins import UserLoginsRepository

        UserLoginsRepository(manager.connection).record(user_id, address, source)

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

        deadline = self._deadline(data)
        if deadline is not None and datetime.now() >= deadline:
            # Signed out after inactivity.
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
