"""
Tests for oc.audit: what changed in a YAML repository since the last audit.

A real git repository is used in a temporary directory (git only; no oc and
no cluster). The user's global git configuration is kept out.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, Mock

import pytest
import yaml

from lib.executor import LinuxExecutor
from lib.plugins.arguments import PluginArguments
from lib.plugins.contract import check_source, declared, read_manifest
from lib.plugins.exceptions import PluginValueError
from resources.plugins.oc.audit.differ import compare, diff
from resources.plugins.oc.audit.plugin import AuditPlugin

PLUGIN_DIRECTORY = Path(__file__).resolve().parents[3] / "resources" / "plugins" / "oc" / "audit"


def configmap(data: dict[str, str]) -> dict[str, Any]:
    return {
        "apiVersion": "v1",
        "kind": "ConfigMap",
        "metadata": {"name": "app-config"},
        "data": data,
    }


def secret(data: dict[str, str]) -> dict[str, Any]:
    return {"apiVersion": "v1", "kind": "Secret", "metadata": {"name": "app-secret"}, "data": data}


def deployment(image: str, env: list[dict[str, str]]) -> dict[str, Any]:
    return {
        "apiVersion": "apps/v1",
        "kind": "Deployment",
        "metadata": {"name": "app", "resourceVersion": image},
        "spec": {
            "replicas": 2,
            "template": {"spec": {"containers": [{"name": "app", "image": image, "env": env}]}},
        },
    }


@pytest.fixture(autouse=True)
def isolated_git(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(tmp_path / "no-global-gitconfig"))
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")


@pytest.fixture()
def repository(tmp_path: Path) -> Path:
    repo = tmp_path / "SIT"
    repo.mkdir()
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    write(
        repo,
        "configmaps/app-config.yaml",
        configmap({"LOG_LEVEL": "info", "OLD_KEY": "x", "app.properties": "a=1\nb=2\n"}),
    )
    write(repo, "secrets/app-secret.yaml", secret({"password": "c2VjcmV0"}))
    write(
        repo,
        "deployments/app.yaml",
        deployment("quay.io/app:1.0", [{"name": "MODE", "value": "a"}]),
    )
    write(
        repo,
        "services/app.yaml",
        {"kind": "Service", "metadata": {"name": "app"}, "spec": {"ports": [{"port": 80}]}},
    )
    return repo


def write(repo: Path, relative: str, document: dict[str, Any]) -> None:
    path = repo / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(document, sort_keys=False))


def run(arguments: dict[str, Any], **context_values: Any) -> Any:
    context = MagicMock()
    context.repositories = {}
    context.git_repository_info = lambda name: {"name": name, "source_type": "managed"}
    context.arguments = PluginArguments(arguments)
    executor = LinuxExecutor()
    context.filesystem = executor
    context.shell = executor
    context.outputs = {}
    context.artifacts = {}
    context.message = Mock()
    context.log = Mock()
    for name, value in context_values.items():
        setattr(context, name, value)
    result = AuditPlugin(context).execute()
    result.artifacts = context.artifacts
    return result


def git(repo: Path, *arguments: str) -> str:
    return subprocess.run(
        ["git", *arguments], cwd=repo, check=True, capture_output=True, text=True
    ).stdout


def test_contract_declares_every_argument_the_code_reads():
    assert check_source(PLUGIN_DIRECTORY, declared(read_manifest(PLUGIN_DIRECTORY))) == []


def test_first_audit_lists_everything_and_commits(repository: Path):
    result = run({"repository": str(repository)})

    assert result.success, result.errors
    assert result.outputs["summary"] == {"modified": 0, "added": 4, "removed": 0, "changes": 0}
    assert result.outputs["base_commit"] == "" and result.outputs["commit"]
    assert git(repository, "status", "--porcelain") == ""
    assert "first audit" in git(repository, "log", "-1", "--format=%s")

    report = Path(result.outputs["report"])
    assert report.parent == repository.parent / "SIT-audit"
    assert result.artifacts["audit_report"] == report
    html = report.read_text()
    assert "First audit" in html and "container app: quay.io/app:1.0" in html
    assert "c2VjcmV0" not in html


def test_second_audit_reports_key_and_field_changes(repository: Path):
    run({"repository": str(repository)})
    write(
        repository,
        "configmaps/app-config.yaml",
        configmap({"LOG_LEVEL": "debug", "NEW_KEY": "1", "app.properties": "a=1\nb=3\n"}),
    )
    write(repository, "secrets/app-secret.yaml", secret({"password": "bmV3c2VjcmV0"}))
    write(
        repository,
        "deployments/app.yaml",
        deployment("quay.io/app:2.0", [{"name": "MODE", "value": "b"}]),
    )
    (repository / "services/app.yaml").unlink()

    result = run({"repository": str(repository)})

    assert result.success, result.errors
    assert result.outputs["summary"]["modified"] == 3
    assert result.outputs["summary"]["removed"] == 1
    html = Path(result.outputs["report"]).read_text()
    # ConfigMap: each key, with before and after; multi-line values as a line diff.
    for text in ("LOG_LEVEL", "info", "debug", "NEW_KEY", "OLD_KEY", "-b=2", "+b=3"):
        assert text in html, text
    # Deployment: matched by container and env name; resourceVersion is ignored.
    assert "spec.template.spec.containers[app].image" in html
    assert "spec.template.spec.containers[app].env[MODE].value" in html
    assert "metadata.resourceVersion" not in html
    # Secret: the key is reported, never its values.
    assert "Value hidden (Secret)" in html and "bmV3c2VjcmV0" not in html and "c2VjcmV0" not in html
    assert "3 modified, 0 added, 1 removed" in git(repository, "log", "-1", "--format=%s")


def test_no_changes_writes_report_without_commit(repository: Path):
    run({"repository": str(repository)})
    before = git(repository, "rev-parse", "HEAD")

    result = run({"repository": str(repository)})

    assert result.success, result.errors
    assert result.outputs["commit"] == ""
    assert git(repository, "rev-parse", "HEAD") == before
    assert "No changes." in Path(result.outputs["report"]).read_text()


def test_reports_older_than_retention_are_removed(repository: Path, tmp_path: Path):
    reports = tmp_path / "reports"
    reports.mkdir()
    old = reports / "audit-20200101-090000.html"
    other = reports / "notes.html"
    old.write_text("old")
    other.write_text("not a report")

    result = run(
        {"repository": str(repository), "report_directory": str(reports), "retention_days": 10}
    )

    assert result.success, result.errors
    assert not old.exists() and other.exists()
    assert result.outputs["removed_reports"] == [str(old.resolve())]
    assert result.outputs["reports"] == [result.outputs["report"]]


def test_report_directory_inside_repository_is_git_ignored(repository: Path):
    result = run(
        {"repository": str(repository), "report_directory": str(repository / "audit-reports")}
    )

    assert result.success, result.errors
    assert "/audit-reports/" in (repository / ".gitignore").read_text().splitlines()
    tracked = git(repository, "ls-files")
    assert "audit-reports" not in tracked and ".gitignore" in tracked


def test_commit_off_leaves_git_alone(repository: Path):
    result = run({"repository": str(repository), "commit": False})

    assert result.success, result.errors
    assert result.outputs["commit"] == ""
    assert (
        subprocess.run(["git", "rev-parse", "--verify", "-q", "HEAD"], cwd=repository).returncode
        != 0
    )


def test_not_a_git_repository_fails(tmp_path: Path):
    plain = tmp_path / "plain"
    plain.mkdir()

    result = run({"repository": str(plain)})

    assert not result.success
    assert "not a git repository" in result.errors[0]


def test_named_lists_match_by_name_not_position():
    old = {"containers": [{"name": "a", "image": "1"}, {"name": "b", "image": "1"}]}
    new = {"containers": [{"name": "b", "image": "1"}, {"name": "a", "image": "2"}]}

    assert diff(old, new) == [
        {"path": "containers[a].image", "change": "changed", "before": "1", "after": "2"}
    ]


def test_only_ignored_fields_changed_is_not_reported():
    old = {"kind": "Service", "metadata": {"name": "s", "resourceVersion": "1"}, "status": {"x": 1}}
    new = {"kind": "Service", "metadata": {"name": "s", "resourceVersion": "2"}, "status": {"x": 2}}

    assert compare(old, new, "services/s.yaml") is None
    assert compare(old, new, "services/s.yaml", ignored=())["fields"]


@pytest.fixture()
def managed(tmp_path: Path) -> dict[str, Path]:
    """A Tools -> Git repositories repository (bare) and the run's checkout of it."""

    bare = tmp_path / "managed" / "sit-yamls.git"
    subprocess.run(["git", "init", "-q", "--bare", str(bare)], check=True)
    checkout = tmp_path / "workspace" / ".entropy-repositories" / "1-sit-yamls"
    subprocess.run(
        ["git", "clone", "-q", str(bare), str(checkout)], check=True, capture_output=True
    )
    # oc.sync_yamls writes into the checkout.
    write(checkout, "configmaps/app-config.yaml", configmap({"LOG_LEVEL": "info"}))
    return {"bare": bare, "checkout": checkout}


def checkout_for(paths: dict[str, Path]) -> Any:
    def git_repository(name: str) -> Path:
        if name != "sit-yamls":
            raise PluginValueError(
                f"No Git repository '{name}' is available to you in this project."
            )
        return paths["checkout"]

    return git_repository


def test_git_repository_is_audited_committed_and_pushed(managed: dict[str, Path], tmp_path: Path):
    data = tmp_path / "plugin-data"

    result = run(
        {"git_repository": "sit-yamls"},
        git_repository=checkout_for(managed),
        data_directory=data,
    )

    assert result.success, result.errors
    assert result.outputs["git_repository"] == "sit-yamls" and result.outputs["pushed"] is True
    # The commit reached the managed repository, not only the temporary checkout.
    assert "first audit" in git(managed["bare"], "log", "-1", "--format=%s")
    # Reports outlast the run workspace.
    report = Path(result.outputs["report"])
    assert report.parent == (data / "reports" / "sit-yamls").resolve()
    assert "sit-yamls (Tools → Git repositories)" in report.read_text()


def test_single_assigned_repository_is_used(managed: dict[str, Path], tmp_path: Path):
    result = run(
        {},
        repositories={"sit-yamls": managed["checkout"]},
        data_directory=tmp_path / "plugin-data",
    )

    assert result.success, result.errors
    assert result.outputs["git_repository"] == "sit-yamls" and result.outputs["pushed"] is True


def test_repository_choice_errors(managed: dict[str, Path], repository: Path):
    both = run({"repository": str(repository), "git_repository": "sit-yamls"})
    assert not both.success and "not both" in both.errors[0]

    unknown = run({"git_repository": "nope"}, git_repository=checkout_for(managed))
    assert not unknown.success and "No Git repository 'nope'" in unknown.errors[0]

    several = run({}, repositories={"a": repository, "b": managed["checkout"]})
    assert not several.success and "several are assigned to this run: a, b" in several.errors[0]


def test_folder_repository_is_not_pushed_by_default(repository: Path):
    result = run({"repository": str(repository)})

    assert result.success, result.errors
    assert result.outputs["pushed"] is False


def test_repository_created_from_a_folder_audits_that_folder(repository: Path, tmp_path: Path):
    """Tools -> Git repositories made from a server folder: Entropy keeps a --mirror copy."""

    git(repository, "add", "-A")
    git(repository, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "initial")
    mirror = tmp_path / "git-repositories" / "abc.git"
    subprocess.run(["git", "clone", "-q", "--mirror", str(repository), str(mirror)], check=True)
    # oc.sync_yamls then writes new content into the folder, not into the copy.
    write(
        repository,
        "configmaps/app-config.yaml",
        configmap({"LOG_LEVEL": "debug", "OLD_KEY": "x", "app.properties": "a=1\nb=2\n"}),
    )
    info = {
        "name": "SIT",
        "source_type": "local",
        "source_location": str(repository),
        "path": str(mirror),
    }

    result = run(
        {"git_repository": "SIT"},
        git_repository_info=lambda name: info,
        git_repository=Mock(side_effect=AssertionError("a folder repository is not checked out")),
        data_directory=tmp_path / "plugin-data",
    )

    assert result.success, result.errors
    assert result.outputs["repository"] == str(repository.resolve())
    assert result.outputs["summary"]["modified"] == 1 and result.outputs["pushed"] is True
    html = Path(result.outputs["report"]).read_text()
    assert "LOG_LEVEL" in html and "debug" in html and "was created from the server folder" in html
    # The audit commit is in the folder and in Entropy's copy.
    branch = git(repository, "rev-parse", "--abbrev-ref", "HEAD").strip()
    assert git(repository, "rev-parse", "HEAD") == git(mirror, "rev-parse", branch)


def test_git_repository_argument_offers_the_repository_picker():
    contract = declared(read_manifest(PLUGIN_DIRECTORY))
    pickers = {item["name"]: item.get("picker") for item in contract["arguments"]}

    assert pickers["git_repository"] == "git_repository"
