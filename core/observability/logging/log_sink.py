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

        self._manager = manager

    def publish(
        self,
        event: BaseEvent,
    ) -> None:

        if not isinstance(event, LogEvent):
            return

        logger = self._manager.logger(
            event.source,
        )

        if event.level == LogLevel.DEBUG:

            logger.debug(event.message)

        elif event.level == LogLevel.INFO:

            logger.info(event.message)

        elif event.level == LogLevel.WARNING:

            logger.warning(event.message)

        elif event.level == LogLevel.ERROR:

            logger.error(event.message)

        elif event.level == LogLevel.CRITICAL:

            logger.critical(event.message)
