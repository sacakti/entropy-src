from pathlib import Path

import pytest
from cm_secret_update.exceptions import (
    UpdateFileError,
)
from cm_secret_update.loader import (
    ConfigMapSecretUpdateLoader,
)


class FakeFilesystem:
    """
    Minimal filesystem implementation for loader tests.
    """

    def load_yaml_documents(
        self,
        content: str,
    ):
        return self.documents

    def __init__(
        self,
        documents=None,
    ) -> None:
        self.documents = documents


def _loader(
    documents=None,
) -> ConfigMapSecretUpdateLoader:
    return ConfigMapSecretUpdateLoader(
        filesystem=FakeFilesystem(
            documents,
        ),
    )


def _definition() -> dict:
    return {
        "apiVersion": "entropy/v1",
        "kind": "ConfigMapSecretUpdate",
        "target": {
            "kind": "ConfigMap",
            "name": "application-config",
        },
        "operations": [
            {
                "action": "update",
                "key": "environment",
                "value": "uat",
            },
        ],
    }


def test_load_file_returns_definition(
    tmp_path: Path,
) -> None:
    path = tmp_path / "source.yaml"

    path.write_text(
        "dummy",
        encoding="utf-8",
    )

    loader = _loader(
        [
            _definition(),
        ],
    )

    definitions = loader.load_file(
        path,
    )

    assert len(definitions) == 1

    definition = definitions[0]

    assert definition.api_version == "entropy/v1"
    assert definition.kind == "ConfigMapSecretUpdate"
    assert definition.target.kind == "ConfigMap"
    assert definition.target.name == "application-config"

    assert len(definition.operations) == 1
    assert definition.operations[0].action == "update"
    assert definition.operations[0].key == "environment"
    assert definition.operations[0].value == "uat"


def test_load_file_returns_multiple_documents(
    tmp_path: Path,
) -> None:
    path = tmp_path / "source.yaml"

    path.write_text(
        "dummy",
        encoding="utf-8",
    )

    first = _definition()

    second = _definition()
    second["target"] = {
        "kind": "Secret",
        "name": "application-secret",
    }

    loader = _loader(
        [
            first,
            second,
        ],
    )

    definitions = loader.load_file(
        path,
    )

    assert len(definitions) == 2

    assert definitions[0].target.kind == "ConfigMap"
    assert definitions[0].target.name == "application-config"

    assert definitions[1].target.kind == "Secret"
    assert definitions[1].target.name == "application-secret"


def test_load_file_skips_empty_documents(
    tmp_path: Path,
) -> None:
    path = tmp_path / "source.yaml"

    path.write_text(
        "dummy",
        encoding="utf-8",
    )

    loader = _loader(
        [
            None,
            _definition(),
            None,
        ],
    )

    definitions = loader.load_file(
        path,
    )

    assert len(definitions) == 1


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


def test_load_file_path_is_directory(
    tmp_path: Path,
) -> None:
    directory = tmp_path / "source.yaml"
    directory.mkdir()

    loader = _loader()

    with pytest.raises(
        UpdateFileError,
        match="is not a file",
    ):
        loader.load_file(
            directory,
        )


def test_load_file_invalid_yaml(
    tmp_path: Path,
) -> None:
    path = tmp_path / "source.yaml"

    path.write_text(
        "dummy",
        encoding="utf-8",
    )

    class InvalidFilesystem:
        def load_yaml_documents(
            self,
            content: str,
        ):
            raise ValueError(
                "invalid YAML",
            )

    loader = ConfigMapSecretUpdateLoader(
        filesystem=InvalidFilesystem(),
    )

    with pytest.raises(
        UpdateFileError,
        match="Unable to parse source YAML file",
    ):
        loader.load_file(
            path,
        )


def test_load_file_invalid_definition(
    tmp_path: Path,
) -> None:
    path = tmp_path / "source.yaml"

    path.write_text(
        "dummy",
        encoding="utf-8",
    )

    invalid = {
        "apiVersion": "entropy/v1",
        "kind": "ConfigMapSecretUpdate",
    }

    loader = _loader(
        [
            invalid,
        ],
    )

    with pytest.raises(
        UpdateFileError,
        match="Invalid update definition",
    ):
        loader.load_file(
            path,
        )


def test_load_directory_loads_yaml_files(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source"
    source.mkdir()

    (source / "first.yaml").write_text(
        "dummy",
        encoding="utf-8",
    )

    (source / "second.yml").write_text(
        "dummy",
        encoding="utf-8",
    )

    (source / "ignored.txt").write_text(
        "ignored",
        encoding="utf-8",
    )

    filesystem = FakeFilesystem(
        [
            _definition(),
        ],
    )

    loader = ConfigMapSecretUpdateLoader(
        filesystem=filesystem,
    )

    definitions = loader.load_directory(
        source,
    )

    assert len(definitions) == 2


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
    path = tmp_path / "source"

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


def test_load_directory_without_yaml_files(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source"
    source.mkdir()

    (source / "ignored.txt").write_text(
        "ignored",
        encoding="utf-8",
    )

    loader = _loader()

    with pytest.raises(
        UpdateFileError,
        match="No YAML update definitions found",
    ):
        loader.load_directory(
            source,
        )
