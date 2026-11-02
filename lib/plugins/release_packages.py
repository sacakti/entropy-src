"""
Read release packages for plugins that work across several releases.

A release is a ZIP/TAR or an extracted folder. Its content is at the top of the
package, or inside the one folder the package holds (H010/..., App-Published/...).
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, List, Optional, Sequence, Tuple, Type

IGNORED = (
    "__MACOSX",
    ".DS_Store",
)

ARCHIVES = (
    ".zip",
    ".tar",
    ".tgz",
    ".gz",
)

YAML_EXTENSIONS = (
    ".yaml",
    ".yml",
)


def natural_key(text: str) -> List[Any]:
    """Sort key that orders numbers by value: H9 < H10 < H101."""

    return [
        (0, int(part)) if part.isdigit() else (1, part.casefold())
        for part in re.split(r"(\d+)", text)
        if part
    ]


def release_name(path: Path) -> str:
    """H010.zip, H010.tar.gz and the folder H010 are all 'H010'."""

    name = path.name
    for suffix in (".tar.gz", ".tgz", ".tar", ".zip"):
        if name.casefold().endswith(suffix):
            return name[: -len(suffix)]
    return name


class ReleasePackages:
    """
    Locate, open and read release packages through the plugin's executor facades.

    Problems are raised as `error`, the calling plugin's own exception.
    """

    def __init__(
        self,
        filesystem: Any,
        archive: Any,
        extraction_directory: Path,
        error: Type[Exception],
    ) -> None:

        self._filesystem = filesystem
        self._archive = archive
        self._extraction_directory = extraction_directory
        self._error = error

    # ------------------------------------------------------------------
    # Releases
    # ------------------------------------------------------------------

    def resolve(
        self,
        folder: Optional[Path],
        listed: Optional[Sequence[Any]],
    ) -> List[Path]:
        """
        The releases in the order they are applied: the given list as is,
        or the folder's packages in natural name order.
        """

        if (folder is None) == (not listed):

            raise self._error(
                "Give either 'release_directory' or 'releases' (one of them, not both).",
            )

        if listed:

            releases = [Path(str(item)).expanduser() for item in listed]

            for release in releases:

                if not self._filesystem.exists(release):

                    raise self._error(
                        f"Release not found: {release}",
                    )

            if len({release_name(path) for path in releases}) != len(releases):

                raise self._error(
                    "Two releases have the same name: " + ", ".join(map(str, releases)),
                )

            return releases

        assert folder is not None

        if not self._filesystem.is_directory(folder):

            raise self._error(
                f"Release folder not found: {folder}",
            )

        releases = [
            path
            for path in self._filesystem.listdir(folder)
            if path.name not in IGNORED
            and not path.name.startswith(".")
            and (self._filesystem.is_directory(path) or self._is_archive(path))
        ]

        if not releases:

            raise self._error(
                f"No release packages (ZIPs or folders) in {folder}.",
            )

        names = [release_name(path) for path in releases]

        duplicates = sorted({name for name in names if names.count(name) > 1})

        if duplicates:

            raise self._error(
                "Release given both as a ZIP and a folder: " + ", ".join(duplicates),
            )

        return sorted(
            releases,
            key=lambda path: natural_key(release_name(path)),
        )

    def open(
        self,
        release: Path,
    ) -> Path:
        """A release folder; archives are extracted below the extraction directory."""

        if self._filesystem.is_directory(release):

            return release

        if not self._is_archive(release):

            raise self._error(
                f"Release '{release}' is neither a folder nor an archive.",
            )

        destination = self._extraction_directory / release_name(release)

        if self._filesystem.exists(destination):

            self._filesystem.remove(
                destination,
            )

        try:

            return Path(
                self._archive.extract(
                    release,
                    destination,
                ),
            )

        except Exception as exc:  # noqa: BLE001 - reported as a release error

            raise self._error(
                f"Unable to extract release '{release}': {exc}",
            ) from exc

    def find_folder(
        self,
        root: Path,
        layouts: Sequence[Tuple[str, ...]],
        *,
        release: str,
        label: str,
    ) -> Optional[Path]:
        """
        The folder of the first matching layout: at the top of the package, or
        inside the one folder it holds. `label` names the folder in errors.
        """

        candidates = [root] + [
            path
            for path in self._filesystem.listdir(root)
            if self._filesystem.is_directory(path)
            and path.name not in IGNORED
            and not path.name.startswith(".")
        ]

        found = []

        for candidate in candidates:

            for parts in layouts:

                folder = candidate.joinpath(*parts)

                if self._filesystem.is_directory(folder):

                    found.append(folder)

                    break

        if len(found) > 1:

            raise self._error(
                f"Release '{release}' has several {label} folders: "
                + ", ".join(str(path) for path in found),
            )

        return found[0] if found else None

    def files(
        self,
        folder: Path,
        extensions: Optional[Sequence[str]] = None,
    ) -> List[Path]:
        """Files below the folder in natural path order, without packaging leftovers."""

        return sorted(
            (
                path
                for path in self._filesystem.find(folder, "*", recursive=True)
                if self._filesystem.is_file(path)
                and (extensions is None or path.suffix.casefold() in extensions)
                and not any(part in IGNORED for part in path.parts)
                and not path.name.startswith("._")
            ),
            key=lambda path: natural_key(path.relative_to(folder).as_posix()),
        )

    def yaml_documents(
        self,
        path: Path,
        where: str,
    ) -> List[Any]:
        """The non-empty YAML documents of a file; `where` names it in errors."""

        try:

            return [
                document
                for document in self._filesystem.load_yaml_documents(
                    self._filesystem.read_text(path),
                )
                if document is not None
            ]

        except Exception as exc:  # noqa: BLE001 - reported with the file

            raise self._error(
                f"{where} is not valid YAML: {exc}",
            ) from exc

    # ------------------------------------------------------------------
    # Output
    # ------------------------------------------------------------------

    def prepare_output(
        self,
        output: Optional[Path],
        overwrite: Optional[bool],
    ) -> Path:
        """An empty output folder (emptied first when `overwrite`)."""

        if output is None:

            raise self._error(
                "'output_directory' is required.",
            )

        if self._filesystem.exists(output):

            if not self._filesystem.is_directory(output):

                raise self._error(
                    f"output_directory is not a folder: {output}",
                )

            if self._filesystem.listdir(output):

                if not overwrite:

                    raise self._error(
                        f"output_directory is not empty: {output}. Set 'overwrite' to "
                        "empty it first (old files there would be applied too).",
                    )

                self._filesystem.remove(
                    output,
                )

        self._filesystem.mkdir(
            output,
        )

        return output

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _is_archive(
        self,
        path: Path,
    ) -> bool:

        return self._filesystem.is_file(path) and path.suffix.casefold() in ARCHIVES
