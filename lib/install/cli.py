"""
Installer command line, run by install.sh / install.cmd from an
extracted release package:

    install.sh                      interactive installation
    install.sh --yes --workspace /srv/entropy --admin-password-file pw.txt
    install.sh --deps index --index-url https://pypi.example.com/simple
    install.sh --python /usr/bin/python3.9 --deps manual
    install.sh --print-requirements
    install.sh uninstall
"""

from __future__ import annotations

import os
import sys

# Run as a script, this file's directory leads sys.path, where
# lib/install/platform.py would shadow the standard library's platform.
_HERE = os.path.realpath(os.path.dirname(os.path.abspath(__file__)))
sys.path[:] = [entry for entry in sys.path if entry and os.path.realpath(entry) != _HERE]

import argparse  # noqa: E402
import json  # noqa: E402
from pathlib import Path  # noqa: E402

APPLICATION = Path(__file__).resolve().parents[2]


def _arguments(argv=None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="install",
        description="Install Entropy from this release package.",
    )
    parser.add_argument("command", nargs="?", choices=("install", "uninstall"), default="install")
    parser.add_argument("--workspace", type=Path, help="Workflow workspace directory.")
    parser.add_argument("--admin-user", help="Bootstrap administrator username (default admin).")
    parser.add_argument("--admin-name", default="Administrator", help="Administrator full name.")
    parser.add_argument(
        "--admin-password-file",
        type=Path,
        help="File holding the administrator password (or set ENTROPY_ADMIN_PASSWORD).",
    )
    parser.add_argument(
        "--deps",
        choices=("bundled", "index", "manual"),
        help="Python packages: bundled wheels (offline, default), a package index, "
        "or already installed manually into the chosen Python.",
    )
    parser.add_argument("--index-url", help="Package index URL for --deps index.")
    parser.add_argument(
        "--host", default="127.0.0.1", help="Web server address (default 127.0.0.1)."
    )
    parser.add_argument("--port", type=int, default=8000, help="Web server port (default 8000).")
    parser.add_argument(
        "--service",
        choices=("auto", "systemd", "none"),
        default="auto",
        help="Run the web server as a systemd user service when available (auto).",
    )
    parser.add_argument("--no-start", action="store_true", help="Do not start the web server.")
    parser.add_argument(
        "-y",
        "--yes",
        action="store_true",
        help="Non-interactive: never prompt (requires --workspace and a password).",
    )
    parser.add_argument(
        "--print-requirements",
        action="store_true",
        help="Print the Python requirements (for --deps manual) and exit.",
    )
    parser.add_argument("--package-root", type=Path, help=argparse.SUPPRESS)
    return parser.parse_args(argv)


def _manifest(package_root: Path | None) -> dict:
    if package_root is None:
        return {}
    try:
        return json.loads((package_root / "manifest.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _ask_deps() -> str:
    print()
    print("Python packages")
    print("  1) Bundled wheels, offline (recommended)")
    print("  2) Download from a package index")
    print("  3) Already installed manually into this Python")
    while True:
        choice = input("Choose [1]: ").strip() or "1"
        if choice in ("1", "2", "3"):
            return {"1": "bundled", "2": "index", "3": "manual"}[choice]
        print("Enter 1, 2 or 3.")


def main(argv=None) -> int:
    args = _arguments(argv)
    requirements = APPLICATION / "resources" / "wheels" / "requirements.txt"

    if args.print_requirements:
        print(requirements.read_text(encoding="utf-8"), end="")
        print(f"\n# Install with:\n#   {sys.executable} -m pip install -r {requirements}")
        return 0

    sys.path.insert(0, str(APPLICATION))

    if args.command == "uninstall":
        from lib.install.uninstaller import Uninstaller

        if not args.yes:
            answer = (
                input("Remove Entropy, its data (~/.entropy) and its launcher? [y/N]: ")
                .strip()
                .lower()
            )
            if answer not in ("y", "yes"):
                print("Cancelled.")
                return 1
        result = Uninstaller().uninstall()
        print(result.message)
        return 0 if result.success else 1

    interactive = not args.yes and sys.stdin.isatty()
    manifest = _manifest(args.package_root)

    password = os.environ.pop("ENTROPY_ADMIN_PASSWORD", None)
    if args.admin_password_file is not None:
        password = args.admin_password_file.read_text(encoding="utf-8").strip()

    deps = args.deps or (_ask_deps() if interactive else "bundled")
    index_url = args.index_url
    if deps == "index" and not index_url and interactive:
        index_url = input("Package index URL [https://pypi.org/simple]: ").strip() or None

    bundled_python = None
    if args.package_root is not None and (args.package_root / "python").is_dir():
        python_dir = (args.package_root / "python").resolve()
        # Only when the installer runs on the package's own Python; a venv
        # made from it links to it but has its own prefix (and packages).
        if Path(sys.prefix).resolve() == python_dir:
            bundled_python = python_dir

    from lib.install.installer import Installer, InstallOptions

    options = InstallOptions(
        workspace=args.workspace,
        admin_username=args.admin_user,
        admin_full_name=args.admin_name,
        admin_password=password,
        deps=deps,
        index_url=index_url,
        bundled_python=bundled_python,
        platform=manifest.get("platform"),
        web_host=args.host,
        web_port=args.port,
        service=args.service,
        start_web=not args.no_start,
        interactive=interactive,
    )

    version = manifest.get("version", "")
    print(f"Installing Entropy {version}".rstrip() + "...")
    result = Installer(options).install()
    print()
    print(result.message)
    return 0 if result.success else 1


if __name__ == "__main__":
    sys.exit(main())
