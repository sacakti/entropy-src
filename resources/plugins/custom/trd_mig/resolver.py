"""
trd_mig argument and mapping resolution.
"""

from __future__ import annotations

import contextlib
import json
import re
from collections.abc import Mapping
from pathlib import PurePosixPath
from typing import Any

from .exceptions import TrdMigPluginException

# Oracle object name, optionally schema-qualified (SCHEMA.TABLE).
_IDENTIFIER = re.compile(
    r"^[A-Za-z][A-Za-z0-9_$#]*(\.[A-Za-z][A-Za-z0-9_$#]*)?$",
)


class TrdMigResolver:
    """
    Validate trd_mig arguments and the product mapping.
    """

    @staticmethod
    def connection(
        value: Any,
    ) -> dict[str, Any]:

        if not isinstance(value, dict):
            raise TrdMigPluginException(
                "'connection' must be an object.",
            )

        host = value.get("IP")
        port = value.get("PORT")
        sid = value.get("SID")

        if not isinstance(host, str) or not host.strip():
            raise TrdMigPluginException(
                "Connection 'IP' must be a non-empty string.",
            )

        if isinstance(port, bool) or not isinstance(port, int) or not 1 <= port <= 65535:
            raise TrdMigPluginException(
                "Connection 'PORT' must be an integer between 1 and 65535.",
            )

        if not isinstance(sid, str) or not sid.strip():
            raise TrdMigPluginException(
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
            raise TrdMigPluginException(
                "'credentials' must be an object with username and password.",
            )

        username = value.get("username")
        password = value.get("password")

        if not isinstance(username, str) or not username.strip():
            raise TrdMigPluginException(
                "Credentials 'username' must be a non-empty string.",
            )

        if not isinstance(password, str):
            raise TrdMigPluginException(
                "Credentials 'password' is missing.",
            )

        return {
            "username": username.strip(),
            "password": password,
        }

    @staticmethod
    def mapping(
        value: Any,
        *,
        country: str,
        product: str,
        truncate_profile: str | None = None,
        truncate_tables: list[Any] | None = None,
    ) -> dict[str, Any]:
        """
        Resolve the country and product entries of the mapping.

        Returns the truncate tables, the count table, the country's SQL
        file (relative to the sqls folder) and its database link.
        """

        if not isinstance(value, dict):
            raise TrdMigPluginException(
                "The mapping must be an object.",
            )

        countries = value.get("countries")
        products = value.get("products")
        profiles = value.get("truncate_profiles", {})

        if not isinstance(countries, dict) or not isinstance(products, dict):
            raise TrdMigPluginException(
                "The mapping must contain 'countries' and 'products' objects.",
            )

        if not isinstance(profiles, dict):
            raise TrdMigPluginException(
                "Mapping 'truncate_profiles' must be an object of table lists.",
            )

        country_entry = TrdMigResolver._entry(
            countries,
            country,
            "country",
        )

        product_entry = TrdMigResolver._entry(
            products,
            product,
            "product",
        )

        dblink = country_entry.get("dblink")

        if dblink is not None and (not isinstance(dblink, str) or not dblink.strip()):
            raise TrdMigPluginException(
                f"Country '{country}' 'dblink' must be a non-empty string.",
            )

        tables, source = TrdMigResolver._truncate(
            profiles,
            truncate_profile=truncate_profile,
            truncate_tables=truncate_tables,
        )

        count_table = TrdMigResolver._identifier(
            product_entry.get("count_table"),
            f"Product '{product}' 'count_table'",
        )

        return {
            "dblink": dblink.strip() if dblink else None,
            "truncate": tables,
            "truncate_source": source,
            "count_table": count_table,
            "sql_file": TrdMigResolver._sql_file(
                country_entry.get("sql"),
                country=country,
                product=product,
            ),
        }

    @staticmethod
    def sql(
        text: str,
        *,
        country: str,
        product: str,
        dblink: str | None,
        sql_file: str,
    ) -> str:
        """
        Substitute {dblink}, {country} and {product} in a SQL file.
        """

        if not text.strip():
            raise TrdMigPluginException(
                f"SQL file '{sql_file}' is empty.",
            )

        if "{dblink}" in text:

            if dblink is None:
                raise TrdMigPluginException(
                    f"SQL file '{sql_file}' uses {{dblink}} but country "
                    f"'{country}' has no 'dblink' in the mapping.",
                )

            text = text.replace("{dblink}", dblink)

        return text.replace("{country}", country).replace("{product}", product).rstrip()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _truncate(
        profiles: dict[str, Any],
        *,
        truncate_profile: str | None,
        truncate_tables: list[Any] | None,
    ) -> tuple[list[str], str]:
        """
        Resolve the tables to truncate and where they came from.

        The step's truncate_tables win over its truncate_profile; with
        neither (truncate disabled) nothing is truncated.
        """

        if truncate_tables:
            tables: Any = truncate_tables
            source = "arguments"

        elif truncate_profile:
            tables = TrdMigResolver._profile(profiles, truncate_profile)
            source = f"profile:{truncate_profile}"

        else:
            return [], "none"

        if not isinstance(tables, list):
            raise TrdMigPluginException(
                f"Truncate tables ({source}) must be a list of tables.",
            )

        return [
            TrdMigResolver._identifier(
                table,
                f"Truncate table ({source})",
            )
            for table in tables
        ], source

    @staticmethod
    def _profile(
        profiles: dict[str, Any],
        name: str,
    ) -> Any:

        if name not in profiles:
            available = ", ".join(sorted(profiles)) or "none"
            raise TrdMigPluginException(
                f"Unknown truncate profile '{name}'. Available: {available}.",
            )

        return profiles[name]

    @staticmethod
    def _sql_file(
        value: Any,
        *,
        country: str,
        product: str,
    ) -> str:
        """
        The country's SQL file: one file, or one per product.
        """

        if isinstance(value, dict):
            matches = {
                name.casefold(): entry for name, entry in value.items() if isinstance(name, str)
            }
            value = matches.get(product.casefold())

            if value is None:
                raise TrdMigPluginException(
                    f"Country '{country}' has no SQL file for product '{product}'.",
                )

        if not isinstance(value, str) or not value.strip():
            raise TrdMigPluginException(
                f"Country '{country}' has no 'sql' file in the mapping.",
            )

        relative = PurePosixPath(value.strip())

        if relative.is_absolute() or ".." in relative.parts:
            raise TrdMigPluginException(
                f"Country '{country}' SQL file '{value}' must be a path " "inside the sqls folder.",
            )

        return str(relative)

    @staticmethod
    def _entry(
        entries: dict[str, Any],
        key: str,
        label: str,
    ) -> dict[str, Any]:

        # Case-insensitive lookup so 'IN' matches 'in'.
        matches = {
            name.casefold(): entry for name, entry in entries.items() if isinstance(name, str)
        }

        entry = matches.get(key.casefold())

        if entry is None:
            available = ", ".join(sorted(entries)) or "none"
            raise TrdMigPluginException(
                f"Unknown {label} '{key}'. Available: {available}.",
            )

        if not isinstance(entry, dict):
            raise TrdMigPluginException(
                f"Mapping entry for {label} '{key}' must be an object.",
            )

        return entry

    @staticmethod
    def _identifier(
        value: Any,
        label: str,
    ) -> str:

        if not isinstance(value, str) or not _IDENTIFIER.match(value.strip()):
            raise TrdMigPluginException(
                f"{label} must be an Oracle table name, got {value!r}.",
            )

        return value.strip()
