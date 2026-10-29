"""
Tests for the skopeo.generic plugin: image references, selection, pods, skopeo.
"""

from __future__ import annotations

import base64
import json
from contextlib import nullcontext
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict, List
from unittest.mock import Mock

import pytest

from lib.plugins import contract
from lib.plugins.arguments import PluginArguments
from resources.plugins.skopeo.generic.exceptions import SkopeoRuleError
from resources.plugins.skopeo.generic.images import ImageReference, digest_of, parse_rules
from resources.plugins.skopeo.generic.plugin import SkopeoGenericPlugin

PLUGIN_DIRECTORY = (
    Path(__file__).resolve().parents[3] / "resources" / "plugins" / "skopeo" / "generic"
)
REGISTRY = "quay.example.com/finance"
DIGEST_A = "sha256:" + "a" * 64
DIGEST_B = "sha256:" + "b" * 64
DIGEST_S = "sha256:" + "c" * 64


# ----------------------------------------------------------------------
# Image references and rules
# ----------------------------------------------------------------------


@pytest.mark.parametrize(
    "text, registry, repository, tag, digest",
    [
        (f"{REGISTRY}/app:1.2.0", "quay.example.com", "finance/app", "1.2.0", None),
        ("nginx", "docker.io", "library/nginx", None, None),
        ("bitnami/redis:7", "docker.io", "bitnami/redis", "7", None),
        ("reg.local:5000/a/b:t-1", "reg.local:5000", "a/b", "t-1", None),
        ("localhost/x:y", "localhost", "x", "y", None),
        (f"docker://{REGISTRY}/app@{DIGEST_A}", "quay.example.com", "finance/app", None, DIGEST_A),
        (f"{REGISTRY}/app:1.0@{DIGEST_A}", "quay.example.com", "finance/app", "1.0", DIGEST_A),
    ],
)
def test_image_references(text: str, registry: str, repository: str, tag, digest) -> None:
    reference = ImageReference.parse(text)
    assert (reference.registry, reference.repository, reference.tag, reference.digest) == (
        registry,
        repository,
        tag,
        digest,
    )


def test_digest_of_container_image_ids() -> None:
    assert digest_of(f"{REGISTRY}/app@{DIGEST_A}") == DIGEST_A
    assert digest_of(f"docker-pullable://{REGISTRY}/app@{DIGEST_A}") == DIGEST_A
    assert digest_of(DIGEST_A) == DIGEST_A
    assert digest_of("") is None
    assert digest_of("sha256:short") is None


@pytest.mark.parametrize(
    "rules, message",
    [
        (["app-*"], "must be an object"),
        ([{}], "needs deployments, tags or containers"),
        ([{"deployments": "x", "names": "y"}], "unknown field"),
        ([{"tags": "re:("}], "invalid regular expression"),
        ([{"deployments": 3}], "pattern or a list"),
    ],
)
def test_bad_rules_are_refused(rules: list, message: str) -> None:
    with pytest.raises(SkopeoRuleError, match=message):
        parse_rules(rules)


# ----------------------------------------------------------------------
# OpenShift objects
# ----------------------------------------------------------------------


def _workload(kind: str, name: str, image: str) -> Dict[str, Any]:
    return {
        "kind": kind,
        "metadata": {"name": name, "namespace": "fin"},
        "spec": {"template": {"spec": {"containers": [{"name": "app", "image": image}]}}},
    }


def _controller(kind: str, name: str, owner_kind: str, owner: str) -> Dict[str, Any]:
    return {
        "kind": kind,
        "metadata": {
            "name": name,
            "namespace": "fin",
            "ownerReferences": [{"kind": owner_kind, "name": owner, "controller": True}],
        },
    }


def _pod(name: str, owner_kind: str, owner: str, image: str, digest: str, phase="Running"):
    return {
        "kind": "Pod",
        "metadata": {
            "name": name,
            "namespace": "fin",
            "ownerReferences": [{"kind": owner_kind, "name": owner, "controller": True}],
        },
        "spec": {"containers": [{"name": "app", "image": image}]},
        "status": {
            "phase": phase,
            "containerStatuses": [
                {"name": "app", "image": image, "imageID": f"{image.split(':')[0]}@{digest}"}
            ],
        },
    }


API = f"{REGISTRY}/app-finance-api:release-1.2.0-b7"
OBJECTS = [
    _workload("Deployment", "app-finance-api", API),
    _controller("ReplicaSet", "app-finance-api-1", "Deployment", "app-finance-api"),
    _controller("ReplicaSet", "app-finance-api-2", "Deployment", "app-finance-api"),
    # A rollout: two pods run different digests of the same tag.
    _pod("api-1-a", "ReplicaSet", "app-finance-api-1", API, DIGEST_A),
    _pod("api-1-b", "ReplicaSet", "app-finance-api-1", API, DIGEST_A),
    _pod("api-2-a", "ReplicaSet", "app-finance-api-2", API, DIGEST_B),
    _pod("api-old", "ReplicaSet", "app-finance-api-1", API, DIGEST_B, phase="Succeeded"),
    _workload("Deployment", "app-finance-ui", f"{REGISTRY}/app-finance-ui:1.1.0"),
    _controller("ReplicaSet", "app-finance-ui-1", "Deployment", "app-finance-ui"),
    _pod("ui-1", "ReplicaSet", "app-finance-ui-1", f"{REGISTRY}/app-finance-ui:1.1.0", DIGEST_A),
    # Scaled to 0: no pods.
    _workload("Deployment", "app-finance-batch", f"{REGISTRY}/app-finance-batch:release-1.2.0"),
    _workload("Deployment", "app-finance-canary", f"{REGISTRY}/app-finance-api:1.3.0"),
    _workload("DeploymentConfig", "app-hr-api", "quay.example.com/hr/app-hr-api:2.0.0"),
    _controller("ReplicationController", "app-hr-api-4", "DeploymentConfig", "app-hr-api"),
    _pod(
        "hr-4-a",
        "ReplicationController",
        "app-hr-api-4",
        "quay.example.com/hr/app-hr-api:2.0.0",
        DIGEST_B,
    ),
    _workload("Deployment", "payments", "quay.example.com/pay/payments:9.9.9"),
]


def _result(stdout: str = "", success: bool = True, stderr: str = "") -> SimpleNamespace:
    return SimpleNamespace(
        success=success, stdout=stdout, stderr=stderr, exit_code=0 if success else 1
    )


class TestSkopeoGenericPlugin:

    def setup_method(self) -> None:
        self.context = Mock()
        self.context.outputs = {}
        self.context.artifacts = {}
        self.context.activity.return_value = nullcontext()
        self.context.session_directory = Path("/sessions")
        self.context.workspace = Path("/workspace")
        self.context.data_directory = Path("/data/skopeo.generic")
        self.context.filesystem.exists.return_value = True
        self.context.filesystem.path.side_effect = Path
        self.commands: List[List[str]] = []
        self.environments: List[Any] = []
        self.skopeo_failures: Dict[str, str] = {}
        self.context.shell.run.side_effect = self._shell

    def _shell(self, command: List[str], **options: Any) -> SimpleNamespace:
        self.commands.append(command)
        self.environments.append(options.get("env"))
        if command[0] == "oc":
            return _result(json.dumps({"kind": "List", "items": OBJECTS}))
        image = command[-1][len("docker://") :]
        if image in self.skopeo_failures:
            return _result(success=False, stderr=self.skopeo_failures[image])
        return _result(
            json.dumps({"Name": image, "Digest": DIGEST_S, "Created": "2026-10-01T10:00:00Z"})
        )

    def _run(self, **arguments: Any):
        self.context.arguments = PluginArguments(arguments)
        return SkopeoGenericPlugin(self.context).execute()

    def _skopeo(self) -> List[List[str]]:
        return [command for command in self.commands if command[0] == "skopeo"]

    def test_pod_mode_reads_running_pods_with_one_oc_call(self) -> None:
        result = self._run(
            mode="pod", environment="SIT", namespace="fin", deployments="app-finance-*"
        )

        assert result.success is True and result.changed is False
        assert self.commands[0] == [
            "oc",
            "get",
            "deployment,deploymentconfig,replicaset,replicationcontroller,pod",
            "-o",
            "json",
            "-n",
            "fin",
        ]
        assert self.environments[0] == {"KUBECONFIG": "/sessions/.kube/SIT/config"}
        assert self._skopeo() == []

        api = [row for row in result.outputs["images"] if row["deployment"] == "app-finance-api"]
        assert [(row["digest"], sorted(row["pods"])) for row in api] == [
            (DIGEST_A, ["api-1-a", "api-1-b"]),
            (DIGEST_B, ["api-2-a"]),
        ]
        assert api[0]["image"] == API and api[0]["registry"] == "quay.example.com"
        assert api[0]["tag"] == "release-1.2.0-b7" and api[0]["source"] == "pod"
        assert api[0]["reference"] == f"{REGISTRY}/app-finance-api@{DIGEST_A}"
        assert result.outputs["missing"] == ["app-finance-batch/app", "app-finance-canary/app"]
        assert result.outputs["digests"]["app-finance-ui"]["app"] == {
            "image": f"{REGISTRY}/app-finance-ui:1.1.0",
            "digest": DIGEST_A,
        }
        assert isinstance(result.outputs["digests"]["app-finance-api"]["app"], list)
        assert "payments" not in result.outputs["deployments"]

    def test_tag_rules_exclude_and_deploymentconfigs(self) -> None:
        result = self._run(
            mode="pod",
            environment="SIT",
            rules=[
                {"deployments": "app-finance-*", "tags": "*-1.2.0*"},
                {"deployments": "re:^app-hr-"},
            ],
            exclude=["*-canary"],
        )

        found = {(row["deployment"], row["tag"]) for row in result.outputs["images"]}
        assert found == {("app-finance-api", "release-1.2.0-b7"), ("app-hr-api", "2.0.0")}
        hr = next(row for row in result.outputs["images"] if row["deployment"] == "app-hr-api")
        assert hr["kind"] == "deploymentconfig" and hr["pods"] == ["hr-4-a"]
        # The batch has the tag but no pod; ui's 1.1.0 does not match the tag rule.
        assert result.outputs["missing"] == ["app-finance-batch/app"]
        # Selected workloads, resolved or not.
        assert result.outputs["deployments"] == [
            "app-finance-api",
            "app-finance-batch",
            "app-hr-api",
        ]

    def test_auto_falls_back_to_skopeo_without_a_running_pod(self) -> None:
        result = self._run(environment="SIT", deployments=["app-finance-batch", "app-finance-api"])

        assert result.success is True
        assert self._skopeo() == [
            [
                "skopeo",
                "inspect",
                "--no-tags",
                f"docker://{REGISTRY}/app-finance-batch:release-1.2.0",
            ]
        ]
        batch = next(r for r in result.outputs["images"] if r["deployment"] == "app-finance-batch")
        assert batch["source"] == "skopeo" and batch["digest"] == DIGEST_S
        assert batch["created"] == "2026-10-01T10:00:00Z"
        assert result.outputs["missing"] == []

    def test_skopeo_mode_inspects_each_image_once(self) -> None:
        result = self._run(
            mode="skopeo",
            environment="SIT",
            deployments=["app-finance-api", "app-finance-canary"],
            tls_verify=False,
            images=[f"{REGISTRY}/app-finance-api:release-1.2.0-b7", "nginx:1.27"],
            tags=["*-1.2.0*", "1.27"],
        )

        inspected = [command[-1] for command in self._skopeo()]
        assert inspected == [f"docker://{API}", "docker://docker.io/library/nginx:1.27"]
        assert all("--tls-verify=false" in command for command in self._skopeo())
        assert {row["source"] for row in result.outputs["images"]} == {"skopeo"}
        assert result.outputs["count"] == 3  # api, and the two direct images
        assert result.outputs["digests"][f"{API}"]["image"]["digest"] == DIGEST_S

    def test_images_alone_need_no_openshift(self) -> None:
        result = self._run(images=["quay.example.com/x/y:1"])
        assert result.success is True
        assert [command[0] for command in self.commands] == ["skopeo"]
        assert result.outputs["images"][0]["deployment"] is None

    def test_credentials_go_to_a_private_temporary_auth_file(self) -> None:
        self._run(
            mode="skopeo",
            environment="SIT",
            deployments="app-hr-api",
            credentials={"username": "robot", "password": "pa55"},
        )

        path, text = self.context.filesystem.write_text.call_args[0]
        assert path.parent == Path("/workspace") and path.name.startswith(".skopeo-auth-")
        auth = json.loads(text)["auths"]["quay.example.com"]["auth"]
        assert base64.b64decode(auth).decode() == "robot:pa55"
        self.context.filesystem.chmod.assert_called_once_with(path, 0o600)
        self.context.filesystem.remove.assert_called_once_with(path)
        assert ["--authfile", str(path)] == self._skopeo()[0][3:5]
        assert not any("pa55" in " ".join(command) for command in self.commands)

    def test_inspect_failures(self) -> None:
        self.skopeo_failures[f"{REGISTRY}/app-finance-batch:release-1.2.0"] = "manifest unknown"

        failed = self._run(environment="SIT", deployments="app-finance-batch")
        assert failed.success is False
        assert failed.errors == [f"{REGISTRY}/app-finance-batch:release-1.2.0: manifest unknown"]

        tolerated = self._run(
            environment="SIT", deployments="app-finance-batch", fail_on_error=False
        )
        assert tolerated.success is True and tolerated.outputs["errors"]

    def test_a_missing_login_points_to_oc_generic(self) -> None:
        self.context.filesystem.exists.return_value = False
        result = self._run(environment="UAT")
        assert result.success is False and "oc.generic" in result.errors[0]

    @pytest.mark.parametrize(
        "arguments, message",
        [
            ({"mode": "registry", "environment": "SIT"}, "'mode' must be one of"),
            ({}, "Give 'environment'"),
            ({"mode": "pod", "images": ["a/b:c"]}, "needs 'environment'"),
            ({"environment": "SIT", "kinds": ["cronjob"]}, "unknown: cronjob"),
        ],
    )
    def test_invalid_arguments(self, arguments: Dict[str, Any], message: str) -> None:
        result = self._run(**arguments)
        assert result.success is False and message in result.errors[0]

    # ------------------------------------------------------------------
    # generate
    # ------------------------------------------------------------------

    def _written(self) -> Dict[str, str]:
        return {
            str(call.args[0]): call.args[1]
            for call in self.context.filesystem.write_text.call_args_list
        }

    def test_generate_writes_image_checksum_lines(self) -> None:
        import re

        result = self._run(
            mode="pod",
            environment="SIT",
            namespace="fin",
            deployments="app-finance-*",
            generate=True,
        )

        path = self.context.artifacts["image_checksums"]
        assert path.parent == Path("/data/skopeo.generic/generated")
        assert re.fullmatch(r"fin-\d{8}-\d{6}\.txt", path.name)
        assert result.outputs["file"] == str(path)
        self.context.filesystem.mkdir.assert_called_with(path.parent)
        # One line per distinct image and checksum, in the order found.
        assert self._written()[str(path)].splitlines() == [
            f"{API}:{DIGEST_A}",
            f"{API}:{DIGEST_B}",
            f"{REGISTRY}/app-finance-ui:1.1.0:{DIGEST_A}",
        ]

    def test_generate_names_the_file_after_the_namespace_read(self) -> None:
        self._run(
            environment="SIT", deployments="app-hr-api", generate=True, output_directory="/out"
        )
        path = self.context.artifacts["image_checksums"]
        assert path.parent == Path("/out") and path.name.startswith("fin-")
        assert self._written()[str(path)] == f"quay.example.com/hr/app-hr-api:2.0.0:{DIGEST_B}\n"

    def test_nothing_is_generated_by_default(self) -> None:
        result = self._run(environment="SIT", deployments="app-hr-api")
        assert result.outputs["file"] == "" and "image_checksums" not in self.context.artifacts
        self.context.filesystem.write_text.assert_not_called()


def test_manifest_contract_and_oc_generic_requirement() -> None:
    declared = contract.declared(contract.read_manifest(PLUGIN_DIRECTORY))
    assert declared is not None
    assert contract.check_source(PLUGIN_DIRECTORY, declared) == []
    manifest = json.loads((PLUGIN_DIRECTORY / "plugin.json").read_text(encoding="utf-8"))
    assert manifest["required_plugins"] == [{"name": "oc.generic", "version": ">=1.0.4"}]
