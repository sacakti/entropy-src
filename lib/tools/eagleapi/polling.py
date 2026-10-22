"""
Polling: where the poll URL comes from, and when to stop.

The browser drives the polling (it calls the send endpoint once per
attempt); these helpers read a response and say what to do next.
"""

from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional, Sequence, Tuple

_TOKEN = re.compile(r"""\[\s*(-?\d+)\s*\]|\[\s*['"]([^'"]*)['"]\s*\]|([^.\[\]]+)""")
_MISSING = object()


class PollError(ValueError):
    """The poll URL or the stop value could not be read from a response."""


def json_path(document: Any, expression: str) -> Any:
    """
    A value by a dot path: `data.links.status`, `$.data.links.status`,
    `items[0].href`, `['odd key'].value`. Raises PollError when absent.
    """

    path = (expression or "").strip()
    if path.startswith("$"):
        path = path[1:]
    path = path.lstrip(".")
    current = document
    for match in _TOKEN.finditer(path):
        index, quoted, name = match.groups()
        if index is not None:
            if not isinstance(current, list):
                raise PollError(f"'{expression}': [{index}] needs a list.")
            position = int(index)
            if not -len(current) <= position < len(current):
                raise PollError(f"'{expression}': index {position} is out of range.")
            current = current[position]
            continue
        key = quoted if quoted is not None else name.strip()
        if isinstance(current, dict) and key in current:
            current = current[key]
        elif isinstance(current, list) and key.lstrip("-").isdigit():
            try:
                current = current[int(key)]
            except IndexError:
                raise PollError(f"'{expression}': index {key} is out of range.") from None
        else:
            raise PollError(f"'{expression}' was not found in the response.")
    return current


def _parse_json(body: str) -> Any:
    try:
        return json.loads(body)
    except ValueError:
        raise PollError("The response body is not JSON.") from None


def _header(headers: Sequence[Tuple[str, str]], name: str) -> Optional[str]:
    wanted = name.strip().lower()
    for key, value in headers:
        if key.lower() == wanted:
            return value
    return None


def extract_poll_url(spec: Dict[str, Any], headers: Sequence[Tuple[str, str]], body: str) -> str:
    """The poll URL found in a response by a JSON path, a header or a regex."""

    source = spec.get("source") or "json"
    expression = str(spec.get("expression") or "").strip()
    if not expression:
        raise PollError("Polling needs an expression to find the poll URL.")

    if source == "header":
        value = _header(headers, expression)
        if value is None:
            raise PollError(f"The response has no '{expression}' header.")
    elif source == "regex":
        try:
            pattern = re.compile(expression)
        except re.error as exc:
            raise PollError(f"Invalid regular expression: {exc}.") from None
        match = pattern.search(body or "")
        if match is None:
            raise PollError("The regular expression found nothing in the response.")
        value = match.group(1) if pattern.groups else match.group(0)
    else:
        value = json_path(_parse_json(body), expression)
        if not isinstance(value, (str, int, float)) or isinstance(value, bool):
            raise PollError(f"'{expression}' is not a URL.")

    url = str(value).strip()
    if not url:
        raise PollError("The poll URL found in the response is empty.")
    return url


def _values(text: str) -> List[str]:
    return [value.strip() for value in str(text or "").split(",") if value.strip()]


def stop_state(spec: Dict[str, Any], status: Optional[int], body: str) -> Dict[str, Any]:
    """
    Whether polling is over after this response:
    {"done": bool, "reason": str, "value": the JSON value checked (if any)}.
    """

    stop = spec.get("stop") or {}
    kind = stop.get("type") or "json"
    on_error = stop.get("on_error", True) is not False

    if status is None:
        return {"done": True, "reason": "The poll request failed.", "value": None}
    if on_error and status >= 400:
        return {"done": True, "reason": f"HTTP {status} (an error status).", "value": None}

    if kind == "status":
        expected = int(stop.get("status") or 202)
        if status != expected:
            return {"done": True, "reason": f"HTTP {status} (not {expected}).", "value": None}
        return {"done": False, "reason": f"HTTP {status}.", "value": None}

    if kind == "json":
        path = str(stop.get("path") or "").strip()
        wanted = _values(stop.get("values") or "")
        if not path or not wanted:
            return {"done": False, "reason": "No stop condition is set.", "value": None}
        try:
            value = json_path(_parse_json(body), path)
        except PollError as exc:
            return {"done": False, "reason": str(exc), "value": None}
        shown = value if isinstance(value, str) else json.dumps(value)
        if any(shown.lower() == candidate.lower() for candidate in wanted):
            return {"done": True, "reason": f"{path} is {shown}.", "value": value}
        return {"done": False, "reason": f"{path} is {shown}.", "value": value}

    return {"done": False, "reason": f"HTTP {status}.", "value": None}
