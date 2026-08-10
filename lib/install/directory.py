from lib.install.paths import InstallerPathManager


class DirectoryInstaller:

    def __init__(
        self,
        paths: InstallerPathManager,
    ) -> None:

        self._paths = paths

    def install(self) -> None:

        for directory in self._paths.directories:

            directory.mkdir(
                parents=True,
                exist_ok=True,
            )
