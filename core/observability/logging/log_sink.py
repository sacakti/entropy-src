from core.observability.event import BaseEvent, LogEvent
from core.observability.logging.manager import LoggingManager
from core.observability.sink import Sink

from pathlib import Path

class LogFileSink(Sink):
    """
    Persists application log events.
    """

    def __init__(
        self,
        manager: LoggingManager,
        log_file: Path,
    ) -> None:

        self._logger = manager.logger(
            log_file,
        )

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
