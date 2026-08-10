"""
Application version information.
"""

from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as package_version

APP_NAME = "Entropy"

try:
    VERSION = package_version(
        "entropy",
    )
except PackageNotFoundError:
    VERSION = "1.1.2"

AUTHOR = "Aravinthan"

COPYRIGHT = "© 2026 Entropy Deployment Framework"
