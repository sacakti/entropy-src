
"""FastAPI application and Entropy context lifecycle."""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from typing import AsyncIterator
import pkgutil
import importlib

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.openapi.docs import get_swagger_ui_html
from fastapi.responses import FileResponse, HTMLResponse

from core.context import EntropyContext
from core.context_factory import ContextFactory
from core.bootstrap import bootstrap
from core.version import VERSION
from core.web import routes
from core.web.session_store import WebSessionStore

def _close_context(context: EntropyContext) -> None:
    """Close context-owned resources when their managers expose close()."""

    database_manager = getattr(context, "database_manager", None)
    close = getattr(database_manager, "close", None)

    if callable(close):
        close()

def _start_background(context: EntropyContext):
    """Start schedules, node metrics and housekeeping for a real context."""

    if os.environ.get("ENTROPY_WEB_BACKGROUND", "true").strip().lower() == "false":
        return None

    if getattr(context, "database_manager", None) is None or getattr(context, "bootstrap", None) is None:
        return None

    from lib.runs.background import RunsBackground

    background = RunsBackground(context)
    return background if background.start() else None

def frontend_directory() -> Path | None:
    """The built web UI (`frontend/dist`), when this install ships one."""

    configured = os.environ.get("ENTROPY_WEB_DIST")
    directory = (
        Path(configured)
        if configured
        else Path(__file__).resolve().parents[2] / "frontend" / "dist"
    )
    return directory if (directory / "index.html").is_file() else None


def mount_frontend(app: FastAPI, directory: Path) -> None:
    """Serve the single-page web UI; unknown paths fall back to index.html."""

    root = directory.resolve()

    @app.api_route("/{path:path}", methods=["GET", "HEAD"], include_in_schema=False)
    async def web_ui(path: str) -> FileResponse:
        if path == "api" or path.startswith("api/"):
            raise HTTPException(status_code=404, detail="Not Found")

        candidate = (root / path).resolve()
        if path and candidate.is_file() and root in candidate.parents:
            # Built assets carry content hashes in their names.
            immutable = candidate.parent.name == "assets"
            return FileResponse(
                candidate,
                headers={
                    "Cache-Control": (
                        "public, max-age=31536000, immutable" if immutable else "no-cache"
                    )
                },
            )

        return FileResponse(root / "index.html", headers={"Cache-Control": "no-cache"})

def register_routes(app: FastAPI) -> None:
    """Register routers discovered in the routes package."""

    module_names = sorted(
        module_name
        for _, module_name, _ in pkgutil.iter_modules(routes.__path__)
    )

    for module_name in module_names:
        module = importlib.import_module(
            f"{routes.__package__}.{module_name}",
        )

        router = getattr(
            module,
            "router",
            None,
        )

        if router is not None:
            app.include_router(
                router,
            )

def create_app(context_factory: ContextFactory | None = None) -> FastAPI:
    """Create the web app without initializing Entropy until server startup."""

    factory = context_factory or ContextFactory(interactive=False)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        context = factory.build()
        app.state.entropy_context = context
        app.state.context_factory = factory
        app.state.web_session_store = WebSessionStore(context)

        background = None

        try:
            factory.discover()
            background = _start_background(context)
            app.state.runs_background = background
            yield
        finally:
            if background is not None:
                background.stop()
            _close_context(context)
            app.state.entropy_context = None
            app.state.web_session_store = None

    app = FastAPI(
        title="Entropy",
        description="Entropy deployment framework web API",
        version=VERSION,
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

    register_routes(
        app,
    )

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

    # Last: the UI's catch-all route must not shadow the API or /docs.
    dist = frontend_directory()
    if dist is not None:
        mount_frontend(app, dist)

    return app

bootstrap()

app = create_app()
