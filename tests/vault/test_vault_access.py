"""Vault access comes from project roles (RBAC)."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from lib.authorization.constants import PERMISSION_RENAMES, PERMISSIONS
from lib.authorization.projects import BUILTIN_ROLES, PROJECT_PERMISSIONS, role_scope
from lib.vault import access
from lib.vault.exceptions import VaultAccessDeniedError

VAULT = {
    "vault.namespace.read",
    "vault.read",
    "vault.add",
    "vault.modify",
    "vault.delete",
    "vault.namespace.create",
    "vault.namespace.modify",
    "vault.namespace.delete",
}


def _vault_permissions(role: str) -> set:
    return set(BUILTIN_ROLES[role][3]) & VAULT


# ----------------------------------------------------------------------
# Catalogue and roles
# ----------------------------------------------------------------------


def test_vault_permissions_are_project_permissions() -> None:
    assert VAULT <= PROJECT_PERMISSIONS
    assert role_scope(VAULT) == "project"


def test_per_namespace_user_grants_are_gone() -> None:
    names = {permission.name for permission in PERMISSIONS}

    assert "vault.namespace.users" not in names
    # Removed at startup, with its grants.
    assert PERMISSION_RENAMES["vault.namespace.users"] == ()
    assert "vault-user" not in BUILTIN_ROLES


def test_builtin_project_roles_follow_the_tiers() -> None:
    assert _vault_permissions("viewer") == {"vault.namespace.read"}
    assert _vault_permissions("operator") == {"vault.namespace.read"}
    assert _vault_permissions("developer") == {
        "vault.namespace.read",
        "vault.read",
        "vault.add",
        "vault.modify",
    }
    assert _vault_permissions("maintainer") == VAULT
    # No global built-in role (other than Administrator, which has all) holds Vault.
    for name, (_, scope, _, permissions) in BUILTIN_ROLES.items():
        if scope == "global" and permissions is not None:
            assert not set(permissions) & VAULT, name


# ----------------------------------------------------------------------
# Access helpers
# ----------------------------------------------------------------------


class FakeAuthorization:
    def __init__(self, *grants: tuple) -> None:
        self.grants = set(grants)

    def has_permission(self, user_id, permission, project_id=None) -> bool:
        return (user_id, permission, project_id) in self.grants


def test_can_is_per_project() -> None:
    authorization = FakeAuthorization((1, "vault.read", 10))

    assert access.can(authorization, 1, "vault.read", 10)
    assert not access.can(authorization, 1, "vault.read", 11)
    assert not access.can(authorization, None, "vault.read", 10)
    assert not access.can(None, 1, "vault.read", 10)

    with pytest.raises(VaultAccessDeniedError, match="vault.read"):
        access.require(authorization, 1, "vault.read", 11)


@pytest.mark.parametrize("permission", ["workflows.execute", "plugins.execute"])
def test_runs_need_run_rights_in_the_project(permission: str) -> None:
    access.require_run(FakeAuthorization((1, permission, 10)), 1, 10)

    with pytest.raises(VaultAccessDeniedError):
        access.require_run(FakeAuthorization((1, permission, 10)), 1, 11)


# ----------------------------------------------------------------------
# Web routes
# ----------------------------------------------------------------------


def _request(authorization) -> SimpleNamespace:
    context = SimpleNamespace(authorization=authorization)
    return SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(entropy_context=context)))


def test_route_permissions_describe_the_project_role() -> None:
    from core.web.routes.vault import _permissions

    user = SimpleNamespace(id=1)
    viewer = FakeAuthorization((1, "vault.namespace.read", 10))

    assert _permissions(_request(viewer), user, 10) == {
        "namespace_read": True,
        "reveal": False,
        "add": False,
        "modify": False,
        "delete": False,
        "namespace_create": False,
        "namespace_modify": False,
        "namespace_delete": False,
    }
    assert not any(_permissions(_request(viewer), user, 11).values())


def test_route_require_refuses_other_projects() -> None:
    from fastapi import HTTPException

    from core.web.routes.vault import _require

    user = SimpleNamespace(id=1)
    request = _request(FakeAuthorization((1, "vault.read", 10)))

    _require(request, user, "vault.read", 10)
    with pytest.raises(HTTPException) as raised:
        _require(request, user, "vault.read", 11)
    assert raised.value.status_code == 403
