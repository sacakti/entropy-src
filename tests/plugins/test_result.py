from lib.models.plugin import PluginResult


def test_result_defaults() -> None:
    result = PluginResult()

    assert result.success is True
    assert result.changed is False
    assert result.outputs == {}
    assert result.changes == []
    assert result.errors == []
    assert result.warnings == []
    assert result.metadata == {}


def test_result_accepts_execution_data() -> None:
    result = PluginResult(
        success=True,
        changed=True,
        outputs={
            "image": "quay.io/example/app:1.2.3",
        },
        changes=[
            {
                "action": "build",
                "image": "quay.io/example/app:1.2.3",
            },
        ],
        warnings=[
            "Existing image was replaced.",
        ],
        metadata={
            "plugin": "docker_build",
        },
    )

    assert result.success is True
    assert result.changed is True
    assert result.outputs["image"] == ("quay.io/example/app:1.2.3")
    assert len(result.changes) == 1
    assert result.warnings == [
        "Existing image was replaced.",
    ]
    assert result.metadata["plugin"] == "docker_build"


def test_result_can_represent_failure() -> None:
    result = PluginResult(
        success=False,
        errors=[
            {
                "code": "IMAGE_BUILD_FAILED",
                "message": "Docker build failed.",
            },
        ],
    )

    assert result.success is False
    assert result.errors[0]["code"] == ("IMAGE_BUILD_FAILED")


def test_result_to_dict() -> None:
    result = PluginResult(
        success=True,
        changed=True,
        outputs={
            "release": "/release/app.zip",
        },
    )

    data = result.to_dict()

    assert data == {
        "success": True,
        "changed": True,
        "outputs": {
            "release": "/release/app.zip",
        },
        "changes": [],
        "errors": [],
        "warnings": [],
        "metadata": {},
    }


def test_result_mutable_defaults_are_independent() -> None:
    first = PluginResult()
    second = PluginResult()

    first.outputs["value"] = 1
    first.changes.append(
        {
            "action": "test",
        },
    )

    assert second.outputs == {}
    assert second.changes == []
