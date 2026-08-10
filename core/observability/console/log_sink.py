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

    # def publish(
    #     self,
    #     event: BaseEvent,
    # ) -> None:

    #     if not isinstance(event, LogEvent):
    #         return

    #     if event.level.value < self._level.value:
    #         return

    #     handler = getattr(
    #         self._renderer,
    #         event.level.name.lower(),
    #         None,
    #     )

    #     if handler is not None:
    #         handler(event.message)
    def publish(
        self,
        event: BaseEvent,
    ) -> None:

        # print(f"Sink received: {type(event).__name__}")

        if not isinstance(event, LogEvent):
            # print("Ignored (not LogEvent)")
            return

        # print(f"Level={event.level} Message={event.message}")

        if event.level.value < self._level.value:
            # print("Filtered by level")
            return

        handler = getattr(
            self._renderer,
            event.level.name.lower(),
            None,
        )

        # print(f"Handler={handler}")

        if handler is not None:
            handler(event.message)

    @property
    def level(self) -> LogLevel:
        return self._level

    @level.setter
    def level(
        self,
        value: LogLevel,
    ) -> None:
        self._level = value
