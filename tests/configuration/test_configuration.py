from pathlib import Path

from core.configuration.configuration import Configuration


def test_configuration_lookup(configuration_dict):

    configuration = Configuration(
        configuration_dict,
    )

    assert (
        configuration.get(
            "application.name"
        )
        == "Entropy"
    )

    assert (
        configuration.get(
            "database.path"
        )
        == "./database.db"
    )


def test_configuration_default(configuration_dict):

    configuration = Configuration(
        configuration_dict,
    )

    assert (
        configuration.get(
            "missing.value",
            "default",
        )
        == "default"
    )


def test_configuration_paths(configuration_dict):

    configuration = Configuration(
        configuration_dict,
    )

    assert configuration.database_path == Path(
        "./database.db"
    )

    assert configuration.logging_directory == Path(
        "./logs"
    )
