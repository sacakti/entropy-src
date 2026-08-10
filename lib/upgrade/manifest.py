"""
Upgrade package manifest.
"""

from __future__ import annotations

from dataclasses import dataclass

from lib.upgrade.exceptions import UpgradeManifestError


@dataclass(frozen=True)
class ApplicationManifest:
    """
    Application information contained in an upgrade package.
    """

    name: str
    version: str
    minimum_python: str | None = None


@dataclass(frozen=True)
class PackageManifest:
    """
    Entropy upgrade package manifest.
    """

    format: int
    package_type: str
    application: ApplicationManifest


class ManifestReader:
    """
    Reads upgrade package manifests.
    """

    def read(
        self,
        data: dict,
    ) -> PackageManifest:
        """
        Convert raw manifest data into a package manifest.
        """

        try:

            application = data["application"]

            return PackageManifest(
                format=int(
                    data["format"],
                ),
                package_type=str(
                    data["package"]["type"],
                ),
                application=ApplicationManifest(
                    name=str(
                        application["name"],
                    ),
                    version=str(
                        application["version"],
                    ),
                    minimum_python=(
                        str(
                            application["minimum_python"],
                        )
                        if application.get(
                            "minimum_python",
                        )
                        else None
                    ),
                ),
            )

        except (
            KeyError,
            TypeError,
            ValueError,
        ) as exc:

            raise UpgradeManifestError(
                "Invalid upgrade package manifest.",
            ) from exc
