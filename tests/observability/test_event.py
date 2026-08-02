from core.models.enums import EventType


def test_event_properties(event):

    assert event.type is EventType.STAGE_STARTED

    assert event.name == "Validation"

    assert event.execution_id == "exec-1"

    assert event.node is not None

    assert event.timestamp is not None

    assert event.id


def test_event_is_immutable(event):

    import pytest

    with pytest.raises(AttributeError):

        event.source = "shell"
