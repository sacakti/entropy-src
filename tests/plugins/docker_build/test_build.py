"""
Tests for the docker.build plugin.

These tests mock Docker itself and verify that the plugin:
- accepts multiple image specifications;
- processes images one by one;
- constructs the expected Docker build command;
- aggregates successful results;
- stops on the first failed image;
- supports tag_image=False.

The tests intentionally use lightweight fake SDK objects so they can run
without Docker being installed.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import Mock

import pytest

from resources.plugins.docker.build.plugin import BuildPlugin


@dataclass
class FakeProcessResult:
    """Fake result returned by self.shell.run()."""

    exit_code: int
    success: bool
    stdout: str = ""
    stderr: str = ""
    duration: float = 0.0

    @property
    def failed(self) -> bool:
        """Return whether the process failed."""

        return not self.success


class FakeArguments:
    """Minimal implementation of PluginArguments used by BuildPlugin."""

    def __init__(self, values: dict[str, Any]) -> None:
        self.values = values

    def get(
        self,
        name: str,
        default: Any = None,
    ) -> Any:
        return self.values.get(name, default)

    def boolean(
        self,
        name: str,
        default: bool = False,
    ) -> bool:
        value = self.values.get(name, default)

        if not isinstance(value, bool):
            raise ValueError(
                f"Argument '{name}' must be a boolean.",
            )

        return value


class FakeFilesystem:
    """Minimal filesystem implementation required by BuildPlugin."""

    def exists(
        self,
        path: str | Path,
    ) -> bool:
        return True

    def is_directory(
        self,
        path: str | Path,
    ) -> bool:
        return True


class FakeContext:
    """Minimal PluginContext implementation required by BasePlugin."""

    def __init__(
        self,
        arguments: dict[str, Any],
    ) -> None:
        self.arguments = FakeArguments(arguments)
        self.outputs: dict[str, Any] = {}
        self.artifacts: dict[str, Path] = {}
        self.filesystem = FakeFilesystem()
        self.shell = Mock()
        self.message = Mock()
        self.log = Mock()
        self.ui = Mock()

        self.mode = SimpleNamespace()
        self.interactive = True
        self.automated = False
        self.variables = {}
        self.workspace = Path("/tmp")
        self.path = Path
        self.archive = Mock()
        self.environment = Mock()
        self.information = Mock()
        self.configuration = Mock()
        self.template = Mock()
        self.database = Mock()
        self.user = "test"

        self.activity = MockActivity()


class MockActivity:
    """Context manager used instead of the real activity implementation."""

    def __call__(
        self,
        name: str,
        metadata: dict[str, Any] | None = None,
    ) -> "MockActivity":
        return self

    def __enter__(self) -> "MockActivity":
        return self

    def __exit__(
        self,
        exc_type: Any,
        exc_value: Any,
        traceback: Any,
    ) -> bool:
        return False


def create_plugin(
    arguments: dict[str, Any],
) -> tuple[BuildPlugin, FakeContext]:
    """Create a BuildPlugin with a mocked SDK context."""

    context = FakeContext(arguments)
    plugin = BuildPlugin(context)
    return plugin, context


def multi_image_arguments() -> dict[str, Any]:
    """Return a representative multi-image build specification."""

    return {
        "images": {
            "service-1": {
                "dockerfile": "/mock/service-1/Dockerfile",
                "context": "/mock/service-1",
                "image_name": "service-1",
                "image_tag": "1.1.7",
            },
            "service-2": {
                "dockerfile": "/mock/service-2/Dockerfile",
                "context": "/mock/service-2",
                "image_name": "service-2",
                "image_tag": "1.1.7",
            },
            "service-3": {
                "dockerfile": "/mock/service-3/Dockerfile",
                "context": "/mock/service-3",
                "image_name": "service-3",
                "image_tag": "1.1.7",
            },
        },
        "image_registry": "quay.io/company",
        "tag_image": True,
    }


def test_multiple_images_are_built_sequentially() -> None:
    """
    Verify that each image is processed independently and in order.
    """

    plugin, context = create_plugin(
        multi_image_arguments(),
    )

    context.shell.run.side_effect = [
        FakeProcessResult(
            exit_code=0,
            success=True,
            stdout="service-1 built",
            duration=1.0,
        ),
        FakeProcessResult(
            exit_code=0,
            success=True,
            stdout="service-2 built",
            duration=1.1,
        ),
        FakeProcessResult(
            exit_code=0,
            success=True,
            stdout="service-3 built",
            duration=1.2,
        ),
    ]

    result = plugin.execute()

    assert result.success is True
    assert result.changed is True

    assert result.outputs["count"] == 3
    assert result.outputs["tag_image"] is True
    assert result.outputs["image_registry"] == "quay.io/company"

    assert context.shell.run.call_count == 3

    calls = context.shell.run.call_args_list

    assert calls[0].args[0] == [
        "docker",
        "build",
        "-f",
        "/mock/service-1/Dockerfile",
        "-t",
        "quay.io/company/service-1:1.1.7",
        "/mock/service-1",
    ]

    assert calls[1].args[0] == [
        "docker",
        "build",
        "-f",
        "/mock/service-2/Dockerfile",
        "-t",
        "quay.io/company/service-2:1.1.7",
        "/mock/service-2",
    ]

    assert calls[2].args[0] == [
        "docker",
        "build",
        "-f",
        "/mock/service-3/Dockerfile",
        "-t",
        "quay.io/company/service-3:1.1.7",
        "/mock/service-3",
    ]

    assert list(
        result.outputs["images"],
    ) == [
        "service-1",
        "service-2",
        "service-3",
    ]


def test_build_stops_when_an_image_fails() -> None:
    """
    Verify that a failed image stops subsequent builds.
    """

    plugin, context = create_plugin(
        multi_image_arguments(),
    )

    context.shell.run.side_effect = [
        FakeProcessResult(
            exit_code=0,
            success=True,
            stdout="service-1 built",
            duration=1.0,
        ),
        FakeProcessResult(
            exit_code=1,
            success=False,
            stdout="",
            stderr="Docker build failed",
            duration=1.0,
        ),
    ]

    result = plugin.execute()

    assert result.success is False

    # The first image was built, so this was a partial change.
    assert result.changed is True

    assert context.shell.run.call_count == 2

    assert "service-1" in result.outputs["images"]
    assert "service-2" not in result.outputs["images"]
    assert "service-3" not in result.outputs["images"]

    assert result.errors == [
        "Docker build failed for image 'service-2' with exit code 1.",
    ]


def test_build_without_image_tagging() -> None:
    """
    Verify that tag_image=False does not add -t to docker build.
    """

    arguments = {
        "dockerfile": "/mock/service/Dockerfile",
        "context": "/mock/service",
        "image_name": "service",
        "image_tag": "1.1.7",
        "image_registry": "quay.io/company",
        "tag_image": False,
    }

    plugin, context = create_plugin(
        arguments,
    )

    context.shell.run.return_value = FakeProcessResult(
        exit_code=0,
        success=True,
        stdout="built",
        duration=1.0,
    )

    result = plugin.execute()

    assert result.success is True
    assert result.changed is True

    command = context.shell.run.call_args.args[0]

    assert command == [
        "docker",
        "build",
        "-f",
        "/mock/service/Dockerfile",
        "/mock/service",
    ]

    assert "-t" not in command


def test_single_image_build_is_supported() -> None:
    """
    Verify the single-image argument model.
    """

    arguments = {
        "dockerfile": "/mock/service/Dockerfile",
        "context": "/mock/service",
        "image_name": "service",
        "image_tag": "1.1.7",
        "image_registry": "quay.io/company",
        "tag_image": True,
    }

    plugin, context = create_plugin(
        arguments,
    )

    context.shell.run.return_value = FakeProcessResult(
        exit_code=0,
        success=True,
        stdout="built",
        duration=1.0,
    )

    result = plugin.execute()

    assert result.success is True
    assert result.outputs["count"] == 1

    command = context.shell.run.call_args.args[0]

    assert command == [
        "docker",
        "build",
        "-f",
        "/mock/service/Dockerfile",
        "-t",
        "quay.io/company/service:1.1.7",
        "/mock/service",
    ]


def test_missing_image_registry_when_tagging_fails() -> None:
    """
    Verify that tagging requires an image registry.
    """

    arguments = {
        "dockerfile": "/mock/service/Dockerfile",
        "context": "/mock/service",
        "image_name": "service",
        "image_tag": "1.1.7",
        "tag_image": True,
    }

    plugin, context = create_plugin(
        arguments,
    )

    result = plugin.execute()

    assert result.success is False
    assert result.changed is False

    assert result.errors == [
        (
            "Argument 'image_registry' is required when "
            "'tag_image' is true."
        ),
    ]

    context.shell.run.assert_not_called()


def test_empty_images_fails() -> None:
    """
    Verify that an empty multi-image specification is rejected.
    """

    plugin, context = create_plugin(
        {
            "images": {},
            "image_registry": "quay.io/company",
            "tag_image": True,
        },
    )

    result = plugin.execute()

    assert result.success is False
    assert result.changed is False

    assert result.errors == [
        "At least one Docker image build must be specified.",
    ]

    context.shell.run.assert_not_called()


def test_images_and_single_image_arguments_cannot_be_combined() -> None:
    """
    Verify that the two input models are mutually exclusive.
    """

    arguments = multi_image_arguments()

    arguments.update(
        {
            "dockerfile": "/mock/other/Dockerfile",
            "context": "/mock/other",
            "image_name": "other",
            "image_tag": "1.1.7",
        },
    )

    plugin, context = create_plugin(
        arguments,
    )

    result = plugin.execute()

    assert result.success is False
    assert result.changed is False

    assert result.errors == [
        (
            "Use either 'images' or the single-image "
            "arguments, not both."
        ),
    ]

    context.shell.run.assert_not_called()


def test_docker_stdout_is_logged() -> None:
    """
    Verify Docker stdout is sent to the plugin logger.
    """

    plugin, context = create_plugin(
        {
            "dockerfile": "/mock/service/Dockerfile",
            "context": "/mock/service",
            "image_name": "service",
            "image_tag": "1.1.7",
            "image_registry": "quay.io/company",
            "tag_image": True,
        },
    )

    context.shell.run.return_value = FakeProcessResult(
        exit_code=0,
        success=True,
        stdout="Docker build output",
        duration=1.0,
    )

    plugin.execute()

    context.log.info.assert_any_call(
        "Docker build output",
    )


def test_docker_stderr_is_logged_as_warning_on_success() -> None:
    """
    Verify Docker stderr is logged as warning when build succeeds.
    """

    plugin, context = create_plugin(
        {
            "dockerfile": "/mock/service/Dockerfile",
            "context": "/mock/service",
            "image_name": "service",
            "image_tag": "1.1.7",
            "image_registry": "quay.io/company",
            "tag_image": True,
        },
    )

    context.shell.run.return_value = FakeProcessResult(
        exit_code=0,
        success=True,
        stdout="",
        stderr="Docker warning",
        duration=1.0,
    )

    plugin.execute()

    assert context.log.warning.called


def test_docker_stderr_is_logged_as_error_on_failure() -> None:
    """
    Verify Docker stderr is logged as error when build fails.
    """

    plugin, context = create_plugin(
        {
            "dockerfile": "/mock/service/Dockerfile",
            "context": "/mock/service",
            "image_name": "service",
            "image_tag": "1.1.7",
            "image_registry": "quay.io/company",
            "tag_image": True,
        },
    )

    context.shell.run.return_value = FakeProcessResult(
        exit_code=1,
        success=False,
        stdout="",
        stderr="Docker build failed",
        duration=1.0,
    )

    result = plugin.execute()

    assert result.success is False
    assert context.log.error.called

def test_docker_unavailable_returns_failure_result() -> None:
    plugin, context = create_plugin(
        {
            "dockerfile": "/mock/service/Dockerfile",
            "context": "/mock/service",
            "image_name": "service",
            "image_tag": "1.1.7",
            "image_registry": "quay.io/company",
            "tag_image": True,
        },
    )

    # Docker unavailable by default.

    result = plugin.execute()

    assert result.success is False
    assert result.changed is False
    assert result.errors == [
        "Docker is not available on this system.",
    ]

    context.shell.run.assert_not_called()

def test_single_image_build_is_supported(
    monkeypatch,
) -> None:

    plugin, context = create_plugin(
        {
            "dockerfile": "/mock/service/Dockerfile",
            "context": "/mock/service",
            "image_name": "service",
            "image_tag": "1.1.7",
            "image_registry": "quay.io/company",
            "tag_image": True,
        },
    )

    monkeypatch.setattr(
        plugin,
        "_docker_available",
        lambda: True,
    )

    context.shell.run.return_value = FakeProcessResult(
        exit_code=0,
        success=True,
        stdout="built",
        duration=1.0,
    )

    result = plugin.execute()

    assert result.success is True
