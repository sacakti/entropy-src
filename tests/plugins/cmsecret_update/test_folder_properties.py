"""
Folder-mode properties updates through the real loader and YAML layer.
"""

from __future__ import annotations

import base64
from pathlib import Path

import pytest
from cm_secret_update.engine import ConfigMapSecretUpdateEngine
from cm_secret_update.loader import ConfigMapSecretUpdateLoader
from cm_secret_update.model import ConfigMapSecretUpdate, SourceType
from cm_secret_update.target_loader import ConfigMapSecretTargetLoader
from cm_secret_update.updater import ConfigMapSecretUpdater

from lib.executor.filesystem import FileSystemMixin

UPDATE = """\
# Comment in the update definition
apiVersion: entropy/v1
kind: ConfigMapSecretUpdate
target:
  kind: {kind}
  name: app
operations:
  - action: update
    key: application.properties
    format: properties
    entries:
      server.port: "9090"
      new.key: added
"""

WITH_COMMENTS = "# header\nserver.port=8080\n! note\nother=1\n"
WITH_COMMENTS_UPDATED = "# header\nserver.port=9090\n! note\nother=1\nnew.key=added\n"
WITHOUT_COMMENTS = "server.port=8080\nother=1\n"
WITHOUT_COMMENTS_UPDATED = "server.port=9090\nother=1\nnew.key=added\n"

CASES = [
    (WITH_COMMENTS, WITH_COMMENTS_UPDATED),
    (WITHOUT_COMMENTS, WITHOUT_COMMENTS_UPDATED),
]


def _configmap(body: str) -> str:
    block = "".join(f"    {line}\n" for line in body.splitlines())

    return (
        "apiVersion: v1\nkind: ConfigMap\nmetadata:\n  name: app\n"
        f"data:\n  application.properties: |\n{block}"
    )


def _secret(body: str) -> str:
    encoded = base64.b64encode(body.encode()).decode()

    return (
        "apiVersion: v1\nkind: Secret\nmetadata:\n  name: app\n"
        f"data:\n  application.properties: {encoded}\n"
    )


def _run(tmp_path: Path, kind: str, target: str) -> dict:
    filesystem = FileSystemMixin()

    source_dir = tmp_path / "source"
    target_dir = tmp_path / "target"
    source_dir.mkdir()
    target_dir.mkdir()

    (source_dir / "update.yaml").write_text(UPDATE.format(kind=kind))
    (target_dir / "app.yaml").write_text(target)

    summary = ConfigMapSecretUpdater(
        engine=ConfigMapSecretUpdateEngine(
            yaml_loader=filesystem.parse_yaml,
            yaml_dumper=filesystem.serialize_yaml,
        ),
        filesystem=filesystem,
    ).update(
        ConfigMapSecretUpdateLoader(filesystem=filesystem).load_directory(source_dir),
        ConfigMapSecretTargetLoader(filesystem=filesystem).load_directory(target_dir),
        target_directory=target_dir,
    )

    assert summary.errors == []

    return filesystem.parse_yaml((target_dir / "app.yaml").read_text())


def test_loader_returns_update_definition_once(tmp_path: Path) -> None:
    path = tmp_path / "update.yaml"
    path.write_text(UPDATE.format(kind="ConfigMap"))

    source = ConfigMapSecretUpdateLoader(filesystem=FileSystemMixin()).load_file(path)[0]

    assert source.source_type == SourceType.UPDATE
    assert isinstance(source.update, ConfigMapSecretUpdate)
    assert source.path == path
    assert (source.kind, source.name) == ("ConfigMap", "app")


@pytest.mark.parametrize(("body", "expected"), CASES)
def test_configmap_properties_update(tmp_path: Path, body: str, expected: str) -> None:
    document = _run(tmp_path, "ConfigMap", _configmap(body))

    assert document["data"]["application.properties"] == expected


@pytest.mark.parametrize(("body", "expected"), CASES)
def test_secret_properties_update(tmp_path: Path, body: str, expected: str) -> None:
    document = _run(tmp_path, "Secret", _secret(body))

    decoded = base64.b64decode(document["data"]["application.properties"]).decode()

    assert decoded == expected


COMMENTED_UPDATE = """\
apiVersion: entropy/v1
kind: ConfigMapSecretUpdate
target:
  kind: {kind}
  name: app
operations:
  - action: add
    format: properties
    key: application.properties
    entries:
      # first
      server.port: 9090 # inline
      # second line one
      # second line two

      new.key: added
      # trailing
    # belongs to the next operation
  - action: add
    format: properties
    key: other.properties
    entries:
      plain: value
"""

COMMENTED_EXPECTED = (
    "# existing\n"
    "# first\n"
    "# inline\n"
    "server.port=9090\n"
    "other=1\n"
    "# second line one\n"
    "# second line two\n"
    "new.key=added\n"
    "# trailing\n"
)


def _run_commented(tmp_path: Path, kind: str, target: str, runs: int = 1) -> dict:
    filesystem = FileSystemMixin()

    source_dir = tmp_path / "source"
    target_dir = tmp_path / "target"
    source_dir.mkdir()
    target_dir.mkdir()

    (source_dir / "update.yaml").write_text(COMMENTED_UPDATE.format(kind=kind))
    (target_dir / "app.yaml").write_text(target)

    for _ in range(runs):
        summary = ConfigMapSecretUpdater(
            engine=ConfigMapSecretUpdateEngine(
                yaml_loader=filesystem.parse_yaml,
                yaml_dumper=filesystem.serialize_yaml,
            ),
            filesystem=filesystem,
        ).update(
            ConfigMapSecretUpdateLoader(filesystem=filesystem).load_directory(source_dir),
            ConfigMapSecretTargetLoader(filesystem=filesystem).load_directory(target_dir),
            target_directory=target_dir,
        )

        assert summary.errors == []

    return filesystem.parse_yaml((target_dir / "app.yaml").read_text())


@pytest.mark.parametrize("runs", [1, 2])
def test_source_comments_reach_configmap(tmp_path: Path, runs: int) -> None:
    document = _run_commented(
        tmp_path,
        "ConfigMap",
        _configmap("# existing\nserver.port=8080\nother=1\n"),
        runs,
    )

    assert document["data"]["application.properties"] == COMMENTED_EXPECTED
    assert document["data"]["other.properties"].strip() == "plain=value"


@pytest.mark.parametrize("runs", [1, 2])
def test_source_comments_reach_secret(tmp_path: Path, runs: int) -> None:
    document = _run_commented(
        tmp_path,
        "Secret",
        _secret("# existing\nserver.port=8080\nother=1\n"),
        runs,
    )

    decoded = base64.b64decode(document["data"]["application.properties"]).decode()

    assert decoded == COMMENTED_EXPECTED
