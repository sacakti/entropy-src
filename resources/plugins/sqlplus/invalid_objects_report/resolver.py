"""
Invalid objects report argument resolution.
"""

from __future__ import annotations

import fnmatch
import json
from collections.abc import Mapping
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

        # A schema credential record may itself have been stored as a JSON
        # string inside a vault object containing the full schema map.
        value = {
            schema: InvalidObjectsReportResolver._credential_object(credentials)
            for schema, credentials in value.items()
        }

        for schema, credentials in value.items():

            if not isinstance(schema, str) or not schema.strip():
                raise InvalidObjectsReportPluginException(
                    "Schema names must be non-empty strings.",
                )

            if not isinstance(credentials, Mapping):
                raise InvalidObjectsReportPluginException(
                    f"Credentials for schema '{schema}' must be an object.",
                )

            credentials = dict(credentials)
            value[schema] = credentials

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

    @staticmethod
    def plan_schemas(
        execution: Any,
    ) -> list[str]:
        """
        The schemas a release changes, from its database context (the `database`
        output of release.context_builder or consolidate.db_scripts): its `schemas`
        list when it has one, else every schema its execution plan names.
        """

        if execution is None:
            return []

        if not isinstance(execution, Mapping):
            raise InvalidObjectsReportPluginException(
                "'execution' must be a database context object, such as "
                "${steps.BuildReleaseContext.outputs.database}.",
            )

        listed = execution.get("schemas")
        if isinstance(listed, list):
            names = listed
        else:
            plan = execution.get("execution_plan") or {}
            applications = plan.get("applications") if isinstance(plan, Mapping) else None
            if applications is not None and not isinstance(applications, Mapping):
                raise InvalidObjectsReportPluginException(
                    "'execution.execution_plan.applications' must be an object.",
                )
            names = [
                definition.get("schema")
                for definition in (applications or {}).values()
                if isinstance(definition, Mapping)
            ]

        schemas: list[str] = []
        for name in names:
            if isinstance(name, str) and name.strip() and name.strip() not in schemas:
                schemas.append(name.strip())
        return schemas

    @staticmethod
    def only_schemas(
        value: Any,
    ) -> list[str]:
        if value is None:
            return []
        items = [value] if isinstance(value, str) else value
        if not isinstance(items, list) or not all(
            isinstance(item, str) and item.strip() for item in items
        ):
            raise InvalidObjectsReportPluginException(
                "'only_schemas' must be a list of schema names or patterns such as APP*.",
            )
        return [item.strip() for item in items]

    @staticmethod
    def select(
        schemas: dict[str, Any],
        wanted: list[str],
    ) -> tuple[dict[str, Any], list[str], list[str]]:
        """
        The schemas to check, in the order asked for: (credentials by schema,
        schemas asked for that have no credentials, patterns that matched nothing).
        Names and patterns (APP*) are compared without case.
        """

        by_name = {name.casefold(): name for name in schemas}
        selected: dict[str, Any] = {}
        missing: list[str] = []
        unmatched: list[str] = []

        for item in wanted:
            if any(char in item for char in "*?["):
                found = [
                    name
                    for name in schemas
                    if fnmatch.fnmatchcase(name.casefold(), item.casefold())
                ]
                if not found:
                    unmatched.append(item)
                for name in found:
                    selected.setdefault(name, schemas[name])
                continue
            known = by_name.get(item.casefold())
            if known is None:
                if item not in missing:
                    missing.append(item)
            else:
                selected.setdefault(known, schemas[known])

        return selected, missing, unmatched

    @staticmethod
    def _credential_object(value: Any) -> Any:
        if isinstance(value, Mapping):
            return dict(value)
        if not isinstance(value, str):
            return value
        try:
            decoded = json.loads(value)
        except json.JSONDecodeError:
            return value
        return decoded if isinstance(decoded, dict) else value

    @staticmethod
    def report(
        value: Any,
    ) -> dict[str, Any]:
        if value is None:
            return {
                "add_text": False,
                "position": "after",
                "text": "",
            }

        if not isinstance(value, dict):
            raise InvalidObjectsReportPluginException(
                "'report' must be an object.",
            )

        add_text = value.get(
            "add_text",
            False,
        )

        if not isinstance(add_text, bool):
            raise InvalidObjectsReportPluginException(
                "'report.add_text' must be a boolean.",
            )

        position = value.get(
            "position",
            "after",
        )

        if not isinstance(position, str):
            raise InvalidObjectsReportPluginException(
                "'report.position' must be either 'before' or 'after'.",
            )

        position = position.strip().casefold()

        if position not in {
            "before",
            "after",
        }:
            raise InvalidObjectsReportPluginException(
                "'report.position' must be either 'before' or 'after'.",
            )

        text = value.get(
            "text",
            "",
        )

        if not isinstance(text, str):
            raise InvalidObjectsReportPluginException(
                "'report.text' must be a string.",
            )

        text = text.strip()

        if add_text and not text:
            raise InvalidObjectsReportPluginException(
                "'report.text' must not be empty when " "'report.add_text' is true.",
            )

        return {
            "add_text": add_text,
            "position": position,
            "text": text,
        }
