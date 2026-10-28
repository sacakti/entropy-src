#!/usr/bin/env python3
"""
Check the results of the ReleaseScenarios workflow in a sandbox made by
build.py.

Usage:
    python verify.py <sandbox directory>

Exits with 1 when any check fails.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

import yaml

Check = Tuple[str, Callable[[Path], Optional[str]]]


def _document(path: Path) -> Dict[str, Any]:
    if not path.is_file():
        raise AssertionError(f"missing file {path}")
    document: Dict[str, Any] = yaml.safe_load(path.read_text())
    return document


def _pod(repository: Path, name: str) -> Dict[str, Any]:
    pod: Dict[str, Any] = _document(repository / "deployments" / f"{name}.yaml")["spec"][
        "template"
    ]["spec"]
    return pod


def _container(repository: Path, name: str) -> Dict[str, Any]:
    container: Dict[str, Any] = _pod(repository, name)["containers"][0]
    return container


def _env(repository: Path, name: str) -> Dict[str, Any]:
    return {item["name"]: item.get("value") for item in _container(repository, name).get("env", [])}


def _expect(label: str, actual: Any, expected: Any) -> Optional[str]:
    if actual != expected:
        return f"{label}: expected {expected!r}, got {actual!r}"
    return None


def _prepared_apply(sandbox: Path, scenario: str, scripts: str) -> Optional[str]:
    script = sandbox / "releases" / scenario / scripts / "apply_yaml.sh"
    if not script.is_file():
        return f"prepared apply script not found: {script}"
    text = script.read_text()
    problems = []
    if "oc login https://api.example.cluster:6443" not in text:
        problems.append("oc login credentials were not removed")
    if "git pull" in text:
        problems.append("git command was not removed")
    if "/home/devops" in text:
        problems.append("oc apply path was not rewritten")
    return "; ".join(problems) or None


def s1(sandbox: Path) -> Optional[str]:
    yamls = sandbox / "yamls" / "S1"
    return _expect(
        "app-1 image", _container(yamls, "app-1")["image"], "quay.io/sacakti/app-1:2.0.0"
    )


def _app_1_fields(yamls: Path) -> Optional[str]:
    pod = _pod(yamls, "app-1")
    return (
        _expect("app-1 env", _env(yamls, "app-1"), {"LOG_LEVEL": "debug", "APP_MODE": "production"})
        or _expect(
            "app-1 volumes",
            pod.get("volumes"),
            [{"name": "app-config", "configMap": {"name": "app-config"}}],
        )
        or _expect(
            "app-1 volumeMounts",
            pod["containers"][0].get("volumeMounts"),
            [{"name": "app-config", "mountPath": "/etc/app"}],
        )
    )


def s2(sandbox: Path) -> Optional[str]:
    yamls = sandbox / "yamls" / "S2"
    return _app_1_fields(yamls) or _expect(
        "app-1 image (unchanged)",
        _container(yamls, "app-1")["image"],
        "quay.io/sacakti/app-1:1.0.0",
    )


def s3(sandbox: Path) -> Optional[str]:
    yamls = sandbox / "yamls" / "S3"
    return _app_1_fields(yamls) or _expect(
        "app-1 image", _container(yamls, "app-1")["image"], "quay.io/sacakti/app-1:2.0.0"
    )


def s4(sandbox: Path) -> Optional[str]:
    yamls = sandbox / "yamls" / "S4"
    return (
        _expect(
            "app1 image",
            _container(yamls, "app1")["image"],
            "quay.io/sacakti/app1/app-service:1.5.0",
        )
        or _expect("app1 env (unchanged)", _env(yamls, "app1"), {"LOG_LEVEL": "info"})
        or _prepared_apply(sandbox, "S4-transfer-only", "scripts/deploy")
    )


def s5(sandbox: Path) -> Optional[str]:
    yamls = sandbox / "yamls" / "S5"
    return (
        _expect(
            "app1 image",
            _container(yamls, "app1")["image"],
            "quay.io/sacakti/app1/app-service:1.6.0",
        )
        or _expect("app1 env", _env(yamls, "app1"), {"APP_MODE": "published"})
        or _prepared_apply(
            sandbox, "S5-published-transfer-and-fields", "App-Published/scripts/deploy"
        )
    )


def s6(sandbox: Path) -> Optional[str]:
    yamls = sandbox / "yamls" / "S6"
    return _expect(
        "app-3 created", _container(yamls, "app-3")["image"], "quay.io/sacakti/app-3:1.0.0"
    ) or _expect(
        "app-2 image (whole-file update skipped)",
        _container(yamls, "app-2")["image"],
        "quay.io/sacakti/app-2:1.0.0",
    )


def s7(sandbox: Path) -> Optional[str]:
    folder = sandbox / "folder"
    for name in ("app-1", "app-2"):
        problem = _expect(f"{name} FOLDER_MODE", _env(folder, name).get("FOLDER_MODE"), "yes")
        if problem:
            return problem
    return None


CHECKS: List[Check] = [
    ("S1 docker build -> image tag", s1),
    ("S2 DeploymentUpdate -> env/mounts/volumes", s2),
    ("S3 docker build + DeploymentUpdate", s3),
    ("S4 scripts-only image_transfer.sh -> image tag", s4),
    ("S5 App-Published: DeploymentUpdate + image_transfer.sh", s5),
    ("S6 new Deployment created, whole-file update skipped", s6),
    ("S7 folder mode, several DeploymentUpdate files", s7),
]


def main() -> None:
    if len(sys.argv) != 2:
        sys.exit(__doc__)

    sandbox = Path(sys.argv[1]).expanduser().resolve()
    failed = 0

    for label, check in CHECKS:
        try:
            problem = check(sandbox)
        except (AssertionError, KeyError, IndexError, TypeError) as exc:
            problem = f"{type(exc).__name__}: {exc}"
        print(f"{'PASS' if problem is None else 'FAIL'}  {label}")
        if problem:
            print(f"      {problem}")
            failed += 1

    print(f"\n{len(CHECKS) - failed}/{len(CHECKS)} scenarios passed.")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
