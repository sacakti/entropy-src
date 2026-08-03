from lib.install.paths import InstallerPathManager


class DirectoryInstaller:

    def __init__(self) -> None:

        self._paths = InstallerPathManager()

    def install(self) -> None:

        for directory in self._paths.directories:

            directory.mkdir(
                parents=True,
                exist_ok=True,
            )
