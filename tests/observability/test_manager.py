from unittest.mock import Mock

from core.observability.manager import ObservabilityManager


def test_emitter_cache():

    manager = ObservabilityManager()

    a = manager.emitter("workflow")

    b = manager.emitter("workflow")

    assert a is b


def test_register():

    manager = ObservabilityManager()

    sink = Mock()

    manager.register(sink)

    assert sink in manager._dispatcher._sinks
