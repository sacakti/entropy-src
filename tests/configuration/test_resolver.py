from core.configuration.resolver import (
    ConfigurationResolver,
)


def test_identity(configuration_dict):

    resolver = ConfigurationResolver()

    result = resolver.resolve(
        configuration_dict,
    )

    assert result == configuration_dict

    assert result is not configuration_dict
