"""
HTTPS client the node agent uses to talk to the main node (stdlib only).
"""

from __future__ import annotations

import json
import ssl
import urllib.error
import urllib.request
from typing import Any, Dict, Optional


class AgentRevokedError(Exception):
    """The main node no longer accepts this agent's token."""


class AgentTransientError(Exception):
    """The main node could not be reached or failed; retry later."""


class AgentClient:
    """Authenticated JSON requests to the main node's agent API."""

    def __init__(
        self,
        server_url: str,
        token: str,
        *,
        verify_tls: bool = True,
        ca_file: Optional[str] = None,
        version: str = "",
    ) -> None:
        self._base = server_url.rstrip("/")
        self._token = token
        self._version = version

        if self._base.startswith("https://"):
            context = ssl.create_default_context(cafile=ca_file or None)
            if not verify_tls:
                context.check_hostname = False
                context.verify_mode = ssl.CERT_NONE
            self._context: Optional[ssl.SSLContext] = context
        else:
            self._context = None

    def _open(self, method: str, path: str, body: Optional[bytes], timeout: float):
        request = urllib.request.Request(
            f"{self._base}{path}",
            data=body,
            method=method,
            headers={
                "Authorization": f"Bearer {self._token}",
                "Content-Type": "application/json",
                "User-Agent": f"entropy-agent/{self._version}",
            },
        )
        try:
            return urllib.request.urlopen(request, timeout=timeout, context=self._context)
        except urllib.error.HTTPError as exc:
            if exc.code in (401, 403):
                raise AgentRevokedError(f"The main node rejected this agent ({exc.code}).") from exc
            detail = exc.read().decode("utf-8", "replace")[:300]
            raise AgentTransientError(f"{method} {path} failed with {exc.code}: {detail}") from exc
        except (urllib.error.URLError, OSError) as exc:
            raise AgentTransientError(f"{method} {path} failed: {exc}") from exc

    def request(
        self,
        method: str,
        path: str,
        payload: Optional[Dict[str, Any]] = None,
        *,
        timeout: float = 30,
    ) -> Dict[str, Any]:
        body = json.dumps(payload).encode("utf-8") if payload is not None else None
        with self._open(method, path, body, timeout) as response:
            text = response.read().decode("utf-8")
        return json.loads(text) if text else {}

    def download(self, path: str, *, timeout: float = 120) -> bytes:
        with self._open("GET", path, None, timeout) as response:
            return response.read()
