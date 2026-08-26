"""
Cache refresh argument resolver.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from .exceptions import CacheRefreshPluginException
from .model import (
    CacheConfig,
    CacheEnvironment,
    CacheRefreshConfig,
    StartupConfig,
)


class CacheRefreshResolver:
    """
    Resolve and validate cache refresh arguments.
    """

    DEFAULT_MODE = "force"
    DEFAULT_STOP_ALL = True
    DEFAULT_PARALLEL = False
    DEFAULT_TIMEOUT = 300
    DEFAULT_POLL_INTERVAL = 5

    ALLOWED_MODES = {
        "graceful",
        "force",
    }

    ENVIRONMENT_NAME_PATTERN = re.compile(
        r"^[A-Za-z_][A-Za-z0-9_]*$",
    )

    def resolve(
        self,
        arguments: Any,
    ) -> CacheRefreshConfig:
        """
        Resolve plugin arguments into a validated configuration.
        """

        kubeconfig = self._kubeconfig(
            arguments,
        )

        namespace = self._required_string(
            arguments,
            "namespace",
        )

        rebuild = self._boolean(
            arguments,
            "rebuild",
            False,
        )

        stop_all = self._boolean(
            arguments,
            "stop_all_before_cache_rebuild",
            self.DEFAULT_STOP_ALL,
        )

        mode = self._mode(
            arguments,
        )

        services = self._services(
            arguments,
        )

        startup = self._startup(
            arguments,
        )

        parallel = self._boolean(
            arguments,
            "parallel",
            self.DEFAULT_PARALLEL,
        )

        cache = None

        if rebuild:
            cache = self._cache(
                arguments,
                services,
            )

        return CacheRefreshConfig(
            kubeconfig=kubeconfig,
            namespace=namespace,
            rebuild=rebuild,
            stop_all_before_cache_rebuild=stop_all,
            mode=mode,
            services=services,
            cache=cache,
            startup=startup,
            parallel=parallel,
        )

    # ------------------------------------------------------------------
    # Basic values
    # ------------------------------------------------------------------

    @staticmethod
    def _kubeconfig(
        arguments: Any,
    ) -> Path:
        """
        Resolve kubeconfig.
        """

        try:
            return arguments.path(
                "kubeconfig",
                required=True,
            )
        except (TypeError, ValueError) as exc:
            raise CacheRefreshPluginException(
                "'kubeconfig' is required and must be a valid path.",
            ) from exc

    @staticmethod
    def _required_string(
        arguments: Any,
        name: str,
    ) -> str:
        """
        Resolve a required non-empty string.
        """

        try:
            value = arguments.string(
                name,
                required=True,
            )
        except (TypeError, ValueError) as exc:
            raise CacheRefreshPluginException(
                f"Argument '{name}' is required and must be a string.",
            ) from exc

        value = value.strip()

        if not value:
            raise CacheRefreshPluginException(
                f"Argument '{name}' must not be empty.",
            )

        return value

    @staticmethod
    def _boolean(
        arguments: Any,
        name: str,
        default: bool,
    ) -> bool:
        """
        Resolve a strict boolean argument.
        """

        value = arguments.get(
            name,
            default,
        )

        if not isinstance(value, bool):
            raise CacheRefreshPluginException(
                f"Argument '{name}' must be a boolean.",
            )

        return value

    # ------------------------------------------------------------------
    # Mode
    # ------------------------------------------------------------------

    def _mode(
        self,
        arguments: Any,
    ) -> str:
        """
        Resolve restart mode.
        """

        value = arguments.get(
            "mode",
            self.DEFAULT_MODE,
        )

        if not isinstance(value, str):
            raise CacheRefreshPluginException(
                "Argument 'mode' must be a string.",
            )

        mode = value.strip().casefold()

        if mode not in self.ALLOWED_MODES:
            allowed = ", ".join(
                sorted(self.ALLOWED_MODES),
            )

            raise CacheRefreshPluginException(
                f"Unsupported mode '{value}'. "
                f"Allowed values: {allowed}.",
            )

        return mode

    # ------------------------------------------------------------------
    # Services
    # ------------------------------------------------------------------

    @staticmethod
    def _services(
        arguments: Any,
    ) -> tuple[str, ...]:
        """
        Resolve and validate deployment services.
        """

        value = arguments.get(
            "services",
        )

        if not isinstance(value, list):
            raise CacheRefreshPluginException(
                "Argument 'services' must be a list.",
            )

        if not value:
            raise CacheRefreshPluginException(
                "Argument 'services' must not be empty.",
            )

        services: list[str] = []

        for service in value:

            if not isinstance(service, str):
                raise CacheRefreshPluginException(
                    "All values in 'services' must be strings.",
                )

            service = service.strip()

            if not service:
                raise CacheRefreshPluginException(
                    "Values in 'services' must not be empty.",
                )

            services.append(
                service,
            )

        if len(services) != len(set(services)):
            raise CacheRefreshPluginException(
                "Argument 'services' must not contain duplicates.",
            )

        return tuple(services)

    # ------------------------------------------------------------------
    # Cache
    # ------------------------------------------------------------------

    def _cache(
        self,
        arguments: Any,
        services: tuple[str, ...],
    ) -> CacheConfig:
        """
        Resolve cache rebuild configuration.
        """

        value = arguments.get(
            "cache",
        )

        if not isinstance(value, dict):
            raise CacheRefreshPluginException(
                "Argument 'cache' must be an object "
                "when 'rebuild' is true.",
            )

        deployment = value.get(
            "deployment",
        )

        if not isinstance(deployment, str):
            raise CacheRefreshPluginException(
                "'cache.deployment' must be a string.",
            )

        deployment = deployment.strip()

        if not deployment:
            raise CacheRefreshPluginException(
                "'cache.deployment' must not be empty.",
            )

        if deployment not in services:
            raise CacheRefreshPluginException(
                f"Cache deployment '{deployment}' "
                "is not present in 'services'.",
            )

        environment = value.get(
            "environment",
        )

        if not isinstance(environment, dict):
            raise CacheRefreshPluginException(
                "'cache.environment' must be an object.",
            )

        name = environment.get(
            "name",
        )

        if not isinstance(name, str):
            raise CacheRefreshPluginException(
                "'cache.environment.name' must be a string.",
            )

        name = name.strip()

        if not name:
            raise CacheRefreshPluginException(
                "'cache.environment.name' must not be empty.",
            )

        if not self.ENVIRONMENT_NAME_PATTERN.fullmatch(name):
            raise CacheRefreshPluginException(
                f"Invalid environment variable name '{name}'.",
            )

        env_value = environment.get(
            "value",
        )

        if not isinstance(env_value, str):
            raise CacheRefreshPluginException(
                "'cache.environment.value' must be a string.",
            )

        return CacheConfig(
            deployment=deployment,
            environment=CacheEnvironment(
                name=name,
                value=env_value,
            ),
        )

    # ------------------------------------------------------------------
    # Startup
    # ------------------------------------------------------------------

    def _startup(
        self,
        arguments: Any,
    ) -> StartupConfig:
        """
        Resolve startup verification configuration.
        """

        value = arguments.get(
            "startup",
        )

        if not isinstance(value, dict):
            raise CacheRefreshPluginException(
                "Argument 'startup' must be an object.",
            )

        messages = value.get(
            "messages",
        )

        if not isinstance(messages, list):
            raise CacheRefreshPluginException(
                "'startup.messages' must be a list.",
            )

        if not messages:
            raise CacheRefreshPluginException(
                "'startup.messages' must not be empty.",
            )

        normalized_messages: list[str] = []

        for message in messages:

            if not isinstance(message, str):
                raise CacheRefreshPluginException(
                    "All values in 'startup.messages' "
                    "must be strings.",
                )

            message = message.strip()

            if not message:
                raise CacheRefreshPluginException(
                    "Values in 'startup.messages' "
                    "must not be empty.",
                )

            normalized_messages.append(
                message,
            )

        timeout = value.get(
            "timeout",
            self.DEFAULT_TIMEOUT,
        )

        if (
            not isinstance(timeout, int)
            or isinstance(timeout, bool)
            or timeout <= 0
        ):
            raise CacheRefreshPluginException(
                "'startup.timeout' must be a positive integer.",
            )

        poll_interval = value.get(
            "poll_interval",
            self.DEFAULT_POLL_INTERVAL,
        )

        if (
            not isinstance(poll_interval, int)
            or isinstance(poll_interval, bool)
            or poll_interval <= 0
        ):
            raise CacheRefreshPluginException(
                "'startup.poll_interval' "
                "must be a positive integer.",
            )

        if poll_interval > timeout:
            raise CacheRefreshPluginException(
                "'startup.poll_interval' cannot be greater "
                "than 'startup.timeout'.",
            )

        return StartupConfig(
            messages=tuple(
                dict.fromkeys(
                    normalized_messages,
                ),
            ),
            timeout=timeout,
            poll_interval=poll_interval,
        )
