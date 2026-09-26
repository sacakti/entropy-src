"""
SQLPlus script classification.
"""

from __future__ import annotations

from enum import Enum
from pathlib import Path

from .model import AnalyseStatement
from .parser import AnalyseParser


class AnalyseScriptType(str, Enum):
    """
    Supported SQLPlus script types.
    """

    CALLING = "calling"
    DATABASE = "database"


class AnalyseClassifier:
    """
    Classify SQL / SQLPlus scripts.
    """

    _CALLING_COMMANDS = {
        "@",
        "@@",
    }

    _SQLPLUS_COMMANDS = {
        "ACCEPT",
        "APPEND",
        "BREAK",
        "COLUMN",
        "DEFINE",
        "DESCRIBE",
        "EXIT",
        "HOST",
        "PROMPT",
        "SET",
        "SHOW",
        "SPOOL",
        "START",
        "UNDEFINE",
        "VARIABLE",
        "WHENEVER",
    }

    def __init__(
        self,
        parser: AnalyseParser | None = None,
    ) -> None:
        """
        Initialize the classifier.
        """

        self._parser = (
            parser
            if parser is not None
            else AnalyseParser()
        )

    def classify(
        self,
        script: Path,
    ) -> AnalyseScriptType:
        """
        Classify a script as calling or database.
        """

        statements = self._parser.parse(
            script,
        )

        if self._is_calling_script(
            statements,
        ):
            return AnalyseScriptType.CALLING

        return AnalyseScriptType.DATABASE

    def _is_calling_script(
        self,
        statements: tuple[AnalyseStatement, ...],
    ) -> bool:
        """
        Determine whether the script is a SQLPlus calling script.
        """

        for statement in statements:

            if self._contains_call(
                statement,
            ):
                return True

        return False

    def _contains_call(
        self,
        statement: AnalyseStatement,
    ) -> bool:
        """
        Determine whether a statement contains a script call.
        """

        for token in statement.tokens:

            value = token.value.strip()

            if value in self._CALLING_COMMANDS:
                return True

            if (
                value.startswith("@")
                and len(value) > 1
            ):
                return True

        return False
