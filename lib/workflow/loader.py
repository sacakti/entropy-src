"""
Workflow loader.
"""

from __future__ import annotations

from pathlib import Path

from core.context import EntropyContext
from lib.models.workflow import Workflow

from .exceptions import (
    InvalidWorkflowError,
    WorkflowNotFoundError,
)


class WorkflowLoader:
    """
    Loads workflow definitions.
    """

    def __init__(
        self,
        context: EntropyContext,
    ) -> None:

        assert context.executor is not None
        assert context.workflow_codecs is not None

        self._executor = context.executor
        self._codecs = context.workflow_codecs

    # ------------------------------------------------------------------
    # Public
    # ------------------------------------------------------------------

    def load(
        self,
        workflow: Path,
    ) -> Workflow:
        """
        Load a workflow definition.
        """

        workflow = self._executor.path(
            str(workflow),
        )

        if not self._executor.exists(
            workflow,
        ):

            raise WorkflowNotFoundError(
                workflow,
            )

        try:

            codec = self._codecs.for_path(
                workflow,
            )

            return codec.decode_file(
                workflow,
            )

        except (
            WorkflowNotFoundError,
            InvalidWorkflowError,
        ):

            raise

        except Exception as exc:

            raise InvalidWorkflowError(
                f"Unable to load workflow "
                f"'{workflow}': {exc}",
            ) from exc
