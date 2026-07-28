"""
Category Logger

A lightweight proxy that binds a log category to the OutputManager.
"""

from typing import Any

class CategoryLogger:

    def __init__(self, manager: "OutputManager", category: str):
        self._manager = manager
        self._category = category

    def _log(self, level: str, message: str, **kwargs: Any) -> None:
        self._manager.emit(
            level=level,
            category=self._category,
            message=message,
            **kwargs,
        )

    def debug(self, message: str, **kwargs: Any) -> None:
        self._log("DEBUG", message, **kwargs)

    def info(self, message: str, **kwargs: Any) -> None:
        self._log("INFO", message, **kwargs)

    def success(self, message: str, **kwargs: Any) -> None:
        self._log("SUCCESS", message, **kwargs)

    def warning(self, message: str, **kwargs: Any) -> None:
        self._log("WARNING", message, **kwargs)

    def error(self, message: str, **kwargs: Any) -> None:
        self._log("ERROR", message, **kwargs)

    def exception(self, message: str, **kwargs: Any) -> None:
        self._log("EXCEPTION", message, exception=True, **kwargs)