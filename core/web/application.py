
"""FastAPI application and Entropy context lifecycle."""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI
from fastapi.openapi.docs import get_swagger_ui_html
from fastapi.responses import HTMLResponse

from core.context import EntropyContext
from core.context_factory import ContextFactory
from core.web.routes.auth import router as auth_router
from core.web.routes.health import router as health_router
from core.web.routes.workflow import router as workflow_router
from core.web.session_store import WebSessionStore


def _close_context(context: EntropyContext) -> None:
    """Close context-owned resources when their managers expose close()."""

    database_manager = getattr(context, "database_manager", None)
    close = getattr(database_manager, "close", None)

    if callable(close):
        close()


def create_app(context_factory: ContextFactory | None = None) -> FastAPI:
    """Create the web app without initializing Entropy until server startup."""

    factory = context_factory or ContextFactory(interactive=False)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        context = factory.build()
        app.state.entropy_context = context
        app.state.context_factory = factory
        app.state.web_session_store = WebSessionStore(context)

        try:
            factory.discover()
            yield
        finally:
            _close_context(context)
            app.state.entropy_context = None
            app.state.web_session_store = None

    app = FastAPI(
        title="Entropy",
        description="Entropy deployment framework web API",
        version="1.0.2",
        docs_url=None,
        lifespan=lifespan,
    )

    secure_setting = os.environ.get(
        "ENTROPY_WEB_COOKIE_SECURE",
        "false",
    ).strip().lower()

    if secure_setting not in ("true", "false"):
        raise ValueError(
            "ENTROPY_WEB_COOKIE_SECURE must be 'true' or 'false'."
        )

    app.state.web_cookie_secure = secure_setting == "true"

    app.include_router(health_router)
    app.include_router(auth_router)
    app.include_router(workflow_router)

    @app.get("/docs", include_in_schema=False)
    async def custom_swagger_ui() -> HTMLResponse:
        """Serve Swagger UI with automatic CSRF headers for API mutations."""

        response = get_swagger_ui_html(
            openapi_url=app.openapi_url or "/openapi.json",
            title="Entropy - Swagger UI",
        )

        html = response.body.decode("utf-8")

        interceptor = r"""
        const ui = SwaggerUIBundle({
            requestInterceptor: async (req) => {
                const method = String(req.method || "GET").toUpperCase();
                const url = new URL(req.url, window.location.origin);
                const mutatingMethods = ["POST", "PUT", "PATCH", "DELETE"];

                if (
                    mutatingMethods.includes(method) &&
                    url.origin === window.location.origin &&
                    url.pathname.startsWith("/api/")
                ) {
                    const csrfResponse = await fetch("/api/auth/csrf", {
                        method: "GET",
                        credentials: "same-origin",
                        cache: "no-store"
                    });

                    if (!csrfResponse.ok) {
                        throw new Error("Unable to obtain CSRF token.");
                    }

                    const csrfData = await csrfResponse.json();

                    if (!csrfData.csrf_token) {
                        throw new Error("CSRF token is missing from the response.");
                    }

                    req.headers = req.headers || {};
                    req.headers["X-CSRF-Token"] = csrfData.csrf_token;
                    req.credentials = "same-origin";
                }

                return req;
            },
        """

        marker = "const ui = SwaggerUIBundle({"

        if marker not in html:
            raise RuntimeError(
                "Unable to install the Swagger UI CSRF interceptor."
            )

        # Replace the original initializer with the interceptor-enabled one.
        html = html.replace(marker, interceptor, 1)

        return HTMLResponse(
            content=html,
            headers={"Cache-Control": "no-store"},
        )

    return app


app = create_app()
