from unittest.mock import Mock

from core.observability.dispatcher import EventDispatcher
from core.observability.emitter import Emitter
from core.models.enums import EventType


def test_emit(node):

    dispatcher = Mock(spec=EventDispatcher)

    emitter = Emitter(
        dispatcher,
        "workflow",
    )

    emitter.emit(
        EventType.STAGE_STARTED,
        "exec-1",
        node,
    )

    dispatcher.dispatch.assert_called_once()
