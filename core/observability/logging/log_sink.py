from core.models.logger import LogLevel
from core.observability.event import BaseEvent, LogEvent
from core.observability.logging.manager import LoggingManager
from core.observability.sink import Sink


class LogFileSink(Sink):
    """
    Persists application log events.
    """

    def __init__(
        self,
        manager: LoggingManager,
    ) -> None:

        self._logger = manager.logger()

    def publish(
        self,
        event: BaseEvent,
    ) -> None:

        if not isinstance(event, LogEvent):
            return

        self._logger.log(
            level=event.level,
            module=event.source,
            message=event.message,
        )
