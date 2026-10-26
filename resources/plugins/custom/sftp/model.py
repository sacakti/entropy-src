"""
SFTP plugin models.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class SftpConnectionSettings:
    """
    Optional SFTP connection settings.
    """

    timeout: float | None = None
    banner_timeout: float | None = None
    auth_timeout: float | None = None


# Preferred when the settings name none: modern first, legacy RSA last.
DEFAULT_HOST_KEY_ALGORITHMS = (
    "ssh-ed25519",
    "ecdsa-sha2-nistp256",
    "ecdsa-sha2-nistp384",
    "ecdsa-sha2-nistp521",
    "rsa-sha2-512",
    "rsa-sha2-256",
    "ssh-rsa",
)

# Authenticated (GCM) and counter-mode AES only; no CBC or 3DES.
DEFAULT_CIPHERS = (
    "aes256-gcm@openssh.com",
    "aes128-gcm@openssh.com",
    "aes256-ctr",
    "aes192-ctr",
    "aes128-ctr",
)


@dataclass(frozen=True)
class SftpAlgorithmSettings:
    """
    Optional SSH algorithm configuration: each a preference list, the
    first the server also offers is used.
    """

    kex: tuple[str, ...] | None = None
    host_key: tuple[str, ...] | None = None
    cipher: tuple[str, ...] | None = None
    mac: tuple[str, ...] | None = None


@dataclass(frozen=True)
class SftpHostKeySettings:
    """
    Optional SSH host-key verification settings.
    """

    policy: str = "known_hosts"


@dataclass(frozen=True)
class SftpSettings:
    """
    Optional SFTP connection and SSH settings.
    """

    connection: SftpConnectionSettings | None = None
    algorithms: SftpAlgorithmSettings | None = None
    host_key: SftpHostKeySettings | None = None
    # Trust an unknown server on first connection and save its key to
    # `known_hosts`; later runs verify against it.
    add_host: bool = False
    known_hosts: Path | None = None


@dataclass(frozen=True)
class SftpCredentials:
    """
    SFTP authentication and endpoint credentials.
    """

    host: str
    port: int
    user: str
    password: str | None
    key_filename: Path | None = None


@dataclass(frozen=True)
class SftpArchive:
    """
    Archive configuration.
    """

    enabled: bool = False
    filename_policy: str | None = None


@dataclass(frozen=True)
class SftpRequest:
    """
    Resolved SFTP operation request.
    """

    operation: str
    source: str | None
    destination: str | None
    archive: SftpArchive
    sftp: SftpCredentials
    settings: SftpSettings | None = None
