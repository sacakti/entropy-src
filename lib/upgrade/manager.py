"""
Entropy application upgrade manager.
"""

from __future__ import annotations

from pathlib import Path

from core.context import EntropyContext
from core.version import VERSION

from .package import UpgradePackage
from .staging import UpgradeStager
from .transaction import UpgradeTransaction
from .validator import UpgradeValidator


class UpgradeManager:
    """
    Coordinates Entropy application upgrades.

    Application data under ~/.entropy is intentionally not modified
    by the filesystem transaction.
    """

    def __init__(
        self,
        context: EntropyContext,
    ) -> None:

        assert context.bootstrap is not None

        self._context = context

        self._paths = context.bootstrap.application

        self._validator = UpgradeValidator()

    # ------------------------------------------------------------------
    # Upgrade
    # ------------------------------------------------------------------

    def upgrade(
        self,
        source: Path,
    ) -> None:
        """
        Upgrade Entropy from an .epkg package.
        """

        package = UpgradePackage(
            source.expanduser().resolve(),
        )

        manifest = self._validator.validate(
            package,
            VERSION,
        )

        stager = UpgradeStager()

        transaction: UpgradeTransaction | None = None

        try:

            staged = stager.stage(
                package,
            )

            transaction = UpgradeTransaction(
                self._paths,
            )

            transaction.begin(
                staged_application=staged / "application",
                version=VERSION,
                target_version=manifest.application.version,
            )

            self._verify_application(
                manifest.application.version,
            )

            transaction.commit()

        except Exception:

            if transaction is not None:

                transaction.rollback()

            raise

        finally:

            stager.cleanup()

    # ------------------------------------------------------------------
    # Verification
    # ------------------------------------------------------------------

    def _verify_application(
        self,
        expected_version: str,
    ) -> None:
        """
        Verify the activated application.
        """

        application = self._paths.directory

        required = (
            application / "entropy.py",
            application / "core",
            application / "lib",
        )

        for path in required:

            if not path.exists():

                raise RuntimeError(
                    f"Upgraded application is incomplete: {path}",
                )

        #
        # Version verification will be added once the installed
        # application's version can be queried independently.
        #
