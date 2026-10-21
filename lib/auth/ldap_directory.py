"""
Sign-in against LDAP / Active Directory (settings in Administration ->
Settings -> LDAP).

The service account (or an anonymous bind) finds the user's entry with the
user filter; the password is then checked by binding as that entry.
"""

from __future__ import annotations

import ssl
import warnings
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

CONNECT_TIMEOUT = 10
RECEIVE_TIMEOUT = 15


class DirectoryError(RuntimeError):
    """The directory could not be used; the message says why."""


@dataclass
class DirectoryUser:
    dn: str
    username: str
    full_name: Optional[str]
    email: Optional[str]
    groups: List[str] = field(default_factory=list)


def _ldap3():
    try:
        with warnings.catch_warnings():
            # ldap3 2.9 still uses pyasn1's old names.
            warnings.simplefilter("ignore", DeprecationWarning)
            import ldap3
            import ldap3.utils.conv  # noqa: F401
    except ImportError:  # pragma: no cover - ldap3 ships in the wheels
        raise DirectoryError(
            "LDAP sign-in needs the ldap3 package; reinstall Entropy's requirements."
        ) from None
    return ldap3


def _first(entry: Dict[str, Any], name: str) -> Optional[str]:
    value = entry.get(name) if name else None
    if isinstance(value, list):
        value = value[0] if value else None
    return str(value).strip() if value not in (None, "") else None


class Directory:
    # ldap3 client strategy; tests use MOCK_SYNC with an in-memory directory.
    client_strategy: Optional[str] = None

    def __init__(self, settings: Dict[str, Any]) -> None:
        self.settings = settings

    def _server(self):
        ldap3 = _ldap3()
        url = str(self.settings["server_url"])
        tls = ldap3.Tls(
            validate=ssl.CERT_REQUIRED if self.settings.get("verify_tls", True) else ssl.CERT_NONE
        )
        return ldap3.Server(
            url,
            use_ssl=url.lower().startswith("ldaps://"),
            tls=tls,
            get_info=ldap3.NONE,
            connect_timeout=CONNECT_TIMEOUT,
        )

    def _bind(self, user: Optional[str], password: Optional[str]):
        """An open connection bound as `user` (anonymous without one), or None if refused."""

        ldap3 = _ldap3()
        connection = ldap3.Connection(
            self._server(),
            user=user or None,
            password=password or None,
            auto_bind=ldap3.AUTO_BIND_NONE,
            client_strategy=self.client_strategy or ldap3.SYNC,
            receive_timeout=RECEIVE_TIMEOUT,
            raise_exceptions=False,
            read_only=True,
        )
        from ldap3.core.exceptions import LDAPSocketOpenError

        try:
            try:
                connection.open()
            except LDAPSocketOpenError:
                raise DirectoryError(f"Could not reach {self.settings['server_url']}.") from None
            if self.settings.get("start_tls") and not connection.start_tls():
                raise DirectoryError("STARTTLS failed; check the server and its certificate.")
            if not connection.bind():
                connection.unbind()
                return None
        except DirectoryError:
            raise
        except Exception as exc:  # noqa: BLE001 - ldap3 raises many kinds
            raise DirectoryError(f"LDAP error: {exc}") from None
        return connection

    def find(self, username: str) -> Optional[DirectoryUser]:
        """The user's entry, found with the service account; None if there is none."""

        ldap3 = _ldap3()
        from ldap3.utils.conv import escape_filter_chars

        settings = self.settings
        connection = self._bind(settings.get("bind_dn"), settings.get("bind_password"))
        if connection is None:
            raise DirectoryError(
                "The directory refused the service account (bind DN and password)."
            )
        attributes = [
            name
            for name in (
                settings.get("attr_username"),
                settings.get("attr_full_name"),
                settings.get("attr_email"),
                settings.get("group_attribute"),
            )
            if name
        ]
        search_filter = str(settings["user_filter"]).replace(
            "{username}", escape_filter_chars(username)
        )
        try:
            ok = connection.search(
                settings["user_base_dn"],
                search_filter,
                search_scope=ldap3.SUBTREE,
                attributes=attributes,
                size_limit=2,
            )
            entries = [
                item for item in (connection.response or []) if item.get("type") == "searchResEntry"
            ]
        except Exception as exc:  # noqa: BLE001
            raise DirectoryError(f"The user search failed: {exc}") from None
        finally:
            connection.unbind()
        if not ok or not entries:
            return None
        if len(entries) > 1:
            raise DirectoryError(
                f"More than one entry matches '{username}'; narrow the user filter."
            )
        entry = entries[0]
        values = entry.get("attributes") or {}
        groups = values.get(settings.get("group_attribute") or "") or []
        if isinstance(groups, str):
            groups = [groups]
        return DirectoryUser(
            dn=entry["dn"],
            username=_first(values, settings.get("attr_username")) or username,
            full_name=_first(values, settings.get("attr_full_name")),
            email=_first(values, settings.get("attr_email")),
            groups=[str(group) for group in groups],
        )

    def check_password(self, user: DirectoryUser, password: str) -> bool:
        # An empty password would be an anonymous ("unauthenticated") bind
        # that many servers accept: never treat it as a sign-in.
        if not password:
            return False
        connection = self._bind(user.dn, password)
        if connection is None:
            return False
        connection.unbind()
        return True

    def authenticate(self, username: str, password: str) -> Optional[DirectoryUser]:
        """The user if the password is right, else None."""

        user = self.find(username)
        if user is None or not self.check_password(user, password):
            return None
        return user


def _normal_dn(value: str) -> str:
    return ",".join(part.strip() for part in value.split(",")).lower()


def _cn(dn: str) -> str:
    first = dn.split(",", 1)[0]
    return first.split("=", 1)[1].strip().lower() if "=" in first else first.strip().lower()


def mapped_groups(mappings: List[Dict[str, str]], external: List[str], *, dn: bool) -> List[str]:
    """
    Entropy groups for these external groups. LDAP groups match by full DN
    or by their CN; IdP groups by name (case-insensitive).
    """

    found: List[str] = []
    wanted = {_normal_dn(name) if dn else name.strip().lower() for name in external}
    if dn:
        wanted |= {_cn(name) for name in external}
    for mapping in mappings:
        key = mapping["external"]
        key = _normal_dn(key) if dn and "=" in key else key.strip().lower()
        if key in wanted and mapping["group"] not in found:
            found.append(mapping["group"])
    return found
