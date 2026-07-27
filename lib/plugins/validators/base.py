"""
Base validator.
"""


class BaseValidator:
    """
    Base validator.
    """

    def validate(self, *args, **kwargs):
        """
        Validate an object.
        """

        raise NotImplementedError()