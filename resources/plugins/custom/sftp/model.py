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


@dataclass(frozen=True)
class SftpAlgorithmSettings:
    """
    Optional SSH algorithm configuration.
    """

    kex: str | None = None
    host_key: str | None = None
    cipher: str | None = None
    mac: str | None = None


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
