"""
Cache refresh plugin models.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ReadinessConfig:
    """
    Service readiness verification configuration.
    """

    ready_by: str
    success_messages: tuple[str, ...]
    failure_messages: tuple[str, ...]
    timeout: int
    poll_interval: int


@dataclass(frozen=True)
class CacheEnvironment:
    """
    Temporary cache environment variable configuration.
    """

    name: str
    value: str


@dataclass(frozen=True)
class CacheConfig:
    """
    Cache rebuild configuration.
    """

    deployment: str
    environment: CacheEnvironment
    readiness: ReadinessConfig


@dataclass(frozen=True)
class CacheRefreshConfig:
    """
    Normalized cache refresh configuration.
    """

    kubeconfig: Path
    namespace: str

    rebuild: bool
    stop_all_before_cache_rebuild: bool
    mode: str

    services: tuple[str, ...]

    cache: CacheConfig | None

    service_readiness: ReadinessConfig

    parallel: bool
