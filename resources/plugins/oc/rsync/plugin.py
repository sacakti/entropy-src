"""
OpenShift rsync plugin.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from lib.models.plugin import PluginResult
from lib.plugins.base import BasePlugin

from .exceptions import RsyncPluginException


class RsyncPlugin(
    BasePlugin,
):
    """
    Execute OpenShift rsync operations from an rsync plan.

    The plugin expects:

    environment:
        OpenShift environment/session name.

    rsync_plan:
        A list containing:
            {
                "deployment": "...",
                "target": "...",
                "source": "..."
            }

    Authentication and project selection are intentionally
    outside this plugin. An existing environment-specific
    OpenShift session is required.
    """

    KUBECONFIG_DIRECTORY = ".kube"
    KUBECONFIG_FILENAME = "config"

    def execute(
        self,
    ) -> PluginResult:
        """
        Execute the rsync plan.
        """

        self.message.info(
            "Starting rsync.",
        )

        try:

            with self.activity(
                "rsync",
            ):

                result = self._execute()

        except RsyncPluginException as exc:

            self.log.error(
                str(exc),
            )

            self.message.error(
                str(exc),
            )

            return self._failure(
                str(exc),
            )

        if result.success:

            self.message.success(
                "rsync completed successfully.",
            )

        else:

            self.message.error(
                "rsync failed.",
            )

        return result

    # ------------------------------------------------------------------
    # Implementation
    # ------------------------------------------------------------------

    def _execute(
        self,
    ) -> PluginResult:
        """
        Execute every operation in the rsync plan.
        """

        environment = self.arguments.get(
            "environment",
        )

        if (
            not isinstance(
                environment,
                str,
            )
            or not environment.strip()
        ):

            raise RsyncPluginException(
                "Argument 'environment' must be a "
                "non-empty string.",
            )

        environment = environment.strip()

        rsync_plan = self.arguments.get(
            "rsync_plan",
        )

        plan = self._validate_plan(
            rsync_plan,
        )

        if not plan:

            self.outputs.update(
                {
                    "success": True,
                    "environment": environment,
                    "resources_processed": 0,
                    "resources_succeeded": 0,
                    "resources_failed": 0,
                    "changes": 0,
                    "results": [],
                },
            )

            return self._success(
                changed=False,
            )

        kubeconfig = self._kubeconfig(
            environment,
        )

        results: list[dict[str, Any]] = []
        failed: list[str] = []
        changed = False

        for operation in plan:

            deployment = operation[
                "deployment"
            ]

            target = operation[
                "target"
            ]

            source = operation[
                "source"
            ]

            self.message.info(
                f"  Resolving pod for "
                f"Deployment/{deployment}.",
            )

            pod = self._resolve_ready_pod(
                deployment=deployment,
                kubeconfig=kubeconfig,
            )

            self.message.info(
                f"  Selected pod '{pod}' "
                f"for Deployment/{deployment}.",
            )

            destination = (
                f"{pod}:{target}"
            )

            self.message.info(
                f"  Rsync '{source}' -> "
                f"'{destination}'.",
            )

            result = self._rsync(
                source=source,
                destination=destination,
                kubeconfig=kubeconfig,
            )

            operation_result = {
                "deployment": deployment,
                "pod": pod,
                "source": source,
                "target": target,
                "destination": destination,
                "success": result.success,
                "exit_code": result.exit_code,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "duration": result.duration,
            }

            results.append(
                operation_result,
            )

            if result.success:

                changed = True

                self.message.success(
                    f"  Rsync completed for "
                    f"Deployment/{deployment} "
                    f"using pod '{pod}'.",
                )

            else:

                failed.append(
                    f"{deployment} -> {pod}:{target}",
                )

                self.message.error(
                    f"  Rsync failed for "
                    f"Deployment/{deployment}.",
                )

        self.outputs.update(
            {
                "success": not failed,
                "environment": environment,
                "resources_processed": len(plan),
                "resources_succeeded": (
                    len(plan) - len(failed)
                ),
                "resources_failed": len(failed),
                "changes": (
                    len(plan) - len(failed)
                ),
                "results": results,
            },
        )

        if failed:

            return self._failure(
                "Rsync failed for: "
                + ", ".join(
                    failed,
                ),
            )

        return self._success(
            changed=changed,
        )

    # ------------------------------------------------------------------
    # Pod resolution
    # ------------------------------------------------------------------

    def _resolve_ready_pod(
        self,
        *,
        deployment: str,
        kubeconfig: Path,
    ) -> str:
        """
        Resolve one Running and Ready pod belonging to a Deployment.

        The Deployment selector is used instead of assuming that
        the Deployment name is also a pod name.
        """

        deployment_result = self._oc_json(
            [
                "get",
                "deployment",
                deployment,
                "-o",
                "json",
            ],
            kubeconfig=kubeconfig,
        )

        deployment_document = deployment_result

        spec = deployment_document.get(
            "spec",
        )

        if not isinstance(
            spec,
            dict,
        ):

            raise RsyncPluginException(
                f"Deployment/{deployment} does not contain "
                "a valid spec.",
            )

        selector = spec.get(
            "selector",
        )

        if not isinstance(
            selector,
            dict,
        ):

            raise RsyncPluginException(
                f"Deployment/{deployment} does not contain "
                "a valid selector.",
            )

        match_labels = selector.get(
            "matchLabels",
        )

        if not isinstance(
            match_labels,
            dict,
        ) or not match_labels:

            raise RsyncPluginException(
                f"Deployment/{deployment} does not contain "
                "spec.selector.matchLabels.",
            )

        label_selector = self._label_selector(
            match_labels,
        )

        pods_document = self._oc_json(
            [
                "get",
                "pods",
                "-l",
                label_selector,
                "-o",
                "json",
            ],
            kubeconfig=kubeconfig,
        )

        items = pods_document.get(
            "items",
        )

        if not isinstance(
            items,
            list,
        ):

            raise RsyncPluginException(
                f"Unable to read pods for "
                f"Deployment/{deployment}.",
            )

        ready_pods: list[str] = []

        for pod in items:

            if not isinstance(
                pod,
                dict,
            ):
                continue

            metadata = pod.get(
                "metadata",
            )

            pod_spec = pod.get(
                "spec",
            )

            status = pod.get(
                "status",
            )

            if not isinstance(
                metadata,
                dict,
            ):

                continue

            if not isinstance(
                pod_spec,
                dict,
            ):

                continue

            if not isinstance(
                status,
                dict,
            ):

                continue

            pod_name = metadata.get(
                "name",
            )

            phase = status.get(
                "phase",
            )

            if (
                not isinstance(
                    pod_name,
                    str,
                )
                or not pod_name.strip()
            ):

                continue

            if phase != "Running":
                continue

            if not self._is_ready(
                status,
            ):

                continue

            ready_pods.append(
                pod_name,
            )

        if not ready_pods:

            raise RsyncPluginException(
                f"No Running and Ready pods found for "
                f"Deployment/{deployment}.",
            )

        ready_pods.sort()

        return ready_pods[0]

    @staticmethod
    def _label_selector(
        labels: dict[str, Any],
    ) -> str:
        """
        Convert Deployment matchLabels into an oc label selector.
        """

        values: list[str] = []

        for key, value in labels.items():

            if (
                not isinstance(
                    key,
                    str,
                )
                or not key.strip()
            ):

                raise RsyncPluginException(
                    "Deployment selector contains "
                    "an invalid label key.",
                )

            if (
                not isinstance(
                    value,
                    str,
                )
                or not value.strip()
            ):

                raise RsyncPluginException(
                    f"Deployment selector label "
                    f"'{key}' must have a non-empty value.",
                )

            values.append(
                f"{key}={value}",
            )

        if not values:

            raise RsyncPluginException(
                "Deployment selector cannot be empty.",
            )

        return ",".join(
            values,
        )

    @staticmethod
    def _is_ready(
        status: dict[str, Any],
    ) -> bool:
        """
        Return True when the Pod Ready condition is True.
        """

        conditions = status.get(
            "conditions",
        )

        if not isinstance(
            conditions,
            list,
        ):

            return False

        for condition in conditions:

            if not isinstance(
                condition,
                dict,
            ):

                continue

            if (
                condition.get("type") == "Ready"
                and condition.get("status") == "True"
            ):

                return True

        return False

    # ------------------------------------------------------------------
    # OpenShift JSON
    # ------------------------------------------------------------------

    def _oc_json(
        self,
        arguments: list[str],
        *,
        kubeconfig: Path,
    ) -> dict[str, Any]:
        """
        Execute an oc command that returns JSON.
        """

        command = [
            "oc",
            *arguments,
        ]

        self.log.debug(
            "Executing OpenShift command: "
            + " ".join(
                command,
            ),
        )

        try:

            result = self.shell.run(
                command,
                env={
                    "KUBECONFIG": str(
                        kubeconfig,
                    ),
                },
            )

        except FileNotFoundError as exc:

            raise RsyncPluginException(
                "OpenShift CLI 'oc' was not found. "
                "Please install the OpenShift CLI and ensure "
                "it is available in PATH.",
            ) from exc

        except OSError as exc:

            raise RsyncPluginException(
                f"Unable to execute OpenShift command: {exc}",
            ) from exc

        if result.stdout:

            self.log.debug(
                result.stdout,
            )

        if result.stderr:

            self.log.warning(
                result.stderr,
            )

        if not result.success:

            message = (
                result.stderr.strip()
                if result.stderr
                else "unknown OpenShift error"
            )

            raise RsyncPluginException(
                f"OpenShift command failed: {message}",
            )

        try:

            value = json.loads(
                result.stdout,
            )

        except (
            TypeError,
            ValueError,
        ) as exc:

            raise RsyncPluginException(
                "OpenShift command returned invalid JSON.",
            ) from exc

        if not isinstance(
            value,
            dict,
        ):

            raise RsyncPluginException(
                "OpenShift command returned an invalid "
                "JSON object.",
            )

        return value

    # ------------------------------------------------------------------
    # Rsync
    # ------------------------------------------------------------------

    def _rsync(
        self,
        *,
        source: str,
        destination: str,
        kubeconfig: Path,
    ) -> Any:
        """
        Execute one local-to-pod oc rsync operation.
        """

        command = [
            "oc",
            "rsync",
            source,
            destination,
        ]

        self.log.debug(
            "Executing OpenShift rsync: "
            + " ".join(
                command,
            ),
        )

        try:

            result = self.shell.run(
                command,
                env={
                    "KUBECONFIG": str(
                        kubeconfig,
                    ),
                },
            )

        except FileNotFoundError as exc:

            raise RsyncPluginException(
                "OpenShift CLI 'oc' was not found. "
                "Please install the OpenShift CLI and ensure "
                "it is available in PATH.",
            ) from exc

        except OSError as exc:

            raise RsyncPluginException(
                f"Unable to execute OpenShift rsync: {exc}",
            ) from exc

        if result.stdout:

            self.log.info(
                result.stdout,
            )

        if result.stderr:

            self.log.warning(
                result.stderr,
            )

        return result

    # ------------------------------------------------------------------
    # Kubeconfig
    # ------------------------------------------------------------------

    def _kubeconfig(
        self,
        environment: str,
    ) -> Path:
        """
        Resolve the existing environment-specific kubeconfig.

        This plugin deliberately does not create or modify
        OpenShift sessions.
        """

        path = (
            self.session_directory
            / self.KUBECONFIG_DIRECTORY
            / environment
            / self.KUBECONFIG_FILENAME
        )

        if not self.filesystem.exists(
            path,
        ):

            raise RsyncPluginException(
                f"No OpenShift session exists for environment "
                f"'{environment}'. Run the login operation first.",
            )

        return path

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    @staticmethod
    def _validate_plan(
        value: Any,
    ) -> list[dict[str, str]]:
        """
        Validate and normalize the rsync plan.
        """

        if not isinstance(
            value,
            list,
        ):

            raise RsyncPluginException(
                "Argument 'rsync_plan' must be a list.",
            )

        if not value:

            return []

        plan: list[dict[str, str]] = []

        for index, item in enumerate(
            value,
            start=1,
        ):

            if not isinstance(
                item,
                dict,
            ):

                raise RsyncPluginException(
                    f"Rsync plan item {index} must be "
                    "an object.",
                )

            deployment = item.get(
                "deployment",
            )

            target = item.get(
                "target",
            )

            source = item.get(
                "source",
            )

            if (
                not isinstance(
                    deployment,
                    str,
                )
                or not deployment.strip()
            ):

                raise RsyncPluginException(
                    f"Rsync plan item {index} must contain "
                    "a non-empty 'deployment'.",
                )

            if (
                not isinstance(
                    target,
                    str,
                )
                or not target.strip()
            ):

                raise RsyncPluginException(
                    f"Rsync plan item {index} must contain "
                    "a non-empty 'target'.",
                )

            if (
                not isinstance(
                    source,
                    str,
                )
                or not source.strip()
            ):

                raise RsyncPluginException(
                    f"Rsync plan item {index} must contain "
                    "a non-empty 'source'.",
                )

            source_path = Path(
                source,
            )

            if not source_path.exists():

                raise RsyncPluginException(
                    f"Rsync source '{source}' does not exist.",
                )

            plan.append(
                {
                    "deployment": deployment.strip(),
                    "target": target.strip(),
                    "source": source.strip(),
                },
            )

        return plan

    # ------------------------------------------------------------------
    # Results
    # ------------------------------------------------------------------

    def _success(
        self,
        *,
        changed: bool,
    ) -> PluginResult:
        """
        Create a successful plugin result.
        """

        return PluginResult(
            success=True,
            changed=changed,
            outputs=dict(
                self.outputs,
            ),
            changes=[],
            errors=[],
            warnings=[],
            metadata={
                "artifacts": {
                    name: str(path)
                    for name, path
                    in self.artifacts.items()
                },
            },
        )

    def _failure(
        self,
        error: str,
    ) -> PluginResult:
        """
        Create a failed plugin result.
        """

        return PluginResult(
            success=False,
            changed=False,
            outputs=dict(
                self.outputs,
            ),
            changes=[],
            errors=[
                error,
            ],
            warnings=[],
            metadata={
                "artifacts": {
                    name: str(path)
                    for name, path
                    in self.artifacts.items()
                },
            },
        )
