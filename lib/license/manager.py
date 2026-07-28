"""
License manager.
"""

from datetime import datetime

from .edition import FEATURES


class LicenseManager:

    def __init__(
        self,
        repository,
    ):

        self._repository = repository

    def license(self):

        return self._repository.get()

    def exists(self):

        return self._repository.exists()

    def edition(self):

        license = self.license()

        if license is None:

            return None

        return license.edition

    def is_valid(self):

        license = self.license()

        if license is None:

            return False

        if license.expires_at is None:

            return True

        return (
            license.expires_at >=
            datetime.utcnow()
        )

    def is_expired(self):

        return not self.is_valid()

    def has_feature(
        self,
        feature,
    ):

        if not self.is_valid():

            return False

        edition = self.edition()

        return (
            feature in
            FEATURES.get(
                edition,
                set(),
            )
        )