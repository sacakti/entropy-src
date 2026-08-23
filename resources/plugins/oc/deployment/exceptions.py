"""Deployment plugin exceptions."""

from __future__ import annotations

from lib.plugins.exceptions import PluginException


class DeploymentPluginException(PluginException):
    """Base exception for the Deployment plugin."""


class DeploymentUpdateException(DeploymentPluginException):
    """Base Deployment update exception."""


class DeploymentUpdateDefinitionError(DeploymentUpdateException):
    """Invalid Deployment update definition."""


class DeploymentUpdateFileError(DeploymentUpdateException):
    """Deployment source or target file error."""


class DeploymentUpdateTargetError(DeploymentUpdateException):
    """Invalid Deployment target or operation."""
