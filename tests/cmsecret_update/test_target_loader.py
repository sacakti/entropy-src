from __future__ import annotations

from pathlib import Path

import pytest

from cm_secret_update.exceptions import (
    UpdateFileError,
)
from cm_secret_update.target_loader import (
    ConfigMapSecretTargetLoader,
)


class FakeFilesystem:
    """
    Minimal filesystem implementation required by the target loader.
    """

    def __init__(
        self,
        documents=None,
    ) -> None:
        self.documents = documents or []

    def exists(
        self,
        path: Path,
    ) -> bool:
        return path.exists()

    def is_directory(
        self,
        path: Path,
    ) -> bool:
        return path.is_dir()

    def is_file(
        self,
        path: Path,
    ) -> bool:
        return path.is_file()

    def listdir(
        self,
        path: Path,
    ) -> list[Path]:
        return sorted(path.iterdir())

    def read_text(
        self,
        path: Path,
    ) -> str:
        return path.read_text(
            encoding="utf-8",
        )

    def load_yaml_documents(
        self,
        content: str,
    ):
        if content == "configmap":
            return [
                _configmap(),
            ]

        if content == "secret":
            return [
                _secret(),
            ]

        return self.documents


def _loader(
    documents=None,
) -> ConfigMapSecretTargetLoader:
    return ConfigMapSecretTargetLoader(
        filesystem=FakeFilesystem(
            documents,
        ),
    )


def _configmap(
    name: str = "application-config",
) -> dict:
    return {
        "apiVersion": "v1",
        "kind": "ConfigMap",
        "metadata": {
            "name": name,
        },
        "data": {
            "environment": "uat",
        },
    }


def _secret(
    name: str = "application-secret",
) -> dict:
    return {
        "apiVersion": "v1",
        "kind": "Secret",
        "metadata": {
            "name": name,
        },
        "data": {
            "username": "YWRtaW4=",
        },
    }


def test_load_file_returns_configmap(
    tmp_path: Path,
) -> None:
    path = tmp_path / "application.yaml"

    path.write_text(
        "dummy",
        encoding="utf-8",
    )

    loader = _loader(
        [
            _configmap(),
        ],
    )

    resources = loader.load_file(
        path,
    )

    assert len(resources) == 1

    resource = resources[0]

    assert resource.kind == "ConfigMap"
    assert resource.name == "application-config"
    assert resource.document["kind"] == "ConfigMap"
    assert resource.document["metadata"]["name"] == (
        "application-config"
    )

    assert resource.target_file.path == path
    assert resource.target_file.documents == [
        _configmap(),
    ]

    assert resource.document_index == 0


def test_load_file_returns_secret(
    tmp_path: Path,
) -> None:
    path = tmp_path / "secret.yaml"

    path.write_text(
        "dummy",
        encoding="utf-8",
    )

    loader = _loader(
        [
            _secret(),
        ],
    )

    resources = loader.load_file(
        path,
    )

    assert len(resources) == 1

    resource = resources[0]

    assert resource.kind == "Secret"
    assert resource.name == "application-secret"


def test_load_file_returns_multiple_documents(
    tmp_path: Path,
) -> None:
    path = tmp_path / "resources.yaml"

    path.write_text(
        "dummy",
        encoding="utf-8",
    )

    configmap = _configmap()
    secret = _secret()

    loader = _loader(
        [
            configmap,
            secret,
        ],
    )

    resources = loader.load_file(
        path,
    )

    assert len(resources) == 2

    assert resources[0].kind == "ConfigMap"
    assert resources[0].name == "application-config"
    assert resources[0].document_index == 0

    assert resources[1].kind == "Secret"
    assert resources[1].name == "application-secret"
    assert resources[1].document_index == 1

    assert resources[0].target_file is resources[1].target_file

    assert resources[0].target_file.documents == [
        configmap,
        secret,
    ]


def test_load_file_skips_empty_documents(
    tmp_path: Path,
) -> None:
    path = tmp_path / "resources.yaml"

    path.write_text(
        "dummy",
        encoding="utf-8",
    )

    loader = _loader(
        [
            None,
            _configmap(),
            None,
        ],
    )

    resources = loader.load_file(
        path,
    )

    assert len(resources) == 1
    assert resources[0].document_index == 1


def test_load_file_missing_file(
    tmp_path: Path,
) -> None:
    path = tmp_path / "missing.yaml"

    loader = _loader()

    with pytest.raises(
        UpdateFileError,
        match="does not exist",
    ):
        loader.load_file(
            path,
        )


def test_load_file_path_is_not_file(
    tmp_path: Path,
) -> None:
    directory = tmp_path / "resources.yaml"
    directory.mkdir()

    loader = _loader()

    with pytest.raises(
        UpdateFileError,
        match="is not a file",
    ):
        loader.load_file(
            directory,
        )


def test_load_file_rejects_non_object_document(
    tmp_path: Path,
) -> None:
    path = tmp_path / "resources.yaml"

    path.write_text(
        "dummy",
        encoding="utf-8",
    )

    loader = _loader(
        [
            "not-an-object",
        ],
    )

    with pytest.raises(
        UpdateFileError,
        match="resource must be an object",
    ):
        loader.load_file(
            path,
        )


def test_load_file_rejects_unsupported_kind(
    tmp_path: Path,
) -> None:
    path = tmp_path / "resources.yaml"

    path.write_text(
        "dummy",
        encoding="utf-8",
    )

    document = {
        "apiVersion": "v1",
        "kind": "Deployment",
        "metadata": {
            "name": "application",
        },
    }

    loader = _loader(
        [
            document,
        ],
    )

    with pytest.raises(
        UpdateFileError,
        match="Expected ConfigMap or Secret",
    ):
        loader.load_file(
            path,
        )


def test_load_file_rejects_missing_metadata(
    tmp_path: Path,
) -> None:
    path = tmp_path / "resources.yaml"

    path.write_text(
        "dummy",
        encoding="utf-8",
    )

    document = {
        "apiVersion": "v1",
        "kind": "ConfigMap",
    }

    loader = _loader(
        [
            document,
        ],
    )

    with pytest.raises(
        UpdateFileError,
        match="must contain metadata",
    ):
        loader.load_file(
            path,
        )


def test_load_file_rejects_invalid_metadata(
    tmp_path: Path,
) -> None:
    path = tmp_path / "resources.yaml"

    path.write_text(
        "dummy",
        encoding="utf-8",
    )

    document = {
        "apiVersion": "v1",
        "kind": "ConfigMap",
        "metadata": "invalid",
    }

    loader = _loader(
        [
            document,
        ],
    )

    with pytest.raises(
        UpdateFileError,
        match="must contain metadata",
    ):
        loader.load_file(
            path,
        )


def test_load_file_rejects_missing_metadata_name(
    tmp_path: Path,
) -> None:
    path = tmp_path / "resources.yaml"

    path.write_text(
        "dummy",
        encoding="utf-8",
    )

    document = {
        "apiVersion": "v1",
        "kind": "ConfigMap",
        "metadata": {},
    }

    loader = _loader(
        [
            document,
        ],
    )

    with pytest.raises(
        UpdateFileError,
        match="must contain metadata.name",
    ):
        loader.load_file(
            path,
        )


def test_load_file_rejects_empty_metadata_name(
    tmp_path: Path,
) -> None:
    path = tmp_path / "resources.yaml"

    path.write_text(
        "dummy",
        encoding="utf-8",
    )

    document = {
        "apiVersion": "v1",
        "kind": "ConfigMap",
        "metadata": {
            "name": "   ",
        },
    }

    loader = _loader(
        [
            document,
        ],
    )

    with pytest.raises(
        UpdateFileError,
        match="must contain metadata.name",
    ):
        loader.load_file(
            path,
        )


def test_load_file_strips_metadata_name(
    tmp_path: Path,
) -> None:
    path = tmp_path / "resources.yaml"

    path.write_text(
        "dummy",
        encoding="utf-8",
    )

    document = _configmap()

    document["metadata"]["name"] = "  application-config  "

    loader = _loader(
        [
            document,
        ],
    )

    resources = loader.load_file(
        path,
    )

    assert resources[0].name == "application-config"


def test_load_directory_loads_yaml_files(
    tmp_path: Path,
) -> None:
    directory = tmp_path / "target"
    directory.mkdir()

    (directory / "first.yaml").write_text(
        "configmap",
        encoding="utf-8",
    )

    (directory / "second.yml").write_text(
        "secret",
        encoding="utf-8",
    )

    (directory / "ignored.txt").write_text(
        "ignored",
        encoding="utf-8",
    )

    loader = _loader()

    resources = loader.load_directory(
        directory,
    )

    assert len(resources) == 2

    assert resources[0].kind == "ConfigMap"
    assert resources[0].name == "application-config"

    assert resources[1].kind == "Secret"
    assert resources[1].name == "application-secret"


def test_load_directory_skips_subdirectories(
    tmp_path: Path,
) -> None:
    directory = tmp_path / "target"
    directory.mkdir()

    (directory / "nested.yaml").mkdir()

    loader = _loader()

    resources = loader.load_directory(
        directory,
    )

    assert resources == []


def test_load_directory_missing_directory(
    tmp_path: Path,
) -> None:
    directory = tmp_path / "missing"

    loader = _loader()

    with pytest.raises(
        UpdateFileError,
        match="does not exist",
    ):
        loader.load_directory(
            directory,
        )


def test_load_directory_path_is_not_directory(
    tmp_path: Path,
) -> None:
    path = tmp_path / "target"

    path.write_text(
        "dummy",
        encoding="utf-8",
    )

    loader = _loader()

    with pytest.raises(
        UpdateFileError,
        match="is not a directory",
    ):
        loader.load_directory(
            path,
        )


def test_duplicate_targets_are_rejected(
    tmp_path: Path,
) -> None:
    directory = tmp_path / "target"
    directory.mkdir()

    first = directory / "first.yaml"
    second = directory / "second.yaml"

    first.write_text(
        "dummy",
        encoding="utf-8",
    )

    second.write_text(
        "dummy",
        encoding="utf-8",
    )

    # The fake filesystem returns the same resource for both files.
    loader = _loader(
        [
            _configmap(),
        ],
    )

    with pytest.raises(
        UpdateFileError,
        match="Duplicate target resource",
    ):
        loader.load_directory(
            directory,
        )
