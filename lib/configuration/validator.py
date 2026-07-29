"""
Entropy configuration validator.
"""

from lib.configuration.exceptions import InvalidConfigurationError


class ConfigurationValidator:
    """
    Validates configuration.
    """

    REQUIRED_SECTIONS = (
        "application",
        "logging",
        "database",
        "runtime",
        "workflow",
    )

    def validate(
        self,
        configuration: dict,
    ) -> None:
        """
        Validate configuration.
        """

        errors = []

        for section in self.REQUIRED_SECTIONS:

            if section not in configuration:

                errors.append(
                    f"Missing configuration section "
                    f"'{section}'."
                )

        if errors:

            message = (
                "Invalid configuration:\n\n"
                + "\n".join(
                    f"  • {error}"
                    for error in errors
                )
            )

            raise InvalidConfigurationError(
                message
            )
