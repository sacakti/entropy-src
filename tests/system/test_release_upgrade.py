"""Release package inspection, safe extraction, apply, failure restore and rollback."""

import io
import json
import tarfile
from pathlib import Path

import pytest

from core.version import VERSION
from lib.system import install
from lib.system.upgrade import ReleaseUpgrader, UpgradeError, _safe_members, read_manifest

PLATFORM = "linux-x86_64"


def _add(archive: tarfile.TarFile, name: str, data: bytes = b"", **fields) -> None:
    info = tarfile.TarInfo(name)
    info.size = len(data)
    for key, value in fields.items():
        setattr(info, key, value)
    archive.addfile(info, io.BytesIO(data) if data else None)


def _package(directory: Path, version: str, *, platform: str = PLATFORM, extra=None) -> Path:
    root = f"entropy-{version}"
    manifest = {
        "format": 2,
        "name": "entropy",
        "version": version,
        "platform": platform,
        "python": "3.9.20",
        "built_at": "2026-10-20T00:00:00+00:00",
    }
    path = directory / f"{root}-{platform}.tar.gz"
    with tarfile.open(path, "w:gz") as archive:
        _add(archive, f"{root}/manifest.json", json.dumps(manifest).encode())
        _add(archive, f"{root}/application/entropy.py", f"# {version}\n".encode())
        for item in extra or ():
            item(archive, root)
    return path


@pytest.fixture
def installation(tmp_path, monkeypatch):
    home = tmp_path / "home"
    root = tmp_path / "share"
    application = root / "application"
    application.mkdir(parents=True)
    (application / "entropy.py").write_text("# current\n", encoding="utf-8")
    (home / "site-packages").mkdir(parents=True)
    (home / "site-packages" / "old.txt").write_text("old", encoding="utf-8")
    monkeypatch.setenv("ENTROPY_HOME", str(home))
    install.save(
        {
            "version": VERSION,
            "python": "/usr/bin/python3",
            "deps": "bundled",
            "platform": PLATFORM,
            "application": str(application),
            "upgrades": [],
        }
    )
    return {
        "home": home,
        "root": root,
        "application": application,
        "packages": tmp_path / "packages",
    }


def _fake_steps(monkeypatch, *, fail_finalize: bool = False):
    def install_packages(self, python, application, target):
        target.mkdir(parents=True, exist_ok=True)
        (target / "new.txt").write_text("new", encoding="utf-8")

    def finalize(self, version):
        if fail_finalize:
            raise UpgradeError("The new version could not migrate the database: boom")
        return {"ok": True, "database": str(self.home / "entropy.db"), "backup": None}

    monkeypatch.setattr(ReleaseUpgrader, "_install_packages", install_packages)
    monkeypatch.setattr(ReleaseUpgrader, "_finalize", finalize)


def test_manifest_and_inspect(installation, tmp_path) -> None:
    package = _package(tmp_path, "99.0.0")

    assert read_manifest(package)["_root"] == "entropy-99.0.0"
    info = ReleaseUpgrader().inspect(package)
    assert info["newer"] and not info["same"] and info["problems"] == []
    assert info["current"] == VERSION


def test_inspect_reports_wrong_platform_and_older_version(installation, tmp_path) -> None:
    info = ReleaseUpgrader().inspect(_package(tmp_path, "0.0.1", platform="windows-x86_64"))

    assert not info["newer"]
    assert any("windows-x86_64" in problem for problem in info["problems"])


def test_source_checkouts_are_not_upgraded(installation, tmp_path) -> None:
    install.record_path().unlink()

    info = ReleaseUpgrader().inspect(_package(tmp_path, "99.0.0"))
    assert any("source checkout" in problem for problem in info["problems"])


def test_not_a_package(tmp_path) -> None:
    bogus = tmp_path / "bogus.tar.gz"
    bogus.write_bytes(b"not a tarball")
    with pytest.raises(UpgradeError):
        read_manifest(bogus)

    unrelated = tmp_path / "unrelated.tar.gz"
    with tarfile.open(unrelated, "w:gz") as archive:
        _add(archive, "something/README.txt", b"hi")
    with pytest.raises(UpgradeError, match="manifest.json"):
        read_manifest(unrelated)


@pytest.mark.parametrize(
    "item",
    [
        lambda archive, root: _add(archive, "../evil.txt", b"x"),
        lambda archive, root: _add(archive, "/etc/evil", b"x"),
        lambda archive, root: _add(
            archive, f"{root}/link", type=tarfile.SYMTYPE, linkname="/etc/passwd"
        ),
        lambda archive, root: _add(
            archive, f"{root}/a/link", type=tarfile.SYMTYPE, linkname="../../../etc"
        ),
        lambda archive, root: _add(
            archive, f"{root}/hard", type=tarfile.LNKTYPE, linkname="../outside"
        ),
        lambda archive, root: _add(archive, f"{root}/dev", type=tarfile.CHRTYPE),
    ],
)
def test_unsafe_members_are_refused(tmp_path, item) -> None:
    package = _package(tmp_path, "1.0.0", extra=[item])
    with tarfile.open(package, "r:gz") as archive, pytest.raises(UpgradeError):
        _safe_members(archive)


def test_links_inside_the_package_are_allowed(tmp_path) -> None:
    package = _package(
        tmp_path,
        "1.0.0",
        extra=[
            lambda archive, root: _add(
                archive, f"{root}/python/bin/python3", type=tarfile.SYMTYPE, linkname="python3.9"
            ),
            lambda archive, root: _add(
                archive, f"{root}/python/lib/x", type=tarfile.SYMTYPE, linkname="../bin/python3"
            ),
        ],
    )
    with tarfile.open(package, "r:gz") as archive:
        assert len(_safe_members(archive)) == 4


def test_apply_then_rollback(installation, tmp_path, monkeypatch) -> None:
    _fake_steps(monkeypatch)
    application = installation["application"]
    packages = installation["home"] / "site-packages"

    entry = ReleaseUpgrader().apply(_package(tmp_path, "99.0.0"), user="admin")

    assert entry["to"] == "99.0.0" and entry["by"] == "admin"
    assert (application / "entropy.py").read_text() == "# 99.0.0\n"
    assert (packages / "new.txt").exists()
    assert install.load()["version"] == "99.0.0"
    assert not (installation["root"] / "upgrade-staging").exists()

    upgrader = ReleaseUpgrader()
    assert upgrader.can_rollback()
    upgrader.rollback(user="admin")

    assert (application / "entropy.py").read_text() == "# current\n"
    assert (packages / "old.txt").exists()
    record = install.load()
    assert record["version"] == VERSION and record["upgrades"][-1]["rollback"]
    assert not ReleaseUpgrader().can_rollback()


def test_failed_upgrade_restores_everything(installation, tmp_path, monkeypatch) -> None:
    _fake_steps(monkeypatch, fail_finalize=True)

    with pytest.raises(UpgradeError, match="boom"):
        ReleaseUpgrader().apply(_package(tmp_path, "99.0.0"))

    assert (installation["application"] / "entropy.py").read_text() == "# current\n"
    assert (installation["home"] / "site-packages" / "old.txt").exists()
    assert install.load()["version"] == VERSION
    assert not (installation["home"] / "run" / "upgrade.lock").exists()


def test_downgrade_needs_permission(installation, tmp_path, monkeypatch) -> None:
    _fake_steps(monkeypatch)
    package = _package(tmp_path, "0.0.1")

    with pytest.raises(UpgradeError, match="not newer"):
        ReleaseUpgrader().apply(package)
    assert ReleaseUpgrader().apply(package, allow_downgrade=True)["to"] == "0.0.1"
