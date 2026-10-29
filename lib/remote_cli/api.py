"""HTTP calls to an Entropy server with a bearer token."""

from __future__ import annotations

import json
import ssl
from typing import Any, Dict, Optional
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

from . import client_version
from .contract import PROJECT_HEADER


class ApiError(Exception):
    """A request failed; `status` is the HTTP status (0 when unreachable)."""

    def __init__(self, message: str, status: int = 0) -> None:
        super().__init__(message)
        self.status = status


def path(*parts: Any) -> str:
    """Join URL path segments, quoting each."""

    return "/" + "/".join(quote(str(part), safe="") for part in parts)


class Client:
    def __init__(
        self,
        server: str,
        token: Optional[str] = None,
        *,
        verify_tls: bool = True,
        ca_file: Optional[str] = None,
        timeout: float = 60.0,
        project: Optional[str] = None,
    ) -> None:
        self.server = server.rstrip("/")
        self.token = token
        # Sent with every request: the server works in this project.
        self.project = project
        self.timeout = timeout
        if self.server.startswith("https://"):
            if not verify_tls:
                self.context: Optional[ssl.SSLContext] = ssl._create_unverified_context()
            else:
                self.context = ssl.create_default_context(cafile=ca_file or None)
        else:
            self.context = None

    @classmethod
    def for_context(cls, context: Dict[str, Any], project: Optional[str] = None) -> Client:
        return cls(
            context["server"],
            context.get("token"),
            verify_tls=context.get("verify_tls", True),
            ca_file=context.get("ca_file"),
            project=project or context.get("project"),
        )

    def request(
        self,
        method: str,
        url_path: str,
        body: Any = None,
        params: Optional[Dict[str, Any]] = None,
        raw: bool = False,
    ) -> Any:
        url = self.server + "/api" + url_path
        if params:
            clean = {key: value for key, value in params.items() if value not in (None, "")}
            if clean:
                url += "?" + urlencode(clean, doseq=True)

        headers = {"Accept": "application/json", "User-Agent": f"ent/{client_version()}"}
        data = None
        if body is not None:
            data = json.dumps(body).encode("utf-8")
            headers["Content-Type"] = "application/json"
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        if self.project:
            headers[PROJECT_HEADER] = self.project

        request = Request(url, data=data, headers=headers, method=method)
        try:
            with urlopen(request, timeout=self.timeout, context=self.context) as response:
                payload = response.read()
        except HTTPError as error:
            raise ApiError(self._detail(error), error.code) from None
        except URLError as error:
            reason = error.reason
            if isinstance(reason, ssl.SSLError):
                raise ApiError(
                    f"TLS error talking to {self.server}: {reason}. Use --certificate-authority "
                    "FILE for a private CA, or --insecure-skip-tls-verify."
                ) from None
            raise ApiError(f"Cannot reach {self.server}: {reason}") from None
        except OSError as error:
            raise ApiError(f"Cannot reach {self.server}: {error}") from None

        if raw:
            return payload
        if not payload:
            return None
        try:
            return json.loads(payload.decode("utf-8"))
        except ValueError:
            raise ApiError(f"{url} did not answer with JSON; is this an Entropy server?") from None

    @staticmethod
    def _detail(error: HTTPError) -> str:
        try:
            payload = json.loads(error.read().decode("utf-8"))
            detail = payload.get("detail") if isinstance(payload, dict) else None
        except Exception:  # noqa: BLE001 - fall back to the status text
            detail = None
        if isinstance(detail, dict):
            detail = detail.get("message") or json.dumps(detail)
        if isinstance(detail, list):
            detail = "; ".join(
                str(item.get("msg", item)) if isinstance(item, dict) else str(item)
                for item in detail
            )
        if error.code == 401 and (not detail or detail == "Authentication required."):
            detail = "Not logged in, or the session expired. Run: ent login"
        return str(detail or f"HTTP {error.code} {error.reason}")

    def get(self, url_path: str, **params: Any) -> Any:
        return self.request("GET", url_path, params=params)

    def post(self, url_path: str, body: Any = None, **params: Any) -> Any:
        return self.request("POST", url_path, body if body is not None else {}, params=params)

    def put(self, url_path: str, body: Any) -> Any:
        return self.request("PUT", url_path, body)

    def delete(self, url_path: str) -> Any:
        return self.request("DELETE", url_path)
