"""Extensions: libraries for plugins, several versions side by side (offline)."""

from __future__ import annotations

import io
import subprocess
import sys
import zipfile
from pathlib import Path
from types import SimpleNamespace
from typing import Iterator

import pytest

from lib.database.connection import DatabaseConnection
from lib.extensions import packages, resolver
from lib.extensions.exceptions import ExtensionExistsError, ExtensionValueError
from lib.extensions.manager import ExtensionManager


@pytest.fixture
def manager(tmp_path) -> Iterator[ExtensionManager]:
    connection = DatabaseConnection(tmp_path / "entropy.db")
    connection.open()
    context = SimpleNamespace(
        paths=SimpleNamespace(extensions=SimpleNamespace(root=tmp_path / "extensions")),
        database_manager=SimpleNamespace(connection=connection),
        observability=None,
    )
    yield ExtensionManager(context)  # type: ignore[arg-type]
    connection.close()


def _module(version: str) -> bytes:
    return f'VERSION = "{version}"\n\ndef greet():\n    return "hello from {version}"\n'.encode()


def test_plain_modules_install_side_by_side(manager) -> None:
    first = manager.install_upload(
        "greeter.py", _module("1.0"), name="greeter", version="1.0", user="dev"
    )
    second = manager.install_upload(
        "greeter.py", _module("2.0"), name="greeter", version="2.0", user="dev"
    )
    assert (first["version"], second["version"]) == ("1.0", "2.0")
    assert first["packages"] == ["greeter==1.0"] and first["source"] == "upload"
    assert {entry["version"] for entry in manager.list()} == {"1.0", "2.0"}
    for version in ("1.0", "2.0"):
        assert (manager.folder("greeter", version) / "site" / "greeter.py").is_file()
        assert manager.verify("greeter", version) == []

    # The same version again is refused, as is a library Entropy already has.
    with pytest.raises(ExtensionExistsError, match="already installed"):
        manager.install_upload("greeter.py", _module("1.0"), name="greeter", version="1.0")
    host = packages.host_distributions()["packaging"]
    with pytest.raises(ExtensionExistsError, match="already part of Entropy"):
        manager.install("packaging", host)


def test_requirements_resolve_to_entropy_or_the_newest_fitting_version(manager) -> None:
    for version in ("1.0", "1.5", "2.0"):
        manager.install_upload("greeter.py", _module(version), name="greeter", version=version)
    host = packages.host_distributions()["packaging"]
    found = {
        entry["requirement"]: (entry["status"], entry["version"])
        for entry in manager.check(
            [
                {"name": "greeter", "version": "1.5"},
                {"name": "greeter", "version": "<2"},
                {"name": "greeter"},
                {"name": "greeter", "version": ">=3"},
                {"name": "packaging", "version": host},
                {"name": "nothing-like-this"},
            ]
        )
    }
    assert found == {
        "greeter==1.5": ("extension", "1.5"),
        "greeter<2": ("extension", "1.5"),
        "greeter": ("extension", "2.0"),
        "greeter>=3": ("missing", None),
        f"packaging=={host}": ("entropy", host),
        "nothing-like-this": ("missing", None),
    }
    with pytest.raises(ExtensionValueError):
        resolver.specifier("not a version!")


def test_activation_puts_the_chosen_version_on_the_path(manager, tmp_path) -> None:
    manager.install_upload("greeter.py", _module("1.0"), name="greeter", version="1.0")
    manager.install_upload("greeter.py", _module("2.0"), name="greeter", version="2.0")
    # A separate process, as a workflow worker is.
    script = (
        "import sys, types\n"
        "from types import SimpleNamespace\n"
        "from lib.database.connection import DatabaseConnection\n"
        "from lib.extensions.manager import ExtensionManager\n"
        f"c = DatabaseConnection({str(tmp_path / 'entropy.db')!r}); c.open()\n"
        f"ctx = SimpleNamespace(paths=SimpleNamespace(extensions=SimpleNamespace(root=__import__('pathlib').Path({str(tmp_path / 'extensions')!r}))), database_manager=SimpleNamespace(connection=c), observability=None)\n"  # noqa: E501
        "m = ExtensionManager(ctx)\n"
        "m.activate([{'name': 'greeter', 'version': sys.argv[1]}])\n"
        "import greeter; print(greeter.greet())\n"
        "try:\n"
        "    m.activate([{'name': 'greeter', 'version': '2.0' if sys.argv[1] != '2.0' else '1.0'}])\n"  # noqa: E501
        "except Exception as exc: print(type(exc).__name__)\n"
    )
    root = Path(__file__).resolve().parents[2]
    for version in ("1.0", "2.0"):
        result = subprocess.run(
            [sys.executable, "-c", script, version],
            cwd=root,
            capture_output=True,
            text=True,
            check=True,
        )
        assert result.stdout.splitlines() == [f"hello from {version}", "ExtensionConflictError"]


def test_package_folder_zip_and_removal(manager) -> None:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("acme_tools/__init__.py", "from .core import answer\n")
        archive.writestr("acme_tools/core.py", "def answer():\n    return 42\n")
        archive.writestr("acme_tools/__pycache__/core.cpython-39.pyc", b"junk")
    entry = manager.install_upload(
        "acme_tools.zip",
        buffer.getvalue(),
        name="acme-tools",
        version="0.3.1",
        summary="ACME helpers",
    )
    site = manager.folder("acme-tools", "0.3.1") / "site"
    assert (site / "acme_tools" / "core.py").is_file()
    assert not (site / "acme_tools" / "__pycache__").exists()
    assert entry["summary"] == "ACME helpers"
    # Nodes get the same wheels.
    bundle = manager.bundle("acme-tools", "0.3.1")
    assert bundle[:2] == b"\x1f\x8b"
    assert manager.uninstall("acme-tools") == ["0.3.1"]
    assert manager.list() == [] and not manager.folder("acme-tools", "0.3.1").exists()


def test_uploads_are_checked(manager) -> None:
    with pytest.raises(ExtensionValueError, match="name and version"):
        manager.install_upload("thing.py", b"x = 1\n")
    with pytest.raises(ExtensionValueError, match="Upload a wheel"):
        manager.install_upload("thing.exe", b"MZ")
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("../evil.py", "x = 1\n")
    with pytest.raises(ExtensionValueError, match="unsafe"):
        manager.install_upload("evil.zip", buffer.getvalue(), name="evil", version="1.0")


def _wheel(name: str, version: str, requires=(), tag: str = "py3-none-any") -> tuple:
    distribution = name.replace("-", "_")
    dist_info = f"{distribution}-{version}.dist-info"
    metadata = f"Metadata-Version: 2.1\nName: {name}\nVersion: {version}\n" + "".join(
        f"Requires-Dist: {line}\n" for line in requires
    )
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr(f"{distribution}/__init__.py", f"VERSION = '{version}'\n")
        archive.writestr(f"{dist_info}/METADATA", metadata)
        archive.writestr(f"{dist_info}/WHEEL", f"Wheel-Version: 1.0\nTag: {tag}\n")
        archive.writestr(f"{dist_info}/RECORD", "")
    return f"{distribution}-{version}-{tag}.whl", buffer.getvalue()


def _zip(*wheels) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, data in wheels:
            archive.writestr(f"wheels/{name}", data)
    return buffer.getvalue()


def test_a_zip_of_wheels_installs_the_library_with_its_dependencies(manager) -> None:
    host = packages.host_distributions()["packaging"]
    top = _wheel(
        "sshlib",
        "3.4.0",
        [
            "helper>=1.0",
            f"packaging>={host}",  # Entropy has it: not needed in the zip
            "gssapi>=1.4; extra == 'gssapi'",  # optional: ignored
            "winonly; sys_platform == 'nonexistent'",
        ],
    )
    helper = _wheel("helper", "1.2.0")
    other_platform = _wheel("helper", "1.2.0", tag="cp39-cp39-win_amd64")

    with pytest.raises(
        ExtensionValueError, match=r"lacks dependencies: helper>=1.0 \(for sshlib\)"
    ):
        manager.install_upload("bundle.zip", _zip(top))

    entry = manager.install_upload("bundle.zip", _zip(top, helper, other_platform))
    assert (entry["name"], entry["version"]) == ("sshlib", "3.4.0")
    assert entry["packages"] == ["helper==1.2.0", "sshlib==3.4.0"]
    site = manager.folder("sshlib", "3.4.0") / "site"
    assert (site / "sshlib" / "__init__.py").is_file() and (site / "helper").is_dir()
    # Nodes get exactly the chosen wheels.
    assert sorted(p.name for p in (manager.folder("sshlib", "3.4.0") / "wheels").iterdir()) == [
        helper[0],
        top[0],
    ]


def test_a_zip_of_wheels_is_checked(manager) -> None:
    alone = _wheel("lonely", "1.0", tag="cp39-cp39-win_amd64")
    with pytest.raises(ExtensionValueError, match="do not fit this server"):
        manager.install_upload("bundle.zip", _zip(alone))
    first, second = _wheel("one", "1.0"), _wheel("two", "1.0")
    with pytest.raises(ExtensionValueError, match="Say which library"):
        manager.install_upload("bundle.zip", _zip(first, second))
    assert manager.install_upload("bundle.zip", _zip(first, second), name="two")["name"] == "two"
