"""
License editions.
"""

from enum import Enum

from .feature import Feature


class Edition(str, Enum):

    COMMUNITY = "community"

    PROFESSIONAL = "professional"

    ENTERPRISE = "enterprise"


FEATURES = {
    Edition.COMMUNITY: set(),
    Edition.PROFESSIONAL: {
        Feature.REPORTS,
        Feature.API,
    },
    Edition.ENTERPRISE: {
        Feature.REPORTS,
        Feature.API,
        Feature.PARALLEL,
        Feature.AGENTS,
        Feature.PLUGIN_STORE,
    },
}
