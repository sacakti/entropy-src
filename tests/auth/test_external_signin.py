"""Sign-in with LDAP / Active Directory and single sign-on (OpenID Connect)."""

from __future__ import annotations

import os
from types import SimpleNamespace

import ldap3
import pytest
from fake_idp import FakeIdP

from core.context import EntropyContext
from lib.auth import oidc
from lib.auth.external import ExternalAccounts, SignInRefused, sign_in
from lib.auth.ldap_directory import Directory, mapped_groups
from lib.auth.service import AuthenticationService
from lib.database.objects.groups import GroupsTable
from lib.database.objects.user_groups import UserGroupsTable
from lib.database.repositories.users import UserRepository
from lib.system.settings import SystemSettings
from lib.users.exceptions import AuthenticationError
from lib.users.manager import UserManager
from lib.users.password import PasswordService

BASE = "ou=people,dc=example,dc=com"
OPS = "cn=ops,ou=groups,dc=example,dc=com"


@pytest.fixture
def context(connection):
    """The services sign-in uses (the shared fixture also needs observability)."""

    context = EntropyContext()
    context.password_service = PasswordService()
    context.user_repository = UserRepository(connection)
    context.authentication = AuthenticationService(context)
    context.database_manager = SimpleNamespace(connection=connection)
    return context


@pytest.fixture
def user_manager(context):
    return UserManager(context)


@pytest.fixture
def store(context, connection, monkeypatch):
    GroupsTable().create(connection)
    UserGroupsTable().create(connection)
    settings = SystemSettings(connection, os.urandom(32))
    monkeypatch.setattr("lib.system.settings.settings_for", lambda _context: settings)
    for name in ("ops", "devs", "hand-made"):
        connection.execute(
            "INSERT INTO groups (name, created_at, updated_at) VALUES (?, 'now', 'now')", (name,)
        )
    connection.commit()
    return settings


@pytest.fixture
def directory(store, monkeypatch):
    """An in-memory directory with a service account and two people."""

    server = ldap3.Server("mock")
    monkeypatch.setattr(Directory, "client_strategy", ldap3.MOCK_SYNC)
    monkeypatch.setattr(Directory, "_server", lambda self: server)
    seed = ldap3.Connection(server, client_strategy=ldap3.MOCK_SYNC)
    seed.strategy.add_entry(
        "cn=svc,dc=example,dc=com", {"objectClass": "person", "userPassword": "svc-pass"}
    )
    for uid, name, groups in (("jdoe", "Jane Doe", [OPS]), ("admin", "Directory Admin", [])):
        seed.strategy.add_entry(
            f"uid={uid},{BASE}",
            {
                "objectClass": "person",
                "uid": uid,
                "cn": name,
                "mail": f"{uid}@example.com",
                "userPassword": f"{uid}-pass",
                "memberOf": groups,
            },
        )
    store.update(
        "ldap",
        {
            "enabled": True,
            "server_url": "ldap://directory.example.com",
            "bind_dn": "cn=svc,dc=example,dc=com",
            "bind_password": "svc-pass",
            "user_base_dn": BASE,
            "user_filter": "(uid={username})",
            "group_mappings": [
                {"external": OPS, "group": "ops"},
                {"external": "devs", "group": "devs"},
            ],
        },
    )
    return server


def _groups(connection, user_id):
    rows = connection.fetchall(
        "SELECT g.name FROM user_groups ug JOIN groups g ON g.id = ug.group_id"
        " WHERE ug.user_id = ? ORDER BY g.name",
        (user_id,),
    )
    return [row["name"] for row in rows]


# ----------------------------------------------------------------------
# LDAP
# ----------------------------------------------------------------------


def test_ldap_user_is_created_with_mapped_groups(context, connection, directory) -> None:
    user = sign_in(context, "jdoe", "jdoe-pass")

    assert (user.username, user.full_name, user.email) == ("jdoe", "Jane Doe", "jdoe@example.com")
    assert _groups(connection, user.id) == ["ops"]
    assert ExternalAccounts(context).provider_of(user.id) == "ldap"
    # Next time the same account is used, not a new one.
    assert sign_in(context, "jdoe", "jdoe-pass").id == user.id


def test_ldap_wrong_or_empty_password_is_refused(context, directory) -> None:
    with pytest.raises(AuthenticationError):
        sign_in(context, "jdoe", "wrong")
    # An empty password must never become an anonymous bind that "works".
    with pytest.raises(AuthenticationError):
        sign_in(context, "jdoe", "")
    with pytest.raises(AuthenticationError):
        sign_in(context, "nobody", "x")


def test_local_accounts_are_not_taken_over(context, directory, user_manager) -> None:
    user_manager.create("admin", "Str0ng!Passw0rd#2026")

    # The directory's "admin" password does not open the local admin account.
    with pytest.raises(AuthenticationError):
        sign_in(context, "admin", "admin-pass")
    assert sign_in(context, "admin", "Str0ng!Passw0rd#2026").username == "admin"


def test_group_sync_only_touches_mapped_groups(context, connection, directory) -> None:
    user = sign_in(context, "jdoe", "jdoe-pass")
    hand_made = connection.fetchone("SELECT id FROM groups WHERE name = 'hand-made'")["id"]
    devs = connection.fetchone("SELECT id FROM groups WHERE name = 'devs'")["id"]
    for group_id in (hand_made, devs):
        connection.execute(
            "INSERT INTO user_groups (user_id, group_id, created_at) VALUES (?, ?, 'now')",
            (user.id, group_id),
        )
    connection.commit()

    sign_in(context, "jdoe", "jdoe-pass")

    # devs is mapped and jdoe is not in it in the directory; hand-made is Entropy's own.
    assert _groups(connection, user.id) == ["hand-made", "ops"]


def test_no_auto_create_and_ldap_off(context, store, directory) -> None:
    store.update("ldap", {"auto_create_users": False})
    with pytest.raises(SignInRefused, match="no Entropy account"):
        sign_in(context, "jdoe", "jdoe-pass")

    store.update("ldap", {"auto_create_users": True})
    sign_in(context, "jdoe", "jdoe-pass")
    store.update("ldap", {"enabled": False})
    with pytest.raises(SignInRefused, match="turned off"):
        sign_in(context, "jdoe", "jdoe-pass")


def test_mapping_by_dn_or_cn() -> None:
    mappings = [{"external": "ops", "group": "a"}, {"external": "CN=Devs, OU=x", "group": "b"}]
    assert mapped_groups(mappings, ["cn=ops,ou=groups", "cn=devs,ou=x"], dn=True) == ["a", "b"]
    assert mapped_groups(mappings, ["Ops"], dn=False) == ["a"]


# ----------------------------------------------------------------------
# OpenID Connect
# ----------------------------------------------------------------------


@pytest.fixture
def idp(store):
    with FakeIdP() as provider:
        oidc.forget_cache()
        store.update(
            "oidc",
            {
                "enabled": True,
                "issuer": provider.issuer,
                "client_id": provider.client_id,
                "client_secret": provider.client_secret,
                "group_mappings": [{"external": "platform", "group": "ops"}],
            },
        )
        yield provider
    oidc.forget_cache()


def _sso(store, idp, claims=None):
    settings = store.values("oidc")
    url, state = oidc.start(settings, "https://entropy.example.com/api/auth/oidc/callback")
    callback = idp.authorize(url, claims)
    assert callback["state"] == state
    return oidc.finish(settings, state, callback["code"])


def test_oidc_code_flow_signs_in(context, connection, store, idp) -> None:
    idp.userinfo = {"email": "dana@example.com", "groups": ["platform"], "sub": "other"}
    claims = _sso(store, idp, {"sub": "u-1", "preferred_username": "dana", "groups": ["platform"]})
    assert claims["preferred_username"] == "dana"
    # Userinfo for another subject is ignored.
    assert "email" not in claims

    user = ExternalAccounts(context).account(
        "oidc",
        claims["sub"],
        username=claims["preferred_username"],
        full_name=None,
        email=None,
        auto_create=True,
        groups=mapped_groups(
            [{"external": "platform", "group": "ops"}], claims["groups"], dn=False
        ),
        managed_groups=["ops"],
    )
    assert _groups(connection, user.id) == ["ops"]
    # Password sign-in is refused for single sign-on accounts.
    with pytest.raises(SignInRefused, match="single sign-on"):
        sign_in(context, "dana", "anything")


def test_oidc_rejects_bad_signature_and_reused_state(store, idp) -> None:
    idp.tamper = True
    with pytest.raises(oidc.OidcError, match="signature"):
        _sso(store, idp)

    idp.tamper = False
    settings = store.values("oidc")
    url, state = oidc.start(settings, "https://entropy.example.com/cb")
    callback = idp.authorize(url)
    oidc.finish(settings, state, callback["code"])
    with pytest.raises(oidc.OidcError, match="already used"):
        oidc.finish(settings, state, callback["code"])


def test_oidc_rejects_wrong_audience_and_nonce(store, idp) -> None:
    with pytest.raises(oidc.OidcError, match="another application"):
        _sso(store, idp, {"sub": "u-1", "aud": "someone-else"})
    with pytest.raises(oidc.OidcError, match="matched to this browser"):
        _sso(store, idp, {"sub": "u-1", "nonce": "forged"})


def test_oidc_does_not_take_over_local_accounts(context, idp, user_manager) -> None:
    user_manager.create("dana", "Str0ng!Passw0rd#2026")
    with pytest.raises(SignInRefused, match="local account"):
        ExternalAccounts(context).account(
            "oidc",
            "u-1",
            username="dana",
            full_name=None,
            email=None,
            auto_create=True,
            groups=[],
            managed_groups=[],
        )
