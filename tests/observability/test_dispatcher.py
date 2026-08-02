from unittest.mock import Mock

from core.observability.dispatcher import EventDispatcher


def test_dispatch():

    dispatcher = EventDispatcher()

    sink = Mock()

    dispatcher.register(sink)

    dispatcher.dispatch(Mock())

    sink.publish.assert_called_once()

def test_unregister():

    dispatcher = EventDispatcher()

    sink = Mock()

    dispatcher.register(sink)

    dispatcher.unregister(sink)

    dispatcher.dispatch(Mock())

    sink.publish.assert_not_called()
