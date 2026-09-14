"""
Generic Git plugin.
"""

from __future__ import annotations

import random
from pathlib import Path
from typing import Any

from lib.models.plugin import PluginResult
from lib.plugins.base import BasePlugin

from .exceptions import GenericGitPluginException


class GenericGitPlugin(
    BasePlugin,
):
    """
    Execute generic Git operations.
    """

    OPERATIONS = {
        "status",
        "pull",
        "fetch",
        "add",
        "commit",
        "push",
        "log",
        "checkout",
        "branch",
        "revision",
        "deployment",
    }

    def execute(
        self,
    ) -> PluginResult:
        """
        Execute the requested Git operation.
        """

        self.message.info(
            "Starting Git operation.",
        )

        try:

            with self.activity(
                "git",
            ):

                result = self._execute()

        except GenericGitPluginException as exc:

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

        except Exception as exc:

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

        self.message.success(
            "Git operation completed successfully.",
        )

        return result

    # ------------------------------------------------------------------
    # Implementation
    # ------------------------------------------------------------------

    def _execute(
        self,
    ) -> PluginResult:
        """
        Resolve arguments and execute the Git operation.
        """

        operation = self.arguments.string(
            "operation",
            required=True,
        )

        repository = self.arguments.path(
            "repository",
            required=True,
        )

        assert operation is not None
        assert repository is not None

        operation = operation.strip().lower()

        if operation not in self.OPERATIONS:

            raise GenericGitPluginException(
                f"Unsupported Git operation '{operation}'. "
                f"Supported operations: "
                f"{', '.join(sorted(self.OPERATIONS))}.",
            )

        self._validate_repository(
            repository,
        )

        self.outputs["operation"] = operation
        self.outputs["repository"] = str(
            repository,
        )

        if operation == "status":
            return self._status(repository)

        if operation == "pull":
            return self._pull(repository)

        if operation == "fetch":
            return self._fetch(repository)

        if operation == "add":
            return self._add(repository)

        if operation == "commit":
            return self._commit(repository)

        if operation == "push":
            return self._push(repository)

        if operation == "log":
            return self._log(repository)

        if operation == "checkout":
            return self._checkout(repository)

        if operation == "branch":
            return self._branch(repository)

        if operation == "revision":
            return self._revision(repository)

        return self._deployment(repository)

    # ------------------------------------------------------------------
    # Status
    # ------------------------------------------------------------------

    def _status(
        self,
        repository: Path,
    ) -> PluginResult:

        result = self._git(
            repository,
            [
                "status",
                "--short",
            ],
        )

        self.outputs["status"] = result.stdout

        return self._success(
            changed=False,
        )

    # ------------------------------------------------------------------
    # Pull
    # ------------------------------------------------------------------

    def _pull(
        self,
        repository: Path,
    ) -> PluginResult:

        result = self._git(
            repository,
            [
                "pull",
            ],
        )

        self.outputs["stdout"] = result.stdout
        self.outputs["stderr"] = result.stderr

        return self._success(
            changed=True,
        )

    # ------------------------------------------------------------------
    # Fetch
    # ------------------------------------------------------------------

    def _fetch(
        self,
        repository: Path,
    ) -> PluginResult:
        """
        Fetch remote Git changes.
        """

        result = self._git(
            repository,
            [
                "fetch",
            ],
        )

        self.outputs["stdout"] = result.stdout
        self.outputs["stderr"] = result.stderr

        return self._success(
            changed=True,
        )

    # ------------------------------------------------------------------
    # Add
    # ------------------------------------------------------------------

    def _add(
        self,
        repository: Path,
    ) -> PluginResult:

        paths = self.arguments.get(
            "paths",
        )

        if paths is None:
            paths = [
                ".",
            ]

        if not isinstance(
            paths,
            list,
        ):

            raise GenericGitPluginException(
                "Argument 'paths' must be an array.",
            )

        if not paths:

            raise GenericGitPluginException(
                "Argument 'paths' cannot be empty.",
            )

        normalized_paths: list[str] = []

        for path in paths:

            if (
                not isinstance(
                    path,
                    str,
                )
                or not path.strip()
            ):

                raise GenericGitPluginException(
                    "Every Git add path must be " "a non-empty string.",
                )

            normalized_paths.append(
                path.strip(),
            )

        self._git(
            repository,
            [
                "add",
                "--",
                *normalized_paths,
            ],
        )

        self.outputs["paths"] = normalized_paths

        self.message.info(
            f"Staged {len(normalized_paths)} path(s).",
        )

        return self._success(
            changed=True,
        )

    # ------------------------------------------------------------------
    # Commit
    # ------------------------------------------------------------------

    def _commit(
        self,
        repository: Path,
    ) -> PluginResult:

        message = self.arguments.string(
            "message",
            required=True,
        )

        assert message is not None

        message = message.strip()

        if not message:

            raise GenericGitPluginException(
                "Argument 'message' must not be empty.",
            )

        return self._commit_message(
            repository,
            message,
        )

    # ------------------------------------------------------------------
    # Revision
    # ------------------------------------------------------------------

    def _revision(
        self,
        repository: Path,
    ) -> PluginResult:
        """
        Stage all changes and commit a revision snapshot.
        """

        revision = self.generate_revision()

        message = f"Revision: {revision}"

        self._stage_all(
            repository,
        )

        result = self._commit_message(
            repository,
            message,
        )

        self.outputs["revision"] = revision
        self.outputs["message"] = message

        return result

    # ------------------------------------------------------------------
    # Deployment
    # ------------------------------------------------------------------

    def _deployment(
        self,
        repository: Path,
    ) -> PluginResult:
        """
        Stage all changes and commit the deployment.
        """

        tag = self.arguments.string(
            "tag",
            required=True,
        )

        assert tag is not None

        tag = tag.strip()

        if not tag:

            raise GenericGitPluginException(
                "Argument 'tag' must not be empty.",
            )

        message = f"Deployment - {tag}"

        self._stage_all(
            repository,
        )

        result = self._commit_message(
            repository,
            message,
        )

        self.outputs["tag"] = tag
        self.outputs["message"] = message

        return result

    # ------------------------------------------------------------------
    # Commit helper
    # ------------------------------------------------------------------

    def _commit_message(
        self,
        repository: Path,
        message: str,
    ) -> PluginResult:
        """
        Commit staged changes with the supplied message.
        """

        result = self._git(
            repository,
            [
                "commit",
                "-m",
                message,
            ],
            allow_no_changes=True,
        )

        self.outputs["message"] = message

        if result.success:

            self.outputs["committed"] = True

            self.message.info(
                f"Committed: {message}",
            )

            return self._success(
                changed=True,
            )

        if self._is_nothing_to_commit(
            result,
        ):

            self.outputs["committed"] = False
            self.outputs["nothing_to_commit"] = True

            self.message.info(
                "Nothing to commit.",
            )

            return self._success(
                changed=False,
            )

        raise GenericGitPluginException(
            self._git_error(
                result,
            ),
        )

    # ------------------------------------------------------------------
    # Stage all
    # ------------------------------------------------------------------

    def _stage_all(
        self,
        repository: Path,
    ) -> None:
        """
        Stage all repository changes.
        """

        self._git(
            repository,
            [
                "add",
                "--",
                ".",
            ],
        )

        self.outputs["paths"] = [
            ".",
        ]

        self.message.info(
            "Staged all repository changes.",
        )

    # ------------------------------------------------------------------
    # Push
    # ------------------------------------------------------------------

    def _push(
        self,
        repository: Path,
    ) -> PluginResult:

        result = self._git(
            repository,
            [
                "push",
            ],
        )

        self.outputs["stdout"] = result.stdout
        self.outputs["stderr"] = result.stderr

        return self._success(
            changed=True,
        )

    # ------------------------------------------------------------------
    # Log
    # ------------------------------------------------------------------

    def _log(
        self,
        repository: Path,
    ) -> PluginResult:

        count = self.arguments.number(
            "count",
            default=10,
            minimum=1,
        )

        assert count is not None

        result = self._git(
            repository,
            [
                "log",
                f"-{int(count)}",
                "--oneline",
            ],
        )

        self.outputs["log"] = result.stdout

        return self._success(
            changed=False,
        )

    # ------------------------------------------------------------------
    # Checkout
    # ------------------------------------------------------------------

    def _checkout(
        self,
        repository: Path,
    ) -> PluginResult:
        """
        Checkout a branch or revision.
        """

        reference = self.arguments.string(
            "reference",
            required=True,
        )

        assert reference is not None

        reference = reference.strip()

        if not reference:

            raise GenericGitPluginException(
                "Argument 'reference' must not be empty.",
            )

        self._git(
            repository,
            [
                "checkout",
                reference,
            ],
        )

        self.outputs["reference"] = reference

        return self._success(
            changed=True,
        )

    # ------------------------------------------------------------------
    # Branch
    # ------------------------------------------------------------------

    def _branch(
        self,
        repository: Path,
    ) -> PluginResult:

        result = self._git(
            repository,
            [
                "branch",
                "--list",
            ],
        )

        self.outputs["branches"] = result.stdout

        return self._success(
            changed=False,
        )

    # ------------------------------------------------------------------
    # Git execution
    # ------------------------------------------------------------------

    def _git(
        self,
        repository: Path,
        arguments: list[str],
        *,
        allow_no_changes: bool = False,
    ):
        """
        Execute one Git command.
        """

        command = [
            "git",
            "-C",
            str(repository),
            *arguments,
        ]

        self.log.debug(
            "Executing Git command: " + " ".join(command),
        )

        try:

            result = self.shell.run(
                command,
            )

        except FileNotFoundError as exc:

            raise GenericGitPluginException(
                "Git executable was not found in PATH.",
            ) from exc

        except OSError as exc:

            raise GenericGitPluginException(
                f"Unable to execute Git command: {exc}",
            ) from exc

        if result.stdout:
            self.log.info(
                result.stdout,
            )

        if result.stderr:
            self.log.warning(
                result.stderr,
            )

        if result.success:
            return result

        if allow_no_changes and self._is_nothing_to_commit(
            result,
        ):
            return result

        raise GenericGitPluginException(
            self._git_error(
                result,
            ),
        )

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    @staticmethod
    def _validate_repository(
        repository: Path,
    ) -> None:

        if not repository.exists():

            raise GenericGitPluginException(
                f"Git repository does not exist: " f"{repository}",
            )

        if not repository.is_dir():

            raise GenericGitPluginException(
                f"Git repository path is not a directory: " f"{repository}",
            )

        git_directory = repository / ".git"

        if not git_directory.exists():

            raise GenericGitPluginException(
                f"Path is not a Git repository: " f"{repository}",
            )

    @staticmethod
    def _is_nothing_to_commit(
        result: Any,
    ) -> bool:

        output = (f"{result.stdout}\n" f"{result.stderr}").lower()

        return "nothing to commit" in output or "nothing added to commit" in output

    @staticmethod
    def _git_error(
        result: Any,
    ) -> str:
        """
        Extract a useful Git error message.
        """

        message = result.stderr.strip() if result.stderr else result.stdout.strip()

        if not message:
            return "Git command failed."

        return message

    # ------------------------------------------------------------------
    # Revision
    # ------------------------------------------------------------------

    @staticmethod
    def generate_revision() -> int:
        """
        Generate a random numeric revision.
        """

        return random.randint(
            100000,
            999999,
        )

    # ------------------------------------------------------------------
    # Result
    # ------------------------------------------------------------------

    def _success(
        self,
        *,
        changed: bool,
    ) -> PluginResult:

        return PluginResult(
            success=True,
            changed=changed,
            outputs=dict(
                self.outputs,
            ),
            changes=[],
            errors=[],
            warnings=[],
            metadata={
                "artifacts": {name: str(path) for name, path in self.artifacts.items()},
            },
        )

    def _result(
        self,
        *,
        success: bool,
        changed: bool,
        errors: list[str],
    ) -> PluginResult:

        return PluginResult(
            success=success,
            changed=changed,
            outputs=dict(
                self.outputs,
            ),
            changes=[],
            errors=errors,
            warnings=[],
            metadata={
                "artifacts": {name: str(path) for name, path in self.artifacts.items()},
            },
        )
