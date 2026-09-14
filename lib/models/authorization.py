"""
Authorization models.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Optional


class PermissionType(str, Enum):
    """
    Broad permission classification.
    """

    READ = "read"
    WRITE = "write"
    EXECUTE = "execute"


class VaultVisibility(str, Enum):
    """
    Vault namespace visibility.
    """

    PRIVATE = "private"
    SHARED = "shared"


class VaultAccess(str, Enum):
    """
    Access granted to a Vault namespace.
    """

    READ = "read"
    WRITE = "write"
    ADMIN = "admin"


@dataclass
class Group:
    """
    Represents a user group.
    """

    id: Optional[int] = None

    name: str = ""

    description: Optional[str] = None

    created_at: Optional[datetime] = None

    updated_at: Optional[datetime] = None

    @property
    def is_new(self) -> bool:
        return self.id is None


@dataclass
class Role:
    """
    Represents an authorization role.
    """

    id: Optional[int] = None

    name: str = ""

    description: Optional[str] = None

    created_at: Optional[datetime] = None

    updated_at: Optional[datetime] = None

    @property
    def is_new(self) -> bool:
        return self.id is None


@dataclass
class Module:
    """
    Represents an Entropy functional module.
    """

    id: Optional[int] = None

    name: str = ""

    description: Optional[str] = None

    @property
    def is_new(self) -> bool:
        return self.id is None


@dataclass
class Permission:
    """
    Represents an operation-level permission.
    """

    id: Optional[int] = None

    module_id: Optional[int] = None

    name: str = ""

    description: Optional[str] = None

    permission_type: PermissionType = PermissionType.EXECUTE

    @property
    def is_new(self) -> bool:
        return self.id is None


@dataclass
class UserRole:
    """
    Associates a user with a role.
    """

    id: Optional[int] = None

    user_id: int = 0

    role_id: int = 0

    created_at: Optional[datetime] = None


@dataclass
class UserGroup:
    """
    Associates a user with a group.
    """

    id: Optional[int] = None

    user_id: int = 0

    group_id: int = 0

    created_at: Optional[datetime] = None


@dataclass
class GroupRole:
    """
    Associates a group with a role.
    """

    id: Optional[int] = None

    group_id: int = 0

    role_id: int = 0

    created_at: Optional[datetime] = None


@dataclass
class RolePermission:
    """
    Associates a role with a permission.
    """

    id: Optional[int] = None

    role_id: int = 0

    permission_id: int = 0

    created_at: Optional[datetime] = None


@dataclass
class UserPrivilege:
    """
    Grants a specific permission directly to a user.
    """

    id: Optional[int] = None

    user_id: int = 0

    permission_id: int = 0

    created_at: Optional[datetime] = None


@dataclass
class VaultNamespace:
    """
    Represents a Vault namespace.

    A namespace provides isolation between groups of Vault entries,
    such as SIT, UAT, and PROD.
    """

    id: Optional[int] = None

    name: str = ""

    owner_user_id: Optional[int] = None

    visibility: VaultVisibility = VaultVisibility.PRIVATE

    created_at: Optional[datetime] = None

    updated_at: Optional[datetime] = None

    @property
    def is_new(self) -> bool:
        return self.id is None


@dataclass
class VaultNamespaceAccess:
    """
    Grants a user access to a Vault namespace.
    """

    id: Optional[int] = None

    namespace_id: int = 0

    user_id: int = 0

    access: VaultAccess = VaultAccess.READ

    created_at: Optional[datetime] = None
