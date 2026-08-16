from __future__ import annotations

import yaml

from lib.normalizer import (
    NormalizerManager,
    StructureLoader,
)


def test_openshift_structure() -> None:

    loader = StructureLoader()

    structure = loader.load(
        "resources/structures/openshift.yaml",
    )

    document = yaml.safe_load(
        """
apiVersion: apps/v1
kind: Deployment

metadata:
  name: app-1
  namespace: entropy
  creationTimestamp: "2026-08-15T10:00:00Z"
  generation: 4
  resourceVersion: "123456"
  uid: abc-def
  managedFields:
    - manager: kubectl

  annotations:
    kubectl.kubernetes.io/last-applied-configuration: unwanted
    openshift.openshift.io/restartedAt: unwanted
    custom.annotation: keep-me

spec:
  replicas: 2

  template:
    metadata:
      creationTimestamp: null
      labels:
        app: app-1

status:
  availableReplicas: 2
  readyReplicas: 2
""",
    )

    normalizer = NormalizerManager()

    result = normalizer.normalize(
        document,
        structure,
    )

    assert result == {
        "apiVersion": "apps/v1",
        "kind": "Deployment",
        "metadata": {
            "name": "app-1",
            "namespace": "entropy",
            "annotations": {
                "custom.annotation": "keep-me",
            },
        },
        "spec": {
            "replicas": 2,
            "template": {
                "metadata": {
                    "labels": {
                        "app": "app-1",
                    },
                },
            },
        },
    }
