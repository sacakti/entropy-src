from pathlib import Path

from core.configuration.parser import (
    ConfigurationParser,
)


def test_json_parser(
    entropy_context,
    configuration_dict,
):

    executor = entropy_context.executor

    executor.read_json.return_value = configuration_dict

    parser = ConfigurationParser(
        executor,
    )

    data = parser.read(
        Path("entropy.json"),
    )

    assert data == configuration_dict

    executor.read_json.assert_called_once()


def test_yaml_parser(
    entropy_context,
    configuration_dict,
):

    executor = entropy_context.executor

    executor.read_yaml.return_value = configuration_dict

    parser = ConfigurationParser(
        executor,
    )

    data = parser.read(
        Path("entropy.yaml"),
    )

    assert data == configuration_dict

    executor.read_yaml.assert_called_once()
