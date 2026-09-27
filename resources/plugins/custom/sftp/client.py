"""
SFTP client implementation.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import paramiko

from .exceptions import SftpPluginException
from .model import SftpCredentials, SftpSettings


class SftpClient:
    """
    Thin wrapper around Paramiko SFTP operations.
    """

    def __init__(
        self,
        credentials: SftpCredentials,
        settings: SftpSettings | None = None,
    ) -> None:
        self._credentials = credentials
        self._settings = settings
        self._ssh: paramiko.SSHClient | None = None
        self._sftp: paramiko.SFTPClient | None = None

    def connect(self) -> None:
        """
        Establish the SSH and SFTP connection.
        """

        if self._ssh is not None:
            return

        ssh = paramiko.SSHClient()

        # We intentionally do not automatically trust unknown hosts.
        ssh.load_system_host_keys()

        host_key = (
            self._settings.host_key
            if self._settings is not None
            else None
        )

        if host_key is not None and host_key.policy == "auto_add":
            ssh.set_missing_host_key_policy(
                paramiko.AutoAddPolicy(),
            )

        kwargs: dict[str, Any] = {
            "hostname": self._credentials.host,
            "port": self._credentials.port,
            "username": self._credentials.user,
            "transport_factory": self._transport_factory,
        }

        if self._credentials.password is not None:
            kwargs["password"] = self._credentials.password

        if self._credentials.key_filename is not None:
            kwargs["key_filename"] = str(
                self._credentials.key_filename,
            )

        connection = (
            self._settings.connection
            if self._settings is not None
            else None
        )

        if connection is not None:
            if connection.timeout is not None:
                kwargs["timeout"] = connection.timeout

            if connection.banner_timeout is not None:
                kwargs["banner_timeout"] = connection.banner_timeout

            if connection.auth_timeout is not None:
                kwargs["auth_timeout"] = connection.auth_timeout

        try:
            ssh.connect(**kwargs)
            self._ssh = ssh
            self._sftp = ssh.open_sftp()

        except Exception as exc:
            ssh.close()

            raise SftpPluginException(
                "Unable to establish SFTP connection "
                f"to '{self._credentials.host}:{self._credentials.port}': "
                f"{exc}",
            ) from exc

    def close(self) -> None:
        """
        Close the SFTP and SSH connections.
        """

        if self._sftp is not None:
            try:
                self._sftp.close()
            finally:
                self._sftp = None

        if self._ssh is not None:
            try:
                self._ssh.close()
            finally:
                self._ssh = None

    def __enter__(self) -> SftpClient:
        self.connect()
        return self

    def __exit__(
        self,
        exc_type: Any,
        exc_value: Any,
        traceback: Any,
    ) -> None:
        self.close()

    # ------------------------------------------------------------------
    # Basic operations
    # ------------------------------------------------------------------

    def upload(
        self,
        source: Path,
        destination: str,
    ) -> None:
        """
        Upload a local file to the remote destination.
        """

        sftp = self._require_connection()

        try:
            sftp.put(
                str(source),
                destination,
            )
        except Exception as exc:
            raise SftpPluginException(
                f"Unable to upload '{source}' to "
                f"'{destination}': {exc}",
            ) from exc

    def download(
        self,
        source: str,
        destination: Path,
    ) -> None:
        """
        Download a remote file to a local destination.
        """

        sftp = self._require_connection()

        try:
            sftp.get(
                source,
                str(destination),
            )
        except Exception as exc:
            raise SftpPluginException(
                f"Unable to download '{source}' to "
                f"'{destination}': {exc}",
            ) from exc

    def listdir(
        self,
        path: str,
    ) -> list[str]:
        """
        List entries in a remote directory.
        """

        sftp = self._require_connection()

        try:
            return list(
                sftp.listdir(path),
            )
        except Exception as exc:
            raise SftpPluginException(
                f"Unable to list remote path "
                f"'{path}': {exc}",
            ) from exc

    def stat(
        self,
        path: str,
    ) -> paramiko.SFTPAttributes:
        """
        Return remote path attributes.
        """

        sftp = self._require_connection()

        try:
            return sftp.stat(path)
        except Exception as exc:
            raise SftpPluginException(
                f"Unable to stat remote path "
                f"'{path}': {exc}",
            ) from exc

    def mkdir(
        self,
        path: str,
    ) -> None:
        """
        Create a remote directory.
        """

        sftp = self._require_connection()

        try:
            sftp.mkdir(path)
        except Exception as exc:
            raise SftpPluginException(
                f"Unable to create remote directory "
                f"'{path}': {exc}",
            ) from exc

    def open_directory(
        self,
        path: str,
    ) -> Iterator[paramiko.SFTPAttributes]:
        """
        Iterate over remote directory entries.
        """

        sftp = self._require_connection()

        try:
            yield from sftp.listdir_attr(path)
        except Exception as exc:
            raise SftpPluginException(
                f"Unable to read remote directory "
                f"'{path}': {exc}",
            ) from exc

    # ------------------------------------------------------------------
    # Transport
    # ------------------------------------------------------------------

    def _transport_factory(
        self,
        sock: Any,
        *args: Any,
        **kwargs: Any,
    ) -> paramiko.Transport:
        """
        Create and configure the Paramiko SSH transport.
        """

        transport = paramiko.Transport(
            sock,
            *args,
            **kwargs,
        )

        algorithms = (
            self._settings.algorithms
            if self._settings is not None
            else None
        )

        if algorithms is None:
            return transport

        security = transport.get_security_options()

        if algorithms.kex is not None:
            security.kex = (
                algorithms.kex,
            )

        if algorithms.host_key is not None:
            security.key_types = (
                algorithms.host_key,
            )

        if algorithms.cipher is not None:
            security.ciphers = (
                algorithms.cipher,
            )

        if algorithms.mac is not None:
            security.digests = (
                algorithms.mac,
            )

        return transport

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _require_connection(
        self,
    ) -> paramiko.SFTPClient:
        if self._sftp is None:
            raise SftpPluginException(
                "SFTP client is not connected.",
            )

        return self._sftp
