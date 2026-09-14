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
    ReadinessConfig,
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

    KUBECONFIG_DIRECTORY = ".kube"
    KUBECONFIG_FILENAME = "config"

    ALLOWED_MODES = {
        "graceful",
        "force",
    }

    ALLOWED_READY_BY = {
        "log",
        "ready",
    }

    ENVIRONMENT_NAME_PATTERN = re.compile(
        r"^[A-Za-z_][A-Za-z0-9_]*$",
    )

    def __init__(
        self,
        *,
        session_directory: Path,
        filesystem: Any,
    ) -> None:
        self.session_directory = session_directory
        self.filesystem = filesystem

    # ==================================================================
    # Resolve
    # ==================================================================

    def resolve(
        self,
        arguments: Any,
    ) -> CacheRefreshConfig:
        """
        Resolve plugin arguments into a validated configuration.
        """

        environment = self._required_string(
            arguments,
            "environment",
        )

        kubeconfig = self._kubeconfig(
            environment,
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

        parallel = self._boolean(
            arguments,
            "parallel",
            self.DEFAULT_PARALLEL,
        )

        # --------------------------------------------------------------
        # Normal service readiness
        # --------------------------------------------------------------

        service_readiness = self._readiness(
            arguments,
            "service_readiness",
            require_messages=False,
        )

        # --------------------------------------------------------------
        # Cache configuration
        # --------------------------------------------------------------

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
            service_readiness=service_readiness,
            parallel=parallel,
        )

    # ==================================================================
    # Basic values
    # ==================================================================

    def _kubeconfig(
        self,
        environment: str,
    ) -> Path:
        """
        Resolve the existing environment-specific kubeconfig.
        """

        path = (
            self.session_directory
            / self.KUBECONFIG_DIRECTORY
            / environment
            / self.KUBECONFIG_FILENAME
        )

        if not self.filesystem.exists(path):

            raise CacheRefreshPluginException(
                f"No OpenShift session exists for environment "
                f"'{environment}'. Run the login operation first.",
            )

        return path

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

    # ==================================================================
    # Mode
    # ==================================================================

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

    # ==================================================================
    # Services
    # ==================================================================

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

            services.append(service)

        if len(services) != len(set(services)):

            raise CacheRefreshPluginException(
                "Argument 'services' must not contain duplicates.",
            )

        return tuple(services)

    # ==================================================================
    # Cache
    # ==================================================================

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

        readiness = self._readiness(
            value,
            "readiness",
            require_messages=True,
        )

        return CacheConfig(
            deployment=deployment,
            environment=CacheEnvironment(
                name=name,
                value=env_value,
            ),
            readiness=readiness,
        )

    # ==================================================================
    # Readiness
    # ==================================================================

    def _readiness(
        self,
        arguments: Any,
        name: str,
        *,
        require_messages: bool,
    ) -> ReadinessConfig:
        """
        Resolve readiness verification configuration.
        """

        value = arguments.get(
            name,
        )

        if not isinstance(value, dict):

            raise CacheRefreshPluginException(
                f"Argument '{name}' must be an object.",
            )

        ready_by = value.get(
            "ready_by",
            "ready",
        )

        if not isinstance(ready_by, str):

            raise CacheRefreshPluginException(
                f"'{name}.ready_by' must be a string.",
            )

        ready_by = ready_by.strip().casefold()

        if ready_by not in self.ALLOWED_READY_BY:

            allowed = ", ".join(
                sorted(self.ALLOWED_READY_BY),
            )

            raise CacheRefreshPluginException(
                f"Unsupported '{name}.ready_by' value "
                f"'{ready_by}'. Allowed values: {allowed}.",
            )

        success_messages = self._messages(
            value,
            name,
            "success_messages",
            required=(
                ready_by == "log"
                or require_messages
            ),
        )

        failure_messages = self._messages(
            value,
            name,
            "failure_messages",
            required=False,
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
                f"'{name}.timeout' must be a positive integer.",
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
                f"'{name}.poll_interval' "
                "must be a positive integer.",
            )

        if poll_interval > timeout:

            raise CacheRefreshPluginException(
                f"'{name}.poll_interval' cannot be greater "
                f"than '{name}.timeout'.",
            )

        return ReadinessConfig(
            ready_by=ready_by,
            success_messages=success_messages,
            failure_messages=failure_messages,
            timeout=timeout,
            poll_interval=poll_interval,
        )

    @staticmethod
    def _messages(
        value: dict[str, Any],
        parent: str,
        name: str,
        *,
        required: bool,
    ) -> tuple[str, ...]:
        """
        Resolve readiness messages.
        """

        messages = value.get(
            name,
            [],
        )

        if not isinstance(messages, list):

            raise CacheRefreshPluginException(
                f"'{parent}.{name}' must be a list.",
            )

        if required and not messages:

            raise CacheRefreshPluginException(
                f"'{parent}.{name}' must not be empty.",
            )

        normalized: list[str] = []

        for message in messages:

            if not isinstance(message, str):

                raise CacheRefreshPluginException(
                    f"All values in '{parent}.{name}' "
                    "must be strings.",
                )

            message = message.strip()

            if not message:

                raise CacheRefreshPluginException(
                    f"Values in '{parent}.{name}' "
                    "must not be empty.",
                )

            normalized.append(message)

        return tuple(
            dict.fromkeys(normalized),
        )
