"""
Workflow process management.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


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
        project_root: Path,
        python_packages: Path,
    ) -> None:

        self._job_id = job_id
        self._workflow = workflow
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
            "-m",
            "lib.workflow.worker",
            str(self._job_id),
            str(self._workflow.resolve()),
            "--project-root",
            str(self._project_root),
            "--python-packages",
            str(self._python_packages),
        ]

        process = subprocess.Popen(
            command,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
            close_fds=True,
        )

        if process.pid <= 0:

            raise RuntimeError(
                "Workflow worker process did not provide a PID.",
            )

        return process.pid
