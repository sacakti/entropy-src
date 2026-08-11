"""
Workflow runner.
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

from core.exceptions import EntropyException
from core.runtime.context import ExecutionContext
from lib.models.workflow import (
    Workflow,
    WorkflowStep,
)
from lib.plugins.exceptions import PluginDisabledError
from lib.workflow.exceptions import WorkflowCancelledError, WorkflowError
from lib.workflow.variables import WorkflowVariableResolver

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

        self._jobs: WorkflowJobManager = context.workflow_job_manager

    # ------------------------------------------------------------------
    # Execute
    # ------------------------------------------------------------------

    def execute(
        self,
        workflow: Workflow,
        *,
        execution=None,
        job_id: int | None = None,
    ) -> None:
        """
        Execute a workflow.
        """

        assert self._context.paths is not None
        assert self._context.executor is not None
        assert self._context.vault_manager is not None

        resolver = WorkflowVariableResolver(
            self._context.vault_manager,
        )

        #
        # Create or reuse the execution.
        #

        if execution is None:

            assert self._context.execution_manager is not None

            execution = self._context.execution_manager.create(
                workflow,
            )

        runtime = execution.context

        #
        # Resolve persistent job.
        #

        if job_id is None:

            job = self._jobs.create(
                execution_id=execution.id,
                workflow=workflow.name,
                workspace=runtime.workspace,
                pid=os.getpid(),
            )

        else:

            job = self._jobs.attach(
                job_id,
            )

            self._jobs.set_pid(
                job.require_id(),
                os.getpid(),
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

        enabled_steps = [step for step in workflow.steps if step.enabled]

        runtime.set_variables(
            resolver.resolve_variables(
                workflow.variables,
            ),
        )

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
                            resolver,
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

            raise WorkflowCancelledError("User cancelled operation.") from exc

        except PluginDisabledError:

            #
            # Expected application error.
            #
            # Preserve the original exception so CommandManager
            # can display the correct domain-specific message.
            #

            execution.fail()

            self._jobs.fail(
                job.id,
            )

            raise

        except Exception as exc:

            #
            # Workflow execution failed.
            #

            execution.fail()

            self._jobs.fail(
                job.id,
            )
            import traceback

            raise WorkflowError(f"Failed: {traceback.format_exc()}") from exc

    # ------------------------------------------------------------------
    # Initialize
    # ------------------------------------------------------------------

    def _initialize(
        self,
        runtime: ExecutionContext,
        workflow: Workflow,
        step: WorkflowStep,
        resolver: WorkflowVariableResolver,
    ) -> None:
        """
        Prepare step execution.
        """

        arguments = resolver.resolve(
            step.arguments,
            runtime.variables,
        )

        runtime.set_arguments(
            arguments,
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
