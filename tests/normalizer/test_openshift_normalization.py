"""
OpenShift normalization and YAML formatting tests.
"""

from __future__ import annotations

import yaml

from lib.formatter.formats.yaml import YamlFormatter
from lib.normalizer import (
    NormalizerManager,
    StructureLoader,
)


def test_openshift_normalization_and_formatting() -> None:
    """
    Normalize an OpenShift resource and serialize it as YAML.
    """

    loader = StructureLoader()

    structure = loader.load(
        "resources/structures/openshift.yaml",
    )

    document = yaml.safe_load(
        """
apiVersion: v1
kind: ConfigMap

metadata:
  name: application-config
  namespace: entropy

  creationTimestamp: "2026-08-15T10:00:00Z"
  generation: 3
  resourceVersion: "123456"
  uid: abc-def

  managedFields:
    - manager: kubectl

  annotations:
    kubectl.kubernetes.io/last-applied-configuration: unwanted
    openshift.openshift.io/restartedAt: unwanted
    kubectl.kubernetes.io/restartedAt: unwanted
    custom.annotation: keep-me

data:
  application.properties: |
    application.name=entropy
    application.port=8081
    redis.host=redis
    redis.port=6379

  application.yaml: |
    server:
      port: 8081
    redis:
      timeout: 1500

status:
  unwanted: true
""",
    )

    normalizer = NormalizerManager()

    normalized = normalizer.normalize(
        document,
        structure,
    )

    formatter = YamlFormatter()

    formatted = formatter.format(
        yaml.safe_dump(
            normalized,
            sort_keys=False,
            allow_unicode=True,
        ),
    )

    assert "creationTimestamp" not in formatted
    assert "generation" not in formatted
    assert "resourceVersion" not in formatted
    assert "uid:" not in formatted
    assert "managedFields" not in formatted

    assert "kubectl.kubernetes.io/last-applied-configuration" not in formatted
    assert "openshift.openshift.io/restartedAt" not in formatted
    assert "kubectl.kubernetes.io/restartedAt" not in formatted

    assert "custom.annotation: keep-me" in formatted

    assert "status:" not in formatted

    assert "application.properties: |" in formatted
    assert "application.name=entropy" in formatted
    assert "application.port=8081" in formatted

    assert "application.yaml: |" in formatted
    assert "server:" in formatted
    assert "port: 8081" in formatted
    assert "timeout: 1500" in formatted
