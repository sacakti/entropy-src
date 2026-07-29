"""
Configuration exceptions
"""

from core.exceptions import EntropyException

class ConfigurationException(EntropyException):
     """Base class for all configuration-related errors."""

class ConfigurationFileNotFoundError(ConfigurationException):

     def __init__(self, config_file):
          super().__init__(
               f"Configuration file not found: {config_file}"
          )

class InvalidConfigurationError(ConfigurationException):

     def __init__(self, exc):
          super().__init__(
               f"Invalid configuration: {exc}"
          )

class ConfigurationNotLoadedError(ConfigurationException):

     def __init__(self, *args):
          super().__init__(
               "Configuration has not been loaded."
          )