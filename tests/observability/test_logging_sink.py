from unittest.mock import Mock

from core.observability.logging.logger import ExecutionLogger
from core.observability.logging.manager import LoggingManager
from core.observability.logging.sink import LoggingSink
from core.models.enums import EventType
from core.observability.event import Event


def test_logging(event):

    manager = Mock(spec=LoggingManager)

    logger = Mock(spec=ExecutionLogger)

    manager.logger.return_value = logger

    sink = LoggingSink(manager)

    sink.publish(event)

    logger.info.assert_called_once()



def test_logging_error(node):

    manager = Mock(spec=LoggingManager)

    logger = Mock(spec=ExecutionLogger)

    manager.logger.return_value = logger

    sink = LoggingSink(manager)

    event = Event(
        type=EventType.STAGE_FAILED,
        source="workflow",
        execution_id="1",
        node=node,
    )

    sink.publish(event)

    logger.error.assert_called_once()
