"""
Entropy Vault.
"""

from lib.models.vault import (
    VaultEntry,
    VaultValueType,
)
from lib.database.repositories.vault import VaultRepository
from .serializer import (
    VaultSerializationError,
    VaultSerializer,
)
from .manager import (
    VaultManager,
)

from .exceptions import (
    VaultEntryExistsError,
    VaultEntryNotFoundError,
    VaultError,
)

from .cipher import VaultCipher

from .key import VaultKeyProvider

__all__ = [
    "VaultEntry",
    "VaultEntryExistsError",
    "VaultEntryNotFoundError",
    "VaultError",
    "VaultManager",
    "VaultRepository",
    "VaultSerializationError",
    "VaultSerializer",
    "VaultValueType",
]
