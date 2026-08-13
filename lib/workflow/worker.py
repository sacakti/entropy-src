"""
Workflow background worker.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
import json

def bootstrap(
    project_root: Path,
    python_packages: Path,
) -> None:
    """
    Bootstrap import paths for the detached worker.
    """

    paths = (
        project_root,
        python_packages,
    )

    for path in paths:

        if not path.exists():
            continue

        value = str(
            path,
        )

        if value not in sys.path:

            sys.path.insert(
                0,
                value,
            )


def _parse_args() -> argparse.Namespace:
    """
    Parse worker process arguments.
    """

    parser = argparse.ArgumentParser(
        description="Entropy workflow worker.",
    )

    parser.add_argument(
        "job_id",
        type=int,
    )

    parser.add_argument(
        "workflow",
        type=Path,
    )

    parser.add_argument(
        "--project-root",
        type=Path,
        required=True,
    )

    parser.add_argument(
        "--python-packages",
        type=Path,
        required=True,
    )

    parser.add_argument(
        "--tags",
        default="",
        help="Comma-separated workflow step tags.",
    )

    parser.add_argument(
        "--from-step",
        default=None,
        help="First workflow step to execute.",
    )

    parser.add_argument(
        "--to-step",
        default=None,
        help="Last workflow step to execute.",
    )

    parser.add_argument(
        "--options",
        default="{}",
        help="Serialized workflow execution options.",
    )

    return parser.parse_args()


class WorkflowWorker:
    """
    Executes a workflow inside a background worker process.

    The parent process creates the persistent job. The worker
    attaches to that job and executes the workflow.
    """

    def __init__(
        self,
        job_id: int,
        workflow: Path,
        *,
        tags: tuple[str, ...] = (),
        from_step: str | None = None,
        to_step: str | None = None,
        variables: dict[str, object] | None = None,
        step_overrides: dict[str, dict[str, object]] | None = None,
    ) -> None:

        self._job_id = job_id
        self._workflow = workflow
        self._tags = tags
        self._from_step = from_step
        self._to_step = to_step
        self._variables = variables or {}
        self._step_overrides = step_overrides or {}

    # ------------------------------------------------------------------
    # Execute
    # ------------------------------------------------------------------

    def execute(
        self,
    ) -> None:
        """
        Execute the workflow in the worker process.
        """

        from core.context_factory import ContextFactory
        from lib.models.workflow import WorkflowExecutionOptions
        from lib.workflow.exceptions import WorkflowCancelledError

        factory = ContextFactory(
            interactive=False,
        )

        context = factory.build()

        factory.discover()

        options = WorkflowExecutionOptions(
            tags=self._tags,
            from_step=self._from_step,
            to_step=self._to_step,
            dry_run=False,
            variables=self._variables,
            step_overrides=self._step_overrides,
        )

        try:

            assert context.workflow_manager is not None
            assert context.workflow_job_manager is not None

            #
            # Verify that the parent-created job exists and is queued.
            #

            context.workflow_job_manager.attach(
                self._job_id,
            )

            #
            # Execute using the existing persistent job.
            #

            context.workflow_manager.run(
                file=self._workflow,
                job_id=self._job_id,
                options=options,
            )

        except WorkflowCancelledError:

            raise


# ------------------------------------------------------------------
# Entry point
# ------------------------------------------------------------------

if __name__ == "__main__":

    args = _parse_args()

    bootstrap(
        args.project_root,
        args.python_packages,
    )

    tags = tuple(
        tag.strip()
        for tag in args.tags.split(",")
        if tag.strip()
    )

    options = json.loads(
        args.options,
    )

    worker = WorkflowWorker(
        job_id=args.job_id,
        workflow=args.workflow,
        tags=tags,
        from_step=args.from_step,
        to_step=args.to_step,
        variables=options.get(
            "variables",
            {},
        ),
        step_overrides=options.get(
            "step_overrides",
            {},
        ),
    )

    worker.execute()
