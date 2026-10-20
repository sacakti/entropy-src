"""Run the Entropy web application with Uvicorn."""

from __future__ import annotations

import os

from core.bootstrap import bootstrap

# Dependencies live in the Entropy home's site-packages.
bootstrap()

import uvicorn  # noqa: E402

from lib.system import install  # noqa: E402


def main() -> None:
    """Start the web server (host and port from the environment or install.json)."""

    web = install.load()["web"]
    host = os.environ.get("ENTROPY_WEB_HOST") or str(web["host"])
    port = int(os.environ.get("ENTROPY_WEB_PORT") or web["port"])

    uvicorn.run(
        "core.web.application:app",
        host=host,
        port=port,
        reload=False,
    )


if __name__ == "__main__":
    main()
