"""
A small client of the Quay REST API (v1) with a bearer token: an OAuth
application token or a robot account token with repository admin rights.
"""

from __future__ import annotations

import json
import ssl
from typing import Any, Dict, List, Optional
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

from .exceptions import QuayApiError

PAGE_SIZE = 100
MAX_PAGES = 1000


def _segment(value: str) -> str:
    return quote(value, safe="")


class QuayClient:
    """
    Lists repositories and tags and deletes tags.
    """

    def __init__(
        self,
        url: str,
        token: str,
        *,
        verify_tls: bool = True,
        timeout: float = 60.0,
    ) -> None:

        self.url = url.rstrip("/")
        self._token = token
        self.timeout = timeout
        self._context: Optional[ssl.SSLContext] = None
        if self.url.startswith("https://") and not verify_tls:
            self._context = ssl._create_unverified_context()  # nosec B323 - asked for

    # ------------------------------------------------------------------
    # HTTP
    # ------------------------------------------------------------------

    def request(
        self,
        method: str,
        path: str,
        params: Optional[Dict[str, Any]] = None,
    ) -> Any:

        url = f"{self.url}/api/v1{path}"
        if params:
            url += "?" + urlencode(params)
        request = Request(
            url,
            method=method,
            headers={
                "Accept": "application/json",
                "Authorization": f"Bearer {self._token}",
            },
        )
        try:
            with urlopen(
                request, timeout=self.timeout, context=self._context
            ) as response:  # nosec B310
                payload = response.read()
        except HTTPError as error:
            raise QuayApiError(
                f"{method} {path} failed: HTTP {error.code} {self._detail(error)}",
                error.code,
            ) from None
        except URLError as error:
            raise QuayApiError(f"Cannot reach {self.url}: {error.reason}") from None
        except OSError as error:
            raise QuayApiError(f"Cannot reach {self.url}: {error}") from None

        if not payload:
            return None
        try:
            return json.loads(payload.decode("utf-8"))
        except ValueError:
            raise QuayApiError(f"{method} {path} did not answer with JSON.") from None

    @staticmethod
    def _detail(error: HTTPError) -> str:
        try:
            body = json.loads(error.read().decode("utf-8"))
        except Exception:  # noqa: BLE001 - fall back to the status text
            return str(error.reason)
        if isinstance(body, dict):
            return str(body.get("error_message") or body.get("detail") or error.reason)
        return str(error.reason)

    # ------------------------------------------------------------------
    # API
    # ------------------------------------------------------------------

    def repositories(
        self,
        namespace: str,
    ) -> List[str]:
        """
        Names of the namespace's repositories.
        """

        names: List[str] = []
        params: Dict[str, Any] = {"namespace": namespace}
        for _ in range(MAX_PAGES):
            page = self.request("GET", "/repository", params) or {}
            names.extend(str(item["name"]) for item in page.get("repositories") or [])
            token = page.get("next_page")
            if not token:
                return names
            params = {"namespace": namespace, "next_page": token}
        raise QuayApiError(f"Too many repositories in '{namespace}' (more than {MAX_PAGES} pages).")

    def tags(
        self,
        namespace: str,
        repository: str,
    ) -> List[Dict[str, Any]]:
        """
        The repository's active tags.
        """

        path = f"/repository/{_segment(namespace)}/{_segment(repository)}/tag/"
        tags: List[Dict[str, Any]] = []
        for page in range(1, MAX_PAGES + 1):
            result = (
                self.request(
                    "GET",
                    path,
                    {"onlyActiveTags": "true", "limit": PAGE_SIZE, "page": page},
                )
                or {}
            )
            tags.extend(result.get("tags") or [])
            if not result.get("has_additional"):
                return tags
        raise QuayApiError(f"Too many tags in '{namespace}/{repository}'.")

    def delete_tag(
        self,
        namespace: str,
        repository: str,
        tag: str,
    ) -> None:
        """
        Delete a tag; Quay garbage-collects images no tag points to.
        """

        self.request(
            "DELETE",
            f"/repository/{_segment(namespace)}/{_segment(repository)}/tag/{_segment(tag)}",
        )
