"""
OpenShift pod metrics plugin.

An app plugin: a live table of a namespace's pods with CPU and memory from the metrics
API, compared with their limits. It only reads, through the login session of oc.generic.
Automated runs make one pass and report it in the step's outputs.
"""

from __future__ import annotations

import json
import re
import subprocess  # nosec B404 - only for the timeout raised by the executor
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from lib.models.plugin import PluginResult
from lib.plugins.base import BasePlugin

from .exceptions import PodMetricsException
from .metrics import chart_values, display_row, pod_rows, table_row

NAMESPACE = re.compile(r"^[a-z0-9]([-a-z0-9.]{0,251}[a-z0-9])?$")
ENVIRONMENT = re.compile(r"^[A-Za-z0-9._-]+$")
OC_TIMEOUT_SECONDS = 30


def _highest(name: str) -> Any:
    """Sort key: highest first, with pods that have no value last."""

    return lambda row: (row[name] is None, -(row[name] or 0), row["pod"])


SORT_KEYS = {
    "CPU": _highest("cpu"),
    "Memory": _highest("memory"),
    "CPU % of limit": _highest("cpu_percent"),
    "Memory % of limit": _highest("memory_percent"),
    "Restarts": _highest("restarts"),
    "Name": lambda row: row["pod"],
}


class PodMetricsPlugin(
    BasePlugin,
):
    """
    Live CPU, memory, status and restarts of the pods in an OpenShift namespace.
    """

    KUBECONFIG_DIRECTORY = ".kube"
    KUBECONFIG_FILENAME = "config"

    def execute(
        self,
    ) -> PluginResult:
        """
        Refresh the pod table until the app is stopped.
        """

        try:
            self._monitor()
        except PodMetricsException as error:
            self.message.error(str(error))
            return PluginResult(success=False, errors=[{"message": str(error)}])

        return PluginResult(success=True, changed=False, outputs=dict(self.outputs))

    # ------------------------------------------------------------------
    # App loop
    # ------------------------------------------------------------------

    def _monitor(
        self,
    ) -> None:
        environment = (self.arguments.string("environment", "") or "").strip()
        if not ENVIRONMENT.match(environment):
            raise PodMetricsException(
                "Argument 'environment' is required: the oc.generic environment that is logged in.",
            )

        kubeconfig = self._kubeconfig(environment)
        fallback = (self.arguments.string("namespace", "") or "").strip()
        max_rows = self.arguments.integer("max_rows", 500, minimum=1, maximum=5000) or 500
        session_project: Optional[str] = None
        shown_error: Optional[str] = None
        shown_warning: Optional[str] = None
        charted: Optional[str] = None
        rows: List[Dict[str, Any]] = []

        if self.app.interactive:
            self.message.info("Live page open: use the App tab, and Stop app to finish.")
        self.app.log("activity", "Monitoring started.")

        while self.app.running:
            try:
                namespace = str(self.app.input("namespace", "") or fallback).strip()
                if not namespace:
                    session_project = session_project or self._current_project(kubeconfig)
                    namespace = session_project
                if not NAMESPACE.match(namespace):
                    raise PodMetricsException(f"'{namespace}' is not a valid namespace name.")

                rows, warning = self._read(kubeconfig, namespace)

            except PodMetricsException as error:
                # A one-off run has nothing to show; a live page keeps its last rows.
                if not self.app.interactive:
                    raise
                if str(error) != shown_error:
                    self.app.log("activity", f"Could not refresh: {error}")
                    shown_error = str(error)
            else:
                if shown_error:
                    self.app.log("activity", "Refreshing again.")
                    shown_error = None
                if warning != shown_warning:
                    self.app.log("activity", warning or "Metrics are available again.")
                    shown_warning = warning
                self._publish(namespace, rows, warning, max_rows)
                # The graph follows one namespace; another one starts it again.
                self.app.chart("usage", chart_values(rows), clear=namespace != charted)
                charted = namespace
                self._report(namespace, rows, warning)

            for press in self.app.events("details"):
                self._details(press.selection, rows)

            self.app.wait()

        self.app.log("activity", "Monitoring stopped.")
        self.message.success(f"Pod metrics finished: {len(rows)} pods.")

    def _publish(
        self,
        namespace: str,
        rows: List[Dict[str, Any]],
        warning: Optional[str],
        max_rows: int,
    ) -> None:
        wanted = str(self.app.input("filter", "")).strip().lower()
        only_attention = bool(self.app.input("only_attention", False))
        shown = [
            row
            for row in rows
            if (not wanted or wanted in row["pod"].lower() or wanted in row["status"].lower())
            and (not only_attention or row["attention"])
        ]
        shown.sort(key=SORT_KEYS.get(str(self.app.input("sort", "CPU")), SORT_KEYS["CPU"]))

        cpu = sum(row["cpu"] or 0 for row in shown)
        memory = sum(row["memory"] or 0 for row in shown)

        self.app.stats(
            "summary",
            {
                "Pods": len(rows),
                "Running": sum(1 for row in rows if row["status"] == "Running"),
                "Need attention": sum(1 for row in rows if row["attention"]),
                "Restarts": sum(row["restarts"] for row in rows),
                "CPU (cores, shown)": round(cpu / 1000, 2),
                "Memory (GiB, shown)": round(memory / 1024, 2),
            },
        )
        self.app.keyvalue(
            "source",
            {
                "Namespace": namespace,
                "Metrics": warning or "Available",
                "Updated": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
            },
        )
        self.app.table("pods", [table_row(row) for row in shown[:max_rows]])

    def _report(
        self,
        namespace: str,
        rows: List[Dict[str, Any]],
        warning: Optional[str],
    ) -> None:
        self.outputs.update(
            {
                "namespace": namespace,
                "pod_count": len(rows),
                "attention_count": sum(1 for row in rows if row["attention"]),
                "cpu_millicores": round(sum(row["cpu"] or 0 for row in rows), 1),
                "memory_mib": round(sum(row["memory"] or 0 for row in rows), 1),
                "metrics_available": warning is None,
                "pods": [display_row(row) for row in rows],
            },
        )

    def _details(
        self,
        selection: List[Any],
        rows: List[Dict[str, Any]],
    ) -> None:
        """Log usage per container for the selected pods."""

        chosen = {str(item) for item in selection}
        pods = [row for row in rows if row["pod"] in chosen]
        if not pods:
            self.app.log("activity", "Container details: select one or more pods first.")
            return
        for row in pods:
            self.app.log("activity", f"{row['pod']} ({row['status']}, on {row['node']}):")
            for name, usage in row["containers"].items():
                cpu, memory = usage.get("cpu"), usage.get("memory")
                self.app.log(
                    "activity",
                    f"  {name}: CPU {'—' if cpu is None else f'{cpu:.1f}m'},"
                    f" memory {'—' if memory is None else f'{memory:.1f} MiB'}",
                )

    # ------------------------------------------------------------------
    # OpenShift
    # ------------------------------------------------------------------

    def _kubeconfig(
        self,
        environment: str,
    ) -> Path:
        """The oc.generic login session of `environment` (never created here)."""

        path = (
            self.session_directory
            / self.KUBECONFIG_DIRECTORY
            / environment
            / self.KUBECONFIG_FILENAME
        )
        if not self.filesystem.exists(path):
            raise PodMetricsException(
                f"No OpenShift session for environment '{environment}'. "
                "Log in first with oc.generic (operation 'login').",
            )
        return path

    def _oc(
        self,
        kubeconfig: Path,
        *arguments: str,
    ) -> Any:
        command = ["oc", *arguments]
        try:
            return self.shell.run(
                command,
                timeout=OC_TIMEOUT_SECONDS,
                env={"KUBECONFIG": str(kubeconfig)},
            )
        except FileNotFoundError as exc:
            raise PodMetricsException(
                "'oc' was not found; install it and make sure it is in PATH.",
            ) from exc
        except subprocess.TimeoutExpired as exc:
            raise PodMetricsException(
                f"'oc {arguments[0]}' did not answer in {OC_TIMEOUT_SECONDS} seconds.",
            ) from exc
        except OSError as exc:
            raise PodMetricsException(f"Unable to run oc: {exc}") from exc

    def _current_project(
        self,
        kubeconfig: Path,
    ) -> str:
        result = self._oc(kubeconfig, "project", "-q")
        project = (result.stdout or "").strip()
        if not result.success or not project:
            raise PodMetricsException(
                "The session has no current project: set 'namespace'. "
                f"{(result.stderr or '').strip()}".strip(),
            )
        return project

    def _read(
        self,
        kubeconfig: Path,
        namespace: str,
    ) -> Tuple[List[Dict[str, Any]], Optional[str]]:
        """The namespace's rows, and why there is no usage in them, if there is not."""

        result = self._oc(kubeconfig, "get", "pods", "-n", namespace, "-o", "json")
        if not result.success:
            raise PodMetricsException(
                f"oc get pods failed: {(result.stderr or result.stdout or '').strip()}",
            )
        try:
            pods = json.loads(result.stdout or "{}")
        except ValueError as exc:
            raise PodMetricsException(f"oc get pods did not return JSON: {exc}") from exc

        # Status is still worth showing without usage: the API may be down or forbidden.
        metrics: Optional[Dict[str, Any]] = None
        warning: Optional[str] = None
        usage = self._oc(
            kubeconfig,
            "get",
            "--raw",
            f"/apis/metrics.k8s.io/v1beta1/namespaces/{namespace}/pods",
        )
        if usage.success:
            try:
                metrics = json.loads(usage.stdout or "{}")
            except ValueError:
                warning = "The metrics API did not return JSON."
        else:
            detail = (usage.stderr or usage.stdout or "").strip().splitlines()
            warning = f"Metrics unavailable: {detail[0] if detail else 'no details'}"

        return pod_rows(pods, metrics), warning
