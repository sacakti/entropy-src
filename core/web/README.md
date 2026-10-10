# Entropy Web Application

The web application is a separate entry point. It does not change the existing CLI entry point.

## Install runtime dependencies

Install the project's runtime requirements using the existing Entropy installation workflow. For local development, install the web dependencies in the active Python environment:

```bash
python -m pip install "fastapi>=0.115.0" "uvicorn>=0.34.0"
```

## Start the server

From the project root:

```bash
python -m core.web
```

The server listens on `127.0.0.1:8000` by default.

Override the bind address and port with environment variables:

```bash
ENTROPY_WEB_HOST=127.0.0.1 ENTROPY_WEB_PORT=8080 python -m core.web
```

The initial health endpoint is `GET /api/health`. It reports whether the Entropy context has been initialized. This foundation does not yet expose protected workflow operations or browser authentication; those will be added before workflow endpoints are made available.
