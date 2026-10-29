"""
load_data argument resolution.
"""

from __future__ import annotations

import contextlib
import json
import re
from collections.abc import Mapping
from pathlib import PurePosixPath
from typing import Any

from .exceptions import LoadDataPluginException

# Oracle object name, optionally schema-qualified (SCHEMA.TABLE).
_IDENTIFIER = re.compile(
    r"^[A-Za-z][A-Za-z0-9_$#]*(\.[A-Za-z][A-Za-z0-9_$#]*)?$",
)


class LoadDataResolver:
    """
    Validate load_data arguments.
    """

    @staticmethod
    def connection(
        value: Any,
    ) -> dict[str, Any]:

        if not isinstance(value, dict):
            raise LoadDataPluginException(
                "'connection' must be an object.",
            )

        host = value.get("IP")
        port = value.get("PORT")
        sid = value.get("SID")

        if not isinstance(host, str) or not host.strip():
            raise LoadDataPluginException(
                "Connection 'IP' must be a non-empty string.",
            )

        if isinstance(port, bool) or not isinstance(port, int) or not 1 <= port <= 65535:
            raise LoadDataPluginException(
                "Connection 'PORT' must be an integer between 1 and 65535.",
            )

        if not isinstance(sid, str) or not sid.strip():
            raise LoadDataPluginException(
                "Connection 'SID' must be a non-empty string.",
            )

        return {
            "IP": host.strip(),
            "PORT": port,
            "SID": sid.strip(),
        }

    @staticmethod
    def credentials(
        value: Any,
    ) -> dict[str, str]:

        # Vault entries may hold the credential object as a JSON string.
        if isinstance(value, str):
            with contextlib.suppress(json.JSONDecodeError):
                value = json.loads(value)

        if not isinstance(value, Mapping):
            raise LoadDataPluginException(
                "'credentials' must be an object with username and password.",
            )

        username = value.get("username")
        password = value.get("password")

        if not isinstance(username, str) or not username.strip():
            raise LoadDataPluginException(
                "Credentials 'username' must be a non-empty string.",
            )

        if not isinstance(password, str):
            raise LoadDataPluginException(
                "Credentials 'password' is missing.",
            )

        return {
            "username": username.strip(),
            "password": password,
        }

    @staticmethod
    def status_check(
        value: Any,
        label: str = "'status_check'",
    ) -> dict[str, str]:
        """
        Resolve a status check: table, column and success_value.
        """

        if not isinstance(value, dict):
            raise LoadDataPluginException(
                f"{label} must be an object with a 'table'.",
            )

        success_value = value.get("success_value", "SUCCESS")

        if not isinstance(success_value, str) or not success_value:
            raise LoadDataPluginException(
                f"{label} 'success_value' must be a non-empty string.",
            )

        return {
            "table": LoadDataResolver._identifier(
                value.get("table"),
                f"{label} 'table'",
            ),
            "column": LoadDataResolver._identifier(
                value.get("column", "STATUS"),
                f"{label} 'column'",
            ),
            # Quoted as an SQL literal.
            "success_value": success_value.replace("'", "''"),
        }

    @staticmethod
    def procedures(
        value: Any,
        default_check: Any,
    ) -> list[dict[str, Any]]:
        """
        Resolve the ordered procedure SQL files (relative to the sqls
        folder) and the status check run after each.
        """

        if not isinstance(value, list) or not value:
            raise LoadDataPluginException(
                "'procedures' must be a non-empty list.",
            )

        resolved: list[dict[str, Any]] = []

        for index, item in enumerate(value, start=1):

            label = f"Procedure {index}"

            if isinstance(item, str):
                item = {"sql": item}

            if not isinstance(item, dict):
                raise LoadDataPluginException(
                    f"{label} must be a SQL file name or an object with 'sql'.",
                )

            check = item.get("status_check", default_check)

            if check is None:
                raise LoadDataPluginException(
                    f"{label} has no 'status_check' and no default 'status_check' is set.",
                )

            resolved.append(
                {
                    "sql": LoadDataResolver._sql_file(
                        item.get("sql"),
                        f"{label} 'sql'",
                    ),
                    "status_check": LoadDataResolver.status_check(
                        check,
                        f"{label} 'status_check'",
                    ),
                },
            )

        return resolved

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _sql_file(
        value: Any,
        label: str,
    ) -> str:

        if not isinstance(value, str) or not value.strip():
            raise LoadDataPluginException(
                f"{label} must be a SQL file name.",
            )

        relative = PurePosixPath(value.strip())

        if relative.is_absolute() or ".." in relative.parts:
            raise LoadDataPluginException(
                f"{label} '{value}' must be a path inside the sqls folder.",
            )

        return str(relative)

    @staticmethod
    def _identifier(
        value: Any,
        label: str,
    ) -> str:

        if not isinstance(value, str) or not _IDENTIFIER.match(value.strip()):
            raise LoadDataPluginException(
                f"{label} must be an Oracle object name, got {value!r}.",
            )

        return value.strip()
