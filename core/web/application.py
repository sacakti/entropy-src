"""FastAPI application and Entropy context lifecycle."""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI

from core.context import EntropyContext
from core.context_factory import ContextFactory
from core.web.routes.health import router as health_router


def _close_context(context: EntropyContext) -> None:
    """Close context-owned resources when their managers expose close()."""

    database_manager = context.database_manager
    close = getattr(database_manager, "close", None)

    if callable(close):
        close()


def create_app(context_factory: ContextFactory | None = None) -> FastAPI:
    """Create the web app without initializing Entropy until server startup."""

    factory = context_factory or ContextFactory(interactive=False)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        context = factory.build()
        factory.discover()
        app.state.entropy_context = context
        app.state.context_factory = factory

        try:
            yield
        finally:
            _close_context(context)
            app.state.entropy_context = None

    app = FastAPI(
        title="Entropy",
        description="Entropy deployment framework web API",
        version="1.0.2",
        lifespan=lifespan,
    )
    app.include_router(health_router)
    return app


app = create_app()
