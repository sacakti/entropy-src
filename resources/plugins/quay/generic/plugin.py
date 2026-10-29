"""
Quay registry cleanup plugin.
"""

from __future__ import annotations

import re
import time
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from lib.models.plugin import PluginResult
from lib.plugins.base import BasePlugin

from .client import QuayClient
from .exceptions import QuayApiError, QuayPluginException, QuayRuleError
from .policy import Rule, matches, parse_rules, plan_repository
from .report import build_report


class QuayGenericPlugin(
    BasePlugin,
):
    """
    Clean images from a Quay registry: keep the newest tags of each
    repository (service), 6 by default, or as custom rules say for
    selected tags. Deleting a tag lets Quay garbage-collect the image
    once no other tag points to it. `list` only lists the tags. Both write
    an HTML report, published as a generated artifact.
    """

    DEFAULT_KEEP = 6

    OPERATIONS = (
        "clean",
        "list",
    )

    def execute(
        self,
    ) -> PluginResult:
        """
        Execute the Quay cleanup.
        """

        self.message.info(
            "Starting Quay plugin.",
        )

        try:

            with self.activity(
                "quay-clean",
            ):

                return self._execute()

        except QuayPluginException as exc:

            self.log.error(
                str(exc),
            )

            self.message.error(
                str(exc),
            )

            return self._result(
                success=False,
                changed=False,
                errors=[
                    str(exc),
                ],
            )

    # ------------------------------------------------------------------
    # Implementation
    # ------------------------------------------------------------------

    def _execute(
        self,
    ) -> PluginResult:

        operation = (self.arguments.string("operation", "clean") or "clean").strip().lower()
        url = (self.arguments.string("url", required=True) or "").strip()
        token = (self.arguments.string("token", required=True) or "").strip()
        namespace = (self.arguments.string("namespace", required=True) or "").strip()
        selected = self.arguments.list("repositories", []) or []
        keep = self.arguments.integer("keep", self.DEFAULT_KEEP)
        if keep is None:
            keep = self.DEFAULT_KEEP
        protect = self.arguments.list("protect", ["latest"]) or []
        min_age_days = self.arguments.integer("min_age_days", 0) or 0
        # Listing never deletes.
        dry_run = operation == "list" or bool(self.arguments.boolean("dry_run", True))
        verify_tls = not self.arguments.boolean("insecure_skip_tls_verify", False)
        report = self.arguments.boolean("report", True)

        if operation not in self.OPERATIONS:
            raise QuayPluginException(
                f"'operation' must be one of {', '.join(self.OPERATIONS)}, not '{operation}'."
            )
        if not url.startswith(("https://", "http://")):
            raise QuayPluginException(f"'url' must be an http(s) URL, not '{url}'.")
        if not token or not namespace:
            raise QuayPluginException("'token' and 'namespace' are required.")
        if keep < 1:
            raise QuayRuleError("'keep' must be 1 or more; use a rule with keep 0 to purge tags.")
        if min_age_days < 0:
            raise QuayRuleError("'min_age_days' must be 0 or more.")
        if not all(isinstance(item, str) and item for item in [*selected, *protect]):
            raise QuayRuleError("'repositories' and 'protect' must be lists of patterns.")

        rules = parse_rules(self.arguments.list("rules", []))
        client = QuayClient(url, token, verify_tls=verify_tls)

        repositories = sorted(
            name
            for name in client.repositories(namespace)
            if not selected or any(matches(pattern, name) for pattern in selected)
        )

        self.message.info(
            f"{len(repositories)} repositor{'y' if len(repositories) == 1 else 'ies'} in "
            f"'{namespace}'"
            + (
                "."
                if operation == "list"
                else f"; keeping the newest {keep} tags of each"
                + (f", with {len(rules)} custom rule(s)" if rules else "")
                + "."
            ),
        )

        if operation == "clean" and dry_run:
            self.message.warning(
                "Dry run: nothing is deleted. Set dry_run to false to delete.",
            )

        now = time.time()
        plan: Dict[str, List[Dict[str, Any]]] = {}
        deleted: List[str] = []
        errors: List[str] = []

        for repository in repositories:

            decisions = plan_repository(
                repository,
                client.tags(namespace, repository),
                keep=keep,
                rules=rules,
                protect=protect,
                min_age_days=min_age_days,
                now=now,
            )
            rows = [
                {**decision.as_dict(), "status": decision.as_dict()["action"]}
                for decision in decisions
            ]
            plan[repository] = rows
            removals = [row for row in rows if row["status"] == "delete"]

            if operation == "list":
                self.message.info(
                    f"{repository} ({len(rows)}): "
                    + (", ".join(row["tag"] for row in rows) or "no tags"),
                )
                continue

            self.message.info(
                f"{repository}: {len(rows)} tags, keeping {len(rows) - len(removals)}, "
                f"{'would delete' if dry_run else 'deleting'} {len(removals)}.",
            )

            for row in removals:

                reference = f"{repository}:{row['tag']}"

                if dry_run:
                    self.log.info(f"Would delete {namespace}/{reference} ({row['reason']}).")
                    deleted.append(reference)
                    continue

                try:
                    client.delete_tag(namespace, repository, row["tag"])
                except QuayApiError as exc:
                    row.update(status="failed", error=str(exc))
                    errors.append(f"{reference}: {exc}")
                    self.message.error(f"Could not delete {reference}: {exc}")
                    continue

                row["status"] = "deleted"
                deleted.append(reference)
                self.log.info(f"Deleted {namespace}/{reference} ({row['reason']}).")

        scanned = sum(len(rows) for rows in plan.values())
        kept = sum(1 for rows in plan.values() for row in rows if row["status"] == "keep")

        self.outputs.update(
            {
                "operation": operation,
                "namespace": namespace,
                "repositories": repositories,
                "dry_run": dry_run,
                "tags": {name: [row["tag"] for row in rows] for name, rows in plan.items()},
                "tags_scanned": scanned,
                "tags_kept": kept,
                "deleted": [] if operation == "list" else deleted,
                "deleted_count": 0 if operation == "list" else len(deleted),
                "errors": errors,
                "plan": plan,
                "report": "",
            },
        )

        if report:
            self._write_report(
                url=url,
                namespace=namespace,
                operation=operation,
                dry_run=dry_run,
                keep=keep,
                protect=protect,
                min_age_days=min_age_days,
                rules=rules,
                plan=plan,
                now=now,
            )

        if operation == "list":
            self.message.success(f"Listed {scanned} tags in {len(repositories)} repositories.")
            return self._result(success=True, changed=False)

        summary = (
            f"{'Would delete' if dry_run else 'Deleted'} {len(deleted)} of {scanned} tags "
            f"in {len(repositories)} repositories."
        )
        if errors:
            self.message.error(f"{summary} {len(errors)} deletion(s) failed.")
        else:
            self.message.success(summary)

        return self._result(
            success=not errors,
            changed=bool(deleted) and not dry_run,
            errors=errors,
        )

    # ------------------------------------------------------------------
    # Report
    # ------------------------------------------------------------------

    def _report_directory(
        self,
        namespace: str,
    ) -> Path:
        """
        Where reports are kept: `report_directory`, else the plugin's data
        folder (the run workspace is temporary; artifacts must outlast it).
        """

        value = self.arguments.path("report_directory")
        if value:
            directory = Path(self.filesystem.path(str(value))).expanduser()
        else:
            safe = re.sub(r"[^A-Za-z0-9._-]+", "-", namespace).strip(".-") or "namespace"
            directory = Path(self.data_directory) / "reports" / safe
        self.filesystem.mkdir(directory)
        return directory

    def _write_report(
        self,
        *,
        url: str,
        namespace: str,
        operation: str,
        dry_run: bool,
        keep: int,
        protect: List[str],
        min_age_days: int,
        rules: List[Rule],
        plan: Dict[str, List[Dict[str, Any]]],
        now: float,
    ) -> None:
        """
        Write the HTML report and publish it as a generated artifact.
        """

        moment = datetime.fromtimestamp(now, tz=timezone.utc)
        kind = "tags" if operation == "list" else "dry-run" if dry_run else "cleanup"
        path = self._report_directory(namespace) / (
            f"quay-{kind}-{moment.strftime('%Y%m%d-%H%M%S')}.html"
        )
        self.filesystem.write_text(
            path,
            build_report(
                {
                    "title": (
                        f"Quay tags — {namespace}"
                        if operation == "list"
                        else f"Quay cleanup — {namespace}"
                    ),
                    "registry": url,
                    "namespace": namespace,
                    "operation": operation,
                    "dry_run": dry_run,
                    "keep": keep,
                    "protect": protect,
                    "min_age_days": min_age_days,
                    "rules": [asdict(rule) for rule in rules],
                    "generated": moment.strftime("%Y-%m-%d %H:%M UTC"),
                },
                plan,
                now,
            ),
        )
        self.artifacts["quay_report"] = path
        self.outputs["report"] = str(path)
        self.message.info(f"Report: {path}")

    def _result(
        self,
        *,
        success: bool,
        changed: bool,
        errors: List[str] | None = None,
    ) -> PluginResult:
        """
        Build the standard plugin result.
        """

        return PluginResult(
            success=success,
            changed=changed,
            outputs=dict(
                self.outputs,
            ),
            changes=[],
            errors=errors or [],
            warnings=[],
            metadata={
                "artifacts": {name: str(path) for name, path in self.artifacts.items()},
            },
        )
