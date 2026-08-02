"""
Observability test fixtures.
"""

from pathlib import Path
from unittest.mock import Mock

import pytest

from lib.models.runtime import RuntimeNodeType
from core.runtime.node import RuntimeNode
from core.models.enums import EventType
from core.observability.event import Event


@pytest.fixture
def node():

    return RuntimeNode(
        id="node-1",
        name="Validation",
        type=RuntimeNodeType.STAGE,
    )


@pytest.fixture
def event(node):

    return Event(
        type=EventType.STAGE_STARTED,
        source="workflow",
        execution_id="exec-1",
        node=node,
    )
