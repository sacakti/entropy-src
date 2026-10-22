"""
EagleAPI: an HTTP API tester (method, URL, headers, body, auth, TLS,
polling) whose environment values live in the project's vault namespace.

- store: the project's collections (folders and saved requests)
- references: ${entv:...} resolution for the current user, and masking
- polling: poll-URL extraction and stop conditions
- client: building and sending the request (urllib, TLS, OAuth2)
"""

from __future__ import annotations

NAMESPACE_PREFIX = "eagleapi-"


def namespace_name(project_key: str) -> str:
    """The project's EagleAPI vault namespace (namespace names are global)."""

    return f"{NAMESPACE_PREFIX}{project_key}"
