"""
SFTP client implementation.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import paramiko

from .exceptions import SftpPluginException
from .model import (
    DEFAULT_CIPHERS,
    DEFAULT_HOST_KEY_ALGORITHMS,
    SftpCredentials,
    SftpSettings,
)


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
        # "type fingerprint" of a server key saved by add_host, if any.
        self.added_host_key: str | None = None

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

        add_host = self._settings is not None and self._settings.add_host
        known_hosts = self._known_hosts()

        if add_host:
            # Keys in this file are checked as usual; an unknown server is
            # trusted once and its key saved here for the next runs.
            known_hosts.parent.mkdir(
                mode=0o700,
                parents=True,
                exist_ok=True,
            )
            known_hosts.touch(
                mode=0o600,
                exist_ok=True,
            )
            self._load_known_hosts(ssh, known_hosts)
            ssh.set_missing_host_key_policy(
                paramiko.AutoAddPolicy(),
            )
        elif known_hosts.is_file():
            self._load_known_hosts(ssh, known_hosts)

        lookup = (
            self._credentials.host
            if self._credentials.port == 22
            else f"[{self._credentials.host}]:{self._credentials.port}"
        )
        known_before = ssh.get_host_keys().lookup(lookup) is not None

        kwargs: dict[str, Any] = {
            "hostname": self._credentials.host,
            "port": self._credentials.port,
            "username": self._credentials.user,
            "transport_factory": self._transport_factory,
            "look_for_keys": False,
            "allow_agent": False,
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

            if add_host and not known_before:
                key = ssh.get_transport().get_remote_server_key()
                ssh.save_host_keys(
                    str(known_hosts),
                )
                self.added_host_key = (
                    f"{key.get_name()} {key.fingerprint}"
                    if hasattr(key, "fingerprint")
                    else key.get_name()
                )

            self._ssh = ssh
            self._sftp = ssh.open_sftp()

        except Exception as exc:
            ssh.close()

            hint = ""
            if "known_hosts" in str(exc):
                hint = (
                    " Add the server's key to known_hosts, or set "
                    '"settings": {"add_host": true} to trust it on first '
                    "connection and save it."
                )

            raise SftpPluginException(
                "Unable to establish SFTP connection "
                f"to '{self._credentials.host}:{self._credentials.port}': "
                f"{str(exc).rstrip('.')}.{hint}",
            ) from exc

    @staticmethod
    def _load_known_hosts(
        ssh: paramiko.SSHClient,
        path: Path,
    ) -> None:
        try:
            ssh.load_host_keys(
                str(path),
            )
        except (OSError, paramiko.SSHException) as exc:
            raise SftpPluginException(
                f"known_hosts file '{path}' cannot be read: {exc}",
            ) from exc

    def _known_hosts(self) -> Path:
        """The known_hosts file add_host saves to (and reads)."""

        if self._settings is not None and self._settings.known_hosts is not None:
            return self._settings.known_hosts

        return Path.home() / ".ssh" / "known_hosts"

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

        security = transport.get_security_options()

        # Host-key algorithms and ciphers have defaults; key exchange and
        # MACs keep Paramiko's own unless the settings name them.
        security.key_types = self._choose(
            "host_key",
            (algorithms.host_key if algorithms else None) or DEFAULT_HOST_KEY_ALGORITHMS,
            set(security.key_types) | set(getattr(transport, "_key_info", {})),
            explicit=bool(algorithms and algorithms.host_key),
        )

        security.ciphers = self._choose(
            "cipher",
            (algorithms.cipher if algorithms else None) or DEFAULT_CIPHERS,
            set(security.ciphers) | set(getattr(transport, "_cipher_info", {})),
            explicit=bool(algorithms and algorithms.cipher),
        )

        if algorithms is not None and algorithms.kex is not None:
            security.kex = self._choose(
                "kex",
                algorithms.kex,
                set(security.kex) | set(getattr(transport, "_kex_info", {})),
                explicit=True,
            )

        if algorithms is not None and algorithms.mac is not None:
            security.digests = self._choose(
                "mac",
                algorithms.mac,
                set(security.digests) | set(getattr(transport, "_mac_info", {})),
                explicit=True,
            )

        return transport

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    @staticmethod
    def _choose(
        name: str,
        wanted: tuple[str, ...],
        supported: set[str],
        *,
        explicit: bool,
    ) -> tuple[str, ...]:
        """
        The wanted algorithms this client supports, in order. Defaults skip
        what it lacks; algorithms named in the settings must exist.
        """

        chosen = tuple(item for item in wanted if item in supported)

        if explicit and len(chosen) != len(wanted):
            missing = ", ".join(item for item in wanted if item not in supported)
            raise SftpPluginException(
                f"'settings.algorithms.{name}': not supported here: {missing}. "
                f"Supported: {', '.join(sorted(supported))}.",
            )

        if not chosen:
            raise SftpPluginException(
                f"No {name} algorithm in common with this client.",
            )

        return chosen

    def _require_connection(
        self,
    ) -> paramiko.SFTPClient:
        if self._sftp is None:
            raise SftpPluginException(
                "SFTP client is not connected.",
            )

        return self._sftp
