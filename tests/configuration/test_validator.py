import pytest

from core.configuration.exceptions import (
    InvalidConfigurationError,
)
from core.configuration.validator import (
    ConfigurationValidator,
)


def test_validator(configuration_dict):

    validator = ConfigurationValidator()

    validator.validate(
        configuration_dict,
    )


def test_missing_section():

    validator = ConfigurationValidator()

    with pytest.raises(
        InvalidConfigurationError,
    ):

        validator.validate({})
