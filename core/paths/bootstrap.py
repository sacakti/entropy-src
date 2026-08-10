"""
Bootstrap path manager.

Provides all filesystem paths required before the application
configuration has been loaded.
"""

from pathlib import Path

from core.models.paths import (
    ApplicationPaths,
    ConfigurationPaths,
    ResourcePaths,
    VendorPaths,
)


class BootstrapPathManager:
    """
    Bootstrap path manager.

    Responsible for immutable application paths required during
    application startup.
    """

    def __init__(
        self,
        project_root: Path,
        entropy_home: Path,
    ):

        self._project_root = project_root
        self._entropy_home = entropy_home

        self._application = self._build_application_paths()
        self._configuration = self._build_configuration_paths()
        self._resources = self._build_resource_paths()
        self._vendor = self._build_vendor_paths()

    # ------------------------------------------------------------------
    # Public Properties
    # ------------------------------------------------------------------
    @property
    def application(self) -> ApplicationPaths:
        return self._application

    @property
    def home(self) -> Path:
        return self._entropy_home

    @property
    def project_root(self) -> Path:
        return self._project_root

    @property
    def configuration(self) -> ConfigurationPaths:
        return self._configuration

    @property
    def resources(self) -> ResourcePaths:
        return self._resources

    @property
    def vendor(self) -> VendorPaths:
        return self._vendor

    @property
    def worker(self) -> Path:
        return (
            self._project_root
            / "lib"
            / "workflow"
            / "worker.py"
        )

    # ------------------------------------------------------------------
    # Builders
    # ------------------------------------------------------------------
    def _build_application_paths(
        self,
    ) -> ApplicationPaths:

        root = Path.home() / ".local" / "share" / "entropy"

        directory = root / "application"

        return ApplicationPaths(
            root=root,
            directory=directory,
            executable=directory / "entropy.py",
            staging=root / "staging",
            versions=root / "versions",
            transaction=root / "transaction.json",
        )

    def _build_configuration_paths(self) -> ConfigurationPaths:

        config_directory = self._entropy_home / "config"

        return ConfigurationPaths(
            directory=config_directory,
            file=config_directory / "entropy.json",
            default=self._project_root / "lib" / "install" / "entropy.json.config",
        )

    def _build_resource_paths(self) -> ResourcePaths:

        resource_root = self._project_root / "resources"

        return ResourcePaths(
            root=resource_root,
            templates=resource_root / "templates",
            releases=resource_root / "releases",
            workflows=resource_root / "workflows",
            plugins=resource_root / "plugins",
            reports=resource_root / "reports",
        )

    def _build_vendor_paths(self) -> VendorPaths:

        vendor_root = self._project_root / "resources" / "wheels"

        return VendorPaths(
            root=vendor_root,
            requirements=vendor_root / "requirements.txt",
        )
