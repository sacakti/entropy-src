"""
Template exceptions.
"""


class TemplateError(Exception):
    """
    Base template exception.
    """


class TemplateNotFoundError(TemplateError):
    """
    Raised when a template cannot be found.
    """