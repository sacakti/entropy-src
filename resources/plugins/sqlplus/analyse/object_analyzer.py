"""
Oracle SQL database object analyzer.
"""

from __future__ import annotations

from .model import (
    AnalyseObject,
    AnalyseStatement,
    AnalyseToken,
)


class AnalyseObjectAnalyzer:
    """
    Extract database object operations from SQL statements.
    """

    _DDL_OBJECTS = frozenset(
        {
            "TABLE",
            "VIEW",
            "INDEX",
            "SEQUENCE",
            "SYNONYM",
            "PROCEDURE",
            "FUNCTION",
            "PACKAGE",
            "TRIGGER",
            "TYPE",
            "MATERIALIZED",
        },
    )

    _DDL_OPERATIONS = frozenset(
        {
            "CREATE",
            "ALTER",
            "DROP",
            "TRUNCATE",
            "COMMENT",
            "RENAME",
            "GRANT",
            "REVOKE",
        },
    )

    _DML_OPERATIONS = frozenset(
        {
            "INSERT",
            "UPDATE",
            "DELETE",
            "MERGE",
        },
    )

    _DQL_OPERATIONS = frozenset(
        {
            "SELECT",
        },
    )

    def analyse(
        self,
        statement: AnalyseStatement,
    ) -> tuple[AnalyseObject, ...]:
        """
        Analyse a SQL statement and extract database objects.
        """

        tokens = [
            token
            for token in statement.tokens
            if token.value.strip()
        ]

        if not tokens:
            return ()

        normalized = [
            token.value.strip().upper()
            for token in tokens
        ]

        operation = self._find_operation(
            normalized,
        )

        if operation is None:
            return ()

        category = self._category(
            operation,
        )

        if category == "DDL":
            return self._analyse_ddl(
                statement,
                tokens,
                normalized,
                operation,
            )

        if category in {"DML", "DQL"}:
            return self._analyse_dml_dql(
                statement,
                tokens,
                normalized,
                operation,
                category,
            )

        return ()

    def _analyse_ddl(
        self,
        statement: AnalyseStatement,
        tokens: list[AnalyseToken],
        normalized: list[str],
        operation: str,
    ) -> tuple[AnalyseObject, ...]:
        """
        Analyse a DDL statement.
        """

        object_type_index = self._find_ddl_object_type(
            normalized,
            operation,
        )

        if object_type_index is None:
            return ()

        object_type = normalized[object_type_index]

        if (
            object_type == "MATERIALIZED"
            and object_type_index + 1 < len(normalized)
            and normalized[object_type_index + 1] == "VIEW"
        ):
            object_type = "MATERIALIZED VIEW"

        name_index = object_type_index + (
            2
            if object_type == "MATERIALIZED VIEW"
            else 1
        )

        name, name_token = self._next_name(
            tokens,
            normalized,
            name_index,
        )

        if name is None or name_token is None:
            return ()

        return (
            AnalyseObject(
                name=name,
                object_type=object_type,
                operation=operation,
                category="DDL",
                file=statement.file,
                line=name_token.line,
                column=name_token.column,
            ),
        )

    def _analyse_dml_dql(
        self,
        statement: AnalyseStatement,
        tokens: list[AnalyseToken],
        normalized: list[str],
        operation: str,
        category: str,
    ) -> tuple[AnalyseObject, ...]:
        """
        Analyse a DML or DQL statement.
        """

        name_index = self._target_index(
            normalized,
            operation,
        )

        if name_index is None:
            return ()

        name, name_token = self._next_name(
            tokens,
            normalized,
            name_index,
        )

        if name is None or name_token is None:
            return ()

        return (
            AnalyseObject(
                name=name,
                object_type="TABLE",
                operation=operation,
                category=category,
                file=statement.file,
                line=name_token.line,
                column=name_token.column,
            ),
        )

    def _find_ddl_object_type(
        self,
        tokens: list[str],
        operation: str,
    ) -> int | None:
        """
        Find the object type in a DDL statement.
        """

        start = 1

        for index in range(
            start,
            len(tokens),
        ):
            if tokens[index] in self._DDL_OBJECTS:
                return index

        return None

    def _target_index(
        self,
        tokens: list[str],
        operation: str,
    ) -> int | None:
        """
        Find the position where the DML/DQL target starts.
        """

        if operation in {
            "INSERT",
            "UPDATE",
            "DELETE",
            "MERGE",
        }:
            for keyword in (
                "INTO",
                "FROM",
            ):
                try:
                    return tokens.index(
                        keyword,
                        1,
                    ) + 1
                except ValueError:
                    continue

            if operation == "UPDATE":
                return 1

        if operation == "SELECT":
            try:
                from_index = tokens.index(
                    "FROM",
                    1,
                )
            except ValueError:
                return None

            return from_index + 1

        return None

    def _next_name(
        self,
        tokens: list[AnalyseToken],
        normalized: list[str],
        index: int,
    ) -> tuple[str | None, AnalyseToken | None]:
        """
        Extract the next SQL identifier and its source position.

        Schema-qualified identifiers are normalized to the
        object name without the schema.
        """

        if index >= len(tokens):
            return None, None

        parts: list[str] = []

        name_token: AnalyseToken | None = None

        current = index

        while current < len(tokens):
            value = normalized[current]

            if not value:
                break

            if value in {
                "(",
                ")",
                ";",
                ",",
            }:
                break

            if value == ".":
                current += 1
                continue

            if parts and current > index:
                previous = normalized[current - 1]

                if previous != ".":
                    break

            parts.append(
                value.rstrip(";,"),
            )

            name_token = tokens[current]

            current += 1

        if not parts or name_token is None:
            return None, None

        return parts[-1], name_token

    def _find_operation(
        self,
        tokens: list[str],
    ) -> str | None:
        """
        Find the SQL operation.
        """

        for token in tokens:

            if token == "CREATE OR REPLACE":
                return "CREATE"

            if token in self._DDL_OPERATIONS:
                return token

            if token in self._DML_OPERATIONS:
                return token

            if token in self._DQL_OPERATIONS:
                return token

        return None

    @staticmethod
    def _category(
        operation: str,
    ) -> str | None:
        """
        Resolve the operation category.
        """

        if operation in AnalyseObjectAnalyzer._DDL_OPERATIONS:
            return "DDL"

        if operation in AnalyseObjectAnalyzer._DML_OPERATIONS:
            return "DML"

        if operation in AnalyseObjectAnalyzer._DQL_OPERATIONS:
            return "DQL"

        return None
