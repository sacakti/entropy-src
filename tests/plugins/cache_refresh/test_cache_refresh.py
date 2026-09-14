"""
Tests for the cache_refresh execution engine.
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, call

from resources.plugins.custom.cache_refresh.executor import CacheRefreshExecutor
from resources.plugins.custom.cache_refresh.model import (
    CacheConfig,
    CacheEnvironment,
    CacheRefreshConfig,
    ReadinessConfig,
)
from resources.plugins.custom.cache_refresh.exceptions import CacheRefreshPluginException

class FakeExecutionResult:
    """
    Minimal shell execution result used by the tests.
    """

    def __init__(
        self,
        *,
        stdout: str = "",
        stderr: str = "",
        success: bool = True,
    ) -> None:

        self.stdout = stdout
        self.stderr = stderr
        self.success = success
        self.failed = not success
        self.exit_code = 0 if success else 1


class CacheRefreshExecutorTestCase(unittest.TestCase):
    """
    Base test case for CacheRefreshExecutor.
    """

    def setUp(self) -> None:

        self.shell = Mock()
        self.shell.run.return_value = FakeExecutionResult()
        self.message = Mock()
        self.log = Mock()
        self.result_factory = Mock(
            side_effect=self._result,
        )

        self.executor = CacheRefreshExecutor(
            shell=self.shell,
            message=self.message,
            log=self.log,
            result_factory=self.result_factory,
        )

        self.config = self._config()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _result(
        *,
        success: bool,
        changed: bool,
        **kwargs,
    ) -> SimpleNamespace:

        return SimpleNamespace(
            success=success,
            changed=changed,
        )

    def _config(
        self,
        *,
        rebuild: bool = False,
        parallel: bool = False,
        mode: str = "force",
        cache_ready_by: str = "log",
        service_ready_by: str = "ready",
    ) -> CacheRefreshConfig:

        cache_readiness = ReadinessConfig(
            ready_by=cache_ready_by,
            success_messages=(
                "Server startup in",
            ),
            failure_messages=(
                "Caused by:",
                "Redis",
            ),
            timeout=10,
            poll_interval=1,
        )

        service_readiness = ReadinessConfig(
            ready_by=service_ready_by,
            success_messages=(
                "Server startup in",
            ) if service_ready_by == "log" else (),
            failure_messages=(
                "Caused by:",
            ) if service_ready_by == "log" else (),
            timeout=10,
            poll_interval=1,
        )

        cache = None

        if rebuild:

            cache = CacheConfig(
                deployment="cache",
                environment=CacheEnvironment(
                    name="CACHE_REFRESH",
                    value="true",
                ),
                readiness=cache_readiness,
            )

        return CacheRefreshConfig(
            kubeconfig=Path(
                "/tmp/.kube/config",
            ),
            namespace="test",
            rebuild=rebuild,
            stop_all_before_cache_rebuild=True,
            mode=mode,
            services=(
                "app1",
                "app2",
                "cache",
            ),
            cache=cache,
            service_readiness=service_readiness,
            parallel=parallel,
        )

    @staticmethod
    def _pod_json(
        *,
        pod_name: str = "cache-abc",
        phase: str = "Running",
        ready: bool = True,
    ) -> str:

        return json.dumps(
            {
                "items": [
                    {
                        "metadata": {
                            "name": pod_name,
                            "creationTimestamp": (
                                "2026-09-13T10:00:00Z"
                            ),
                        },
                        "status": {
                            "phase": phase,
                            "containerStatuses": [
                                {
                                    "name": "cache",
                                    "ready": ready,
                                },
                            ],
                        },
                    },
                ],
            },
        )

    def _deployment_json(
        self,
        *,
        deployment: str,
    ) -> str:

        return json.dumps(
            {
                "metadata": {
                    "name": deployment,
                },
                "spec": {
                    "selector": {
                        "matchLabels": {
                            "app": deployment,
                        },
                    },
                },
            },
        )

    # ==================================================================
    # Normal restart
    # ==================================================================

    def test_normal_restart_force(self) -> None:
        """
        Force restart must scale each service down and up.
        """

        self.executor._wait_for_services = Mock()

        self.executor._restart_services(
            self.config,
            ["app1"],
            self.config.service_readiness,
        )

        commands = [
            item.args[0]
            for item in self.shell.run.call_args_list
        ]

        self.assertEqual(
            commands,
            [
                [
                    "oc",
                    "scale",
                    "deployment/app1",
                    "--replicas=0",
                    "-n",
                    "test",
                ],
                [
                    "oc",
                    "scale",
                    "deployment/app1",
                    "--replicas=1",
                    "-n",
                    "test",
                ],
            ],
        )

        self.executor._wait_for_services.assert_called_once_with(
            self.config,
            ["app1"],
            self.config.service_readiness,
        )

    def test_normal_restart_graceful(self) -> None:
        """
        Graceful restart must use rollout restart.
        """

        self.executor._wait_for_services = Mock()

        config = self._config(
            mode="graceful",
        )

        self.executor._restart_services(
            config,
            ["app1"],
            config.service_readiness,
        )

        command = self.shell.run.call_args_list[0].args[0]

        self.assertEqual(
            command,
            [
                "oc",
                "rollout",
                "restart",
                "deployment/app1",
                "-n",
                "test",
            ],
        )

        self.executor._wait_for_services.assert_called_once_with(
            config,
            ["app1"],
            config.service_readiness,
        )

    # ==================================================================
    # Ready-based verification
    # ==================================================================

    def test_ready_by_ready_waits_until_1_of_1(self) -> None:
        """
        ready_by=ready must continue until container readiness is 1/1.
        """

        self.shell.run.side_effect = [
            # deployment selector
            FakeExecutionResult(
                stdout=self._deployment_json(
                    deployment="app1",
                ),
            ),
            # 0/1
            FakeExecutionResult(
                stdout=self._pod_json(
                    ready=False,
                ),
            ),
            # deployment selector
            FakeExecutionResult(
                stdout=self._deployment_json(
                    deployment="app1",
                ),
            ),
            # 1/1
            FakeExecutionResult(
                stdout=self._pod_json(
                    ready=True,
                ),
            ),
        ]

        config = self._config(
            rebuild=True,
            service_ready_by="ready",
        )

        self.executor._wait_for_service(
            config,
            "app1",
            config.service_readiness,
        )

        self.assertEqual(
            self.shell.run.call_count,
            4,
        )

    # ==================================================================
    # Log-based verification
    # ==================================================================

    def test_ready_by_log_retries_container_creating(self) -> None:
        """
        ContainerCreating must be treated as a transient state.
        """

        self.shell.run.side_effect = [
            # deployment selector
            FakeExecutionResult(
                stdout=self._deployment_json(
                    deployment="cache",
                ),
            ),
            # pod list
            FakeExecutionResult(
                stdout=self._pod_json(
                    phase="Pending",
                    ready=False,
                ),
            ),
            # deployment selector
            FakeExecutionResult(
                stdout=self._deployment_json(
                    deployment="cache",
                ),
            ),
            # pod list
            FakeExecutionResult(
                stdout=self._pod_json(
                    phase="Running",
                    ready=False,
                ),
            ),
            # logs
            FakeExecutionResult(
                stdout="org.apache.catalina.startup.Catalina "
                       "start Server startup in 5000 ms",
            ),
        ]

        config = self._config(
            rebuild=True,
            cache_ready_by="log",
        )

        self.executor._wait_for_service(
            config,
            "cache",
            config.cache.readiness,
        )

        self.assertGreaterEqual(
            self.shell.run.call_count,
            5,
        )

    def test_ready_by_log_detects_success_message(self) -> None:
        """
        A configured success message must mark the service ready.
        """

        self.shell.run.side_effect = [
            FakeExecutionResult(
                stdout=self._deployment_json(
                    deployment="cache",
                ),
            ),
            FakeExecutionResult(
                stdout=self._pod_json(
                    phase="Running",
                ),
            ),
            FakeExecutionResult(
                stdout="Server startup in 5000 ms",
            ),
        ]

        config = self._config(
            rebuild=True,
            cache_ready_by="log",
        )

        self.executor._wait_for_service(
            config,
            "cache",
            config.cache.readiness,
        )

        self.assertEqual(
            self.shell.run.call_count,
            3,
        )

    def test_ready_by_log_detects_failure_message(self) -> None:
        """
        A configured failure message must immediately fail readiness.
        """

        self.shell.run.side_effect = [
            FakeExecutionResult(
                stdout=self._deployment_json(
                    deployment="cache",
                ),
            ),
            FakeExecutionResult(
                stdout=self._pod_json(
                    phase="Running",
                ),
            ),
            FakeExecutionResult(
                stdout="ERROR: Caused by: Redis connection refused",
            ),
        ]

        config = self._config(
            rebuild=True,
            cache_ready_by="log",
        )

        with self.assertRaises(
            CacheRefreshPluginException,
        ):
            self.executor._wait_for_service(
                config,
                "cache",
                config.cache.readiness,
            )

    # ==================================================================
    # Cache rebuild
    # ==================================================================

    def test_cache_rebuild_workflow(self) -> None:
        """
        Cache rebuild must follow the expected lifecycle.
        """

        # The workflow calls:
        #
        # scale services
        # set env
        # scale cache
        # cache readiness
        # remove env
        # cache readiness
        # start remaining
        # remaining readiness
        #
        # Mock every OpenShift call as successful.

        def successful_result(command, **kwargs):

            if command[1:3] == [
                "get",
                "deployment",
            ]:

                deployment = command[3]

                return FakeExecutionResult(
                    stdout=self._deployment_json(
                        deployment=deployment,
                    ),
                )

            if command[1:3] == [
                "get",
                "pods",
            ]:

                return FakeExecutionResult(
                    stdout=self._pod_json(
                        ready=True,
                    ),
                )

            if command[1] == "logs":

                return FakeExecutionResult(
                    stdout="Server startup in 5000 ms",
                )

            return FakeExecutionResult()

        self.shell.run.side_effect = successful_result

        config = self._config(
            rebuild=True,
            parallel=False,
            cache_ready_by="log",
            service_ready_by="ready",
        )

        result = self.executor.execute(
            config,
        )

        self.assertTrue(
            result.success,
        )

        commands = [
            item.args[0]
            for item in self.shell.run.call_args_list
        ]

        # Stop all.
        self.assertIn(
            [
                "oc",
                "scale",
                "deployment/app1",
                "--replicas=0",
                "-n",
                "test",
            ],
            commands,
        )

        self.assertIn(
            [
                "oc",
                "scale",
                "deployment/app2",
                "--replicas=0",
                "-n",
                "test",
            ],
            commands,
        )

        self.assertIn(
            [
                "oc",
                "scale",
                "deployment/cache",
                "--replicas=0",
                "-n",
                "test",
            ],
            commands,
        )

        # Set cache environment.
        self.assertIn(
            [
                "oc",
                "set",
                "env",
                "deployment/cache",
                "CACHE_REFRESH=true",
                "-n",
                "test",
            ],
            commands,
        )

        # Start cache.
        self.assertIn(
            [
                "oc",
                "scale",
                "deployment/cache",
                "--replicas=1",
                "-n",
                "test",
            ],
            commands,
        )

        # Remove cache environment.
        self.assertIn(
            [
                "oc",
                "set",
                "env",
                "deployment/cache",
                "CACHE_REFRESH-",
                "-n",
                "test",
            ],
            commands,
        )

        # Remaining services eventually start.
        self.assertIn(
            [
                "oc",
                "scale",
                "deployment/app1",
                "--replicas=1",
                "-n",
                "test",
            ],
            commands,
        )

        self.assertIn(
            [
                "oc",
                "scale",
                "deployment/app2",
                "--replicas=1",
                "-n",
                "test",
            ],
            commands,
        )

    # ==================================================================
    # Sequential execution
    # ==================================================================

    def test_sequential_restart_waits_before_next_service(self) -> None:
        """
        Sequential execution must complete readiness verification for
        service N before restarting service N+1.
        """

        events: list[str] = []

        original_restart = self.executor._restart_service
        original_wait = self.executor._wait_for_services

        def restart(config, service):
            events.append(
                f"restart:{service}",
            )
            original_restart(
                config,
                service,
            )

        def wait(config, services, readiness):
            events.append(
                f"wait:{services[0]}",
            )

            original_wait(
                config,
                services,
                readiness,
            )

        self.executor._restart_service = restart
        self.executor._wait_for_services = wait

        # Don't need actual OC readiness for this ordering test.
        self.executor._wait_for_services = Mock(
            side_effect=lambda config, services, readiness:
                events.append(
                    f"wait:{services[0]}",
                ),
        )

        self.executor._restart_service = Mock(
            side_effect=lambda config, service:
                events.append(
                    f"restart:{service}",
                ),
        )

        config = self._config(
            parallel=False,
        )

        self.executor._restart_services(
            config,
            ["app1", "app2"],
            config.service_readiness,
        )

        self.assertEqual(
            events,
            [
                "restart:app1",
                "wait:app1",
                "restart:app2",
                "wait:app2",
            ],
        )

    # ==================================================================
    # Parallel execution
    # ==================================================================

    def test_parallel_restart_restarts_all_before_waiting(self) -> None:
        """
        Parallel mode must restart all services before readiness
        verification begins.
        """

        events: list[str] = []

        self.executor._restart_service = Mock(
            side_effect=lambda config, service:
                events.append(
                    f"restart:{service}",
                ),
        )

        self.executor._wait_for_services = Mock(
            side_effect=lambda config, services, readiness:
                events.append(
                    "wait",
                ),
        )

        config = self._config(
            parallel=True,
        )

        self.executor._restart_services(
            config,
            ["app1", "app2", "cache"],
            config.service_readiness,
        )

        restart_events = [
            event
            for event in events
            if event.startswith("restart:")
        ]

        self.assertEqual(
            set(restart_events),
            {
                "restart:app1",
                "restart:app2",
                "restart:cache",
            },
        )

        self.assertEqual(
            events[-1],
            "wait",
        )

    def test_ready_by_ready_does_not_accept_old_ready_pod(
        self,
    ) -> None:
        """
        A ready old pod must not satisfy readiness when a newer pod
        belonging to the rollout is still not ready.
        """

        self.shell.run.side_effect = [
            # Deployment selector.
            FakeExecutionResult(
                stdout=self._deployment_json(
                    deployment="cache",
                ),
            ),

            # Pod list:
            # old pod is ready, new pod is not ready.
            FakeExecutionResult(
                stdout=json.dumps(
                    {
                        "items": [
                            {
                                "metadata": {
                                    "name": "cache-old",
                                    "creationTimestamp": (
                                        "2026-09-13T10:00:00Z"
                                    ),
                                },
                                "status": {
                                    "phase": "Running",
                                    "containerStatuses": [
                                        {
                                            "name": "cache",
                                            "ready": True,
                                        },
                                    ],
                                },
                            },
                            {
                                "metadata": {
                                    "name": "cache-new",
                                    "creationTimestamp": (
                                        "2026-09-13T10:05:00Z"
                                    ),
                                },
                                "status": {
                                    "phase": "Running",
                                    "containerStatuses": [
                                        {
                                            "name": "cache",
                                            "ready": False,
                                        },
                                    ],
                                },
                            },
                        ],
                    },
                ),
            ),
        ]

        config = self._config(
            rebuild=True,
            cache_ready_by="ready",
        )

        ready = self.executor._is_pod_ready(
            config,
            "cache",
        )

        self.assertFalse(
            ready,
        )


if __name__ == "__main__":
    unittest.main()

