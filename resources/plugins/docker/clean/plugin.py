"""
Docker storage cleanup plugin.
"""

from __future__ import annotations

import json
import re

from lib.models.plugin import PluginResult
from lib.plugins.base import BasePlugin

from .exceptions import CleanPluginException


class DockerCleanPlugin(
    BasePlugin,
):
    """
    Clean Docker storage using a controlled cleanup strategy.

    Cleanup is storage-aware by default. When ``force`` is enabled,
    the selected cleanup strategy runs regardless of available
    storage.
    """

    CLEANUP_TYPES = {
        "tag",
        "cache",
        "unused",
        "complete",
    }

    DEFAULT_MINIMUM_STORAGE = 10

    def execute(
        self,
    ) -> PluginResult:
        """
        Execute Docker cleanup.
        """

        self.message.info(
            "Starting Docker cleanup.",
        )

        try:

            with self.activity(
                "docker-clean",
            ):

                return self._execute()

        except CleanPluginException as exc:

            self.log.error(
                str(exc),
            )

            self.message.error(
                str(exc),
            )

            return PluginResult(
                success=False,
                changed=False,
                outputs=dict(
                    self.outputs,
                ),
                changes=[],
                errors=[
                    str(exc),
                ],
                warnings=[],
                metadata={
                    "artifacts": {
                        name: str(path)
                        for name, path in self.artifacts.items()
                    },
                },
            )

    # ------------------------------------------------------------------
    # Implementation
    # ------------------------------------------------------------------

    def _execute(
        self,
    ) -> PluginResult:
        """
        Execute the configured cleanup strategy.
        """

        minimum_storage = self.arguments.integer(
            "minimum_storage",
            self.DEFAULT_MINIMUM_STORAGE,
        )

        cleanup = self.arguments.string(
            "cleanup",
            "tag",
        ).strip().lower()

        tag_pattern = self.arguments.string(
            "tag_pattern",
            "",
        ).strip()

        force = self.arguments.boolean(
            "force",
            False,
        )

        dry_run = self.arguments.boolean(
            "dry_run",
            False,
        )

        confirm = self.arguments.boolean(
            "confirm",
            False,
        )

        self._validate(
            minimum_storage=minimum_storage,
            cleanup=cleanup,
            tag_pattern=tag_pattern,
            confirm=confirm,
        )

        storage = self._storage()

        self.outputs.update(
            {
                "cleanup": cleanup,
                "minimum_storage_gb": minimum_storage,
                "storage_before_gb": storage["available_gb"],
                "force": force,
                "dry_run": dry_run,
                "cleanup_required": False,
                "items_removed": 0,
            },
        )

        self.message.info(
            f"Available Docker storage: "
            f"{storage['available_gb']:.2f} GB",
        )

        self.message.info(
            f"Minimum storage: {minimum_storage} GB",
        )

        if (
            not force
            and storage["available_gb"] >= minimum_storage
        ):

            self.message.info(
                "Minimum storage requirement is satisfied. "
                "No cleanup required.",
            )

            return self._result(
                success=True,
                changed=False,
            )

        if force:

            self.message.warning(
                "Force enabled. Running cleanup regardless "
                "of available storage.",
            )

        if dry_run:

            self.message.warning(
                "Dry-run enabled. No Docker resources will "
                "be removed.",
            )

        if cleanup == "tag":

            result = self._cleanup_tags(
                tag_pattern=tag_pattern,
                dry_run=dry_run,
            )

        elif cleanup == "cache":

            result = self._cleanup_cache(
                dry_run=dry_run,
            )

        elif cleanup == "unused":

            result = self._cleanup_unused(
                dry_run=dry_run,
            )

        else:

            result = self._cleanup_complete(
                dry_run=dry_run,
            )

        storage_after = self._storage()

        self.outputs["storage_after_gb"] = (
            storage_after["available_gb"]
        )

        self.outputs["storage_reclaimed_gb"] = max(
            0.0,
            storage_after["available_gb"]
            - storage["available_gb"],
        )

        return result

    # ------------------------------------------------------------------
    # Tag cleanup
    # ------------------------------------------------------------------

    def _cleanup_tags(
        self,
        *,
        tag_pattern: str,
        dry_run: bool,
    ) -> PluginResult:
        """
        Remove images whose full image reference contains tag_pattern.
        """

        result = self._docker(
            [
                "docker",
                "image",
                "ls",
                "--format",
                "{{.Repository}}:{{.Tag}}",
            ],
        )

        if result is None:

            return self._result(
                success=False,
                changed=False,
            )

        references = [
            line.strip()
            for line in result.stdout.splitlines()
            if line.strip()
            and "<none>:<none>" not in line
        ]

        matches = [
            reference
            for reference in references
            if tag_pattern in reference
        ]

        self.outputs["matched_images"] = matches
        self.outputs["items_removed"] = 0

        self.log.info(
            "Tag cleanup matched %d image(s).",
            len(matches),
        )

        if not matches:

            self.message.info(
                "No Docker images matched the requested tag pattern.",
            )

            return self._result(
                success=True,
                changed=False,
            )

        if dry_run:

            for reference in matches:

                self.message.info(
                    f"Would remove: {reference}",
                )

            return self._result(
                success=True,
                changed=False,
            )

        removed = 0
        errors: list[str] = []

        for reference in matches:

            self.log.info(
                "Removing Docker image '%s'.",
                reference,
            )

            remove = self._docker(
                [
                    "docker",
                    "image",
                    "rm",
                    reference,
                ],
            )

            if remove is None:

                errors.append(
                    f"Failed to remove '{reference}'.",
                )

                continue

            if remove.failed:

                errors.append(
                    f"Failed to remove '{reference}': "
                    f"{remove.stderr.strip()}",
                )

                continue

            removed += 1

        self.outputs["items_removed"] = removed

        if errors:

            self.outputs["errors"] = errors

            return self._result(
                success=False,
                changed=removed > 0,
                errors=errors,
            )

        return self._result(
            success=True,
            changed=removed > 0,
        )

    # ------------------------------------------------------------------
    # Standard cleanup
    # ------------------------------------------------------------------

    def _cleanup_cache(
        self,
        *,
        dry_run: bool,
    ) -> PluginResult:
        """
        Remove unused Docker builder cache.
        """

        command = [
            "docker",
            "builder",
            "prune",
            "--force",
        ]

        return self._run_prune(
            command,
            dry_run=dry_run,
        )

    def _cleanup_unused(
        self,
        *,
        dry_run: bool,
    ) -> PluginResult:
        """
        Remove unused Docker images.
        """

        command = [
            "docker",
            "image",
            "prune",
            "--force",
        ]

        return self._run_prune(
            command,
            dry_run=dry_run,
        )

    def _cleanup_complete(
        self,
        *,
        dry_run: bool,
    ) -> PluginResult:
        """
        Remove all unused Docker resources and images.
        """

        command = [
            "docker",
            "system",
            "prune",
            "--all",
            "--force",
        ]

        return self._run_prune(
            command,
            dry_run=dry_run,
        )

    def _run_prune(
        self,
        command: list[str],
        *,
        dry_run: bool,
    ) -> PluginResult:
        """
        Execute a Docker prune command.
        """

        self.log.debug(
            f"Executing Docker command: {' '.join(command)}",
        )

        if dry_run:

            self.log.info(
                "Skipping Docker command because dry-run is enabled.",
            )

            return self._result(
                success=True,
                changed=False,
            )

        result = self._docker(
            command,
        )

        if result is None:

            return self._result(
                success=False,
                changed=False,
            )

        if result.failed:

            return self._result(
                success=False,
                changed=False,
                errors=[
                    (
                        "Docker cleanup failed with "
                        f"exit code {result.exit_code}."
                    ),
                ],
            )

        items_removed = self._count_removed_lines(
            result.stdout,
        )

        self.outputs["items_removed"] = items_removed

        return self._result(
            success=True,
            changed=items_removed > 0,
        )

    # ------------------------------------------------------------------
    # Docker execution
    # ------------------------------------------------------------------

    def _docker(
        self,
        command: list[str],
    ):
        """
        Execute a Docker command and write process output to the log.
        """

        self.log.debug(
            f"Executing Docker command: {' '.join(command)}",
        )

        try:

            result = self.shell.run(
                command,
            )

        except FileNotFoundError as exc:

            self.log.error(
                f"Docker command was not found: {exc}",
            )

            raise CleanPluginException(
                "Docker is not available on this system.",
            ) from exc

        except OSError as exc:

            self.log.error(
                f"Docker command execution failed: {exc}",
            )

            raise CleanPluginException(
                f"Unable to execute Docker: {exc}",
            ) from exc

        if result.stdout:

            self.log.info(
                "Docker stdout:\n%s",
                result.stdout.rstrip(),
            )

        if result.stderr:

            self.log.warning(
                "Docker stderr:\n%s",
                result.stderr.rstrip(),
            )

        self.outputs["exit_code"] = result.exit_code
        self.outputs["success"] = result.success
        self.outputs["stdout"] = result.stdout
        self.outputs["stderr"] = result.stderr
        self.outputs["duration"] = result.duration

        return result

    # ------------------------------------------------------------------
    # Storage
    # ------------------------------------------------------------------

    def _storage(
        self,
    ) -> dict[str, float]:
        """
        Return available storage for Docker's storage filesystem.

        Docker's storage root is obtained from ``docker info`` and
        filesystem availability is then measured using ``df``.
        """

        result = self._docker(
            [
                "docker",
                "info",
                "--format",
                "{{json .DockerRootDir}}",
            ],
        )

        if result.failed:

            raise CleanPluginException(
                "Unable to determine Docker storage root: "
                f"{result.stderr.strip()}",
            )

        try:

            docker_root = json.loads(
                result.stdout.strip(),
            )

        except json.JSONDecodeError as exc:

            self.log.exception(
                "Unable to parse DockerRootDir.",
            )

            raise CleanPluginException(
                "Docker returned an invalid storage root.",
            ) from exc

        if not docker_root:

            raise CleanPluginException(
                "Docker storage root is empty.",
            )

        df = self.shell.run(
            [
                "df",
                "-Pk",
                docker_root,
            ],
        )

        if df.stdout:

            self.log.info(
                f"Filesystem stdout:\n{df.stdout.rstrip()}",
            )

        if df.stderr:

            self.log.warning(
                f"Filesystem stderr:\n{df.stderr.rstrip()}",
            )

        if df.failed:

            raise CleanPluginException(
                "Unable to determine available Docker storage.",
            )

        lines = [
            line
            for line in df.stdout.splitlines()
            if line.strip()
        ]

        if len(lines) < 2:

            raise CleanPluginException(
                "Unable to parse Docker storage information.",
            )

        fields = re.split(
            r"\s+",
            lines[-1].strip(),
        )

        if len(fields) < 4:

            raise CleanPluginException(
                "Docker storage information is invalid.",
            )

        try:

            available_kb = float(fields[3])

        except ValueError as exc:

            raise CleanPluginException(
                "Docker storage availability is invalid.",
            ) from exc

        return {
            "available_gb": available_kb / 1024 / 1024,
        }

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    @classmethod
    def _validate(
        cls,
        *,
        minimum_storage: int,
        cleanup: str,
        tag_pattern: str,
        confirm: bool,
    ) -> None:
        """
        Validate plugin arguments.
        """

        if minimum_storage <= 0:

            raise CleanPluginException(
                "Argument 'minimum_storage' must be "
                "greater than zero.",
            )

        if cleanup not in cls.CLEANUP_TYPES:

            supported = ", ".join(
                sorted(
                    cls.CLEANUP_TYPES,
                ),
            )

            raise CleanPluginException(
                f"Invalid cleanup type '{cleanup}'. "
                f"Expected one of: {supported}.",
            )

        if cleanup == "tag" and not tag_pattern:

            raise CleanPluginException(
                "Argument 'tag_pattern' is required when "
                "cleanup is 'tag'.",
            )

        if cleanup == "complete" and not confirm:

            raise CleanPluginException(
                "Cleanup type 'complete' is destructive and "
                "requires 'confirm=true'.",
            )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _count_removed_lines(
        stdout: str,
    ) -> int:
        """
        Estimate removed resources from Docker prune output.
        """

        return sum(
            1
            for line in stdout.splitlines()
            if line.strip()
            and not line.lower().startswith(
                (
                    "total reclaimed space",
                    "deleted",
                ),
            )
        )

    def _result(
        self,
        *,
        success: bool,
        changed: bool,
        errors: list[str] | None = None,
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
                "artifacts": {
                    name: str(path)
                    for name, path in self.artifacts.items()
                },
            },
        )
