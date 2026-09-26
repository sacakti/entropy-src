"""
Oracle SQL / SQLPlus script analyzer.
"""

from __future__ import annotations

from pathlib import Path

from .calling import CallingScriptAnalyzer
from .classifier import (
    AnalyseClassifier,
    AnalyseScriptType,
)
from .model import (
    AnalyseFileResult,
    AnalyseObject,
    AnalysePolicy,
    AnalyseResult,
)
from .parser import AnalyseParser
from .rules import AnalyseRules, RuleContext
from .scanner import AnalyseScanner
from .object_analyzer import AnalyseObjectAnalyzer

class AnalyseAnalyzer:
    """
    Coordinate SQLPlus script scanning, classification,
    and analysis.
    """

    def __init__(
        self,
        scanner: AnalyseScanner | None = None,
        parser: AnalyseParser | None = None,
        rules: AnalyseRules | None = None,
        classifier: AnalyseClassifier | None = None,
        calling_analyzer: CallingScriptAnalyzer | None = None,
        object_analyzer: AnalyseObjectAnalyzer | None = None,
    ) -> None:
        """
        Initialize the analyzer.
        """

        self._scanner = (
            scanner
            if scanner is not None
            else AnalyseScanner()
        )

        self._parser = (
            parser
            if parser is not None
            else AnalyseParser()
        )

        self._rules = (
            rules
            if rules is not None
            else AnalyseRules()
        )

        self._classifier = (
            classifier
            if classifier is not None
            else AnalyseClassifier(
                parser=self._parser,
            )
        )

        self._calling_analyzer = (
            calling_analyzer
            if calling_analyzer is not None
            else CallingScriptAnalyzer()
        )

        self._object_analyzer = (
            object_analyzer
            if object_analyzer is not None
            else AnalyseObjectAnalyzer()
        )

    def analyse(
        self,
        path: Path,
        extensions: tuple[str, ...],
        policy: AnalysePolicy,
    ) -> AnalyseResult:
        """
        Analyse all supported SQL files under the given path.
        """

        files = self._scanner.scan(
            path,
            extensions,
        )

        objects: list[AnalyseObject] = []
        file_results: list[AnalyseFileResult] = []
        findings = []
        stopped = False

        for file in files:

            file_result = self._analyse_file(
                file,
                policy,
            )

            file_results.append(
                file_result,
            )

            findings.extend(
                file_result.findings,
            )

            objects.extend(
                file_result.objects,
            )

            if any(
                finding.severity == "stop"
                for finding in file_result.findings
            ):
                stopped = True
                # break

        return AnalyseResult(
            files_scanned=len(file_results),
            objects=tuple(objects),
            findings=tuple(findings),
            stopped=stopped,
        )

    def _analyse_file(
        self,
        file: Path,
        policy: AnalysePolicy,
    ) -> AnalyseFileResult:
        """
        Classify and analyse a single SQL file.
        """

        script_type = self._classifier.classify(
            file,
        )

        if script_type == AnalyseScriptType.CALLING:
            return self._analyse_calling_file(
                file,
                policy,
            )

        return self._analyse_database_file(
            file,
            policy,
        )

    def _analyse_calling_file(
        self,
        file: Path,
        policy: AnalysePolicy,
    ) -> AnalyseFileResult:
        """
        Analyse a SQLPlus calling script.
        """

        findings = self._calling_analyzer.analyse(
            script=file,
            policy=policy,
        )

        return AnalyseFileResult(
            file=file,
            findings=findings,
        )

    def _analyse_database_file(
        self,
        file: Path,
        policy: AnalysePolicy,
    ) -> AnalyseFileResult:
        """
        Analyse a database SQL / PL/SQL script.
        """

        statements = self._parser.parse(
            file,
        )

        objects: list[AnalyseObject] = []
        findings = []

        context = RuleContext(
            file=file,
            policy=policy,
        )

        for index, statement in enumerate(
            statements,
        ):
            next_statement = (
                statements[index + 1]
                if index + 1 < len(statements)
                else None
            )

            statement_objects = self._object_analyzer.analyse(
                statement,
            )

            objects.extend(
                statement_objects,
            )

            statement_findings = self._rules.analyse(
                statement,
                context,
                next_statement,
            )

            findings.extend(
                statement_findings,
            )

        return AnalyseFileResult(
            file=file,
            findings=tuple(findings),
            objects=tuple(objects),
        )
