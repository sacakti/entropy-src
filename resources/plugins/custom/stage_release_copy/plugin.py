"""
Stage release copy plugin.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

from lib.models.plugin import PluginResult
from lib.plugins.base import BasePlugin

from .exceptions import StageReleaseCopyError


class StageReleaseCopyPlugin(
    BasePlugin,
):
    """
    Stage release Docker artifacts into a local repository.
    """

    BACKUP_DIRECTORY = ".backup"

    ROTATE_MAX_FILES = "max_files"
    ROTATE_MAX_TIMESTAMP = "max_timestamp"

    TIMESTAMP_HOURS = "hours"
    TIMESTAMP_DAYS = "days"

    ARTIFACT_REPLACE = "replace"
    ARTIFACT_MOVE = "move"

    ATTRIBUTE_SOURCE = "source"
    ATTRIBUTE_DESTINATION = "destination"
    ATTRIBUTE_PRESERVE = "preserve"

    PERMISSION_SOURCE = "source"
    PERMISSION_DESTINATION = "destination"

    def execute(
        self,
    ) -> PluginResult:
        """
        Execute the staging operation.
        """

        self.message.info(
            "Starting release staging.",
        )

        try:

            with self.activity(
                "stage_release_copy",
            ):

                self._execute()

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
            "Release staging completed successfully.",
        )

        return self._result(
            success=True,
            changed=True,
        )

    # ------------------------------------------------------------------
    # Implementation
    # ------------------------------------------------------------------

    def _execute(
        self,
    ) -> None:
        """
        Execute one or more source/destination copy operations.
        """

        copy_type = self.arguments.string(
            "copy_type",
            default="single",
        )

        artifact_matching = self.arguments.get(
            "artifact_matching",
            {},
        )

        artifact_matching = self._validate_artifact_matching(
            artifact_matching,
        )

        backup = self.arguments.boolean(
            "backup",
            default=True,
        )

        rotate_backup_type = self.arguments.string(
            "rotate_backup_type",
            default=self.ROTATE_MAX_FILES,
            required=True,
        )

        max_files = self.arguments.integer(
            "max_files",
            default=5,
            minimum=1,
        )

        max_timestamp = self.arguments.integer(
            "max_timestamp",
            default=5,
            minimum=1,
        )

        max_timestamp_unit = self.arguments.string(
            "max_timestamp_unit",
            default=self.TIMESTAMP_DAYS,
            required=True,
        )

        assert copy_type is not None
        assert backup is not None
        assert rotate_backup_type is not None
        assert max_files is not None
        assert max_timestamp is not None
        assert max_timestamp_unit is not None

        copy_type = copy_type.lower()
        rotate_backup_type = rotate_backup_type.lower()
        max_timestamp_unit = max_timestamp_unit.lower()

        self._validate_backup_configuration(
            backup=backup,
            rotate_backup_type=rotate_backup_type,
            max_timestamp_unit=max_timestamp_unit,
        )

        mappings: list[dict[str, Path]] = []

        if copy_type == "single":

            source = self.arguments.path(
                "source",
                required=True,
            )

            destination = self.arguments.path(
                "destination",
                required=True,
            )

            assert source is not None
            assert destination is not None

            mappings.append(
                {
                    "source": source,
                    "destination": destination,
                },
            )

        elif copy_type == "multi":

            raw_mappings = self.arguments.get(
                "mappings",
            )

            if (
                not isinstance(
                    raw_mappings,
                    list,
                )
                or not raw_mappings
            ):

                raise StageReleaseCopyError(
                    "Argument 'mappings' must contain " "at least one mapping.",
                )

            for index, mapping in enumerate(
                raw_mappings,
                start=1,
            ):

                if not isinstance(
                    mapping,
                    dict,
                ):

                    raise StageReleaseCopyError(
                        f"Mapping {index} must be an object.",
                    )

                source = mapping.get(
                    "source",
                )

                destination = mapping.get(
                    "destination",
                )

                if (
                    not isinstance(
                        source,
                        str,
                    )
                    or not source.strip()
                ):

                    raise StageReleaseCopyError(
                        f"Mapping {index} requires " "a non-empty 'source'.",
                    )

                if (
                    not isinstance(
                        destination,
                        str,
                    )
                    or not destination.strip()
                ):

                    raise StageReleaseCopyError(
                        f"Mapping {index} requires " "a non-empty 'destination'.",
                    )

                mappings.append(
                    {
                        "source": Path(source),
                        "destination": Path(destination),
                    },
                )

        else:

            raise StageReleaseCopyError(
                f"Unsupported copy_type '{copy_type}'. " "Expected 'single' or 'multi'.",
            )

        total_files = 0
        backup_paths: list[str] = []
        rotation_results: list[dict[str, object]] = []

        for mapping in mappings:

            copied_count, backup_root, rotation = self._copy_mapping(
                source=mapping["source"],
                destination=mapping["destination"],
                backup=backup,
                rotate_backup_type=rotate_backup_type,
                max_files=max_files,
                max_timestamp=max_timestamp,
                max_timestamp_unit=max_timestamp_unit,
                artifact_matching=artifact_matching,
            )

            total_files += copied_count

            if backup_root is not None:
                backup_paths.append(
                    str(backup_root),
                )

            rotation_results.append(
                {
                    "destination": str(mapping["destination"]),
                    **rotation,
                },
            )

        self.outputs.update(
            {
                "copy_type": copy_type,
                "mappings": [
                    {
                        "source": str(mapping["source"]),
                        "destination": str(mapping["destination"]),
                    }
                    for mapping in mappings
                ],
                "files_copied": total_files,
                "backup": {
                    "enabled": backup,
                    "paths": backup_paths,
                },
                "rotation": rotation_results
            },
        )

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    def _validate_source(
        self,
        source: Path,
    ) -> None:
        """
        Validate the source directory.
        """

        if not self.filesystem.exists(
            source,
        ):

            raise FileNotFoundError(
                f"Source directory not found: {source}",
            )

        if not self.filesystem.is_directory(
            source,
        ):

            raise StageReleaseCopyError(
                f"Source path is not a directory: {source}",
            )

    def _validate_backup_configuration(
        self,
        *,
        backup: bool,
        rotate_backup_type: str,
        max_timestamp_unit: str,
    ) -> None:
        """
        Validate backup configuration.
        """

        if not backup:

            return

        if rotate_backup_type not in {
            self.ROTATE_MAX_FILES,
            self.ROTATE_MAX_TIMESTAMP,
        }:

            raise StageReleaseCopyError(
                "Invalid rotate_backup_type: "
                f"{rotate_backup_type}. "
                "Expected 'max_files' or "
                "'max_timestamp'.",
            )

        if max_timestamp_unit not in {
            self.TIMESTAMP_HOURS,
            self.TIMESTAMP_DAYS,
        }:

            raise StageReleaseCopyError(
                "Invalid max_timestamp_unit: "
                f"{max_timestamp_unit}. "
                "Expected 'hours' or 'days'.",
            )

    def _validate_artifact_matching(
        self,
        value: object,
    ) -> dict[str, object]:
        """
        Validate artifact matching configuration.
        """

        if value is None:
            return {
                "enabled": False,
                "patterns": [],
                "rule": self.ARTIFACT_MOVE,
            }

        if not isinstance(value, dict):
            raise StageReleaseCopyError(
                "'artifact_matching' must be an object.",
            )

        enabled = value.get(
            "enabled",
            False,
        )

        if not isinstance(enabled, bool):
            raise StageReleaseCopyError(
                "'artifact_matching.enabled' must be a boolean.",
            )

        patterns = value.get(
            "patterns",
            [],
        )

        if not isinstance(patterns, list):
            raise StageReleaseCopyError(
                "'artifact_matching.patterns' must be a list.",
            )

        normalized_patterns: list[str] = []

        for index, pattern in enumerate(patterns, start=1):

            if not isinstance(pattern, str) or not pattern.strip():
                raise StageReleaseCopyError(
                    f"Artifact matching pattern {index} "
                    "must be a non-empty string.",
                )

            normalized_patterns.append(
                pattern.strip(),
            )

        rule = value.get(
            "rule",
            self.ARTIFACT_MOVE,
        )

        if not isinstance(rule, str):
            raise StageReleaseCopyError(
                "'artifact_matching.rule' must be a string.",
            )

        rule = rule.strip().lower()

        if rule not in {
            self.ARTIFACT_REPLACE,
            self.ARTIFACT_MOVE,
        }:
            raise StageReleaseCopyError(
                "Invalid artifact matching rule: "
                f"{rule}. Expected 'replace' or 'move'.",
            )

        if enabled and not normalized_patterns:
            raise StageReleaseCopyError(
                "'artifact_matching.patterns' must contain "
                "at least one pattern when artifact matching "
                "is enabled.",
            )

        return {
            "enabled": enabled,
            "patterns": normalized_patterns,
            "rule": rule,
        }

    # ------------------------------------------------------------------
    # Copy
    # ------------------------------------------------------------------

    def _copy_mapping(
        self,
        *,
        source: Path,
        destination: Path,
        backup: bool,
        rotate_backup_type: str,
        max_files: int,
        max_timestamp: int,
        max_timestamp_unit: str,
        artifact_matching: dict[str, object],
    ) -> tuple[int, Path | None, dict[str, object]]:
        """
        Copy one source directory into one destination.
        """

        source = source.resolve()
        destination = destination.resolve()

        self._validate_source(
            source,
        )

        self.filesystem.mkdir(
            destination,
        )

        backup_root: Path | None = None

        if backup:

            backup_root = self._create_backup_root(
                destination,
            )

        copied_files = self._copy_directory(
            source=source,
            destination=destination,
            backup_root=backup_root,
            backup_enabled=backup,
            artifact_matching=artifact_matching,
        )

        rotation = {
            "required": False,
            "type": rotate_backup_type,
            "removed": [],
        }

        if backup:

            rotation = self._rotate_backups(
                destination_path=destination,
                rotate_backup_type=rotate_backup_type,
                max_files=max_files,
                max_timestamp=max_timestamp,
                max_timestamp_unit=max_timestamp_unit,
            )

        if backup_root is not None:

            self.artifacts[f"backup_{len(self.artifacts)}"] = backup_root

        self.artifacts[f"staged_{len(self.artifacts)}"] = destination

        self.message.info(
            f"Copied {len(copied_files)} file(s) " f"from '{source}' to '{destination}'.",
        )
            
        return len(copied_files), backup_root, rotation

    def _copy_directory(
        self,
        *,
        source: Path,
        destination: Path,
        backup_root: Path | None,
        backup_enabled: bool,
        artifact_matching: dict[str, object],
    ) -> list[Path]:
        """
        Recursively copy source contents into destination.
        """

        copied_files: list[Path] = []

        files = self.filesystem.find(
            source,
            pattern="*",
            recursive=True,
        )

        for source_file in files:

            if not self.filesystem.is_file(
                source_file,
            ):
                continue

            relative = source_file.relative_to(
                source,
            )

            destination_file = destination / relative

            with self.activity(
                f"Copy {relative}",
            ):

                self.filesystem.mkdir(
                    destination_file.parent,
                )

                artifact_enabled = bool(
                    artifact_matching["enabled"],
                )

                if artifact_enabled:

                    destination_file = self._handle_artifact_matching(
                        source_file=source_file,
                        destination_file=destination_file,
                        destination_root=destination,
                        backup_root=backup_root,
                        backup_enabled=backup_enabled,
                        patterns=artifact_matching["patterns"],
                        rule=artifact_matching["rule"],
                    )

                elif self.filesystem.exists(
                    destination_file,
                ):

                    if not backup_enabled:

                        raise FileExistsError(
                            "Destination file already exists "
                            "and backup is disabled: "
                            f"{destination_file}",
                        )

                    if backup_root is None:

                        raise RuntimeError(
                            "Backup root is unavailable.",
                        )

                    self._backup_existing_file(
                        destination=destination_file,
                        destination_root=destination,
                        backup_root=backup_root,
                    )

                self.filesystem.copy(
                    source_file,
                    destination_file,
                )

            copied_files.append(
                destination_file,
            )

        return copied_files

    # ------------------------------------------------------------------
    # Artifacts Copy - *.jar / *.war
    # ------------------------------------------------------------------ 
    def _handle_artifact_matching(
        self,
        *,
        source_file: Path,
        destination_file: Path,
        destination_root: Path,
        backup_root: Path | None,
        backup_enabled: bool,
        patterns: object,
        rule: object,
    ) -> Path:
        """
        Handle replacement of versioned artifacts.
        """

        if not isinstance(patterns, list):
            raise StageReleaseCopyError(
                "Artifact matching patterns are invalid.",
            )

        if not isinstance(rule, str):
            raise StageReleaseCopyError(
                "Artifact matching rule is invalid.",
            )

        matching_files = self._find_matching_artifacts(
            destination_directory=destination_file.parent,
            source_file=source_file,
            patterns=patterns,
        )

        # No artifact with the configured pattern exists.
        if not matching_files:

            if self.filesystem.exists(
                destination_file,
            ):

                if not backup_enabled:
                    raise FileExistsError(
                        "Destination file already exists "
                        "and backup is disabled: "
                        f"{destination_file}",
                    )

                if backup_root is None:
                    raise RuntimeError(
                        "Backup root is unavailable.",
                    )

                self._backup_existing_file(
                    destination=destination_file,
                    destination_root=destination_root,
                    backup_root=backup_root,
                )

            return destination_file

        if rule == self.ARTIFACT_REPLACE:

            if len(matching_files) > 1:

                raise StageReleaseCopyError(
                    "Multiple matching artifacts found for "
                    f"'{source_file.name}': "
                    + ", ".join(
                        str(path)
                        for path in matching_files
                    )
                    + ". Use a more specific artifact "
                    "matching pattern.",
                )

            existing = matching_files[0]

            if backup_enabled:

                if backup_root is None:
                    raise RuntimeError(
                        "Backup root is unavailable.",
                    )

                self._backup_existing_file(
                    destination=existing,
                    destination_root=destination_root,
                    backup_root=backup_root,
                )

            else:

                self.filesystem.remove(
                    existing,
                )

            self.log.info(
                f"Replacing artifact '{existing.name}' "
                f"with '{source_file.name}'.",
            )

            return existing

        if rule == self.ARTIFACT_MOVE:

            for existing in matching_files:

                if backup_enabled:

                    if backup_root is None:
                        raise RuntimeError(
                            "Backup root is unavailable.",
                        )

                    self._backup_existing_file(
                        destination=existing,
                        destination_root=destination_root,
                        backup_root=backup_root,
                    )

                else:

                    self.filesystem.remove(
                        existing,
                    )

                self.log.info(
                    f"Removed existing artifact "
                    f"'{existing}'.",
                )

            return destination_file

        raise StageReleaseCopyError(
            f"Unsupported artifact matching rule: {rule}",
        )

    def _find_matching_artifacts(
        self,
        *,
        destination_directory: Path,
        source_file: Path,
        patterns: list[object],
    ) -> list[Path]:
        """
        Find existing destination artifacts matching the source
        artifact type.

        A source artifact is matched against only the configured
        pattern(s) that match its filename.

        For example:

            myapp-1.0.2.jar -> *.jar
            myext-1.0.2.war -> *.war
        """

        source_patterns = [
            pattern
            for pattern in patterns
            if isinstance(pattern, str)
            and source_file.match(pattern)
        ]

        if not source_patterns:
            return []

        matching_files: list[Path] = []

        existing_files = self.filesystem.find(
            destination_directory,
            pattern="*",
            recursive=False,
        )

        for existing_file in existing_files:

            if not self.filesystem.is_file(
                existing_file,
            ):
                continue

            if existing_file.name == source_file.name:
                continue

            if any(
                existing_file.match(pattern)
                for pattern in source_patterns
            ):
                matching_files.append(
                    existing_file,
                )

        return matching_files

    # ------------------------------------------------------------------
    # Backup
    # ------------------------------------------------------------------

    def _create_backup_root(
        self,
        destination_path: Path,
    ) -> Path:
        """
        Create a timestamped backup directory.
        """

        backup_directory = destination_path / self.BACKUP_DIRECTORY

        self.filesystem.mkdir(
            backup_directory,
        )

        timestamp = datetime.now().strftime(
            "%Y%m%d_%H%M%S_%f",
        )

        backup_root = backup_directory / timestamp

        self.filesystem.mkdir(
            backup_root,
        )

        return backup_root

    def _backup_existing_file(
        self,
        *,
        destination: Path,
        destination_root: Path,
        backup_root: Path,
    ) -> None:
        """
        Move an existing file into the backup.
        """

        relative = destination.relative_to(
            destination_root,
        )

        backup_file = backup_root / relative

        self.filesystem.mkdir(
            backup_file.parent,
        )

        self.filesystem.move(
            destination,
            backup_file,
        )

        self.log.info(
            f"Backed up '{destination}' " f"to '{backup_file}'.",
        )

    # ------------------------------------------------------------------
    # Backup rotation
    # ------------------------------------------------------------------

    def _rotate_backups(
        self,
        *,
        destination_path: Path,
        rotate_backup_type: str,
        max_files: int,
        max_timestamp: int,
        max_timestamp_unit: str,
    ) -> dict[str, object]:
        """
        Rotate backup directories.

        Rotation only operates on the destination .backup directory.

        The newest backup is always retained.
        """

        backup_directory = (
            destination_path / self.BACKUP_DIRECTORY
        )

        result: dict[str, object] = {
            "required": False,
            "type": rotate_backup_type,
            "removed": [],
        }

        if not self.filesystem.exists(
            backup_directory,
        ):
            return result

        backups = [
            path
            for path in self.filesystem.find(
                backup_directory,
                pattern="*",
                recursive=False,
            )
            if self.filesystem.is_directory(
                path,
            )
        ]

        backups.sort(
            key=lambda path: path.name,
            reverse=True,
        )

        # Nothing to rotate.
        if len(backups) <= 1:
            return result

        stale: list[Path] = []

        if rotate_backup_type == self.ROTATE_MAX_FILES:

            # Always retain the newest backup.
            stale = backups[max_files:]

        elif rotate_backup_type == self.ROTATE_MAX_TIMESTAMP:

            now = datetime.now()

            if max_timestamp_unit == self.TIMESTAMP_HOURS:
                cutoff = now - timedelta(
                    hours=max_timestamp,
                )
            else:
                cutoff = now - timedelta(
                    days=max_timestamp,
                )

            # Never remove the newest backup.
            for backup in backups[1:]:

                created_at = self._backup_timestamp(
                    backup,
                )

                if created_at is None:
                    continue

                if created_at < cutoff:
                    stale.append(
                        backup,
                    )

        else:

            raise StageReleaseCopyError(
                f"Unsupported backup rotation type: "
                f"{rotate_backup_type}",
            )

        if not stale:
            return result

        removed: list[str] = []

        for backup in stale:

            self.filesystem.remove(
                backup,
            )

            removed.append(
                str(backup),
            )

            self.log.info(
                f"Removed rotated backup '{backup}'.",
            )

        result["required"] = True
        result["removed"] = removed

        return result

    @staticmethod
    def _backup_timestamp(
        backup: Path,
    ) -> datetime | None:
        """
        Parse backup timestamp.
        """

        try:
            return datetime.strptime(
                backup.name,
                "%Y%m%d_%H%M%S_%f",
            )

        except ValueError:
            return None
 
    # ------------------------------------------------------------------
    # Result
    # ------------------------------------------------------------------

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
                "artifacts": {name: str(path) for name, path in self.artifacts.items()},
            },
        )
