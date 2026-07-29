"""
Licensed features.
"""

from enum import Enum


class Feature(str, Enum):

    REPORTS = "reports"

    API = "api"

    PARALLEL = "parallel"

    AGENTS = "agents"

    PLUGIN_STORE = "plugin_store"
