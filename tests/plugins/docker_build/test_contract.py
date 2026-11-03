"""docker.build's declared contract: it must install, and accept how it is called."""

from __future__ import annotations

from pathlib import Path

import pytest

from lib.plugins.contract import (
    ContractError,
    check_arguments,
    check_source,
    declared,
    read_manifest,
)

DIRECTORY = Path(__file__).resolve().parents[3] / "resources" / "plugins" / "docker" / "build"


@pytest.fixture()
def contract():
    found = declared(read_manifest(DIRECTORY))
    assert found is not None
    return found


def test_the_installer_accepts_it(contract) -> None:
    assert check_source(DIRECTORY, contract) == []


@pytest.mark.parametrize(
    "values",
    [
        # What consolidate.images sends when no release has an image to build.
        {"images": {}},
        {
            "images": {
                "app": {
                    "dockerfile": "/d/Dockerfile",
                    "context": "/d",
                    "image_name": "app",
                    "image_tag": "1.0",
                }
            }
        },
        {
            "dockerfile": "/d/Dockerfile",
            "context": "/d",
            "image_name": "app",
            "image_tag": "1.1.10",
            "image_registry": "quay.io/project1",
            "tag_image": True,
        },
        {},
    ],
)
def test_how_it_is_called_is_accepted_unchanged(contract, values) -> None:
    arguments = check_arguments(contract, values)

    for name, value in values.items():
        assert arguments[name] == value


def test_nothing_appears_that_would_look_like_single_image_arguments(contract) -> None:
    # Giving 'images' and any of these is refused, so a default here would break it.
    arguments = check_arguments(contract, {"images": {}})

    for name in ("dockerfile", "context", "image_name", "image_tag"):
        assert arguments.get(name) is None


def test_tag_image_defaults_on(contract) -> None:
    assert check_arguments(contract, {}).get("tag_image") is True


def test_images_must_be_a_dictionary(contract) -> None:
    with pytest.raises(ContractError):
        check_arguments(contract, {"images": "app"})
