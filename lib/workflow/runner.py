"""
Workflow runner.
"""

from __future__ import annotations

from datetime import datetime, timezone
import os
from typing import TYPE_CHECKING

from core.runtime.context import ExecutionContext

from lib.models.workflow import (
    Workflow,
    WorkflowStep,
)
from lib.workflow.exceptions import WorkflowCancelledError

if TYPE_CHECKING:
    from core.context import EntropyContext
    from lib.plugins.runner import PluginRunner
    from lib.workflow.jobs.manager import WorkflowJobManager


class WorkflowRunner:
    """
    Executes workflows.
    """

    def __init__(
        self,
        context: EntropyContext,
        plugin_runner: PluginRunner,
    ) -> None:

        self._context = context

        self._plugins = plugin_runner

        assert context.workflow_job_manager is not None

        self._jobs: WorkflowJobManager = (
            context.workflow_job_manager
        )

    # ------------------------------------------------------------------
    # Execute
    # ------------------------------------------------------------------

    def execute(
        self,
        workflow: Workflow,
    ) -> None:
        """
        Execute a workflow.
        """

        assert self._context.paths is not None
        assert self._context.executor is not None

        #
        # Create execution workspace.
        #

        workspace = (
            self._context.paths.workflow.directory
            / (
                f"{datetime.now(timezone.utc):%Y%m%d_%H%M%S}_"
                f"{workflow.name.lower().replace(' ', '_')}"
            )
        )

        self._context.executor.mkdir(
            workspace,
        )

        #
        # Runtime
        #

        runtime = ExecutionContext(
            entropy=self._context,
            workspace=workspace,
        )

        runtime.start(
            workflow,
        )

        execution = runtime.execution

        #
        # Create persistent job.
        #

        job = self._jobs.create(
            execution_id=execution.id,
            workflow=workflow.name,
            workspace=workspace,
            pid=os.getpid(),
        )

        runtime.job_id = job.id

        execution.put(
            "job_id",
            job.id,
        )

        #
        # Mark execution as running.
        #

        execution.start()

        self._jobs.start(
            job.id,
        )

        self._jobs.running(
            job.id,
        )

        #
        # Enabled steps.
        #

        enabled_steps = [
            step
            for step in workflow.steps
            if step.enabled
        ]

        total_steps = len(
            enabled_steps,
        )

        #
        # Execute workflow.
        #

        try:

            with runtime.workflow(
                workflow.name,
            ):

                for index, step in enumerate(
                    enabled_steps,
                    start=1,
                ):

                    with runtime.step(
                        step.name,
                        index=index,
                        total=total_steps,
                    ):

                        self._initialize(
                            runtime,
                            workflow,
                            step,
                        )

                        self._execute(
                            runtime,
                            workflow,
                            step,
                        )

                        self._finalize(
                            runtime,
                            workflow,
                            step,
                        )

            #
            # Successful completion.
            #

            execution.complete()

            self._jobs.complete(
                job.id,
            )

        except KeyboardInterrupt as exc:

            #
            # User requested cancellation.
            #

            execution.cancel()

            self._jobs.cancel(
                job.id,
                exit_code=130,
            )

            raise WorkflowCancelledError(
                "User cancelled operation."
            ) from exc

        except Exception:

            #
            # Workflow execution failed.
            #

            execution.fail()

            self._jobs.fail(
                job.id,
            )

            raise

    # ------------------------------------------------------------------
    # Initialize
    # ------------------------------------------------------------------

    def _initialize(
        self,
        runtime: ExecutionContext,
        workflow: Workflow,
        step: WorkflowStep,
    ) -> None:
        """
        Prepare step execution.
        """

        runtime.set_arguments(
            step.arguments,
        )

    # ------------------------------------------------------------------
    # Execute
    # ------------------------------------------------------------------

    def _execute(
        self,
        runtime: ExecutionContext,
        workflow: Workflow,
        step: WorkflowStep,
    ) -> None:
        """
        Execute the workflow plugin.
        """

        self._plugins.execute(
            context=runtime,
            qualified_name=step.plugin,
        )

    # ------------------------------------------------------------------
    # Finalize
    # ------------------------------------------------------------------

    def _finalize(
        self,
        runtime: ExecutionContext,
        workflow: Workflow,
        step: WorkflowStep,
    ) -> None:
        """
        Finalize step execution.
        """

        pass
