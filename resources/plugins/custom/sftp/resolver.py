"""
SFTP plugin argument resolver.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .exceptions import SftpPluginException
from .model import (
    SftpAlgorithmSettings,
    SftpArchive,
    SftpConnectionSettings,
    SftpCredentials,
    SftpHostKeySettings,
    SftpRequest,
    SftpSettings,
)


class SftpResolver:
    """
    Resolve and validate SFTP plugin arguments.
    """

    _OPERATIONS = {
        "put",
        "get",
        "list",
        "mkdir",
    }

    def resolve(
        self,
        arguments: Any,
    ) -> SftpRequest:
        """
        Resolve raw plugin arguments into an SftpRequest.
        """

        if not isinstance(arguments, dict):
            raise SftpPluginException(
                "SFTP arguments must be an object.",
            )

        operation = self._resolve_operation(
            arguments.get("operation"),
        )

        source = self._resolve_source(
            operation=operation,
            value=arguments.get("source"),
        )

        destination = self._resolve_destination(
            operation=operation,
            value=arguments.get("destination"),
        )

        archive = self._resolve_archive(
            operation=operation,
            value=arguments.get("archive"),
        )

        sftp = self._resolve_sftp(
            arguments.get("sftp"),
        )

        settings = self._resolve_settings(
            arguments.get("settings"),
        )

        return SftpRequest(
            operation=operation,
            source=source,
            destination=destination,
            archive=archive,
            sftp=sftp,
            settings=settings,
        )

    # ------------------------------------------------------------------
    # Operation
    # ------------------------------------------------------------------

    @classmethod
    def _resolve_operation(
        cls,
        value: Any,
    ) -> str:
        if not isinstance(value, str) or not value.strip():
            raise SftpPluginException(
                "'operation' must be a non-empty string.",
            )

        operation = value.strip().casefold()

        if operation not in cls._OPERATIONS:
            supported = ", ".join(
                sorted(cls._OPERATIONS),
            )

            raise SftpPluginException(
                f"Unsupported SFTP operation '{operation}'. "
                f"Supported operations: {supported}.",
            )

        return operation

    # ------------------------------------------------------------------
    # Source / destination
    # ------------------------------------------------------------------

    @staticmethod
    def _resolve_source(
        *,
        operation: str,
        value: Any,
    ) -> str | None:
        if operation == "mkdir":
            if value is None:
                return None

            raise SftpPluginException(
                "'source' is not supported for the 'mkdir' operation.",
            )

        if not isinstance(value, str) or not value.strip():
            raise SftpPluginException(
                f"'source' must be a non-empty string "
                f"for '{operation}'.",
            )

        return value.strip()

    @staticmethod
    def _resolve_destination(
        *,
        operation: str,
        value: Any,
    ) -> str | None:
        if operation == "list":
            if value is None:
                return None

            if not isinstance(value, str) or not value.strip():
                raise SftpPluginException(
                    "'destination' must be a non-empty string "
                    "when provided for 'list'.",
                )

            return value.strip()

        if not isinstance(value, str) or not value.strip():
            raise SftpPluginException(
                f"'destination' must be a non-empty string "
                f"for '{operation}'.",
            )

        return value.strip()

    # ------------------------------------------------------------------
    # Archive
    # ------------------------------------------------------------------

    @staticmethod
    def _resolve_archive(
        *,
        operation: str,
        value: Any,
    ) -> SftpArchive:
        if value is None:
            return SftpArchive()

        if not isinstance(value, dict):
            raise SftpPluginException(
                "'archive' must be an object.",
            )

        enabled = value.get(
            "enabled",
            False,
        )

        if not isinstance(enabled, bool):
            raise SftpPluginException(
                "'archive.enabled' must be a boolean.",
            )

        filename_policy = value.get(
            "filename_policy",
        )

        if filename_policy is not None:
            if (
                not isinstance(
                    filename_policy,
                    str,
                )
                or not filename_policy.strip()
            ):
                raise SftpPluginException(
                    "'archive.filename_policy' must be "
                    "a non-empty string.",
                )

            filename_policy = filename_policy.strip()

        if operation in {"list", "mkdir"} and enabled:
            raise SftpPluginException(
                f"'archive.enabled' is not supported "
                f"for '{operation}'.",
            )

        if not enabled and filename_policy:
            raise SftpPluginException(
                "'archive.filename_policy' requires "
                "'archive.enabled' to be true.",
            )

        return SftpArchive(
            enabled=enabled,
            filename_policy=filename_policy,
        )

    # ------------------------------------------------------------------
    # SFTP credentials
    # ------------------------------------------------------------------

    @classmethod
    def _resolve_sftp(
        cls,
        value: Any,
    ) -> SftpCredentials:
        if not isinstance(value, dict):
            raise SftpPluginException(
                "'sftp' must be an object.",
            )

        host = value.get("host")
        port = value.get("port")
        user = value.get("user")
        password = value.get("password")
        key_filename = value.get("key_filename")

        if not isinstance(host, str) or not host.strip():
            raise SftpPluginException(
                "'sftp.host' must be a non-empty string.",
            )

        if isinstance(port, bool) or not isinstance(port, int):
            if isinstance(port, str) and port.strip().isdigit():
                port = int(port.strip())
            else:
                raise SftpPluginException(
                    "'sftp.port' must be an integer.",
                )

        if not 1 <= port <= 65535:
            raise SftpPluginException(
                "'sftp.port' must be between 1 and 65535.",
            )

        if not isinstance(user, str) or not user.strip():
            raise SftpPluginException(
                "'sftp.user' must be a non-empty string.",
            )

        if password is not None and not isinstance(
            password,
            str,
        ):
            raise SftpPluginException(
                "'sftp.password' must be a string.",
            )

        if key_filename is not None:
            if (
                not isinstance(
                    key_filename,
                    str,
                )
                or not key_filename.strip()
            ):
                raise SftpPluginException(
                    "'sftp.key_filename' must be a "
                    "non-empty string.",
                )

            key_filename = Path(
                key_filename,
            ).expanduser()

        if password is None and key_filename is None:
            raise SftpPluginException(
                "'sftp' requires either 'password' "
                "or 'key_filename'.",
            )

        return SftpCredentials(
            host=host.strip(),
            port=port,
            user=user.strip(),
            password=password,
            key_filename=key_filename,
        )

    # ------------------------------------------------------------------
    # Settings
    # ------------------------------------------------------------------

    @classmethod
    def _resolve_settings(
        cls,
        value: Any,
    ) -> SftpSettings | None:
        if value is None:
            return None

        if not isinstance(value, dict):
            raise SftpPluginException(
                "'settings' must be an object.",
            )

        connection = cls._resolve_connection(
            value.get("connection"),
        )

        algorithms = cls._resolve_algorithms(
            value.get("algorithms"),
        )

        host_key = cls._resolve_host_key(
            value.get("host_key"),
        )

        return SftpSettings(
            connection=connection,
            algorithms=algorithms,
            host_key=host_key,
        )

    @staticmethod
    def _resolve_host_key(
        value: Any,
    ) -> SftpHostKeySettings | None:
        if value is None:
            return None

        if not isinstance(value, dict):
            raise SftpPluginException(
                "'settings.host_key' must be an object.",
            )

        policy = value.get(
            "policy",
            "known_hosts",
        )

        if not isinstance(policy, str) or not policy.strip():
            raise SftpPluginException(
                "'settings.host_key.policy' must be a "
                "non-empty string.",
            )

        policy = policy.strip().casefold()

        if policy not in {"known_hosts", "auto_add"}:
            raise SftpPluginException(
                f"Unsupported host-key policy '{policy}'. "
                "Supported policies: auto_add, known_hosts.",
            )

        return SftpHostKeySettings(
            policy=policy,
        )

    @staticmethod
    def _resolve_connection(
        value: Any,
    ) -> SftpConnectionSettings | None:
        if value is None:
            return None

        if not isinstance(value, dict):
            raise SftpPluginException(
                "'settings.connection' must be an object.",
            )

        timeout = SftpResolver._resolve_timeout(
            value.get("timeout"),
            "timeout",
        )

        banner_timeout = SftpResolver._resolve_timeout(
            value.get("banner_timeout"),
            "banner_timeout",
        )

        auth_timeout = SftpResolver._resolve_timeout(
            value.get("auth_timeout"),
            "auth_timeout",
        )

        return SftpConnectionSettings(
            timeout=timeout,
            banner_timeout=banner_timeout,
            auth_timeout=auth_timeout,
        )

    @staticmethod
    def _resolve_timeout(
        value: Any,
        name: str,
    ) -> float | None:
        if value is None:
            return None

        if isinstance(value, bool):
            raise SftpPluginException(
                f"'settings.connection.{name}' must be "
                f"a positive number.",
            )

        try:
            result = float(value)
        except (TypeError, ValueError) as exc:
            raise SftpPluginException(
                f"'settings.connection.{name}' must be "
                f"a positive number.",
            ) from exc

        if result <= 0:
            raise SftpPluginException(
                f"'settings.connection.{name}' must be "
                f"greater than zero.",
            )

        return result

    @staticmethod
    def _resolve_algorithms(
        value: Any,
    ) -> SftpAlgorithmSettings | None:
        if value is None:
            return None

        if not isinstance(value, dict):
            raise SftpPluginException(
                "'settings.algorithms' must be an object.",
            )

        return SftpAlgorithmSettings(
            kex=SftpResolver._resolve_algorithm(
                value.get("kex"),
                "kex",
            ),
            host_key=SftpResolver._resolve_algorithm(
                value.get("host_key"),
                "host_key",
            ),
            cipher=SftpResolver._resolve_algorithm(
                value.get("cipher"),
                "cipher",
            ),
            mac=SftpResolver._resolve_algorithm(
                value.get("mac"),
                "mac",
            ),
        )

    @staticmethod
    def _resolve_algorithm(
        value: Any,
        name: str,
    ) -> str | None:
        if value is None:
            return None

        if not isinstance(value, str) or not value.strip():
            raise SftpPluginException(
                f"'settings.algorithms.{name}' must be "
                f"a non-empty string.",
            )

        return value.strip()
