"""
Invalid objects report argument resolution.
"""

from __future__ import annotations

from typing import Any

from .exceptions import InvalidObjectsReportPluginException


class InvalidObjectsReportResolver:
    """
    Validate invalid-object report arguments.
    """

    @staticmethod
    def connection(
        value: Any,
    ) -> dict[str, Any]:
        if not isinstance(value, dict):
            raise InvalidObjectsReportPluginException(
                "'connection' must be an object.",
            )

        host = value.get("IP")
        port = value.get("PORT")
        sid = value.get("SID")

        if not isinstance(host, str) or not host.strip():
            raise InvalidObjectsReportPluginException(
                "Connection 'IP' must be a non-empty string.",
            )

        if isinstance(port, bool) or not isinstance(port, int):
            raise InvalidObjectsReportPluginException(
                "Connection 'PORT' must be an integer.",
            )

        if not 1 <= port <= 65535:
            raise InvalidObjectsReportPluginException(
                "Connection 'PORT' must be between 1 and 65535.",
            )

        if not isinstance(sid, str) or not sid.strip():
            raise InvalidObjectsReportPluginException(
                "Connection 'SID' must be a non-empty string.",
            )

        return {
            "IP": host.strip(),
            "PORT": port,
            "SID": sid.strip(),
        }

    @staticmethod
    def schemas(
        value: Any,
    ) -> dict[str, Any]:
        if not isinstance(value, dict):
            raise InvalidObjectsReportPluginException(
                "'schemas' must be an object.",
            )

        if not value:
            raise InvalidObjectsReportPluginException(
                "'schemas' must not be empty.",
            )

        for schema, credentials in value.items():

            if not isinstance(schema, str) or not schema.strip():
                raise InvalidObjectsReportPluginException(
                    "Schema names must be non-empty strings.",
                )

            if not isinstance(credentials, dict):
                raise InvalidObjectsReportPluginException(
                    f"Credentials for schema '{schema}' must be an object.",
                )

            username = credentials.get("username")
            password = credentials.get("password")

            if not isinstance(username, str) or not username:
                raise InvalidObjectsReportPluginException(
                    f"Username is missing for schema '{schema}'.",
                )

            if not isinstance(password, str):
                raise InvalidObjectsReportPluginException(
                    f"Password is missing for schema '{schema}'.",
                )

        return value
