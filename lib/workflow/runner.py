"""
Workflow runner.
"""

from __future__ import annotations

import os
import traceback
from typing import TYPE_CHECKING, Any

from core.exceptions import EntropyException
from core.runtime.context import ExecutionContext
from lib.models.plugin import PluginResult
from lib.models.workflow import (
    Workflow,
    WorkflowDryRunResult,
    WorkflowExecutionOptions,
    WorkflowStep,
)
from lib.plugins.exceptions import PluginDisabledError
from lib.report.builder import ReportBuilder
from lib.report.html import HtmlReportRenderer
from lib.workflow.arguments import WorkflowArgumentResolver
from lib.workflow.exceptions import WorkflowArgumentError, WorkflowCancelledError, WorkflowError
from lib.workflow.overrides import WorkflowArgumentOverrides
from lib.workflow.selector import WorkflowStepSelector
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

        self._selector = WorkflowStepSelector()

        self._argument_resolver = WorkflowArgumentResolver()

        self._argument_overrides = WorkflowArgumentOverrides()

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
        options: WorkflowExecutionOptions | None = None,
    ) -> None:
        """
        Execute a workflow.
        """

        if options is None:

            options = WorkflowExecutionOptions()

        assert self._context.vault_manager is not None

        assert self._context.vault_manager is not None
        assert self._context.session_manager is not None

        session = self._context.session_manager.require()

        resolver = WorkflowVariableResolver(
            self._context.vault_manager,
            session.user_id,
        )

        selection = self._selector.select(
            workflow.steps,
            tags=options.tags,
            from_step=options.from_step,
            to_step=options.to_step,
        )

        selected_steps = selection.steps

        skip_steps = set(options.skip_steps)

        selected_steps = [
            step
            for step in selected_steps
            if step.name not in skip_steps
        ]

        enabled_steps = [step for step in selected_steps if step.enabled]

        if options.dry_run:

            result = self._validate_dry_run(
                workflow=workflow,
                steps=enabled_steps,
                resolver=resolver,
                options=options,
            )

            self._dry_run(
                workflow,
                enabled_steps,
                result,
            )

            return

        #
        # Create or reuse the execution.
        #

        assert self._context.paths is not None
        assert self._context.executor is not None

        if execution is None:

            variables = dict(
                workflow.variables,
            )

            variables.update(
                options.variables,
            )

            assert self._context.execution_manager is not None

            execution = self._context.execution_manager.create(
                workflow,
                variables=variables,
            )

        runtime = execution.context

        #
        # Resolve persistent job.
        #

        if job_id is None:

            job = self._jobs.create(
                execution_id=execution.id,
                workflow=workflow.name,
                user_id=session.user_id,
                username=session.username,
                full_name=session.full_name,
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


        runtime.set_variables(
            variables,
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
                        plugin=step.plugin,
                    ):

                        self._initialize(
                            runtime,
                            workflow,
                            step,
                            resolver,
                            options.step_overrides.get(
                                step.name,
                            ),
                        )

                        self._execute(
                            runtime,
                            workflow,
                            step,
                        )

                        self._report_step_result(
                            runtime,
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

        except EntropyException:

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

            raise WorkflowError(f"Failed: {traceback.format_exc()}") from exc

        finally:

            #
            # Generate execution report regardless of
            # workflow outcome.
            #

            try:
                self._generate_report(runtime, job)
            except Exception:
                print("Failed to generate execution report:")
                traceback.print_exc()
                # Report generation must never mask the workflow exception.
                pass

    # ------------------------------------------------------------------
    # Initialize
    # ------------------------------------------------------------------

    def _initialize(
        self,
        runtime: ExecutionContext,
        workflow: Workflow,
        step: WorkflowStep,
        resolver: WorkflowVariableResolver,
        overrides: dict[str, Any] | None = None,
    ) -> None:
        """
        Prepare step execution.
        """

        arguments = dict(
            step.arguments,
        )

        if overrides:

            arguments = self._argument_overrides.apply(
                arguments,
                overrides,
            )

        arguments = resolver.resolve(
            arguments,
            runtime.variables,
        )

        arguments = self._argument_resolver.resolve(
            arguments,
            variables=runtime.variables,
            step_results=runtime.step_results,
        )

        runtime.set_arguments(
            arguments,
        )

    # ------------------------------------------------------------------
    # Execute
    # ------------------------------------------------------------------

    def _validate_dry_run(
        self,
        workflow: Workflow,
        steps: list[WorkflowStep],
        resolver: WorkflowVariableResolver,
        options: WorkflowExecutionOptions,
    ) -> WorkflowDryRunResult:
        """
        Validate workflow without executing plugins.

        Dry-run uses the same argument resolution order
        as normal workflow execution.
        """

        result = WorkflowDryRunResult()

        #
        # Workflow variables.
        #
        # Keep definitions unresolved. Individual step arguments
        # will resolve only the variables they actually reference.
        #

        variables = dict(
            workflow.variables,
        )

        variables.update(
            options.variables,
        )

        #
        # Validate selected step arguments.
        #

        for step in steps:

            arguments = dict(
                step.arguments,
            )

            overrides = options.step_overrides.get(
                step.name,
            )

            #
            # Apply CLI step overrides BEFORE variable resolution.
            #

            if overrides:

                try:

                    arguments = self._argument_overrides.apply(
                        arguments,
                        overrides,
                    )

                except WorkflowArgumentError as exc:

                    result.add_error(
                        f"Step '{step.name}': {exc}",
                    )

                    continue

            #
            # Resolve workflow / vault references.
            #

            try:

                arguments = resolver.resolve(
                    arguments,
                    variables,
                )

            except EntropyException as exc:

                result.add_error(
                    f"Step '{step.name}': {exc}",
                )

                continue

            #
            # Resolve workflow step output references.
            #
            # Dry-run has no previous plugin results.
            #

            try:

                arguments = self._argument_resolver.resolve(
                    arguments,
                    variables=variables,
                    step_results={},
                )

            except WorkflowArgumentError as exc:

                result.add_error(
                    f"Step '{step.name}': {exc}",
                )

                continue

            #
            # Validate resolved arguments.
            #

            errors = resolver.validate(
                arguments,
                variables,
            )

            for error in errors:

                result.add_error(
                    f"Step '{step.name}': {error}",
                )

        return result

    def _dry_run(
        self,
        workflow: Workflow,
        steps: list[WorkflowStep],
        result: WorkflowDryRunResult,
    ) -> None:
        """
        Validate and report the selected workflow steps
        without executing plugins.
        """

        assert self._context.ui is not None

        self._context.ui.info(
            f"Workflow: {workflow.name}",
        )

        self._context.ui.info(
            "Mode: Dry Run",
        )

        #
        # Selected steps.
        #

        self._context.ui.table(
            title="Selected Workflow Steps",
            columns=[
                "#",
                "Step",
                "Plugin",
                "Tags",
            ],
            rows=[
                [
                    str(index),
                    step.name,
                    step.plugin,
                    ", ".join(step.tags),
                ]
                for index, step in enumerate(
                    steps,
                    start=1,
                )
            ],
        )

        #
        # Arguments.
        #

        for step in steps:

            if not step.arguments:
                continue

            self._context.ui.info(
                "",
            )

            self._context.ui.info(
                "Arguments",
            )

            self._context.ui.info(
                f"  {step.name}",
            )

            for key, value in step.arguments.items():

                self._context.ui.info(
                    f"    {key:<10} = {value}",
                )

        if result.errors:

            self._context.ui.info(
                "",
            )

            self._context.ui.error(
                "Validation Errors",
            )

            for error in result.errors:

                self._context.ui.error(
                    f"  {error}",
                )

            self._context.ui.error(
                "Dry-run failed. No steps were executed.",
            )

            return

        self._context.ui.info(
            "",
        )

        self._context.ui.success(
            "Validation passed.",
        )

        self._context.ui.info(
            "No steps were executed.",
        )

    def _execute(
        self,
        runtime: ExecutionContext,
        workflow: Workflow,
        step: WorkflowStep,
    ) -> None:
        """
        Execute the workflow plugin and retain its result.
        """

        result = self._plugins.execute(
            context=runtime,
            qualified_name=step.plugin,
        )

        runtime.set_step_result(
            step.name,
            result,
        )

        runtime.emitter("workflow").result(
            execution=runtime.execution,
            node=runtime.node,
            result=result.to_dict(),
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

    # ------------------------------------------------------------------
    # Finalize
    # ------------------------------------------------------------------

    def _report_step_result(
        self,
        runtime: ExecutionContext,
        step: WorkflowStep,
    ) -> None:
        """
        Report a step result unless result rendering is suppressed.
        """

        result = runtime.get_step_result(
            step.name,
        )

        if result is None:
            return

        if step.suppress_result:
            return

        self._report_result(
            step,
            result,
        )

    def _report_result(
        self,
        step: WorkflowStep,
        result: PluginResult,
    ) -> None:
        """
        Report a plugin result.
        """

        assert self._context.ui is not None

        if result.success:

            self._context.ui.info(
                f"Result: {step.name}",
            )

        else:

            self._context.ui.error(
                f"Result: {step.name} failed.",
            )

        self._context.ui.print(
            result.to_dict(),
        )

    # Generate report
    def _generate_report(self, runtime, job):

        job = self._jobs.get(
            job.require_id(),
        )

        events = self._jobs.events(
            job.require_id(),
            limit=None,
        )

        report = ReportBuilder().build(
            job=job,
            events=events,
        )

        report_path = job.workspace / "report.html"

        HtmlReportRenderer().write(
            report,
            report_path,
        )

        self._context.ui.info(f"Execution report generated: {report_path}")

        return report_path
