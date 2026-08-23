"""
ConfigMap/Secret update plugin exceptions.
"""

from __future__ import annotations

from lib.plugins.exceptions import PluginException


class ConfigMapSecretUpdateException(
    PluginException,
):
    """Base ConfigMap/Secret update plugin exception."""


class UpdateDefinitionError(ConfigMapSecretUpdateException):
    """Invalid update definition."""


class DeploymentUpdateTargetError(ConfigMapSecretUpdateException):
    """Invalid target YAML."""


class UpdateOperationError(ConfigMapSecretUpdateException):
    """Invalid update operation."""


class UpdateKeyNotFoundError(UpdateOperationError):
    """Requested key does not exist."""


class UpdateKeyAlreadyExistsError(UpdateOperationError):
    """Requested key already exists."""


class UnsupportedUpdateFormatError(UpdateOperationError):
    """Unsupported embedded data format."""


class UpdateFileError(ConfigMapSecretUpdateException):
    """Unable to read or write an update file."""
