"""
Workflow process management.
"""

from __future__ import annotations

import os
import signal
import subprocess
import sys
from pathlib import Path

from lib.workflow.exceptions import WorkflowProcessIDError, WorkflowProcessNotRunningError


class WorkflowProcess:
    """
    Manages a detached workflow worker process.

    Workflow execution itself belongs to WorkflowWorker.
    """

    def __init__(
        self,
        job_id: int,
        workflow: Path,
        *,
        worker: Path,
        project_root: Path,
        python_packages: Path,
    ) -> None:

        self._job_id = job_id
        self._workflow = workflow
        self._worker = worker
        self._project_root = project_root
        self._python_packages = python_packages

    # ------------------------------------------------------------------
    # Start
    # ------------------------------------------------------------------

    def start(self) -> int:
        """
        Start the workflow worker as an independent Python process.
        """

        command = [
            sys.executable,
            str(self._worker),
            str(self._job_id),
            str(self._workflow.resolve()),
            "--project-root",
            str(self._project_root),
            "--python-packages",
            str(self._python_packages),
        ]

        worker_log = (
            self._project_root
            / "tmp"
            / f"workflow-worker-{self._job_id}.log"
        )

        worker_log.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        log_file = worker_log.open(
            "ab",
        )

        process = subprocess.Popen(
            command,
            stdin=subprocess.DEVNULL,
            stdout=log_file,
            # stdout=subprocess.DEVNULL,
            stderr=subprocess.STDOUT,
            start_new_session=True,
            close_fds=True,
        )

        if process.pid <= 0:

            raise RuntimeError(
                "Workflow worker process did not provide a PID.",
            )

        return process.pid

    # ------------------------------------------------------------------
    # Stop
    # ------------------------------------------------------------------

    @staticmethod
    def stop(
        pid: int,
    ) -> None:
        """
        Request graceful cancellation of a workflow worker.

        SIGINT is intentionally used so the worker's normal
        KeyboardInterrupt handling can persist the cancelled state.
        """

        if pid <= 0:

            raise WorkflowProcessIDError()

        try:

            os.kill(
                pid,
                signal.SIGINT,
            )

        except ProcessLookupError as exc:

            raise WorkflowProcessNotRunningError(
               pid,
            ) from exc
