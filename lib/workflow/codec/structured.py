"""
Shared structured workflow codec.
"""

from __future__ import annotations

from typing import Any

from lib.models.workflow import (
    Workflow,
    WorkflowStep,
    WorkflowWorkspace,
)
from lib.workflow.exceptions import InvalidWorkflowError

from .base import WorkflowCodec


class StructuredWorkflowCodec(
    WorkflowCodec,
):
    """
    Shared implementation for structured workflow formats.

    JSON and YAML use the same logical workflow structure.
    This class owns the mapping <-> model conversion.

    Concrete codecs are responsible only for format-specific
    filesystem operations.
    """

    # ------------------------------------------------------------------
    # Mapping → Model
    # ------------------------------------------------------------------

    @classmethod
    def _from_mapping(
        cls,
        value: Any,
    ) -> Workflow:
        """
        Convert a structured mapping into a Workflow.
        """

        if not isinstance(
            value,
            dict,
        ):

            raise InvalidWorkflowError(
                "Workflow definition must be an object.",
            )

        name = value.get(
            "name",
        )

        version = value.get(
            "version",
        )

        description = value.get(
            "description",
        )

        if (
            not isinstance(
                name,
                str,
            )
            or not name.strip()
        ):

            raise InvalidWorkflowError(
                "Workflow 'name' must be a non-empty string.",
            )

        if (
            not isinstance(
                version,
                str,
            )
            or not version.strip()
        ):

            raise InvalidWorkflowError(
                "Workflow 'version' must be a non-empty string.",
            )

        if description is not None and not isinstance(
            description,
            str,
        ):

            raise InvalidWorkflowError(
                "Workflow 'description' must be a string or null.",
            )

        variables = value.get(
            "variables",
            {},
        )

        if not isinstance(
            variables,
            dict,
        ):

            raise InvalidWorkflowError(
                "Workflow 'variables' must be an object.",
            )

        workspace_value = value.get(
            "workspace",
        )

        workspace = None

        if workspace_value is not None:

            if not isinstance(
                workspace_value,
                dict,
            ):

                raise InvalidWorkflowError(
                    "Workflow 'workspace' must be an object.",
                )

            add_text = workspace_value.get(
                "add_text",
                False,
            )

            if not isinstance(
                add_text,
                bool,
            ):

                raise InvalidWorkflowError(
                    "Workflow workspace 'add_text' must be a boolean.",
                )

            position = workspace_value.get(
                "position",
                "before",
            )

            if not isinstance(
                position,
                str,
            ):

                raise InvalidWorkflowError(
                    "Workflow workspace 'position' must be a string.",
                )

            workspace_type = workspace_value.get(
                "type",
                "variable",
            )

            if not isinstance(
                workspace_type,
                str,
            ):

                raise InvalidWorkflowError(
                    "Workflow workspace 'type' must be a string.",
                )

            workspace_name = workspace_value.get(
                "name",
            )

            if workspace_name is not None and not isinstance(
                workspace_name,
                str,
            ):

                raise InvalidWorkflowError(
                    "Workflow workspace 'name' must be a string or null.",
                )

            workspace = WorkflowWorkspace(
                add_text=add_text,
                position=position,
                type=workspace_type,
                name=workspace_name,
            )

        steps_value = value.get(
            "steps",
            [],
        )

        if not isinstance(
            steps_value,
            list,
        ):

            raise InvalidWorkflowError(
                "Workflow 'steps' must be an array.",
            )

        steps = [
            cls._step_from_mapping(
                item,
            )
            for item in steps_value
        ]

        return Workflow(
            name=name,
            version=version,
            description=description,
            variables=variables,
            workspace=workspace,
            steps=steps,
        )

    # ------------------------------------------------------------------
    # Step Mapping → Model
    # ------------------------------------------------------------------

    @classmethod
    def _step_from_mapping(
        cls,
        value: Any,
    ) -> WorkflowStep:
        """
        Convert a structured mapping into a WorkflowStep.
        """

        if not isinstance(
            value,
            dict,
        ):

            raise InvalidWorkflowError(
                "Each workflow step must be an object.",
            )

        name = value.get(
            "name",
        )

        plugin = value.get(
            "plugin",
        )

        if (
            not isinstance(
                name,
                str,
            )
            or not name.strip()
        ):

            raise InvalidWorkflowError(
                "Workflow step 'name' must be a " "non-empty string.",
            )

        if (
            not isinstance(
                plugin,
                str,
            )
            or not plugin.strip()
        ):

            raise InvalidWorkflowError(
                "Workflow step 'plugin' must be a " "non-empty string.",
            )

        arguments = value.get(
            "arguments",
            {},
        )

        if not isinstance(
            arguments,
            dict,
        ):

            raise InvalidWorkflowError(
                f"Arguments for workflow step '{name}' " "must be an object.",
            )

        enabled = value.get(
            "enabled",
            True,
        )

        if not isinstance(
            enabled,
            bool,
        ):

            raise InvalidWorkflowError(
                f"'enabled' for workflow step '{name}' " "must be a boolean.",
            )

        tags = value.get(
            "tags",
            [],
        )

        if not isinstance(
            tags,
            list,
        ):

            raise InvalidWorkflowError(
                f"'tags' for workflow step '{name}' " "must be an array.",
            )

        if not all(
            isinstance(
                tag,
                str,
            )
            for tag in tags
        ):

            raise InvalidWorkflowError(
                f"'tags' for workflow step '{name}' " "must contain only strings.",
            )

        on_failure = value.get(
            "on_failure",
            "abort",
        )

        if not isinstance(
            on_failure,
            str,
        ):

            raise InvalidWorkflowError(
                f"'on_failure' for workflow step '{name}' " "must be a string.",
            )

        on_failure = on_failure.strip().lower()

        if on_failure not in {
            "abort",
            "continue",
        }:

            raise InvalidWorkflowError(
                f"Unsupported 'on_failure' policy '{on_failure}' "
                f"for workflow step '{name}'. "
                "Supported values: abort, continue.",
            )

        suppress_result = value.get(
            "suppress_result",
            False,
        )

        if not isinstance(
            suppress_result,
            bool,
        ):

            raise InvalidWorkflowError(
                f"'suppress_result' for workflow step '{name}' " "must be a boolean.",
            )

        return WorkflowStep(
            name=name,
            plugin=plugin,
            arguments=arguments,
            enabled=enabled,
            tags=list(tags),
            on_failure=on_failure,
            suppress_result=suppress_result,
        )

    # ------------------------------------------------------------------
    # Model → Mapping
    # ------------------------------------------------------------------

    @classmethod
    def _to_mapping(
        cls,
        workflow: Workflow,
    ) -> dict[str, Any]:
        """
        Convert a Workflow into a structured mapping.
        """

        mapping = {
            "name": workflow.name,
            "version": workflow.version,
            "description": workflow.description,
            "variables": workflow.variables,
            "steps": [
                cls._step_to_mapping(
                    step,
                )
                for step in workflow.steps
            ],
        }

        if workflow.workspace is not None:
            mapping["workspace"] = cls._workspace_to_mapping(
                workflow.workspace,
            )

        return mapping

    @staticmethod
    def _workspace_to_mapping(
        workspace: WorkflowWorkspace | None,
    ) -> dict[str, Any] | None:
        """
        Convert a WorkflowWorkspace into a structured mapping.
        """

        if workspace is None:
            return None

        return {
            "add_text": workspace.add_text,
            "position": workspace.position,
            "type": workspace.type,
            "name": workspace.name,
        }

    # ------------------------------------------------------------------
    # Step Model → Mapping
    # ------------------------------------------------------------------

    @staticmethod
    def _step_to_mapping(
        step: WorkflowStep,
    ) -> dict[str, Any]:
        """
        Convert a WorkflowStep into a structured mapping.
        """

        return {
            "name": step.name,
            "plugin": step.plugin,
            "enabled": step.enabled,
            "tags": list(
                step.tags,
            ),
            "on_failure": step.on_failure,
            "arguments": step.arguments,
            "suppress_result": step.suppress_result,
        }
