"""
ConfigMap/Secret update exceptions.
"""

from core.exceptions import EntropyException


class ConfigMapSecretUpdateError(
    EntropyException,
):
    """
    Base ConfigMap/Secret update exception.
    """


class UpdateDefinitionError(
    ConfigMapSecretUpdateError,
):
    """
    Invalid update definition.
    """


class UpdateTargetError(
    ConfigMapSecretUpdateError,
):
    """
    Invalid target YAML.
    """


class UpdateOperationError(
    ConfigMapSecretUpdateError,
):
    """
    Invalid update operation.
    """


class UpdateKeyNotFoundError(
    UpdateOperationError,
):
    """
    Requested key does not exist.
    """


class UpdateKeyAlreadyExistsError(
    UpdateOperationError,
):
    """
    Requested key already exists.
    """


class UnsupportedUpdateFormatError(
    UpdateOperationError,
):
    """
    Unsupported embedded data format.
    """


class UpdateFileError(
    ConfigMapSecretUpdateError,
):
    """
    Unable to read or write an update file.
    """
