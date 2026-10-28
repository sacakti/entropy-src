"""
Audit of an OpenShift YAML repository kept up to date by oc.sync_yamls.

Each run compares the synchronized YAML files with the last commit, writes a
detailed HTML report (which ConfigMap keys, Deployment fields, ... changed),
commits the files so the next run starts from them, and removes reports
older than the retention period. The report is a generated artifact.

The repository is a folder on the server, or a repository from Tools -> Git
repositories (checked out into the run's workspace; the audit commit is
pushed back to it). A repository created from a folder on the server is
audited in that folder, where oc.sync_yamls writes, and Entropy's copy is
then updated with the audit commit.
"""

from __future__ import annotations

import re
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Optional

from lib.models.plugin import PluginResult
from lib.plugins.base import BasePlugin
from lib.plugins.exceptions import PluginValueError

from .differ import DEFAULT_IGNORED, compare
from .exceptions import AuditPluginException
from .report import build_report


class AuditPlugin(BasePlugin):
    """
    Report what changed in a YAML repository since the previous audit.
    """

    REPORT_NAME = re.compile(r"^audit-(\d{8}-\d{6})\.html$")

    YAML_SUFFIXES = (".yaml", ".yml")

    STATUS_ORDER = {"modified": 0, "added": 1, "removed": 2}

    DEFAULT_MESSAGE = "Entropy audit {date}: {summary}"

    # Used only when the repository has no git identity configured.
    COMMIT_IDENTITY = ("-c", "user.name=Entropy", "-c", "user.email=entropy@localhost")

    def execute(self) -> PluginResult:
        """
        Execute the audit.
        """

        self.message.info(
            "Starting audit.",
        )

        try:
            with self.activity("audit"):
                result = self._execute()

        except AuditPluginException as exc:
            self.log.error(str(exc))
            self.message.error(str(exc))

            return self._result(
                success=False,
                changed=bool(self.artifacts),
                errors=[str(exc)],
            )

        self.message.success(
            "audit completed successfully.",
        )

        return result

    # ------------------------------------------------------------------
    # Implementation
    # ------------------------------------------------------------------

    def _execute(self) -> PluginResult:
        repository, managed, destination = self._repository()
        report_directory = self._report_directory(repository, managed)
        retention_days = self.arguments.integer("retention_days", 10, minimum=0) or 0
        commit = self.arguments.boolean("commit", True)
        # A managed repository is a fresh checkout: without a push the commit is lost.
        push = self.arguments.boolean("push")
        push = bool(managed) if push is None else push
        ignored = DEFAULT_IGNORED + tuple(
            str(item) for item in (self.arguments.list("ignore_fields", []) or [])
        )
        title = self.arguments.string("title", "OpenShift YAML audit") or "OpenShift YAML audit"

        top = Path(self._git(repository, "rev-parse", "--show-toplevel").strip())
        base = self._head(repository)
        self._ignore_reports(repository, report_directory)

        entries = []
        for relative, previous in self._changed_files(repository):
            old = (
                self._load(self._show(repository, base, previous), previous)
                if base and previous
                else None
            )
            current = top / relative
            new = (
                self._load(self.filesystem.read_text(current), relative)
                if self.filesystem.exists(current)
                else None
            )
            if old is None and new is None:
                continue
            entry = compare(old, new, relative, ignored)
            if entry is not None:
                entries.append(entry)
        entries.sort(
            key=lambda item: (self.STATUS_ORDER[item["status"]], item["kind"], item["name"])
        )

        now = datetime.now().astimezone()
        statuses = Counter(entry["status"] for entry in entries)
        summary = {
            "modified": statuses["modified"],
            "added": statuses["added"],
            "removed": statuses["removed"],
            "changes": sum(len(entry["fields"]) + len(entry["data"]) for entry in entries),
        }

        commit_id = ""
        commit_error = ""
        if commit:
            try:
                commit_id = self._commit(repository, now, summary, first=base is None)
            except AuditPluginException as exc:
                commit_error = f"committing failed: {exc}"
        pushed = False
        if commit_id and push and not commit_error:
            try:
                self._push(repository, destination)
                pushed = True
            except AuditPluginException as exc:
                commit_error = f"pushing {commit_id} failed: {exc}"

        notes = []
        if managed and destination != "origin":
            notes.append(
                f"{managed} was created from the server folder {repository};"
                " that folder was audited and Entropy's copy updated with the audit commit."
            )
        if base is None:
            notes.append(
                "First audit: every resource is listed as added."
                " Later audits list only what changed."
            )
        if not commit:
            notes.append("Committing is off: the next audit compares with the same commit again.")
        if commit_error:
            notes.append(f"Not saved to git: {commit_error}")

        report = report_directory / f"audit-{now.strftime('%Y%m%d-%H%M%S')}.html"
        self.filesystem.write_text(
            report,
            build_report(
                {
                    "title": title,
                    "repository": (
                        f"{managed} (Tools → Git repositories)" if managed else str(repository)
                    ),
                    "generated": now.strftime("%Y-%m-%d %H:%M %Z"),
                    "base": self._describe(repository, base),
                    "commit": commit_id,
                    "notes": notes,
                },
                entries,
            ),
        )
        removed = self._rotate(report_directory, retention_days, now, keep=report)
        self.artifacts["audit_report"] = report

        self.message.info(
            f"{len(entries)} resource(s) changed: {summary['modified']} modified, "
            f"{summary['added']} added, {summary['removed']} removed. Report: {report}",
        )
        if removed:
            self.message.info(f"Removed {len(removed)} report(s) older than {retention_days} days.")

        self.outputs.update(
            {
                "report": str(report),
                "reports": [str(path) for path in self._reports(report_directory)],
                "removed_reports": [str(path) for path in removed],
                "summary": summary,
                "commit": commit_id,
                "base_commit": base or "",
                "repository": str(repository),
                "git_repository": managed or "",
                "pushed": pushed,
            },
        )

        if commit_error:
            raise AuditPluginException(
                f"The report was written to {report}, but {commit_error}",
            )

        return self._result(
            success=True,
            changed=True,
        )

    # ------------------------------------------------------------------
    # Arguments and locations
    # ------------------------------------------------------------------

    def _repository(self) -> tuple[Path, Optional[str], str]:
        """
        The working tree to audit, the Tools -> Git repositories name when it is
        a managed repository (None for a folder on the server), and where the
        audit commit is pushed: 'origin', or Entropy's copy of a repository
        that was created from a server folder.
        """

        managed = (self.arguments.string("git_repository") or "").strip() or None
        folder = self.arguments.path("repository")
        if managed and folder:
            raise AuditPluginException(
                "Give either 'repository' (a folder) or 'git_repository'"
                " (Tools -> Git repositories), not both.",
            )
        destination = "origin"
        checkout: Optional[Path] = None
        if not managed and not folder and len(self.repositories) == 1:
            # The one repository assigned to this plugin or workflow (already checked out).
            managed, assigned_path = next(iter(self.repositories.items()))
            checkout = Path(assigned_path)
        if managed:
            repository, destination = self._managed(managed, checkout)
        elif folder:
            repository = Path(self.filesystem.path(str(folder))).expanduser()
        else:
            assigned = ", ".join(sorted(self.repositories))
            raise AuditPluginException(
                "Give 'repository' (a folder on the server) or 'git_repository'"
                " (a repository from Tools -> Git repositories)"
                + (f"; several are assigned to this run: {assigned}." if assigned else ".")
            )
        if not self.filesystem.is_directory(repository):
            raise AuditPluginException(f"Repository '{repository}' is not a directory.")
        result = self.shell.run(["git", "rev-parse", "--is-inside-work-tree"], cwd=repository)
        if not result.success or result.stdout.strip() != "true":
            raise AuditPluginException(f"Repository '{repository}' is not a git repository.")
        return repository.resolve(), managed, destination

    def _managed(self, name: str, checkout: Optional[Path] = None) -> tuple[Path, str]:
        """
        A repository created from a server folder is audited in that folder:
        oc.sync_yamls writes there, and Entropy's copy only has what was
        committed. Other repositories are checked out into the run.
        """

        try:
            info = self.git_repository_info(name)
            folder = info.get("source_location") if info.get("source_type") == "local" else None
            if folder and self.filesystem.is_directory(Path(folder)):
                return Path(folder), str(info["path"])
            if folder:
                self.message.warning(
                    f"{name} was created from {folder}, which no longer exists; auditing"
                    " Entropy's copy instead."
                )
            return checkout or Path(self.git_repository(name)), "origin"
        except PluginValueError as exc:
            raise AuditPluginException(str(exc)) from exc

    def _push(self, repository: Path, destination: str) -> None:
        if destination == "origin":
            self._git(repository, "push", "--quiet", "origin", "HEAD")
            return
        branch = self._git(repository, "rev-parse", "--abbrev-ref", "HEAD").strip()
        if branch == "HEAD":
            raise AuditPluginException("the folder is not on a branch (detached HEAD)")
        self._git(repository, "push", "--quiet", destination, f"HEAD:refs/heads/{branch}")

    def _report_directory(self, repository: Path, managed: Optional[str]) -> Path:
        value = self.arguments.path("report_directory")
        if value:
            directory = Path(self.filesystem.path(str(value))).expanduser()
        elif managed:
            # The checkout lives in the temporary run workspace; reports must outlast it.
            safe = re.sub(r"[^A-Za-z0-9._-]+", "-", managed).strip(".-") or "repository"
            directory = Path(self.data_directory) / "reports" / safe
        else:
            directory = repository.parent / f"{repository.name}-audit"
        self.filesystem.mkdir(directory)
        return Path(directory).resolve()

    def _ignore_reports(self, repository: Path, report_directory: Path) -> None:
        """Keep a report directory inside the repository out of git."""

        try:
            relative = report_directory.relative_to(repository)
        except ValueError:
            return
        line = f"/{relative.as_posix()}/"
        ignore = repository / ".gitignore"
        text = self.filesystem.read_text(ignore) if self.filesystem.exists(ignore) else ""
        if line in text.splitlines():
            return
        separator = "\n" if text and not text.endswith("\n") else ""
        self.filesystem.write_text(ignore, f"{text}{separator}# Entropy audit reports\n{line}\n")

    # ------------------------------------------------------------------
    # Git
    # ------------------------------------------------------------------

    def _git(self, repository: Path, *arguments: str) -> str:
        result = self.shell.run(["git", *arguments], cwd=repository)
        if not result.success:
            reason = (
                result.stderr or result.stdout or ""
            ).strip() or f"exit code {result.exit_code}"
            raise AuditPluginException(
                f"git {arguments[0] if arguments[0] != '-c' else 'commit'} failed: {reason}"
            )
        return result.stdout or ""

    def _head(self, repository: Path) -> Optional[str]:
        result = self.shell.run(["git", "rev-parse", "--verify", "-q", "HEAD"], cwd=repository)
        return result.stdout.strip() if result.success and result.stdout.strip() else None

    def _describe(self, repository: Path, base: Optional[str]) -> str:
        if base is None:
            return "nothing (first audit)"
        return self._git(
            repository, "log", "-1", "--format=%h (%cd)", "--date=format:%Y-%m-%d %H:%M", base
        ).strip()

    def _changed_files(self, repository: Path) -> list[tuple[str, Optional[str]]]:
        """
        YAML files changed since HEAD in this directory, as (path, previous path)
        relative to the git top level; previous is None for new files.
        """

        output = self._git(
            repository,
            "-c",
            "core.quotepath=off",
            "status",
            "--porcelain=v1",
            "-z",
            "--untracked-files=all",
            "--",
            ".",
        )
        items = output.split("\0")
        changed: list[tuple[str, Optional[str]]] = []
        index = 0
        while index < len(items):
            entry = items[index]
            index += 1
            if len(entry) < 4:
                continue
            code, path = entry[:2], entry[3:]
            previous: Optional[str] = path
            if "R" in code or "C" in code:
                previous = items[index]
                index += 1
            if code in ("??", "A ", "AM"):
                previous = None
            if path.lower().endswith(self.YAML_SUFFIXES):
                changed.append((path, previous))
        return changed

    def _show(self, repository: Path, base: Optional[str], path: str) -> str:
        result = self.shell.run(["git", "show", f"{base}:{path}"], cwd=repository)
        return result.stdout if result.success else ""

    def _commit(self, repository: Path, now: datetime, summary: dict[str, int], first: bool) -> str:
        """Commit the synchronized files; the short commit id, or '' when nothing changed."""

        self._git(repository, "add", "-A", "--", ".")
        staged = self.shell.run(["git", "diff", "--cached", "--quiet"], cwd=repository)
        if staged.success:
            return ""
        template = (
            self.arguments.string("commit_message", self.DEFAULT_MESSAGE) or self.DEFAULT_MESSAGE
        )
        text = (
            "first audit"
            if first
            else f"{summary['modified']} modified, {summary['added']} added, "
            f"{summary['removed']} removed"
        )
        try:
            message = template.format(date=now.strftime("%Y-%m-%d %H:%M"), summary=text)
        except (KeyError, IndexError, ValueError):
            raise AuditPluginException(
                "commit_message may only use {date} and {summary} placeholders."
            ) from None
        configured = self.shell.run(["git", "config", "user.email"], cwd=repository)
        identity = () if configured.success and configured.stdout.strip() else self.COMMIT_IDENTITY
        self._git(repository, *identity, "commit", "-q", "-m", message)
        return self._git(repository, "rev-parse", "--short", "HEAD").strip()

    # ------------------------------------------------------------------
    # Files
    # ------------------------------------------------------------------

    def _load(self, text: str, path: str) -> Optional[dict[str, Any]]:
        if not text.strip():
            return None
        try:
            document = self.filesystem.parse_yaml(text)
        except Exception as exc:  # noqa: BLE001 - the parser raises several error types
            self.message.warning(f"{path} is not valid YAML ({exc}); comparing it as text.")
            return {"kind": "File", "metadata": {"name": path}, "text": text}
        if not isinstance(document, dict):
            return {"kind": "File", "metadata": {"name": path}, "text": text}
        return dict(document)

    def _reports(self, directory: Path) -> list[Path]:
        return [
            path for path in self.filesystem.listdir(directory) if self.REPORT_NAME.match(path.name)
        ]

    def _rotate(self, directory: Path, days: int, now: datetime, keep: Path) -> list[Path]:
        """Remove reports older than `days` (0 keeps every report)."""

        if days <= 0:
            return []
        cutoff = now.replace(tzinfo=None) - timedelta(days=days)
        removed = []
        for path in self._reports(directory):
            match = self.REPORT_NAME.match(path.name)
            if path == keep or match is None:
                continue
            if datetime.strptime(match.group(1), "%Y%m%d-%H%M%S") < cutoff:
                self.filesystem.remove(path)
                removed.append(path)
        return removed

    def _result(
        self,
        *,
        success: bool,
        changed: bool,
        errors: list[str] | None = None,
    ) -> PluginResult:
        """
        Build the plugin result.
        """

        return PluginResult(
            success=success,
            changed=changed,
            outputs=dict(self.outputs),
            changes=[],
            errors=errors or [],
            warnings=[],
            metadata={
                "artifacts": {name: str(path) for name, path in self.artifacts.items()},
            },
        )
