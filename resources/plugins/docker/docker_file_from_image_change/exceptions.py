"""
docker_file_from_image_change plugin exceptions.
"""

from __future__ import annotations

from lib.plugins.exceptions import PluginException


class DockerFileFromImageChangePluginException(
    PluginException,
):
    """
    Base exception for the docker_file_from_image_change plugin.
    """
