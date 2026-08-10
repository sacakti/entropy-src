"""
Upgrade exceptions.
"""

from __future__ import annotations

from core.exceptions import EntropyException


class UpgradeError(EntropyException):
    """
    Base exception for upgrade failures.
    """


class InvalidUpgradePackageError(UpgradeError):
    """
    Raised when an upgrade package is invalid.
    """


class UpgradePackageFormatError(InvalidUpgradePackageError):
    """
    Raised when the package format is unsupported.
    """


class UpgradeManifestError(InvalidUpgradePackageError):
    """
    Raised when the package manifest is invalid.
    """


class UpgradeVersionError(UpgradeError):
    """
    Raised when the requested upgrade version is invalid.
    """


class UpgradeNotRequiredError(UpgradeVersionError):
    """
    Raised when the package version is already installed.
    """


class DowngradeNotAllowedError(UpgradeVersionError):
    """
    Raised when the package version is older than the installed version.
    """
