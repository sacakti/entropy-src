"""
`ent` for remote Entropy servers: a command line client of the REST API.

Uses only the Python standard library (3.9+), so it runs anywhere Python
does and ships as a single file (`ent.pyz`, served at /api/cli/ent.pyz).
It never touches a local Entropy database.
"""

from __future__ import annotations


def client_version() -> str:
    """The version stamped into ent.pyz, else this checkout's version."""

    try:
        from ._version import VERSION  # type: ignore[import-not-found]

        return VERSION
    except ImportError:
        pass
    try:
        from core.version import VERSION as APP_VERSION

        return APP_VERSION
    except Exception:  # noqa: BLE001 - outside a checkout
        return "dev"
