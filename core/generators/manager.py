"""
Generator manager.
"""

from __future__ import annotations

import importlib
import inspect
import pkgutil
from typing import TYPE_CHECKING

from core.generators import __path__
from core.generators.base import BaseGenerator
from core.generators.exceptions import GeneratorNotFoundError

if TYPE_CHECKING:
    from core.context import EntropyContext


class GeneratorManager:
    """
    Generator subsystem.

    Responsible for generator discovery,
    registration and execution.
    """

    IGNORED = frozenset(
        {
            "__init__",
            "base",
            "manager",
            "exceptions",
        }
    )

    def __init__(
        self,
        context: EntropyContext,
    ) -> None:

        self._context = context

        self._generators: dict[str, BaseGenerator] = {}

    # ------------------------------------------------------------------
    # Discovery
    # ------------------------------------------------------------------

    def discover(
        self,
    ) -> None:
        """
        Discover available generators.
        """

        for _, module_name, _ in pkgutil.iter_modules(
            __path__,
        ):

            if module_name in self.IGNORED:
                continue

            self._discover(
                module_name,
            )

    def _discover(
        self,
        module_name: str,
    ) -> None:
        """
        Discover generators from a module.
        """

        module = importlib.import_module(
            f"core.generators.{module_name}",
        )

        for _, cls in inspect.getmembers(
            module,
            inspect.isclass,
        ):

            if (
                not issubclass(
                    cls,
                    BaseGenerator,
                )
                or cls is BaseGenerator
            ):
                continue

            self.register(
                cls(
                    self._context,
                )
            )

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def register(
        self,
        generator: BaseGenerator,
    ) -> None:
        """
        Register a generator.
        """

        self._generators[
            generator.metadata.name
        ] = generator

    # ------------------------------------------------------------------
    # Lookup
    # ------------------------------------------------------------------

    def get(
        self,
        name: str,
    ) -> BaseGenerator | None:
        """
        Return a generator by name.
        """

        return self._generators.get(
            name,
        )

    def list(
        self,
    ) -> list[BaseGenerator]:
        """
        Return registered generators.
        """

        return sorted(
            self._generators.values(),
            key=lambda generator: generator.metadata.name,
        )

    # ------------------------------------------------------------------
    # Execute
    # ------------------------------------------------------------------

    def generate(
        self,
        name: str,
        args,
    ) -> None:
        """
        Execute a generator.
        """

        generator = self.get(
            name,
        )

        if generator is None:

            raise GeneratorNotFoundError(
                name,
            )

        generator.generate(
            args=args,
            context=self._context,
        )
