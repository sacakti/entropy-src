"""
Extension metadata registry.
"""

from __future__ import annotations

import json

from core.context import EntropyContext

from lib.models.extensions import Extension


class ExtensionMetadata:
    """
    Stores installed extension metadata.

    Responsible only for reading and writing the
    installed extension registry.
    """

    FILE = "extensions.json"

    def __init__(
        self,
        context: EntropyContext,
    ) -> None:

        assert context.paths is not None
        assert context.executor is not None

        self._executor = context.executor

        self._file = (
            context.paths.extensions.root /
            self.FILE
        )

    # ------------------------------------------------------------------
    # Public
    # ------------------------------------------------------------------

    def list(
        self,
    ) -> list[Extension]:

        data = self.load()

        return [
            Extension(
                name=name,
                version=value["version"],
                dist_info=value["dist_info"],
                wheel=value["wheel"],
                installer=value["installer"],
                installed_at=value["installed_at"],
                python_tag=value["python_tag"],
                platform_tag=value["platform_tag"],
                entry_points=value.get(
                    "entry_points",
                    [],
                ),
            )
            for name, value in sorted(
                data.items(),
            )
        ]

    def exists(
        self,
        name: str,
    ) -> bool:

        return name in self.load()

    def version(
        self,
        name: str,
    ) -> str | None:

        return self.load().get(
            name,
            {},
        ).get(
            "version",
        )

    def register(
        self,
        extension: Extension,
    ) -> None:

        data = self.load()

        data[extension.name] = {
            "version": extension.version,
            "dist_info": extension.dist_info,
            "wheel": extension.wheel,
            "installer": extension.installer,
            "installed_at": extension.installed_at,
            "python_tag": extension.python_tag,
            "platform_tag": extension.platform_tag,
            "entry_points": extension.entry_points,
        }

        self.save(
            data,
        )

    def unregister(
        self,
        name: str,
    ) -> None:

        data = self.load()

        data.pop(
            name,
            None,
        )

        self.save(
            data,
        )

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def load(
        self,
    ) -> dict:

        if not self._file.exists():

            return {}

        with self._file.open(
            "r",
            encoding="utf-8",
        ) as stream:

            return json.load(
                stream,
            )

    def save(
        self,
        metadata: dict,
    ) -> None:

        with self._file.open(
            "w",
            encoding="utf-8",
        ) as stream:

            json.dump(
                metadata,
                stream,
                indent=4,
                sort_keys=True,
            )


    def get(
        self,
        name: str,
    ) -> Extension:

        data = self.load()

        value = data[name]

        return Extension(
            name=name,
            version=value["version"],
            dist_info=value["dist_info"],
            wheel=value["wheel"],
            installer=value["installer"],
            installed_at=value["installed_at"],
            python_tag=value["python_tag"],
            platform_tag=value["platform_tag"],
            entry_points=value.get(
                "entry_points",
                [],
            ),
        )
