"""
Stage release copy plugin.

Stages release artifacts from a release ZIP into a local
Docker repository path.

The plugin:

    1. Validates the release archive.
    2. Extracts the release into the workflow workspace.
    3. Discovers release artifacts.
    4. Creates backups for files that already exist.
    5. Copies the new release artifacts into the destination.
    6. Rotates backups according to the configured policy.
    7. Removes the temporary extracted release.

All filesystem and archive operations are performed through
the Entropy Plugin SDK / Linux executor.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

from lib.plugins.base import BasePlugin


class StageReleaseCopyPlugin(
    BasePlugin,
):
    """
    Stage release artifacts into a local repository.
    """

    BACKUP_DIRECTORY = ".backup"

    ROTATE_MAX_FILES = "max_files"
    ROTATE_MAX_TIMESTAMP = "max_timestamp"

    TIMESTAMP_HOURS = "hours"
    TIMESTAMP_DAYS = "days"

    # ------------------------------------------------------------------
    # Execute
    # ------------------------------------------------------------------

    def execute(
        self,
    ) -> None:
        """
        Execute the stage release operation.
        """

        self.message.info("Starting release staging.")

        try:

            with self.activity(
                "stage_release_copy",
            ):

                self._execute()

        except Exception:

            # self.message.error(
            #     str(exc),
            # )

            raise

        self.message.success("Release staging completed successfully.")

    # ------------------------------------------------------------------
    # Implementation
    # ------------------------------------------------------------------

    def _execute(
        self,
    ) -> None:
        """
        Stage release artifacts into the destination.
        """

        release_path = self.arguments.path(
            "release_path",
            required=True,
        )

        destination_path = self.arguments.path(
            "destination_path",
            required=True,
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

        assert release_path is not None
        assert destination_path is not None
        assert backup is not None
        assert rotate_backup_type is not None
        assert max_files is not None
        assert max_timestamp is not None
        assert max_timestamp_unit is not None

        rotate_backup_type = rotate_backup_type.lower()

        max_timestamp_unit = max_timestamp_unit.lower()

        self._validate_backup_configuration(
            backup=backup,
            rotate_backup_type=rotate_backup_type,
            max_timestamp_unit=max_timestamp_unit,
        )

        self.outputs["release_path"] = str(
            release_path,
        )

        self.outputs["destination_path"] = str(
            destination_path,
        )

        self.outputs["backup_enabled"] = backup

        self.outputs["rotate_backup_type"] = rotate_backup_type

        #
        # Create destination.
        #

        with self.activity(
            "Prepare destination",
        ):

            self.filesystem.mkdir(
                destination_path,
            )

        #
        # Extract release into workflow workspace.
        #

        extracted_release = self._extract_release(
            release_path,
        )

        try:

            #
            # Discover artifacts.
            #

            artifacts = self._discover_artifacts(
                extracted_release,
            )

            if not artifacts:

                raise ValueError("No release artifacts were found " f"in '{release_path}'.")

            self.message.info(f"Discovered {len(artifacts)} " "release artifact(s).")

            #
            # Create backup if required.
            #

            backup_root: Path | None = None

            if backup:

                backup_root = self._create_backup_root(
                    destination_path,
                )

            #
            # Stage artifacts.
            #

            copied_files = self._stage_artifacts(
                artifacts=artifacts,
                extracted_release=extracted_release,
                destination_path=destination_path,
                backup_root=backup_root,
                backup_enabled=backup,
            )

            #
            # Rotate backups.
            #

            if backup and backup_root is not None:

                self._rotate_backups(
                    destination_path=destination_path,
                    rotate_backup_type=rotate_backup_type,
                    max_files=max_files,
                    max_timestamp=max_timestamp,
                    max_timestamp_unit=max_timestamp_unit,
                )

            self.outputs["files_copied"] = len(
                copied_files,
            )

            self.outputs["copied_files"] = [str(path) for path in copied_files]

            if backup_root is not None:

                self.outputs["backup_path"] = str(
                    backup_root,
                )

            self.artifacts["staged_release"] = destination_path

            if backup_root is not None:

                self.artifacts["backup"] = backup_root

            self.message.success(
                f"Copied {len(copied_files)} " "release artifact(s) into " f"{destination_path}"
            )

        finally:

            #
            # Temporary extraction must never remain
            # after processing.
            #

            self._remove_extracted_release(
                extracted_release,
            )

    # ------------------------------------------------------------------
    # Path validation
    # ------------------------------------------------------------------

    def _resolve_release(
        self,
        release: Path,
    ) -> Path:
        """
        Resolve and validate the release ZIP.
        """

        release = release.resolve()

        if not self.filesystem.exists(
            release,
        ):

            raise FileNotFoundError("Release archive not found: " f"{release}")

        if not self.filesystem.is_file(
            release,
        ):

            raise ValueError("Release path is not a file: " f"{release}")

        if release.suffix.lower() != ".zip":

            raise ValueError("Release path must point to " f"a ZIP archive: {release}")

        return release

    def _resolve_destination(
        self,
        destination: Path,
    ) -> Path:
        """
        Resolve the destination directory.
        """

        return destination.resolve()

    # ------------------------------------------------------------------
    # Backup configuration
    # ------------------------------------------------------------------

    def _validate_backup_configuration(
        self,
        *,
        backup: bool,
        rotate_backup_type: str,
        max_timestamp_unit: str,
    ) -> None:
        """
        Validate backup-related configuration.
        """

        if not backup:

            return

        if rotate_backup_type not in {
            self.ROTATE_MAX_FILES,
            self.ROTATE_MAX_TIMESTAMP,
        }:

            raise ValueError(
                "Invalid rotate_backup_type: "
                f"{rotate_backup_type}. "
                "Expected 'max_files' or "
                "'max_timestamp'."
            )

        if max_timestamp_unit not in {
            self.TIMESTAMP_HOURS,
            self.TIMESTAMP_DAYS,
        }:

            raise ValueError(
                "Invalid max_timestamp_unit: "
                f"{max_timestamp_unit}. "
                "Expected 'hours' or 'days'."
            )

    # ------------------------------------------------------------------
    # Release extraction
    # ------------------------------------------------------------------

    def _extract_release(
        self,
        release_path: Path,
    ) -> Path:
        """
        Extract the release into the workflow workspace.
        """

        staging_root = self.workspace / "stage_release_copy"

        if self.filesystem.exists(
            staging_root,
        ):

            with self.activity(
                "Remove previous staging area",
            ):

                self.filesystem.remove(
                    staging_root,
                )

        with self.activity(
            "Extract release",
        ):

            extracted = self.archive.extract(
                release_path,
                staging_root,
            )

        if not self.filesystem.exists(
            extracted,
        ):

            raise RuntimeError("Release extraction failed: " f"{extracted}")

        if not self.filesystem.is_directory(
            extracted,
        ):

            raise RuntimeError("Release extraction did not " "produce a directory: " f"{extracted}")

        extracted = extracted.resolve()

        self.message.info(f"Release extracted to: {extracted}")

        return extracted

    def _remove_extracted_release(
        self,
        extracted_release: Path,
    ) -> None:
        """
        Remove temporary extracted release.
        """

        if not self.filesystem.exists(
            extracted_release,
        ):

            return

        with self.activity(
            "Cleanup extracted release",
        ):

            self.filesystem.remove(
                extracted_release,
            )

    # ------------------------------------------------------------------
    # Artifact discovery
    # ------------------------------------------------------------------

    def _discover_artifacts(
        self,
        extracted_release: Path,
    ) -> list[Path]:
        """
        Discover application artifacts only.

        Release structure:

            App/
                app-1/
                    image/
                        ...
                app-2/
                    image/
                        ...

        Destination structure:

            destination/
                app-1/
                    image/
                        ...
                app-2/
                    image/
                        ...

        The top-level App directory is stripped.

        DBScripts and all SQL artifacts are ignored.
        """

        app_root = extracted_release / "App"

        if not self.filesystem.exists(
            app_root,
        ):
            raise FileNotFoundError(
                "Release does not contain the " f"required App directory: {app_root}"
            )

        if not self.filesystem.is_directory(
            app_root,
        ):
            raise ValueError(f"Release App path is not a directory: " f"{app_root}")

        artifacts: list[Path] = []

        application_directories = self.filesystem.find(
            app_root,
            pattern="*",
            recursive=False,
        )

        for application in application_directories:

            if not self.filesystem.is_directory(
                application,
            ):
                continue

            files = self.filesystem.find(
                application,
                pattern="*",
                recursive=True,
            )

            for file in files:

                if not self.filesystem.is_file(
                    file,
                ):
                    continue

                artifacts.append(
                    file,
                )

        return sorted(
            artifacts,
            key=str,
        )

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

        self.message.info(f"Backup created at: {backup_root}")

        return backup_root

    def _backup_existing_file(
        self,
        destination: Path,
        destination_root: Path,
        backup_root: Path,
    ) -> None:
        """
        Move an existing destination file into
        the current backup directory while
        preserving its destination-relative path.
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

        self.log.info(f"Backed up existing file " f"'{destination}' to " f"'{backup_file}'")

    # ------------------------------------------------------------------
    # Stage
    # ------------------------------------------------------------------

    def _stage_artifacts(
        self,
        *,
        artifacts: list[Path],
        extracted_release: Path,
        destination_path: Path,
        backup_root: Path | None,
        backup_enabled: bool,
    ) -> list[Path]:
        """
        Copy application artifacts into the destination.

        The release-level App/ directory is stripped
        from the destination path.
        """

        app_root = extracted_release / "App"

        copied_files: list[Path] = []

        for source in artifacts:

            relative = source.relative_to(
                app_root,
            )

            destination = destination_path / relative

            destination_parent = destination.parent

            with self.activity(
                f"Copy {relative}",
            ):

                self.filesystem.mkdir(
                    destination_parent,
                )

                if self.filesystem.exists(
                    destination,
                ):

                    if not backup_enabled:

                        raise FileExistsError(
                            "Destination file already "
                            "exists and backup is disabled: "
                            f"{destination}"
                        )

                    if backup_root is None:

                        raise RuntimeError("Backup root is unavailable " "while backup is enabled.")

                    self._backup_existing_file(
                        destination=destination,
                        destination_root=destination_path,
                        backup_root=backup_root,
                    )

                self.filesystem.copy(
                    source,
                    destination,
                )

            copied_files.append(
                destination,
            )

        return copied_files

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
    ) -> None:
        """
        Rotate completed backup directories.
        """

        backup_directory = destination_path / self.BACKUP_DIRECTORY

        if not self.filesystem.exists(
            backup_directory,
        ):

            return

        if not self.filesystem.is_directory(
            backup_directory,
        ):

            raise ValueError("Backup path is not a directory: " f"{backup_directory}")

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

        if rotate_backup_type == (self.ROTATE_MAX_FILES):

            self._rotate_max_files(
                backups,
                max_files,
            )

            return

        self._rotate_max_timestamp(
            backups,
            max_timestamp,
            max_timestamp_unit,
        )

    def _rotate_max_files(
        self,
        backups: list[Path],
        max_files: int,
    ) -> None:
        """
        Keep only the newest configured number
        of backup directories.
        """

        stale = backups[max_files:]

        for backup in stale:

            with self.activity(
                f"Remove old backup {backup.name}",
            ):

                self.filesystem.remove(
                    backup,
                )

            self.log.info(f"Removed rotated backup: " f"{backup}")

    def _rotate_max_timestamp(
        self,
        backups: list[Path],
        max_timestamp: int,
        max_timestamp_unit: str,
    ) -> None:
        """
        Remove backups older than the configured
        age.
        """

        now = datetime.now()

        if max_timestamp_unit == (self.TIMESTAMP_HOURS):

            cutoff = now - timedelta(
                hours=max_timestamp,
            )

        else:

            cutoff = now - timedelta(
                days=max_timestamp,
            )

        for backup in backups:

            created_at = self._backup_timestamp(
                backup,
            )

            if created_at is None:

                self.message.warning(
                    "Unable to determine timestamp " "for backup; retaining: " f"{backup}"
                )

                continue

            if created_at >= cutoff:

                continue

            with self.activity(
                f"Remove expired backup " f"{backup.name}",
            ):

                self.filesystem.remove(
                    backup,
                )

            self.log.info(f"Removed expired backup: " f"{backup}")

    @staticmethod
    def _backup_timestamp(
        backup: Path,
    ) -> datetime | None:
        """
        Parse a backup directory timestamp.

        Backup format:

            YYYYMMDD_HHMMSS_microseconds
        """

        try:

            return datetime.strptime(
                backup.name,
                "%Y%m%d_%H%M%S_%f",
            )

        except ValueError:

            return None
