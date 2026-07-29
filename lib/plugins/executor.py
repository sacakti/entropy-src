"""
Plugin executor.

Responsible for validating and executing plugins.
"""

from __future__ import annotations

from time import perf_counter

from core.context import EntropyContext

from .exception import (
    PluginError,
    PluginExecutionError,
)
from .loader import PluginLoader


class PluginExecutor:
    """
    Executes plugins.
    """

    def __init__(
        self,
        context: EntropyContext,
        loader: PluginLoader,
    ) -> None:

        self.context = context
        self.loader = loader

    def execute(
        self,
        name: str,
        config: dict,
    ) -> float:
        """
        Validate and execute a plugin.

        Returns
        -------
        float
            Execution duration in seconds.
        """

        plugin = self.loader.load(name)

        start = perf_counter()

        try:

            plugin.initialize()

            plugin.validate(config)

            plugin.execute(config)

        except PluginError:
            raise

        except NotImplementedError as exc:
            raise PluginExecutionError(f"Plugin '{name}' execution is not implemented.") from exc

        except Exception as exc:
            raise PluginExecutionError(f"Plugin '{name}' execution failed.") from exc

        finally:

            try:
                plugin.cleanup()

            except Exception as exc:
                self.context.output.plugin.exception(
                    f"Plugin '{name}' cleanup failed.",
                    exc_info=exc,
                )

            duration = perf_counter() - start

        self.context.output.plugin.success(f"Plugin '{name}' completed " f"({duration:.2f}s)")

        return duration
