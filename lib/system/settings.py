"""
Entropy-wide settings made in the administration panel: e-mail (SMTP),
sign-in with LDAP / Active Directory and OpenID Connect, the address
people use to reach Entropy (for links in e-mails), and the connections
for a database migration target, a Redis cache and a message queue.

The connection sections are stored and can be tested; Entropy itself still
runs on SQLite and does not use the cache or the queue yet.

Each section is one JSON value in the `settings` table. Secrets (passwords,
client secrets) are encrypted with the vault's master key and never sent
back to the browser: the API only says whether one is set.
"""

from __future__ import annotations

import base64
import copy
import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from lib.database.connection import DatabaseConnection
from lib.database.objects.settings import SettingsTable

SECTIONS: Dict[str, Dict[str, Any]] = {
    "general": {
        # Where people open Entropy, e.g. https://entropy.example.com (links in e-mails).
        "public_url": "",
    },
    "smtp": {
        "enabled": False,
        "host": "",
        "port": 587,
        # none | starttls | ssl
        "security": "starttls",
        "username": "",
        "password": "",
        "from_address": "",
        "from_name": "Entropy",
        "verify_tls": True,
    },
    "ldap": {
        "enabled": False,
        # ldap://host:389 or ldaps://host:636
        "server_url": "",
        "start_tls": False,
        "verify_tls": True,
        # Service account used to find users; empty for anonymous search.
        "bind_dn": "",
        "bind_password": "",
        "user_base_dn": "",
        # {username} is replaced (escaped). AD: (sAMAccountName={username})
        "user_filter": "(uid={username})",
        "attr_username": "uid",
        "attr_full_name": "cn",
        "attr_email": "mail",
        # Users signing in for the first time get an Entropy account.
        "auto_create_users": True,
        # LDAP group DN -> Entropy group name (memberOf, or a group search).
        "group_attribute": "memberOf",
        "group_mappings": [],
    },
    "oidc": {
        "enabled": False,
        "button_label": "Sign in with SSO",
        # https://login.example.com/realms/acme (its /.well-known/openid-configuration)
        "issuer": "",
        "client_id": "",
        "client_secret": "",
        "scopes": "openid profile email",
        "claim_username": "preferred_username",
        "claim_full_name": "name",
        "claim_email": "email",
        "claim_groups": "groups",
        "auto_create_users": True,
        # IdP group name -> Entropy group name.
        "group_mappings": [],
        "verify_tls": True,
    },
    "database_target": {
        "enabled": False,
        # postgresql | oracle
        "engine": "postgresql",
        "host": "",
        "port": 5432,
        # The PostgreSQL database, or the Oracle service name.
        "database": "",
        "schema": "",
        "username": "",
        "password": "",
        # PostgreSQL sslmode=require, or Oracle TCPS.
        "ssl": False,
    },
    "cache": {
        "enabled": False,
        "host": "",
        "port": 6379,
        "database": 0,
        # Redis 6 ACL user; empty for the default user.
        "username": "",
        "password": "",
        "tls": False,
        "verify_tls": True,
        "key_prefix": "entropy:",
        "default_ttl_seconds": 300,
    },
    "queue": {
        "enabled": False,
        # activemq (STOMP) | rabbitmq (AMQP 0-9-1) | mqtt | kafka
        "broker": "activemq",
        "host": "",
        "port": 61613,
        "tls": False,
        "verify_tls": True,
        "username": "",
        "password": "",
        # RabbitMQ virtual host, or the STOMP host header.
        "virtual_host": "/",
        "client_id": "entropy",
        "topic_prefix": "entropy",
    },
}

SECRETS = {
    "smtp": ("password",),
    "ldap": ("bind_password",),
    "oidc": ("client_secret",),
    "database_target": ("password",),
    "cache": ("password",),
    "queue": ("password",),
}

ENGINES = ("postgresql", "oracle")
BROKERS = ("activemq", "rabbitmq", "mqtt", "kafka")


class SettingsError(ValueError):
    """A setting that cannot be saved; the message says why."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class SystemSettings:
    def __init__(self, connection: DatabaseConnection, key: Optional[bytes] = None) -> None:
        SettingsTable().create(connection)
        self.connection = connection
        self._key = key

    # -- secrets --------------------------------------------------------

    def _cipher(self):
        if self._key is None:
            raise SettingsError("The vault key is unavailable, so secrets cannot be stored.")
        from lib.vault.cipher import VaultCipher

        return VaultCipher(self._key)

    def _seal(self, value: str) -> str:
        return base64.b64encode(self._cipher().encrypt(value.encode("utf-8"))).decode("ascii")

    def _open(self, value: str) -> str:
        return self._cipher().decrypt(base64.b64decode(value)).decode("utf-8")

    # -- read -----------------------------------------------------------

    def _stored(self, section: str) -> Dict[str, Any]:
        row = self.connection.fetchone(
            "SELECT value FROM settings WHERE key = ?", (f"system.{section}",)
        )
        if row is None or not row["value"]:
            return {}
        try:
            value = json.loads(row["value"])
        except ValueError:
            return {}
        return value if isinstance(value, dict) else {}

    def get(self, section: str) -> Dict[str, Any]:
        """The section for the browser: secrets replaced by whether they are set."""

        if section not in SECTIONS:
            raise SettingsError(f"Unknown settings section '{section}'.")
        values = copy.deepcopy(SECTIONS[section])
        stored = self._stored(section)
        values.update({key: value for key, value in stored.items() if key in values})
        for name in SECRETS.get(section, ()):
            values[f"{name}_set"] = bool(stored.get(name))
            values[name] = ""
        return values

    def values(self, section: str) -> Dict[str, Any]:
        """The section with secrets decrypted, for use on the server only."""

        values = self.get(section)
        stored = self._stored(section)
        for name in SECRETS.get(section, ()):
            values.pop(f"{name}_set", None)
            values[name] = self._open(stored[name]) if stored.get(name) else ""
        return values

    # -- write ----------------------------------------------------------

    def update(self, section: str, changes: Dict[str, Any]) -> Dict[str, Any]:
        """
        Merge changes. For a secret, None keeps the stored one, "" clears it,
        anything else replaces it.
        """

        if section not in SECTIONS:
            raise SettingsError(f"Unknown settings section '{section}'.")
        defaults = SECTIONS[section]
        stored = self._stored(section)
        secrets = SECRETS.get(section, ())
        for key, value in changes.items():
            if key not in defaults:
                continue
            if key in secrets:
                if value is None:
                    continue
                stored[key] = self._seal(str(value)) if value else ""
                continue
            stored[key] = _coerce(key, value, defaults[key])
        self._validate(section, {**defaults, **stored})
        with self.connection.transaction():
            self.connection.execute(
                "INSERT OR REPLACE INTO settings (key, value, updated_at) VALUES (?, ?, ?)",
                (f"system.{section}", json.dumps(stored), _now()),
            )
        return self.get(section)

    @staticmethod
    def _validate(section: str, values: Dict[str, Any]) -> None:
        if section == "smtp" and values["enabled"]:
            if not values["host"]:
                raise SettingsError("Give the SMTP server's host name.")
            if not 0 < int(values["port"]) < 65536:
                raise SettingsError("The SMTP port must be between 1 and 65535.")
            if values["security"] not in ("none", "starttls", "ssl"):
                raise SettingsError("Security must be none, starttls or ssl.")
            if "@" not in str(values["from_address"]):
                raise SettingsError("Give the address e-mails are sent from.")
        if section == "ldap" and values["enabled"]:
            if not str(values["server_url"]).startswith(("ldap://", "ldaps://")):
                raise SettingsError("The LDAP server URL starts with ldap:// or ldaps://.")
            if not values["user_base_dn"]:
                raise SettingsError("Give the base DN to search for users in.")
            if "{username}" not in str(values["user_filter"]):
                raise SettingsError("The user filter must contain {username}.")
        if section == "oidc" and values["enabled"]:
            if not str(values["issuer"]).startswith("https://") and not str(
                values["issuer"]
            ).startswith("http://localhost"):
                raise SettingsError("The issuer is an https:// URL.")
            if not values["client_id"]:
                raise SettingsError("Give the client ID registered with the identity provider.")
        if section in ("database_target", "cache", "queue") and values["enabled"]:
            if not values["host"]:
                raise SettingsError("Give the server's host name.")
            if not 0 < int(values["port"]) < 65536:
                raise SettingsError("The port must be between 1 and 65535.")
        if section == "database_target" and values["enabled"]:
            if values["engine"] not in ENGINES:
                raise SettingsError("The database is PostgreSQL or Oracle.")
            if not values["database"]:
                raise SettingsError("Give the database name (Oracle: the service name).")
        if section == "cache" and values["enabled"]:
            if not 0 <= int(values["database"]) <= 15:
                raise SettingsError("The Redis database number is between 0 and 15.")
            if int(values["default_ttl_seconds"]) < 0:
                raise SettingsError("The cache lifetime cannot be negative.")
        if section == "queue" and values["enabled"] and values["broker"] not in BROKERS:
            raise SettingsError("The broker is ActiveMQ, RabbitMQ, MQTT or Kafka.")
        if (
            section == "general"
            and values["public_url"]
            and not str(values["public_url"]).startswith(("http://", "https://"))
        ):
            raise SettingsError("The address starts with http:// or https://.")


def _coerce(key: str, value: Any, default: Any) -> Any:
    if isinstance(default, bool):
        return bool(value)
    if isinstance(default, int):
        try:
            return int(value)
        except (TypeError, ValueError):
            raise SettingsError(f"{key} must be a number.") from None
    if isinstance(default, list):
        if not isinstance(value, list):
            raise SettingsError(f"{key} must be a list.")
        return _mappings(value) if key == "group_mappings" else value
    return str(value if value is not None else "").strip()


def _mappings(value: List[Any]) -> List[Dict[str, str]]:
    cleaned = []
    for item in value[:200]:
        if not isinstance(item, dict):
            raise SettingsError("Each group mapping has an external group and an Entropy group.")
        external = str(item.get("external") or "").strip()
        group = str(item.get("group") or "").strip()
        if external and group:
            cleaned.append({"external": external, "group": group})
    return cleaned


def settings_for(context: Any) -> SystemSettings:
    """The settings store of a running Entropy (with the vault key for secrets)."""

    key = None
    try:
        from lib.vault.key import VaultKeyProvider

        key = VaultKeyProvider(context.executor, context.bootstrap.vault.key).key()
    except Exception:  # noqa: BLE001 - secrets then cannot be stored or read
        key = None
    return SystemSettings(context.database_manager.connection, key)
