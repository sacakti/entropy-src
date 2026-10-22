"""
Vault references in EagleAPI fields, resolved for the current user.

Any field may hold `${entv:namespace/key}` (the value) or
`${entvfile:namespace/key}` (a file; in text fields its text), and
`{{ENV}}`, replaced by the selected environment's name first, so that
`${entv:eagleapi-default/{{ENV}}_CLIENT_ID}` follows the environment.

Who may read which namespace is decided by the `fetch` callable the web
layer passes in. Values of sensitive entries are remembered so that what
is shown back to the browser (the request that was sent) can be masked.
"""

from __future__ import annotations

import base64
import json
import re
from dataclasses import dataclass
from typing import Any, Callable, Dict, Iterable, List, Optional, Set, Tuple
from urllib.parse import quote, quote_plus

REFERENCE = re.compile(r"\$\{(entv|entvfile):([^}/\s]+)/([^}\s]+)\}")
ENV_PLACEHOLDER = "{{ENV}}"
ENVIRONMENT_NAME = re.compile(r"^[A-Z0-9_]{1,60}$")
URL_KEY = re.compile(r"^([A-Z0-9_]+)_URL$")
MASK = "••••"
# Shorter secrets are masked only where a whole value equals them.
MIN_MASKED_SUBSTRING = 4
SECRET_HEADERS = {"authorization", "proxy-authorization"}


class EagleReferenceError(ValueError):
    """A reference that cannot be used; the message never holds a secret."""


@dataclass
class VaultValue:
    value: Any
    type: str
    sensitive: bool


Fetch = Callable[[str, str], VaultValue]


def environments(keys: Iterable[str]) -> List[str]:
    """Environment names: the keys `<NAME>_URL`."""

    return sorted({match.group(1) for match in map(URL_KEY.match, keys) if match})


def _file_bytes(value: Any) -> Optional[bytes]:
    if isinstance(value, dict) and "data" in value and "filename" in value:
        try:
            return base64.b64decode(str(value["data"]))
        except ValueError:
            return None
    return None


def _as_text(item: VaultValue) -> str:
    raw = _file_bytes(item.value) if item.type == "file" else None
    if raw is not None:
        try:
            return raw.decode("utf-8")
        except UnicodeDecodeError:
            return str(item.value["data"])
    if isinstance(item.value, str):
        return item.value
    if isinstance(item.value, bool):
        return "true" if item.value else "false"
    if isinstance(item.value, (int, float)):
        return str(item.value)
    return json.dumps(item.value, ensure_ascii=False)


class Resolver:
    """Resolves the fields of one send, remembering the secrets it used."""

    def __init__(self, fetch: Fetch, environment: Optional[str] = None) -> None:
        self._fetch = fetch
        self.environment = (environment or "").strip() or None
        if self.environment and not ENVIRONMENT_NAME.match(self.environment):
            raise EagleReferenceError(f"'{self.environment}' is not a valid environment name.")
        self.secrets: Set[str] = set()
        self._cache: Dict[Tuple[str, str], VaultValue] = {}

    # -- lookups -------------------------------------------------------

    def lookup(self, namespace: str, key: str) -> VaultValue:
        cache_key = (namespace, key)
        if cache_key not in self._cache:
            self._cache[cache_key] = self._fetch(namespace, key)
        return self._cache[cache_key]

    def _environment(self, text: str) -> str:
        if ENV_PLACEHOLDER not in text:
            return text
        if not self.environment:
            raise EagleReferenceError("A field uses {{ENV}}, but no environment is selected.")
        return text.replace(ENV_PLACEHOLDER, self.environment)

    def _remember(self, item: VaultValue, text: str) -> None:
        if item.sensitive and text:
            self.secrets.add(text)

    # -- resolution ----------------------------------------------------

    def text(self, value: Any) -> str:
        """A text field with {{ENV}} and every reference replaced."""

        text = self._environment("" if value is None else str(value))

        def replace(match: re.Match[str]) -> str:
            item = self.lookup(match.group(2), match.group(3))
            resolved = _as_text(item)
            self._remember(item, resolved)
            return resolved

        return REFERENCE.sub(replace, text)

    def file(self, value: Any) -> Optional[bytes]:
        """
        A file field (certificate, key, keystore, CA bundle): one reference
        to a vault file (or to a text value holding PEM). Empty means none.
        """

        text = self._environment("" if value is None else str(value)).strip()
        if not text:
            return None
        match = REFERENCE.fullmatch(text)
        if not match:
            raise EagleReferenceError(
                "Certificate fields take a vault file reference such as "
                "${entvfile:namespace/KEY}."
            )
        item = self.lookup(match.group(2), match.group(3))
        raw = _file_bytes(item.value) if item.type == "file" else None
        if raw is None:
            raw = _as_text(item).encode("utf-8")
        return raw

    # -- masking -------------------------------------------------------

    def _variants(self) -> List[str]:
        found: Set[str] = set()
        for secret in self.secrets:
            if len(secret) < MIN_MASKED_SUBSTRING:
                continue
            found.update({secret, quote(secret, safe=""), quote_plus(secret)})
        return sorted(found, key=len, reverse=True)

    def mask(self, text: Any) -> str:
        """Text shown to the browser, with the secrets it used replaced."""

        text = "" if text is None else str(text)
        if text in self.secrets:
            return MASK
        for secret in self._variants():
            text = text.replace(secret, MASK)
        return text

    def mask_header(self, name: str, value: str) -> str:
        if name.strip().lower() in SECRET_HEADERS:
            scheme, _, credentials = value.partition(" ")
            return f"{scheme} {MASK}" if credentials else MASK
        return self.mask(value)
