"""
Release structure definition and resolver.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class ReleaseStructure:
    """
    Normalized release structure definition.
    """

    name: str
    children: tuple[str, ...]
    definition: dict[str, Any]

    def component(
        self,
        name: str,
    ) -> dict[str, Any] | None:
        """
        Return a top-level component definition.
        """

        value = self.definition.get(
            name,
        )

        if not isinstance(
            value,
            dict,
        ):
            return None

        return value


class ReleaseStructureResolver:
    """
    Load and resolve release structure definitions.
    """

    def __init__(
        self,
        filesystem,
    ) -> None:

        self._filesystem = filesystem

    # ------------------------------------------------------------------
    # Load
    # ------------------------------------------------------------------

    def load(
        self,
        path: Path,
    ) -> ReleaseStructure:
        """
        Load a release structure YAML file.
        """

        if not self._filesystem.exists(path):
            raise ValueError(
                f"Release structure file "
                f"'{path}' does not exist.",
            )

        if not self._filesystem.is_file(path):
            raise ValueError(
                f"Release structure path "
                f"'{path}' is not a file.",
            )

        document = self._filesystem.parse_yaml(
            self._filesystem.read_text(path),
        )

        if not isinstance(document, dict):
            raise ValueError(
                "Release structure must contain "
                "a YAML mapping.",
            )

        name = document.get("name")

        if not isinstance(name, str) or not name.strip():
            raise ValueError(
                "Release structure requires a "
                "non-empty 'name'.",
            )

        structure = document.get("structure")

        if not isinstance(structure, dict):
            raise ValueError(
                "Release structure requires "
                "a 'structure' mapping.",
            )

        children = structure.get(
            "children",
            [],
        )

        if not isinstance(children, list):
            raise ValueError(
                "Release structure 'children' "
                "must be a list.",
            )

        if not all(
            isinstance(child, str) and child.strip()
            for child in children
        ):
            raise ValueError(
                "Release structure children "
                "must contain non-empty strings.",
            )

        components = {
            key: value
            for key, value in structure.items()
            if key != "children"
        }

        for child in children:

            if child not in components:
                raise ValueError(
                    f"Release structure component "
                    f"'{child}' is not defined.",
                )

        return ReleaseStructure(
            name=name,
            children=tuple(children),
            definition=components,
        )

    # ------------------------------------------------------------------
    # Definitions
    # ------------------------------------------------------------------

    @staticmethod
    def children(
        definition: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Return child definitions.
        """

        children = definition.get(
            "children",
            {},
        )

        if not isinstance(children, dict):
            return {}

        return children

    def child(
        self,
        definition: dict[str, Any],
        name: str,
    ) -> dict[str, Any] | None:
        """
        Return a named child definition.
        """

        value = self.children(
            definition,
        ).get(name)

        if not isinstance(value, dict):
            return None

        return value

    # ------------------------------------------------------------------
    # Path resolution
    # ------------------------------------------------------------------

    def path(
        self,
        root: Path,
        definition: dict[str, Any],
    ) -> Path | None:
        """
        Resolve a definition path relative to root.
        """

        value = definition.get(
            "path",
        )

        if value is None:
            return root

        if not isinstance(
            value,
            str,
        ) or not value.strip():

            raise ValueError(
                "Structure component 'path' "
                "must be a non-empty string.",
            )

        return self._find_path(
            root,
            value,
        )

    def child_path(
        self,
        root: Path,
        definition: dict[str, Any],
        name: str,
    ) -> Path | None:
        """
        Resolve a named child relative to a definition.
        """

        child = self.child(
            definition,
            name,
        )

        if child is None:
            return None

        parent = self.path(
            root,
            definition,
        )

        if parent is None:
            return None

        return self.path(
            parent,
            child,
        )

    def resolve(
        self,
        root: Path,
        definition: dict[str, Any],
        *names: str,
    ) -> Path | None:
        """
        Resolve nested child definitions.

        Example:

            resolve(
                root,
                openshift_definition,
                "yamls",
            )
        """

        current_root = self.path(
            root,
            definition,
        )

        if current_root is None:
            return None

        current_definition = definition

        for name in names:

            child = self.child(
                current_definition,
                name,
            )

            if child is None:
                return None

            current_root = self.path(
                current_root,
                child,
            )

            if current_root is None:
                return None

            current_definition = child

        return current_root

    # ------------------------------------------------------------------
    # Filesystem
    # ------------------------------------------------------------------

    def _find_path(
        self,
        root: Path,
        relative: str,
    ) -> Path | None:
        """
        Resolve a relative path case-insensitively.
        """

        current = root

        for part in Path(relative).parts:

            if part in (
                ".",
                "",
            ):
                continue

            if part == "..":
                current = current.parent
                continue

            if not self._filesystem.exists(
                current,
            ):
                return None

            found = None

            for child in self._filesystem.listdir(
                current,
            ):

                if child.name.casefold() == part.casefold():
                    found = child
                    break

            if found is None:
                return None

            current = found

        return current
