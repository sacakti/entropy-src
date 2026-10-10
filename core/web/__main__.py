"""Run the Entropy web application with Uvicorn."""

from __future__ import annotations

import os

import uvicorn


def main() -> None:
    """Start the web server."""

    host = os.environ.get("ENTROPY_WEB_HOST", "127.0.0.1")
    port = int(os.environ.get("ENTROPY_WEB_PORT", "8000"))

    uvicorn.run(
        "core.web.application:app",
        host=host,
        port=port,
        reload=False,
    )


if __name__ == "__main__":
    main()
