from unittest.mock import Mock

from core.observability.console.sink import ConsoleSink
from core.observability.console.renderer import ConsoleRenderer

from core.models.enums import EventType

def test_stage_started(event):

    renderer = Mock(spec=ConsoleRenderer)

    sink = ConsoleSink(renderer)

    sink.publish(event)

    renderer.heading.assert_called_once()



def test_activity_started(node):

    renderer = Mock(spec=ConsoleRenderer)

    sink = ConsoleSink(renderer)

    from core.observability.event import Event

    event = Event(
        type=EventType.ACTIVITY_STARTED,
        source="workflow",
        execution_id="1",
        node=node,
    )

    sink.publish(event)

    renderer.spinner.assert_called_once()
