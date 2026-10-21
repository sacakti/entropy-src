"""
Accounts that sign in through LDAP / Active Directory or single sign-on.

An Entropy user is linked to at most one outside identity (`ldap` with the
entry's DN, or `oidc` with the token's subject). Linked users sign in only
there; their Entropy password is a random one nobody knows. Users unknown
to Entropy get an account on first sign-in when the provider allows it.
Local accounts are never taken over by an outside identity with the same
name: an administrator keeps local `admin` even if the directory has one.

On every sign-in the user's mapped Entropy groups are brought in line with
the outside groups. Only groups named in the mappings are touched, so
memberships given by hand in Entropy stay.
"""

from __future__ import annotations

import secrets
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from lib.models.users import User
from lib.users.exceptions import AuthenticationError, UserInactiveError, UserNotFoundError

PROVIDERS = ("ldap", "oidc")


class SignInRefused(AuthenticationError):
    """Sign-in refused for a reason the person should see."""

    def __init__(self, message: str) -> None:
        super().__init__()
        self.message = message

    def __str__(self) -> str:
        return self.message


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def ensure_identity_schema(connection: Any) -> None:
    if getattr(connection, "_entropy_identities_ready", False):
        return
    with connection.transaction():
        connection.execute("""
            CREATE TABLE IF NOT EXISTS external_identities
            (
                user_id     INTEGER PRIMARY KEY REFERENCES users (id) ON DELETE CASCADE,
                provider    TEXT NOT NULL,
                subject     TEXT NOT NULL,
                last_login  TEXT,
                UNIQUE (provider, subject)
            )
            """)
    connection._entropy_identities_ready = True


class ExternalAccounts:
    def __init__(self, context: Any) -> None:
        self.context = context
        self.connection = context.database_manager.connection
        ensure_identity_schema(self.connection)

    # -- lookups --------------------------------------------------------

    def provider_of(self, user_id: int) -> Optional[str]:
        row = self.connection.fetchone(
            "SELECT provider FROM external_identities WHERE user_id = ?", (user_id,)
        )
        return row["provider"] if row else None

    def providers(self) -> Dict[int, str]:
        rows = self.connection.fetchall("SELECT user_id, provider FROM external_identities")
        return {row["user_id"]: row["provider"] for row in rows}

    def _linked(self, provider: str, subject: str) -> Optional[User]:
        row = self.connection.fetchone(
            "SELECT user_id FROM external_identities WHERE provider = ? AND subject = ?",
            (provider, subject),
        )
        if row is None:
            return None
        try:
            return self.context.user_repository.get(row["user_id"])
        except UserNotFoundError:
            return None

    # -- sign-in --------------------------------------------------------

    def account(
        self,
        provider: str,
        subject: str,
        *,
        username: str,
        full_name: Optional[str],
        email: Optional[str],
        auto_create: bool,
        groups: List[str],
        managed_groups: List[str],
    ) -> User:
        """
        The Entropy user for an identity the provider has vouched for;
        creates it if allowed, refreshes name and e-mail, syncs groups.
        """

        users = self.context.user_repository
        user = self._linked(provider, subject)
        if user is None:
            try:
                existing = users.get_by_username(username)
            except UserNotFoundError:
                existing = None
            if existing is not None:
                other = self.provider_of(existing.id)
                raise SignInRefused(
                    f"The Entropy account '{username}' "
                    + (
                        f"signs in with {_label(other)}."
                        if other
                        else "is a local account; ask an administrator."
                    )
                )
            if not auto_create:
                raise SignInRefused(
                    f"'{username}' has no Entropy account yet; ask an administrator to add one."
                )
            user = users.create(
                User(
                    username=username,
                    # Nobody knows it: linked users sign in at their provider.
                    password_hash=self.context.password_service.hash(secrets.token_urlsafe(48)),
                    full_name=full_name,
                    email=email,
                )
            )
            with self.connection.transaction():
                self.connection.execute(
                    "INSERT INTO external_identities (user_id, provider, subject) VALUES (?, ?, ?)",
                    (user.id, provider, subject),
                )
        if not user.is_active:
            raise UserInactiveError(user.username)

        changed = False
        if full_name and full_name != user.full_name:
            user.full_name, changed = full_name, True
        if email and email != user.email:
            user.email, changed = email, True
        if changed:
            users.update(user)
        self.sync_groups(user, groups, managed_groups)
        with self.connection.transaction():
            self.connection.execute(
                "UPDATE external_identities SET last_login = ? WHERE user_id = ?",
                (_now(), user.id),
            )
        return user

    def sync_groups(self, user: User, groups: List[str], managed: List[str]) -> None:
        """Membership of the managed groups follows `groups`; others are left alone."""

        if not managed:
            return
        names = list(dict.fromkeys(managed))
        rows = self.connection.fetchall(
            f"SELECT id, name FROM groups WHERE name IN ({','.join('?' * len(names))})",
            tuple(names),
        )
        ids = {row["name"]: row["id"] for row in rows}
        with self.connection.transaction():
            for name, group_id in ids.items():
                if name in groups:
                    self.connection.execute(
                        "INSERT OR IGNORE INTO user_groups (user_id, group_id, created_at)"
                        " VALUES (?, ?, ?)",
                        (user.id, group_id, _now()),
                    )
                else:
                    self.connection.execute(
                        "DELETE FROM user_groups WHERE user_id = ? AND group_id = ?",
                        (user.id, group_id),
                    )


def _label(provider: Optional[str]) -> str:
    return {"ldap": "LDAP", "oidc": "single sign-on"}.get(provider or "", "another provider")


def sign_in(context: Any, username: str, password: str) -> User:
    """
    Password sign-in: local accounts check their Entropy password, LDAP
    accounts (and new users, when LDAP is on) the directory.
    """

    from lib.system.settings import settings_for

    username = username.strip()
    accounts = ExternalAccounts(context)
    try:
        user = context.user_repository.get_by_username(username)
    except UserNotFoundError:
        user = None
    provider = accounts.provider_of(user.id) if user is not None else None

    if user is not None and provider is None:
        return context.authentication.authenticate(username, password)
    if provider == "oidc":
        raise SignInRefused("This account signs in with single sign-on.")

    ldap = settings_for(context).values("ldap")
    if not ldap.get("enabled"):
        if provider == "ldap":
            raise SignInRefused("LDAP sign-in is turned off; ask an administrator.")
        raise AuthenticationError()

    from .ldap_directory import Directory, DirectoryError, mapped_groups

    try:
        found = Directory(ldap).authenticate(username, password)
    except DirectoryError as exc:
        import logging

        logging.getLogger("entropy.auth").warning("LDAP sign-in failed: %s", exc)
        raise SignInRefused("The directory cannot be reached; try again later.") from None
    if found is None:
        raise AuthenticationError()
    mappings = ldap.get("group_mappings") or []
    return accounts.account(
        "ldap",
        found.dn.lower(),
        username=found.username,
        full_name=found.full_name,
        email=found.email,
        auto_create=bool(ldap.get("auto_create_users")),
        groups=mapped_groups(mappings, found.groups, dn=True),
        managed_groups=[mapping["group"] for mapping in mappings],
    )
