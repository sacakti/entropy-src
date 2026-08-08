"""
Wheel inspector.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from packaging.utils import parse_wheel_filename

from lib.extensions.exceptions import ExtensionValidationError
from lib.models.extensions import Extension


class WheelInspector:
    """
    Inspects Python wheel files.
    """

    def inspect(
        self,
        wheel: Path,
    ) -> Extension:
        """
        Inspect a wheel file.
        """

        try:

            name, version, _, tags = parse_wheel_filename(
                wheel.name,
            )

        except Exception as exc:

            raise ExtensionValidationError(
                f"Invalid wheel '{wheel.name}'.",
            ) from exc

        #
        # Pick one compatibility tag.
        #
        # For most wheels there is only one.
        #

        tag = next(
            iter(tags),
        )
        installed_at=datetime.now(
            timezone.utc,
        )
        return Extension(
            name=name,
            version=str(version),
            wheel=wheel.name,
            installer="offline",
            installed_at=installed_at,
            python_tag=tag.interpreter,
            platform_tag=tag.platform,
        )
