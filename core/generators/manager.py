"""
Generator manager.
"""

from __future__ import annotations

import importlib
import inspect
import pkgutil

from core.generators import __path__
from core.generators.base import BaseGenerator
from core.generators.exceptions import GeneratorNotFoundError


class GeneratorManager:

    IGNORED = frozenset(
        {
            "__init__",
            "base",
            "manager",
            "exceptions",
        }
    )

    def __init__(self, context):

        self.context = context

        self._generators: dict[str, BaseGenerator] = {}

        self._events = context.observability.emitter(
            "generator",
        )

    # ---------------------------------------------------------
    # Discovery
    # ---------------------------------------------------------

    def discover(self) -> None:

        self._events.log.debug("Discovering generators...")

        for _, module_name, _ in pkgutil.iter_modules(__path__):

            if module_name in self.IGNORED:
                continue

            module = importlib.import_module(
                f"core.generators.{module_name}",
            )

            for _, cls in inspect.getmembers(
                module,
                inspect.isclass,
            ):

                if not issubclass(cls, BaseGenerator) or cls is BaseGenerator:
                    continue

                self.register(cls(self.context))

        self._events.log.debug(f"{len(self.list())} generator(s) loaded.")

    # ---------------------------------------------------------
    # Register
    # ---------------------------------------------------------

    def register(
        self,
        generator: BaseGenerator,
    ) -> None:

        self._generators[generator.metadata.name] = generator

    # ---------------------------------------------------------
    # Access
    # ---------------------------------------------------------

    def get(
        self,
        name: str,
    ) -> BaseGenerator | None:

        return self._generators.get(name)

    def list(
        self,
    ) -> list[BaseGenerator]:

        return sorted(
            self._generators.values(),
            key=lambda g: g.metadata.name,
        )

    # ---------------------------------------------------------
    # Generate
    # ---------------------------------------------------------

    def generate(
        self,
        name: str,
        args,
    ) -> None:

        generator = self.get(
            name,
        )

        if generator is None:

            raise GeneratorNotFoundError(
                name,
            )

        self._events.log.debug(
            f"Generator: {generator.metadata} args: {args}"
        )

        self._events.log.debug(
            f"Generating with {generator.metadata.name}..."
        )

        generator.generate(
            args,
            context=self.context,
        )

        self._events.log.debug(
            f"Generation complete with {generator.metadata.name}."
        )
