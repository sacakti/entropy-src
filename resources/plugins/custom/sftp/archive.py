"""
SFTP archive utilities.
"""

from __future__ import annotations

from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile
from uuid import uuid4

from .exceptions import SftpPluginException


class SftpArchiveBuilder:
    """
    Create ZIP archives for SFTP transfers.
    """

    def create(
        self,
        *,
        source: Path,
        workspace: Path,
        filename_policy: str | None = None,
    ) -> Path:
        """
        Create a ZIP archive from a local source.

        Directories are archived by contents so that the archive does
        not contain the source directory as an additional top-level
        component.
        """

        self._validate_source(source)

        if filename_policy is not None:
            self._validate_filename_policy(
                filename_policy,
            )

        workspace.mkdir(
            parents=True,
            exist_ok=True,
        )

        filename = (
            f"{filename_policy}.zip"
            if filename_policy
            else f"{uuid4()}.zip"
        )

        archive = workspace / filename

        if archive.exists():
            raise SftpPluginException(
                f"Archive already exists: {archive}",
            )

        if source.is_dir():
            self._archive_directory(
                source=source,
                archive=archive,
            )
        else:
            self._archive_file(
                source=source,
                archive=archive,
            )

        return archive

    # ------------------------------------------------------------------
    # Archive implementation
    # ------------------------------------------------------------------

    @staticmethod
    def _archive_directory(
        *,
        source: Path,
        archive: Path,
    ) -> None:
        """
        Archive directory contents recursively.
        """

        try:
            with ZipFile(
                archive,
                mode="w",
                compression=ZIP_DEFLATED,
            ) as zip_file:
                for path in sorted(
                    source.rglob("*"),
                ):
                    if path.is_symlink():
                        continue

                    relative = path.relative_to(
                        source,
                    )

                    if path.is_file():
                        zip_file.write(
                            path,
                            arcname=relative,
                        )
                    elif path.is_dir():
                        # Preserve empty directories.
                        if not any(path.iterdir()):
                            zip_file.writestr(
                                f"{relative.as_posix()}/",
                                "",
                            )

        except OSError as exc:
            archive.unlink(
                missing_ok=True,
            )

            raise SftpPluginException(
                f"Unable to create archive "
                f"'{archive}': {exc}",
            ) from exc

    @staticmethod
    def _archive_file(
        *,
        source: Path,
        archive: Path,
    ) -> None:
        """
        Archive a single file.
        """

        try:
            with ZipFile(
                archive,
                mode="w",
                compression=ZIP_DEFLATED,
            ) as zip_file:
                zip_file.write(
                    source,
                    arcname=source.name,
                )

        except OSError as exc:
            archive.unlink(
                missing_ok=True,
            )

            raise SftpPluginException(
                f"Unable to create archive "
                f"'{archive}': {exc}",
            ) from exc

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    @staticmethod
    def _validate_source(
        source: Path,
    ) -> None:
        """
        Validate the local archive source.
        """

        if not source.exists():
            raise SftpPluginException(
                f"Archive source does not exist: {source}",
            )

        if not source.is_file() and not source.is_dir():
            raise SftpPluginException(
                f"Archive source is not a file or directory: "
                f"{source}",
            )

    @staticmethod
    def _validate_filename_policy(
        filename_policy: str,
    ) -> None:
        """
        Validate the resolved archive filename.
        """

        if not filename_policy.strip():
            raise SftpPluginException(
                "Archive filename policy must not be empty.",
            )

        policy_path = Path(
            filename_policy,
        )

        if (
            policy_path.name != filename_policy
            or filename_policy in {".", ".."}
        ):
            raise SftpPluginException(
                "Archive filename policy must contain "
                "a filename only.",
            )

        if "/" in filename_policy or "\\" in filename_policy:
            raise SftpPluginException(
                "Archive filename policy must not contain "
                "path separators.",
            )
