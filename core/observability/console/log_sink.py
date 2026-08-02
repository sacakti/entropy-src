from core.models.logger import LogLevel
from core.observability.console.renderer import ConsoleRenderer
from core.observability.event import BaseEvent, LogEvent
from core.observability.sink import Sink


class LogConsoleSink(Sink):

    def __init__(
        self,
        renderer: ConsoleRenderer,
        level: LogLevel,
    ) -> None:

        self._renderer = renderer
        self._level = level

    def publish(
        self,
        event: BaseEvent,
    ) -> None:

        if not isinstance(event, LogEvent):
            return

        if event.level.value < self._level.value:
            return

        handler = getattr(
            self._renderer,
            event.level.name.lower(),
            None,
        )

        if handler is not None:
            handler(event.message)
