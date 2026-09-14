"""
Dockerfile FROM image change models.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class DockerfileMapping:
    """
    Dockerfile to target base-image mapping.
    """

    dockerfile: Path
    image: str


@dataclass(frozen=True)
class DockerFileFromImageChangeConfig:
    """
    Normalized Dockerfile FROM image change configuration.
    """

    mappings: tuple[DockerfileMapping, ...]
