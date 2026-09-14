from dataclasses import dataclass
from pathlib import Path

# ------------------------------------------------------------------
# Bootstrap Models
# ------------------------------------------------------------------


@dataclass(frozen=True)
class ApplicationPaths:
    """
    Installed application filesystem paths.
    """

    root: Path
    directory: Path
    executable: Path
    staging: Path
    versions: Path
    transaction: Path


@dataclass(frozen=True)
class ConfigurationPaths:
    directory: Path
    file: Path
    default: Path


@dataclass(frozen=True)
class ResourcePaths:
    root: Path
    templates: Path
    releases: Path
    workflows: Path
    plugins: Path
    reports: Path
    structures: Path
    documentation: Path


@dataclass(frozen=True)
class VendorPaths:
    root: Path
    requirements: Path


# ------------------------------------------------------------------
# Runtime Models
# ------------------------------------------------------------------


@dataclass(frozen=True)
class DatabasePaths:
    directory: Path
    file: Path


# @dataclass(frozen=True)
# class RuntimePaths:
#     root: Path
#     pid: Path
#     state: Path
#     lock: Path
#     workspaces: Path


@dataclass(frozen=True)
class SessionPaths:
    directory: Path
    current: Path


@dataclass(frozen=True)
class PythonPaths:
    packages: Path


@dataclass(frozen=True)
class LogPaths:
    root: Path
    entropy: Path
    plugins: Path
    integrations: Path
    workflows: Path


@dataclass(frozen=True)
class PluginPaths:
    """
    Plugin filesystem paths.
    """

    directory: Path


@dataclass(frozen=True)
class WorkflowPaths:
    """
    Workflow filesystem paths.
    """

    default: str


@dataclass(frozen=True)
class GitPaths:
    """
    Git filesystem paths.
    """

    repository: Path


@dataclass(frozen=True)
class WorkspacePaths:
    """
    Workflow workspace filesystem paths.
    """

    root: Path
    workflows: Path
    executions: Path
    generated: Path


# ------------------------------------------------------------------
# Extension Models
# ------------------------------------------------------------------


@dataclass(frozen=True)
class ExtensionPaths:
    """
    Extension runtime paths.
    """

    root: Path

    wheels: Path

    site_packages: Path

    # metadata: Path

    cache: Path

    downloads: Path


@dataclass(frozen=True)
class VaultPaths:
    """
    Vault filesystem paths.
    """

    directory: Path
    key: Path
