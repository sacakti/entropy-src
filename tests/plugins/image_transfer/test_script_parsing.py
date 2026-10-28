"""
Tests for custom.image_transfer script parsing: credentials removed from
docker login and oc login, and invalid shell syntax reported clearly.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from resources.plugins.custom.image_transfer.exceptions import ImageTransferError
from resources.plugins.custom.image_transfer.plugin import ImageTransferPlugin


def _plugin() -> ImageTransferPlugin:
    return ImageTransferPlugin(MagicMock())


def _logins(script: str) -> list[list[str]]:
    return [
        command for command in _plugin()._extract_docker_commands(script) if command[1] == "login"
    ]


@pytest.mark.parametrize(
    "line",
    [
        "docker login quay.io/sacakti $user $password",
        "docker login quay.io/sacakti $1 $2",
        "docker login quay.io/sacakti -u $1 -p $2",
        "docker login quay.io/sacakti --username $1 --password $2",
        "docker login quay.io/sacakti --username=$1 --password=$2",
        "docker login -u $1 -p $2 quay.io/sacakti",
    ],
)
def test_docker_login_credentials_are_removed(line):
    assert _logins(line) == [["docker", "login", "quay.io/sacakti"]]


def test_docker_login_keeps_other_options():
    assert _logins("docker login quay.io/sacakti --password-stdin") == [
        ["docker", "login", "quay.io/sacakti", "--password-stdin"],
    ]


def test_docker_login_without_registry_fails():
    with pytest.raises(ImageTransferError, match="missing the registry"):
        _logins("docker login -u $1 -p $2")


@pytest.mark.parametrize(
    ("line", "expected"),
    [
        ("oc login $1 $2", "oc login"),
        ("oc login -u $1 -p $2 https://api.cluster:6443", "oc login https://api.cluster:6443"),
        (
            "oc login --username=$user --password=$password https://api.cluster:6443",
            "oc login https://api.cluster:6443",
        ),
        ("oc login --token $TOKEN https://api.cluster:6443", "oc login https://api.cluster:6443"),
        (
            "oc login https://api.cluster:6443 --insecure-skip-tls-verify",
            "oc login https://api.cluster:6443 --insecure-skip-tls-verify",
        ),
    ],
)
def test_oc_login_credentials_are_removed(line, expected):
    prepared, _ = _plugin()._transform_apply_script(
        f"{line}\n",
        Path("/releases/H001"),
        Path("/home/devops"),
    )

    assert prepared == f"{expected}\n"


def test_invalid_shell_syntax_in_transfer_script_is_reported():
    with pytest.raises(
        ImageTransferError, match="Invalid shell syntax in image_transfer.sh at line 2"
    ):
        _plugin()._extract_docker_commands(
            "docker login quay.io/sacakti\ndocker pull 'quay.io/sacakti/app:1.0\n",
        )


def test_invalid_shell_syntax_in_oc_login_is_reported():
    with pytest.raises(ImageTransferError, match="Invalid shell syntax in apply_yaml.sh"):
        _plugin()._transform_apply_script(
            "oc login 'https://api.cluster:6443\n",
            Path("/releases/H001"),
            Path("/home/devops"),
        )


def test_unparsable_line_is_not_treated_as_git_command():
    prepared, _ = _plugin()._transform_apply_script(
        "echo 'unterminated\n",
        Path("/releases/H001"),
        Path("/home/devops"),
    )

    assert prepared == "echo 'unterminated\n"


def test_non_numeric_df_output_is_reported():
    output = "Filesystem 1K-blocks Used Available Use% Mounted\n/dev/disk1 100 50 n/a 50% /\n"

    with pytest.raises(ImageTransferError, match="Invalid available-space value"):
        _plugin()._parse_df_free_bytes(output)
