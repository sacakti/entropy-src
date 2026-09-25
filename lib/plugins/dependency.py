"""
Plugin dependency resolution.
"""

from __future__ import annotations

import ast
from pathlib import Path

from packaging.specifiers import SpecifierSet
from packaging.version import Version

from lib.database.repositories.plugin_registry import PluginRepository
from lib.models.plugin import (
    Plugin,
    PluginImportRequirement,
    PluginManifest,
    PluginRequirement,
)
from lib.plugins.exceptions import PluginDependencyError

from .manifest import ManifestReader


class PluginDependencyResolver:
    """
    Resolves and validates plugin-to-plugin dependencies.
    """

    def __init__(
        self,
        repository: PluginRepository,
        reader: ManifestReader,
    ) -> None:

        self._repository = repository
        self._reader = reader

    # ------------------------------------------------------------------
    # Public
    # ------------------------------------------------------------------

    def validate_manifest(
        self,
        manifest: PluginManifest,
    ) -> None:
        """
        Validate dependencies declared by a plugin manifest.
        """

        for requirement in manifest.required_plugins:

            dependency = self._resolve(
                requirement,
            )

            self._validate_imports(
                dependency,
                requirement,
            )

    def validate(
        self,
        plugin: Plugin,
    ) -> tuple[Plugin, ...]:
        """
        Validate dependencies of an installed plugin.

        Returns the required plugins.
        """

        manifest = self._reader.read(
            plugin.path,
        )

        dependencies: list[Plugin] = []

        for requirement in manifest.required_plugins:

            dependency = self._resolve(
                requirement,
            )

            self._validate_imports(
                dependency,
                requirement,
            )

            dependencies.append(
                dependency,
            )

        return tuple(
            dependencies,
        )

    # ------------------------------------------------------------------
    # Resolve
    # ------------------------------------------------------------------

    def _resolve(
        self,
        requirement: PluginRequirement,
    ) -> Plugin:
        """
        Resolve an installed plugin dependency.
        """

        if "." not in requirement.name:

            raise PluginDependencyError(
                f"Invalid required plugin name "
                f"'{requirement.name}'. "
                "Expected 'namespace.name'.",
            )

        namespace, name = requirement.name.split(
            ".",
            1,
        )

        if not self._repository.exists(
            namespace,
            name,
        ):

            raise PluginDependencyError(
                f"Required plugin '{requirement.name}' "
                "is not installed.",
            )

        plugin = self._repository.get_by_qualified_name(
            requirement.name,
        )

        if not plugin.enabled:

            raise PluginDependencyError(
                f"Required plugin '{requirement.name}' "
                "is disabled.",
            )

        if requirement.version is not None:

            specifier = SpecifierSet(
                requirement.version,
            )

            if Version(
                plugin.version,
            ) not in specifier:

                # raise PluginDependencyError(
                #     f"Required plugin '{requirement.name}' "
                #     f"version '{requirement.version}' "
                #     f"is not satisfied. "
                #     f"Installed version: '{plugin.version}'.",
                # )
                raise PluginDependencyError(
                    f"Required plugin '{requirement.name}' "
                    f"version '{plugin.version}' does not satisfy "
                    f"requirement '{requirement.version}'.",
                )

        return plugin

    # ------------------------------------------------------------------
    # Imports
    # ------------------------------------------------------------------

    def _validate_imports(
        self,
        plugin: Plugin,
        requirement: PluginRequirement,
    ) -> None:
        """
        Validate explicitly declared imports.
        """

        for imported in requirement.imports:

            module_file = self._module_file(
                plugin,
                imported,
            )

            if module_file is None:

                raise PluginDependencyError(
                    f"Required import '{imported.reference}' "
                    f"was not found in plugin "
                    f"'{plugin.qualified_name}'.",
                )

            self._validate_symbol(
                module_file,
                imported,
                plugin,
            )

    @staticmethod
    def _module_file(
        plugin: Plugin,
        imported: PluginImportRequirement,
    ) -> Path | None:
        """
        Resolve a module to its installed source file.
        """

        relative = Path(
            *imported.module.split(
                ".",
            ),
        )

        module_file = plugin.path / f"{relative}.py"

        if module_file.is_file():

            return module_file

        package_file = plugin.path / relative / "__init__.py"

        if package_file.is_file():

            return package_file

        return None

    @staticmethod
    def _validate_symbol(
        module_file: Path,
        imported: PluginImportRequirement,
        plugin: Plugin,
    ) -> None:
        """
        Verify that the requested symbol exists.
        """

        try:

            source = module_file.read_text(
                encoding="utf-8",
            )

            tree = ast.parse(
                source,
                filename=str(module_file),
            )

        except (OSError, SyntaxError) as exc:

            raise PluginDependencyError(
                f"Unable to inspect import "
                f"'{imported.reference}' from plugin "
                f"'{plugin.qualified_name}'.",
            ) from exc

        names: set[str] = set()

        for node in tree.body:

            if isinstance(
                node,
                (
                    ast.ClassDef,
                    ast.FunctionDef,
                    ast.AsyncFunctionDef,
                ),
            ):

                names.add(
                    node.name,
                )

            elif isinstance(
                node,
                ast.Import,
            ):

                for alias in node.names:

                    names.add(
                        alias.asname or alias.name.split(".")[0],
                    )

            elif isinstance(
                node,
                ast.ImportFrom,
            ):

                for alias in node.names:

                    names.add(
                        alias.asname or alias.name,
                    )

            elif isinstance(
                node,
                ast.Assign,
            ):

                for target in node.targets:

                    if isinstance(
                        target,
                        ast.Name,
                    ):

                        names.add(
                            target.id,
                        )

            elif isinstance(
                node,
                ast.AnnAssign,
            ):

                if isinstance(
                    node.target,
                    ast.Name,
                ):

                    names.add(
                        node.target.id,
                    )

        if imported.symbol not in names:

            raise PluginDependencyError(
                f"Import '{imported.reference}' "
                f"was not found in plugin "
                f"'{plugin.qualified_name}'.",
            )

