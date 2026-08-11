"""
Vault master key provider.
"""

from __future__ import annotations

import secrets
from pathlib import Path

from lib.executor import LinuxExecutor
from lib.vault.exceptions import VaultKeyError

class VaultKeyProvider:
    """
    Provides the Vault master encryption key.

    The key is generated once and persisted with restrictive
    filesystem permissions.
    """

    KEY_SIZE = 32

    KEY_MODE = 0o600

    def __init__(
        self,
        executor: LinuxExecutor,
        path: Path,
    ) -> None:

        self._executor = executor
        self._path = path

    # ------------------------------------------------------------------
    # Public
    # ------------------------------------------------------------------

    def key(self) -> bytes:
        """
        Return the Vault master key.

        Creates the key when it does not already exist.
        """

        if self._executor.exists(
            self._path,
        ):

            return self._read()

        return self._create()

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _read(self) -> bytes:
        """
        Read and validate the existing master key.
        """

        try:

            key = self._executor.read_bytes(
                self._path,
            )

        except Exception as exc:

            raise VaultKeyError(
                "Unable to read Vault master key."
            ) from exc

        if len(key) != self.KEY_SIZE:

            raise VaultKeyError(
                "Invalid Vault master key length. "
                f"Expected {self.KEY_SIZE} bytes, "
                f"received {len(key)} bytes."
            )

        return key

    def _create(self) -> bytes:
        """
        Generate and persist a new master key.
        """

        directory = self._path.parent

        try:

            self._executor.mkdir(
                directory,
            )

            key = secrets.token_bytes(
                self.KEY_SIZE,
            )

            self._executor.write_bytes(
                self._path,
                key,
            )

            self._executor.chmod(
                self._path,
                self.KEY_MODE,
            )

        except Exception as exc:

            raise VaultKeyError(
                "Unable to create Vault master key."
            ) from exc

        return key
