"""
Vault encryption.
"""

from __future__ import annotations

import secrets

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM


class VaultEncryptionError(RuntimeError):
    """
    Raised when Vault encryption or decryption fails.
    """


class VaultCipher:
    """
    AES-256-GCM encryption for Vault values.

    The cipher does not know where the key comes from.
    """

    NONCE_SIZE = 12

    KEY_SIZE = 32

    def __init__(
        self,
        key: bytes,
    ) -> None:

        if len(key) != self.KEY_SIZE:

            raise VaultEncryptionError(
                "Invalid Vault encryption key length. "
                f"Expected {self.KEY_SIZE} bytes, "
                f"received {len(key)} bytes."
            )

        self._cipher = AESGCM(
            key,
        )

    # ------------------------------------------------------------------
    # Public
    # ------------------------------------------------------------------

    def encrypt(
        self,
        value: bytes,
    ) -> bytes:
        """
        Encrypt a value.

        Returns
        -------
        bytes
            Nonce followed by AES-GCM ciphertext.
        """

        nonce = secrets.token_bytes(
            self.NONCE_SIZE,
        )

        try:

            ciphertext = self._cipher.encrypt(
                nonce,
                value,
                None,
            )

        except Exception as exc:

            raise VaultEncryptionError(
                "Unable to encrypt Vault value."
            ) from exc

        return nonce + ciphertext

    def decrypt(
        self,
        value: bytes,
    ) -> bytes:
        """
        Decrypt and authenticate a Vault value.
        """

        if len(value) <= self.NONCE_SIZE:

            raise VaultEncryptionError(
                "Invalid Vault ciphertext."
            )

        nonce = value[
            : self.NONCE_SIZE
        ]

        ciphertext = value[
            self.NONCE_SIZE :
        ]

        try:

            return self._cipher.decrypt(
                nonce,
                ciphertext,
                None,
            )

        except InvalidTag as exc:

            raise VaultEncryptionError(
                "Vault value authentication failed."
            ) from exc

        except Exception as exc:

            raise VaultEncryptionError(
                "Unable to decrypt Vault value."
            ) from exc
