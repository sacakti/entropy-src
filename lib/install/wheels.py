"""
Python package installation.

Three modes:

* bundled - offline, from the wheels shipped in the package (default);
* index   - from a package index (PyPI or `--index-url`), for platforms
            the package carries no wheels for;
* manual  - the administrator installed the packages into the runtime
            Python beforehand; they are only verified.
"""

from __future__ import annotations

import subprocess
import sys

from lib.install.paths import InstallerPathManager

# Import names that must resolve for Entropy to run.
REQUIRED_MODULES = (
    "argon2",
    "cryptography",
    "jinja2",
    "rich",
    "ruamel.yaml",
    "packaging",
    "questionary",
    "markdown",
    "sqlparse",
    "fastapi",
    "uvicorn",
    "multipart",
    "PIL",
)


class WheelInstaller:

    def __init__(
        self,
        platform,
        paths: InstallerPathManager,
        mode: str = "bundled",
        index_url: str | None = None,
    ) -> None:

        self._platform = platform
        self._paths = paths
        self._mode = mode
        self._index_url = index_url

    def install(self):

        if not self._paths.requirements.exists():

            raise FileNotFoundError(f"Requirements file not found: {self._paths.requirements}")

        self._paths.packages.mkdir(
            parents=True,
            exist_ok=True,
        )

        if self._mode == "manual":

            self.verify()
            return

        command = [
            sys.executable,
            "-m",
            "pip",
            "install",
            "--disable-pip-version-check",
            "--no-warn-script-location",
            "--target",
            str(self._paths.packages),
            "-r",
            str(self._paths.requirements),
        ]

        if self._mode == "index":

            if self._index_url:
                command.extend(["--index-url", self._index_url])

        else:

            wheel_directory = self._paths.vendor / self._platform.value

            if not wheel_directory.exists():

                raise FileNotFoundError(
                    f"Wheel directory not found: {wheel_directory}. Install with "
                    "--deps index (package index) or --deps manual instead."
                )

            command.extend(["--no-index", "--find-links", str(wheel_directory)])

        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
        )

        if result.returncode != 0:

            print(result.stdout)
            print(result.stderr)

            raise RuntimeError("Failed to install Python packages.")

        self.verify()

    def verify(self) -> None:
        """Fail with a clear list when required packages cannot be imported."""

        probe = (
            "import importlib.util, sys\n"
            f"sys.path.insert(0, {str(self._paths.packages)!r})\n"
            f"missing = [m for m in {REQUIRED_MODULES!r} if importlib.util.find_spec(m) is None]\n"
            "print(','.join(missing))\n"
        )
        result = subprocess.run(
            [sys.executable, "-c", probe],
            capture_output=True,
            text=True,
        )
        missing = [name for name in result.stdout.strip().split(",") if name]

        if result.returncode != 0 or missing:

            raise RuntimeError(
                f"Python packages missing for {sys.executable}: "
                f"{', '.join(missing) or 'unknown'}.\n"
                f"Install them with:\n\n"
                f"    {sys.executable} -m pip install -r {self._paths.requirements}\n\n"
                "then run the installer again."
            )
