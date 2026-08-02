from pathlib import Path


class InstallerPathManager:

    def __init__(self):

        self.project_root = Path(__file__).resolve().parents[2]

        self.application = self.project_root / "entropy.py"

        self.home = Path.home() / ".entropy"

        self.config = self.home / "config"
        self.database = self.home / "database"
        self.packages = self.home / "site-packages"

        self.vendor = self.project_root / "resources" / "wheels"

        self.requirements = self.vendor / "requirements.txt"

        self.default_config = (
            self.project_root
            / "lib"
            / "install"
            / "entropy.json.config"
        )

        self.config_file = self.config / "entropy.json"

        self.launcher_unix = (
            Path.home()
            / ".local"
            / "bin"
            / "ent"
        )

        self.launcher_windows = (
            Path.home()
            / "AppData"
            / "Local"
            / "Programs"
            / "Entropy"
            / "ent.cmd"
        )
