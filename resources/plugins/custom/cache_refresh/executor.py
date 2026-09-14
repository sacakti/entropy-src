"""
Cache refresh execution engine.
"""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

from lib.models.plugin import PluginResult

from .exceptions import CacheRefreshPluginException
from .model import (
    CacheRefreshConfig,
    ReadinessConfig,
)


class CacheRefreshExecutor:
    """
    Execute OpenShift cache refresh and service lifecycle operations.
    """

    def __init__(
        self,
        *,
        shell: Any,
        message: Any,
        log: Any,
        result_factory: Any,
    ) -> None:

        self.shell = shell
        self.message = message
        self.log = log
        self.result_factory = result_factory

    # ==================================================================
    # Main execution
    # ==================================================================

    def execute(
        self,
        config: CacheRefreshConfig,
    ) -> PluginResult:
        """
        Execute the configured workflow.
        """

        if config.rebuild:

            return self._execute_cache_refresh(
                config,
            )

        return self._execute_restart(
            config,
        )

    # ==================================================================
    # Normal restart
    # ==================================================================

    def _execute_restart(
        self,
        config: CacheRefreshConfig,
    ) -> PluginResult:
        """
        Restart all configured services.
        """

        self.message.info(
            "Starting service restart.",
        )

        self._restart_services(
            config,
            list(config.services),
            config.service_readiness,
        )

        return self.result_factory(
            success=True,
            changed=True,
        )

    # ==================================================================
    # Cache rebuild
    # ==================================================================

    def _execute_cache_refresh(
        self,
        config: CacheRefreshConfig,
    ) -> PluginResult:
        """
        Execute the cache rebuild workflow.
        """

        if config.cache is None:

            raise CacheRefreshPluginException(
                "Cache configuration is required when "
                "'rebuild' is true.",
            )

        cache_deployment = config.cache.deployment

        remaining_services = [
            service
            for service in config.services
            if service != cache_deployment
        ]

        # --------------------------------------------------------------
        # 1. Stop all services
        # --------------------------------------------------------------

        self.message.info(
            "Stopping all services before cache refresh.",
        )

        self._stop_services(
            config,
            list(config.services),
        )

        # --------------------------------------------------------------
        # 2. Set cache refresh environment
        # --------------------------------------------------------------

        self.message.info(
            f"Setting cache refresh environment on "
            f"'{cache_deployment}'.",
        )

        self._set_cache_environment(
            config,
        )

        # --------------------------------------------------------------
        # 3. Start cache
        # --------------------------------------------------------------

        self.message.info(
            f"Starting cache service '{cache_deployment}' "
            "for cache rebuild.",
        )

        self._start_services(
            config,
            [cache_deployment],
        )

        # --------------------------------------------------------------
        # 4. Wait for cache rebuild startup
        # --------------------------------------------------------------

        self.message.info(
            f"Waiting for cache service '{cache_deployment}' "
            "cache rebuild completion.",
        )

        self._wait_for_services(
            config,
            [cache_deployment],
            config.cache.readiness,
        )

        # --------------------------------------------------------------
        # 5. Remove cache refresh environment
        #
        # `oc set env ... NAME-` changes the Deployment template
        # and therefore triggers the next rollout automatically.
        # --------------------------------------------------------------

        self.message.info(
            f"Removing cache refresh environment from "
            f"'{cache_deployment}'.",
        )

        self._remove_cache_environment(
            config,
        )

        # --------------------------------------------------------------
        # 6. Wait for normal cache startup
        # --------------------------------------------------------------

        self.message.info(
            f"Waiting for cache service '{cache_deployment}' "
            "normal startup.",
        )

        self._wait_for_services(
            config,
            [cache_deployment],
            config.cache.readiness,
        )

        # --------------------------------------------------------------
        # 7. Start remaining services
        # --------------------------------------------------------------

        if remaining_services:

            self.message.info(
                "Starting remaining services: "
                + ", ".join(remaining_services),
            )

            self._start_services(
                config,
                remaining_services,
            )

            # ----------------------------------------------------------
            # 8. Wait for remaining services
            # ----------------------------------------------------------

            self._wait_for_services(
                config,
                remaining_services,
                config.service_readiness,
            )

        return self.result_factory(
            success=True,
            changed=True,
        )

    # ==================================================================
    # Service lifecycle
    # ==================================================================

    def _stop_services(
        self,
        config: CacheRefreshConfig,
        services: list[str],
    ) -> None:
        """
        Stop multiple deployments.
        """

        if not services:
            return

        self._run_services(
            config,
            services,
            self._stop_service,
        )

    def _start_services(
        self,
        config: CacheRefreshConfig,
        services: list[str],
    ) -> None:
        """
        Start multiple deployments.
        """

        if not services:
            return

        self._run_services(
            config,
            services,
            self._start_service,
        )

    def _restart_services(
        self,
        config: CacheRefreshConfig,
        services: list[str],
        readiness: ReadinessConfig,
    ) -> None:
        """
        Restart services and wait for them according to the
        configured parallel/sequential execution policy.
        """

        if not services:
            return

        if config.parallel:

            self._run_services(
                config,
                services,
                self._restart_service,
            )

            self._wait_for_services(
                config,
                services,
                readiness,
            )

            return

        for service in services:

            self._restart_service(
                config,
                service,
            )

            self._wait_for_services(
                config,
                [service],
                readiness,
            )

    def _run_services(
        self,
        config: CacheRefreshConfig,
        services: list[str],
        operation: Any,
    ) -> None:
        """
        Execute a lifecycle operation against multiple services.
        """

        if not services:
            return

        if config.parallel and len(services) > 1:

            with ThreadPoolExecutor(
                max_workers=len(services),
            ) as executor:

                futures = {
                    executor.submit(
                        operation,
                        config,
                        service,
                    ): service
                    for service in services
                }

                for future in as_completed(futures):

                    service = futures[future]

                    try:

                        future.result()

                    except Exception as exc:

                        raise CacheRefreshPluginException(
                            f"Operation failed for deployment "
                            f"'{service}': {exc}",
                        ) from exc

            return

        for service in services:

            operation(
                config,
                service,
            )

    def _stop_service(
        self,
        config: CacheRefreshConfig,
        deployment: str,
    ) -> None:
        """
        Stop one deployment.
        """

        self._scale(
            config,
            deployment,
            replicas=0,
        )

    def _start_service(
        self,
        config: CacheRefreshConfig,
        deployment: str,
    ) -> None:
        """
        Start one deployment.
        """

        self._scale(
            config,
            deployment,
            replicas=1,
        )

    def _restart_service(
        self,
        config: CacheRefreshConfig,
        deployment: str,
    ) -> None:
        """
        Restart one deployment according to the configured mode.
        """

        if config.mode == "graceful":

            self._rollout_restart(
                config,
                deployment,
            )

            return

        self._scale(
            config,
            deployment,
            replicas=0,
        )

        self._scale(
            config,
            deployment,
            replicas=1,
        )

    # ==================================================================
    # OpenShift execution
    # ==================================================================

    def _oc_result(
        self,
        command: list[str],
        *,
        config: CacheRefreshConfig,
    ) -> Any:
        """
        Execute an OpenShift command without converting a non-zero
        exit code into an exception.

        Used for polling operations where a transient failure is
        expected while a pod is starting.
        """

        full_command = [
            "oc",
            *command,
        ]

        self.log.debug(
            "Executing OpenShift command: "
            + " ".join(full_command),
        )

        try:

            return self.shell.run(
                full_command,
                env={
                    "KUBECONFIG": str(
                        config.kubeconfig,
                    ),
                },
            )

        except FileNotFoundError as exc:

            raise CacheRefreshPluginException(
                "OpenShift CLI 'oc' was not found. "
                "Please install the OpenShift CLI and ensure "
                "it is available in PATH.",
            ) from exc

        except OSError as exc:

            raise CacheRefreshPluginException(
                f"Unable to execute OpenShift CLI: {exc}",
            ) from exc

    def _oc(
        self,
        command: list[str],
        *,
        config: CacheRefreshConfig,
    ) -> Any:
        """
        Execute an OpenShift command and fail on command errors.
        """

        result = self._oc_result(
            command,
            config=config,
        )

        if result.failed:

            stderr = result.stderr.strip()

            raise CacheRefreshPluginException(
                stderr
                or (
                    "OpenShift command failed: "
                    + " ".join(
                        [
                            "oc",
                            *command,
                        ],
                    )
                ),
            )

        return result

    # ==================================================================
    # OpenShift lifecycle operations
    # ==================================================================

    def _scale(
        self,
        config: CacheRefreshConfig,
        deployment: str,
        *,
        replicas: int,
    ) -> None:
        """
        Scale a deployment.
        """

        self._oc(
            [
                "scale",
                f"deployment/{deployment}",
                f"--replicas={replicas}",
                "-n",
                config.namespace,
            ],
            config=config,
        )

    def _rollout_restart(
        self,
        config: CacheRefreshConfig,
        deployment: str,
    ) -> None:
        """
        Restart a deployment using OpenShift rollout restart.
        """

        self._oc(
            [
                "rollout",
                "restart",
                f"deployment/{deployment}",
                "-n",
                config.namespace,
            ],
            config=config,
        )

    # ==================================================================
    # Cache environment
    # ==================================================================

    def _set_cache_environment(
        self,
        config: CacheRefreshConfig,
    ) -> None:
        """
        Set the temporary cache refresh environment variable.
        """

        if config.cache is None:

            raise CacheRefreshPluginException(
                "Cache configuration is required.",
            )

        environment = config.cache.environment

        self._oc(
            [
                "set",
                "env",
                f"deployment/{config.cache.deployment}",
                f"{environment.name}={environment.value}",
                "-n",
                config.namespace,
            ],
            config=config,
        )

    def _remove_cache_environment(
        self,
        config: CacheRefreshConfig,
    ) -> None:
        """
        Remove the temporary cache refresh environment variable.
        """

        if config.cache is None:

            raise CacheRefreshPluginException(
                "Cache configuration is required.",
            )

        environment = config.cache.environment

        self._oc(
            [
                "set",
                "env",
                f"deployment/{config.cache.deployment}",
                f"{environment.name}-",
                "-n",
                config.namespace,
            ],
            config=config,
        )

    # ==================================================================
    # Readiness
    # ==================================================================

    def _wait_for_services(
        self,
        config: CacheRefreshConfig,
        services: list[str],
        readiness: ReadinessConfig,
    ) -> None:
        """
        Wait for all services to satisfy their readiness criteria.
        """

        if not services:
            return

        if config.parallel and len(services) > 1:

            with ThreadPoolExecutor(
                max_workers=len(services),
            ) as executor:

                futures = {
                    executor.submit(
                        self._wait_for_service,
                        config,
                        service,
                        readiness,
                    ): service
                    for service in services
                }

                for future in as_completed(futures):

                    service = futures[future]

                    try:

                        future.result()

                    except Exception as exc:

                        if isinstance(
                            exc,
                            CacheRefreshPluginException,
                        ):
                            raise

                        raise CacheRefreshPluginException(
                            f"Readiness verification failed for "
                            f"deployment '{service}': {exc}",
                        ) from exc

            return

        for service in services:

            self._wait_for_service(
                config,
                service,
                readiness,
            )

    def _wait_for_service(
        self,
        config: CacheRefreshConfig,
        deployment: str,
        readiness: ReadinessConfig,
    ) -> None:
        """
        Wait until one service satisfies its readiness criteria.
        """

        self.message.info(
            f"Waiting for deployment '{deployment}' "
            f"using ready_by='{readiness.ready_by}'.",
        )

        deadline = (
            time.monotonic()
            + readiness.timeout
        )

        while True:

            if readiness.ready_by == "ready":

                if self._is_pod_ready(
                    config,
                    deployment,
                ):
                    self.message.info(
                        f"Deployment '{deployment}' is ready.",
                    )
                    return

            elif readiness.ready_by == "log":

                if self._is_startup_log_ready(
                    config,
                    deployment,
                    readiness,
                ):
                    self.message.info(
                        f"Deployment '{deployment}' startup "
                        "message detected.",
                    )
                    return

            else:

                raise CacheRefreshPluginException(
                    f"Unsupported readiness method "
                    f"'{readiness.ready_by}'.",
                )

            if time.monotonic() >= deadline:

                raise CacheRefreshPluginException(
                    f"Deployment '{deployment}' did not become "
                    f"ready within {readiness.timeout} seconds.",
                )

            time.sleep(
                readiness.poll_interval,
            )

    # ==================================================================
    # Pod readiness
    # ==================================================================

    def _is_pod_ready(
        self,
        config: CacheRefreshConfig,
        deployment: str,
    ) -> bool:
        """
        Check whether the current pod for a deployment has
        all containers ready.
        """

        selector = self._deployment_selector(
            config,
            deployment,
        )

        if not selector:

            self.log.debug(
                f"No deployment selector found for "
                f"'{deployment}'.",
            )

            return False

        result = self._oc_result(
            [
                "get",
                "pods",
                "-l",
                selector,
                "-n",
                config.namespace,
                "-o",
                "json",
            ],
            config=config,
        )

        if result.failed:

            self.log.debug(
                f"Unable to inspect pods for '{deployment}': "
                f"{result.stderr.strip()}",
            )

            return False

        try:

            data = self._parse_json(
                result.stdout,
            )

        except CacheRefreshPluginException:

            return False

        items = data.get(
            "items",
            [],
        )

        if not items:

            self.log.debug(
                f"No pod found yet for deployment "
                f"'{deployment}'.",
            )

            return False

        # A deployment can temporarily have multiple pods during
        # a rollout. Consider the service ready when the newest
        # active pod has all its containers ready.
        pods = sorted(
            items,
            key=lambda pod: (
                pod.get(
                    "metadata",
                    {},
                ).get(
                    "creationTimestamp",
                    "",
                ),
            ),
            reverse=True,
        )

        pod = pods[0]

        status = pod.get(
            "status",
            {},
        )

        phase = status.get(
            "phase",
        )

        if phase in {
            "Failed",
            "Unknown",
        }:

            return False

        container_statuses = status.get(
            "containerStatuses",
            [],
        )

        if not container_statuses:

            return False

        ready_count = sum(
            1
            for container in container_statuses
            if container.get(
                "ready",
                False,
            )
        )

        total_count = len(
            container_statuses,
        )

        self.log.debug(
            f"Deployment '{deployment}' pod "
            f"'{pod.get('metadata', {}).get('name', '')}' "
            f"container readiness: "
            f"{ready_count}/{total_count}.",
        )

        return ready_count == total_count

    # ==================================================================
    # Deployment selector
    # ==================================================================

    def _deployment_selector(
        self,
        config: CacheRefreshConfig,
        deployment: str,
    ) -> str | None:
        """
        Retrieve a deployment's matchLabels selector and convert it
        to a Kubernetes label selector string.
        """

        result = self._oc_result(
            [
                "get",
                "deployment",
                deployment,
                "-n",
                config.namespace,
                "-o",
                "json",
            ],
            config=config,
        )

        if result.failed:

            self.log.debug(
                f"Unable to retrieve deployment "
                f"'{deployment}': {result.stderr.strip()}",
            )

            return None

        try:

            data = self._parse_json(
                result.stdout,
            )

        except CacheRefreshPluginException:

            return None

        match_labels = (
            data
            .get(
                "spec",
                {},
            )
            .get(
                "selector",
                {},
            )
            .get(
                "matchLabels",
                {},
            )
        )

        if not match_labels:

            return None

        return ",".join(
            f"{key}={value}"
            for key, value in match_labels.items()
        )

    # ==================================================================
    # Log readiness
    # ==================================================================

    def _is_startup_log_ready(
        self,
        config: CacheRefreshConfig,
        deployment: str,
        readiness: ReadinessConfig,
    ) -> bool:
        """
        Check application logs for startup success/failure messages.

        Transient pod states such as ContainerCreating are treated
        as "not ready yet", not as a fatal error.
        """

        selector = self._deployment_selector(
            config,
            deployment,
        )

        if not selector:

            return False

        pod = self._current_pod(
            config,
            selector,
        )

        if pod is None:

            self.log.debug(
                f"No pod available yet for deployment "
                f"'{deployment}'.",
            )

            return False

        pod_name = pod.get(
            "metadata",
            {},
        ).get(
            "name",
        )

        if not pod_name:

            return False

        status = pod.get(
            "status",
            {},
        )

        phase = status.get(
            "phase",
        )

        if phase in {
            "Pending",
            "Unknown",
        }:

            self.log.debug(
                f"Pod '{pod_name}' for deployment "
                f"'{deployment}' is in phase '{phase}'.",
            )

            return False

        if phase == "Failed":

            raise CacheRefreshPluginException(
                f"Pod '{pod_name}' for deployment "
                f"'{deployment}' entered Failed state.",
            )

        result = self._oc_result(
            [
                "logs",
                pod_name,
                "-n",
                config.namespace,
            ],
            config=config,
        )

        if result.failed:

            stderr = result.stderr.strip()

            # The container can exist but not yet be available
            # for log retrieval.
            if self._is_transient_log_error(
                stderr,
            ):

                self.log.debug(
                    f"Logs for pod '{pod_name}' are not "
                    "available yet. Retrying.",
                )

                return False

            raise CacheRefreshPluginException(
                f"Unable to retrieve logs for pod "
                f"'{pod_name}': "
                f"{stderr or 'unknown error'}",
            )

        logs = result.stdout

        for message in readiness.failure_messages:

            if message in logs:

                raise CacheRefreshPluginException(
                    f"Deployment '{deployment}' reported "
                    f"startup failure. Matched message: "
                    f"'{message}'.",
                )

        for message in readiness.success_messages:

            if message in logs:

                return True

        return False

    def _current_pod(
        self,
        config: CacheRefreshConfig,
        selector: str,
    ) -> dict[str, Any] | None:
        """
        Return the newest non-terminal pod matching a deployment selector.
        """

        result = self._oc_result(
            [
                "get",
                "pods",
                "-l",
                selector,
                "-n",
                config.namespace,
                "-o",
                "json",
            ],
            config=config,
        )

        if result.failed:

            self.log.debug(
                f"Unable to list pods: "
                f"{result.stderr.strip()}",
            )

            return None

        try:

            data = self._parse_json(
                result.stdout,
            )

        except CacheRefreshPluginException:

            return None

        items = data.get(
            "items",
            [],
        )

        if not items:

            return None

        active = [
            pod
            for pod in items
            if pod.get(
                "status",
                {},
            ).get(
                "phase",
            ) not in {
                "Succeeded",
                "Failed",
            }
        ]

        if not active:

            return None

        return max(
            active,
            key=lambda pod: (
                pod.get(
                    "metadata",
                    {},
                ).get(
                    "creationTimestamp",
                    "",
                ),
            ),
        )

    # ==================================================================
    # Helpers
    # ==================================================================

    @staticmethod
    def _parse_json(
        value: str,
    ) -> dict[str, Any]:
        """
        Parse OpenShift JSON output.
        """

        import json

        try:

            data = json.loads(value)

        except json.JSONDecodeError as exc:

            raise CacheRefreshPluginException(
                f"Invalid JSON returned by OpenShift: {exc}",
            ) from exc

        if not isinstance(data, dict):

            raise CacheRefreshPluginException(
                "Expected OpenShift JSON output to be an object.",
            )

        return data

    @staticmethod
    def _is_transient_log_error(
        message: str,
    ) -> bool:
        """
        Determine whether an oc logs error is caused by a pod/container
        that has not reached a loggable state yet.
        """

        value = message.casefold()

        transient_messages = (
            "containercreating",
            "container creating",
            "pod initializing",
            "is waiting to start",
            "waiting to start",
            "container has not started",
            "container is waiting",
            "not found",
            "unable to retrieve container logs",
            "a container name must be specified",
        )

        return any(
            item in value
            for item in transient_messages
        )
