"""
Oracle SQL / SQLPlus script parser.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import sqlparse
from sqlparse.sql import TokenList
from sqlparse.tokens import Comment, Whitespace

from .model import AnalyseStatement, AnalyseToken

class AnalyseParser:
    """
    Parse Oracle SQL / SQLPlus source using sqlparse.
    """

    def parse(
        self,
        script: Path,
    ) -> tuple[AnalyseStatement, ...]:
        """
        Parse a SQL script into statements.
        """

        content = script.read_text(
            encoding="utf-8",
        )

        statements = sqlparse.parse(
            content,
        )

        results: list[AnalyseStatement] = []

        for statement in statements:

            text = str(statement)

            if not text.strip():
                continue

            offset = self._statement_offset(
                content,
                text,
            )

            line, column = self._offset_to_position(
                content,
                offset,
            )

            tokens = tuple(
                self._tokens(
                    content,
                    statement,
                    offset,
                ),
            )

            results.append(
                AnalyseStatement(
                    file=script,
                    text=text,
                    line=line,
                    column=column,
                    tokens=tokens,
                ),
            )

        return tuple(results)

    def _tokens(
        self,
        content: str,
        statement: TokenList,
        statement_offset: int,
    ) -> list[AnalyseToken]:
        """
        Flatten tokens while preserving source positions.
        """

        tokens: list[AnalyseToken] = []

        statement_text = str(
            statement,
        )

        cursor = 0

        for token in statement.flatten():

            value = token.value

            if not value:
                continue

            relative_offset = statement_text.find(
                value,
                cursor,
            )

            if relative_offset < 0:
                continue

            absolute_offset = (
                statement_offset
                + relative_offset
            )

            line, column = self._offset_to_position(
                content,
                absolute_offset,
            )

            tokens.append(
                AnalyseToken(
                    value=value,
                    token_type=self._token_type(
                        token.ttype,
                    ),
                    line=line,
                    column=column,
                ),
            )

            cursor = (
                relative_offset
                + len(value)
            )

        return tokens

    @staticmethod
    def _token_type(
        token_type,
    ) -> str:
        """
        Convert sqlparse token types into stable names.
        """

        if token_type is None:
            return ""

        return str(
            token_type,
        )

    @staticmethod
    def _statement_offset(
        content: str,
        statement: str,
    ) -> int:
        """
        Find the statement's position in the source.
        """

        offset = content.find(
            statement,
        )

        if offset < 0:
            return 0

        return offset

    @staticmethod
    def _offset_to_position(
        content: str,
        offset: int,
    ) -> tuple[int, int]:
        """
        Convert a character offset into line and column.
        """

        line = (
            content.count(
                "\n",
                0,
                offset,
            )
            + 1
        )

        last_newline = content.rfind(
            "\n",
            0,
            offset,
        )

        if last_newline < 0:
            column = offset + 1
        else:
            column = offset - last_newline

        return line, column
