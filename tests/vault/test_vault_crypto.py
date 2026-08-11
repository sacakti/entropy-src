from pathlib import Path
import tempfile

from lib.executor import LinuxExecutor
from lib.vault import (
    VaultCipher,
    VaultKeyProvider,
)


def main() -> None:

    executor = LinuxExecutor()

    with tempfile.TemporaryDirectory() as directory:

        root = Path(directory)

        key_path = root / "vault" / "master.key"

        # ---------------------------------------------------------
        # Create / load master key
        # ---------------------------------------------------------

        provider = VaultKeyProvider(
            executor=executor,
            path=key_path,
        )

        key1 = provider.key()

        print(
            f"Key created: {len(key1)} bytes"
        )

        assert len(key1) == 32

        # ---------------------------------------------------------
        # Key must be reused
        # ---------------------------------------------------------

        key2 = provider.key()

        assert key1 == key2

        print("Key reuse: PASS")

        # ---------------------------------------------------------
        # Encrypt
        # ---------------------------------------------------------

        cipher = VaultCipher(
            key1,
        )

        plaintext = b"my-secret-password"

        encrypted1 = cipher.encrypt(
            plaintext,
        )

        encrypted2 = cipher.encrypt(
            plaintext,
        )

        assert encrypted1 != encrypted2

        print("Unique ciphertext: PASS")

        # ---------------------------------------------------------
        # Decrypt
        # ---------------------------------------------------------

        decrypted = cipher.decrypt(
            encrypted1,
        )

        assert decrypted == plaintext

        print("Encryption/decryption: PASS")

        # ---------------------------------------------------------
        # Tamper detection
        # ---------------------------------------------------------

        tampered = bytearray(
            encrypted1,
        )

        tampered[-1] ^= 1

        try:

            cipher.decrypt(
                bytes(tampered),
            )

        except Exception:

            print("Tamper detection: PASS")

        else:

            raise AssertionError(
                "Tampered ciphertext was accepted."
            )

        # ---------------------------------------------------------
        # Wrong key
        # ---------------------------------------------------------

        wrong_cipher = VaultCipher(
            b"x" * 32,
        )

        try:

            wrong_cipher.decrypt(
                encrypted1,
            )

        except Exception:

            print("Wrong key detection: PASS")

        else:

            raise AssertionError(
                "Ciphertext decrypted with wrong key."
            )

        # ---------------------------------------------------------
        # Invalid key length
        # ---------------------------------------------------------

        try:

            VaultCipher(
                b"short",
            )

        except Exception:

            print("Invalid key length: PASS")

        else:

            raise AssertionError(
                "Invalid key length was accepted."
            )

        # ---------------------------------------------------------
        # Key file
        # ---------------------------------------------------------

        assert executor.exists(
            key_path,
        )

        print(
            f"Key path: {key_path}"
        )

        print(
            "All Vault crypto tests passed."
        )


if __name__ == "__main__":
    main()
