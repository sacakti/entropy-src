"""
Application upgrade transaction.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from core.models.paths import ApplicationPaths

from .exceptions import UpgradeError


class UpgradeTransaction:
    """
    Performs an application filesystem upgrade transaction.

    The transaction does not modify Entropy persistent data.
    """

    def __init__(
        self,
        paths: ApplicationPaths,
    ) -> None:

        self._paths = paths

        self._backup: Path | None = None
        self._active = False

        self._from_version: str | None = None
        self._to_version: str | None = None

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def backup(self) -> Path | None:
        """
        Return the backup created by the transaction.
        """

        return self._backup

    # ------------------------------------------------------------------
    # Begin
    # ------------------------------------------------------------------

    def begin(
        self,
        staged_application: Path,
        version: str,
        target_version: str,
    ) -> None:
        """
        Replace the current application with the staged application.
        """
        self._from_version = version
        self._to_version = target_version

        if self._active:

            raise UpgradeError(
                "Upgrade transaction is already active.",
            )

        if not staged_application.exists():

            raise UpgradeError(
                f"Staged application does not exist: " f"{staged_application}",
            )

        if not staged_application.is_dir():

            raise UpgradeError(
                f"Staged application is not a directory: " f"{staged_application}",
            )

        application = self._paths.directory

        if not application.exists():

            raise UpgradeError(
                f"Installed application does not exist: " f"{application}",
            )

        #
        # Prepare version storage.
        #

        self._paths.versions.mkdir(
            parents=True,
            exist_ok=True,
        )

        backup = self._paths.versions / version

        if backup.exists():

            raise UpgradeError(
                f"Application version already exists: " f"{backup}",
            )

        #
        # Record transaction before making destructive changes.
        #

        self._write_state(
            state="prepared",
            from_version=version,
            to_version=target_version,
        )

        #
        # Move current application out of the active location.
        #

        try:

            shutil.move(
                str(application),
                str(backup),
            )

            self._backup = backup

            self._write_state(
                state="activating",
                from_version=version,
                to_version=target_version,
            )

            #
            # Activate staged application.
            #

            shutil.move(
                str(staged_application),
                str(application),
            )

            self._active = True

            self._write_state(
                state="activated",
                from_version=version,
                to_version=target_version,
            )

        except Exception as exc:

            #
            # Activation failed. Restore immediately.
            #

            self._restore()

            self._clear_state()

            raise UpgradeError(
                "Failed to activate upgraded application.",
            ) from exc

    # ------------------------------------------------------------------
    # Commit
    # ------------------------------------------------------------------

    def commit(self) -> None:
        """
        Commit the active upgrade.

        The previous application version remains available
        for rollback.
        """

        if not self._active:

            raise UpgradeError(
                "No active upgrade transaction.",
            )

        self._write_state(
            state="committed",
            from_version=self._from_version or "",
            to_version=self._to_version or "",
        )

        self._active = False

        self._clear_state()

    # ------------------------------------------------------------------
    # Rollback
    # ------------------------------------------------------------------

    def rollback(self) -> None:
        """
        Roll back the active upgrade.
        """

        if not self._active and self._backup is None:

            return

        self._restore()

        self._active = False

        self._clear_state()

    # ------------------------------------------------------------------
    # Recovery
    # ------------------------------------------------------------------

    def recover(self) -> None:
        """
        Recover an interrupted upgrade transaction.

        If transaction metadata exists, restore the previous
        application version when possible.
        """

        if not self.has_pending_transaction():

            return

        state = self._read_state()

        if state is None:

            raise UpgradeError(
                "Upgrade transaction state is invalid.",
            )

        from_version = state.get(
            "from_version",
        )

        if (
            not isinstance(
                from_version,
                str,
            )
            or not from_version
        ):

            raise UpgradeError(
                "Upgrade transaction does not contain " "a valid source version.",
            )

        application = self._paths.directory

        backup = self._paths.versions / from_version

        #
        # If the old application is already in versions/,
        # restore it.
        #

        if backup.exists():

            if application.exists():

                shutil.rmtree(
                    application,
                )

            shutil.move(
                str(backup),
                str(application),
            )

        #
        # If no backup exists, we cannot safely reconstruct
        # the previous application.
        #

        elif not application.exists():

            raise UpgradeError(
                "Interrupted upgrade cannot be recovered: " "previous application is missing.",
            )

        self._clear_state()

        self._backup = None
        self._active = False

    # ------------------------------------------------------------------
    # State
    # ------------------------------------------------------------------

    def has_pending_transaction(
        self,
    ) -> bool:
        """
        Return whether an upgrade transaction is pending.
        """

        return self._paths.transaction.exists()

    def _write_state(
        self,
        state: str,
        from_version: str,
        to_version: str,
    ) -> None:
        """
        Persist transaction state.
        """

        self._paths.transaction.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        data = {
            "operation": "upgrade",
            "state": state,
            "from_version": from_version,
            "to_version": to_version,
        }

        temporary = self._paths.transaction.with_suffix(
            ".tmp",
        )

        temporary.write_text(
            json.dumps(
                data,
                indent=4,
            )
            + "\n",
            encoding="utf-8",
        )

        temporary.replace(
            self._paths.transaction,
        )

    def _read_state(
        self,
    ) -> dict | None:
        """
        Read persisted transaction state.
        """

        try:

            data = json.loads(
                self._paths.transaction.read_text(
                    encoding="utf-8",
                ),
            )

        except (
            OSError,
            json.JSONDecodeError,
        ) as exc:

            raise UpgradeError(
                "Unable to read upgrade transaction state.",
            ) from exc

        if not isinstance(
            data,
            dict,
        ):

            raise UpgradeError(
                "Upgrade transaction state must be an object.",
            )

        return data

    def _clear_state(self) -> None:
        """
        Remove transaction state.
        """

        if self._paths.transaction.exists():

            self._paths.transaction.unlink()

    # ------------------------------------------------------------------
    # Restore
    # ------------------------------------------------------------------

    def _restore(self) -> None:
        """
        Restore the previous application.
        """

        application = self._paths.directory
        backup = self._backup

        if backup is None:

            return

        #
        # Remove the failed active application.
        #

        if application.exists():

            shutil.rmtree(
                application,
            )

        #
        # Restore the previous application.
        #

        if backup.exists():

            shutil.move(
                str(backup),
                str(application),
            )

        self._backup = None
