"""
Sending an EagleAPI request with the standard library (urllib).

`prepare` turns a stored request definition into the concrete request
(references resolved, environment base URL applied, auth added) and
`send` sends it with the request's TLS settings. What is returned to the
browser masks every secret the resolver used.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import shutil
import socket
import ssl
import tempfile
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlencode, urljoin, urlsplit, urlunsplit

from .polling import PollError, extract_poll_url, stop_state
from .references import EagleReferenceError, Resolver
from .store import normalize_request

MAX_BODY_BYTES = 10 * 1024 * 1024
MAX_TIMEOUT = 300.0
_ABSOLUTE = re.compile(r"^[a-z][a-z0-9+.-]*://", re.IGNORECASE)
_METHOD = re.compile(r"^[A-Z]{1,20}$")
_TEXT_TYPES = ("json", "xml", "text/", "javascript", "html", "x-www-form-urlencoded", "yaml")


class EagleRequestError(ValueError):
    """The request cannot be sent as defined; the message is safe to show."""


@dataclass
class Tls:
    verify: bool = True
    ca: Optional[bytes] = None
    cert: Optional[bytes] = None
    key: Optional[bytes] = None
    pfx: Optional[bytes] = None
    password: Optional[str] = None


@dataclass
class Prepared:
    method: str
    url: str
    headers: List[Tuple[str, str]] = field(default_factory=list)
    body: Optional[bytes] = None
    tls: Tls = field(default_factory=Tls)
    timeout: float = 30.0
    follow_redirects: bool = True


# ----------------------------------------------------------------------
# TLS
# ----------------------------------------------------------------------


def _private_file(folder: str, name: str, content: bytes) -> str:
    path = os.path.join(folder, name)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(content)
    return path


def _pfx_to_pem(data: bytes, password: Optional[str]) -> Tuple[bytes, bytes]:
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.serialization import pkcs12

    try:
        key, certificate, extra = pkcs12.load_key_and_certificates(
            data, password.encode("utf-8") if password else None
        )
    except (ValueError, TypeError) as exc:
        raise EagleRequestError(
            "The PFX/P12 keystore could not be opened (wrong password or not a keystore)."
        ) from exc
    if key is None or certificate is None:
        raise EagleRequestError("The PFX/P12 keystore holds no private key and certificate.")
    chain = certificate.public_bytes(serialization.Encoding.PEM) + b"".join(
        item.public_bytes(serialization.Encoding.PEM) for item in extra or []
    )
    key_pem = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )
    return chain, key_pem


def ssl_context(tls: Tls, folder: str) -> ssl.SSLContext:
    """The client TLS context; key material is written to `folder` (0600)."""

    context = ssl.create_default_context()
    if not tls.verify:
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
    if tls.ca:
        try:
            context.load_verify_locations(cadata=tls.ca.decode("utf-8"))
        except (UnicodeDecodeError, ssl.SSLError) as exc:
            raise EagleRequestError("The CA bundle is not a PEM certificate file.") from exc

    cert, key, password = tls.cert, tls.key, tls.password
    if tls.cert or tls.pfx:
        # TLS 1.3 servers may ask for the client certificate after the
        # handshake (per path); without this the request is refused.
        context.post_handshake_auth = True
    if tls.pfx:
        cert, key = _pfx_to_pem(tls.pfx, tls.password)
        password = None
    if cert:
        certfile = _private_file(folder, "client.crt", cert)
        keyfile = _private_file(folder, "client.key", key) if key else None
        try:
            context.load_cert_chain(certfile, keyfile, password=password or None)
        except ssl.SSLError as exc:
            raise EagleRequestError(
                "The client certificate and key could not be loaded "
                "(not PEM, they do not match, or the key password is wrong)."
            ) from exc
    elif key:
        raise EagleRequestError("A client key needs its certificate.")
    return context


# ----------------------------------------------------------------------
# Sending
# ----------------------------------------------------------------------


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: D102
        return None


def _is_text(content_type: str, raw: bytes) -> bool:
    lowered = content_type.lower()
    if any(marker in lowered for marker in _TEXT_TYPES):
        return True
    if not raw:
        return True
    try:
        raw.decode("utf-8")
    except UnicodeDecodeError:
        return False
    return b"\x00" not in raw[:1024]


def _read(response: Any, limit: int) -> Tuple[bytes, bool]:
    raw = response.read(limit + 1)
    return raw[:limit], len(raw) > limit


# Handshake failures a second connection usually gets past: servers and load
# balancers that drop a client's first TLS handshake (client certificate
# negotiation, renegotiation, a back end not ready). Certificate errors are
# not among them: they would fail the same way again.
_TRANSIENT_TLS = ("UNEXPECTED_EOF", "EOF OCCURRED", "CONNECTION RESET", "TLSV1_ALERT_INTERNAL_ERROR",
                  "SSLV3_ALERT_HANDSHAKE_FAILURE", "DECRYPTION_FAILED", "BAD_RECORD_MAC")


def _transient_tls(result: Dict[str, Any]) -> bool:
    error = str(result.get("error") or "").upper()
    if not error.startswith(("TLS ERROR", "CONNECTION FAILED")):
        return False
    return any(marker in error for marker in _TRANSIENT_TLS)


def send(prepared: Prepared, max_body: int = MAX_BODY_BYTES) -> Dict[str, Any]:
    """
    Send the request. Network failures come back as {"error": ...}; any
    HTTP status (also 4xx/5xx) is a response.

    An HTTPS request whose TLS handshake is dropped is sent once more on a
    new connection: the handshake comes before any of the request is sent,
    so this is safe for every method. The result says so (tls_retry).
    """

    result = _send_once(prepared, max_body)
    if urlsplit(prepared.url).scheme.lower() == "https" and _transient_tls(result):
        first = result["error"]
        result = _send_once(prepared, max_body)
        result["tls_retry"] = f"The first TLS handshake failed ({first}); the request was sent again."
    return result


def _send_once(prepared: Prepared, max_body: int) -> Dict[str, Any]:

    folder = tempfile.mkdtemp(prefix="entropy-eagleapi-")
    os.chmod(folder, 0o700)
    started = time.monotonic()
    try:
        handlers: List[Any] = []
        if urlsplit(prepared.url).scheme.lower() == "https":
            handlers.append(urllib.request.HTTPSHandler(context=ssl_context(prepared.tls, folder)))
        if not prepared.follow_redirects:
            handlers.append(_NoRedirect())
        opener = urllib.request.build_opener(*handlers)
        request = urllib.request.Request(
            prepared.url,
            data=prepared.body,
            method=prepared.method,
            headers=dict(prepared.headers),
        )
        try:
            response = opener.open(request, timeout=prepared.timeout)
        except urllib.error.HTTPError as exc:
            # 4xx/5xx (and unfollowed redirects) are responses too.
            response = exc
        try:
            try:
                raw, truncated = _read(response, max_body)
            except (AttributeError, TypeError):
                # An HTTPError without a body.
                raw, truncated = b"", False
            status = int(response.status if hasattr(response, "status") else response.code)
            reason = str(getattr(response, "reason", "") or "")
            headers = [[str(key), str(value)] for key, value in response.headers.items()]
            final_url = response.geturl() if hasattr(response, "geturl") else prepared.url
        finally:
            response.close()
    except EagleRequestError:
        raise
    except urllib.error.URLError as exc:
        reason = exc.reason
        if isinstance(reason, ssl.SSLError):
            message = f"TLS error: {reason}"
        elif isinstance(reason, socket.timeout):
            message = f"Timed out after {prepared.timeout:g} s."
        else:
            message = f"Connection failed: {reason}"
        return {"error": message, "elapsed_ms": round((time.monotonic() - started) * 1000)}
    except (socket.timeout, TimeoutError):
        return {
            "error": f"Timed out after {prepared.timeout:g} s.",
            "elapsed_ms": round((time.monotonic() - started) * 1000),
        }
    except (OSError, ValueError, ssl.SSLError) as exc:
        return {
            "error": f"Request failed: {exc}",
            "elapsed_ms": round((time.monotonic() - started) * 1000),
        }
    finally:
        shutil.rmtree(folder, ignore_errors=True)

    elapsed = round((time.monotonic() - started) * 1000)
    content_type = next((value for key, value in headers if key.lower() == "content-type"), "")
    text = _is_text(content_type, raw)
    body = raw.decode("utf-8", errors="replace") if text else base64.b64encode(raw).decode("ascii")
    return {
        "status": status,
        "reason": reason,
        "elapsed_ms": elapsed,
        "size": len(raw),
        "headers": headers,
        "body": body,
        "is_base64": not text,
        "truncated": truncated,
        "final_url": final_url,
    }


# ----------------------------------------------------------------------
# OAuth2 client credentials
# ----------------------------------------------------------------------

_TOKENS: Dict[str, Tuple[str, float]] = {}
_TOKENS_LOCK = threading.Lock()


def _token_cache_key(*parts: str) -> str:
    return hashlib.sha256("\x00".join(parts).encode("utf-8")).hexdigest()


def client_credentials_token(
    token_url: str,
    client_id: str,
    client_secret: str,
    scope: str,
    client_auth: str,
    tls: Tls,
    timeout: float,
) -> str:
    """An access token (cached until shortly before it expires)."""

    if not _ABSOLUTE.match(token_url):
        raise EagleRequestError("OAuth2 needs an absolute token URL.")
    cache_key = _token_cache_key(token_url, client_id, client_secret, scope, client_auth)
    with _TOKENS_LOCK:
        cached = _TOKENS.get(cache_key)
        if cached and cached[1] > time.time():
            return cached[0]

    form = {"grant_type": "client_credentials"}
    headers = [
        ("Content-Type", "application/x-www-form-urlencoded"),
        ("Accept", "application/json"),
    ]
    if client_auth == "basic":
        pair = f"{client_id}:{client_secret}".encode()
        headers.append(("Authorization", "Basic " + base64.b64encode(pair).decode("ascii")))
    else:
        form.update({"client_id": client_id, "client_secret": client_secret})
    if scope:
        form["scope"] = scope

    result = send(
        Prepared(
            method="POST",
            url=token_url,
            headers=headers,
            body=urlencode(form).encode("utf-8"),
            tls=tls,
            timeout=timeout,
        ),
        max_body=1024 * 1024,
    )
    if result.get("error"):
        raise EagleRequestError(f"OAuth2 token request failed: {result['error']}")
    if not 200 <= result["status"] < 300:
        raise EagleRequestError(
            f"OAuth2 token request failed: HTTP {result['status']} {result['reason']}".strip()
        )
    try:
        payload = json.loads(result["body"])
        token = str(payload["access_token"])
    except (ValueError, KeyError, TypeError):
        raise EagleRequestError("The OAuth2 token response has no access_token.") from None
    try:
        lifetime = float(payload.get("expires_in") or 300)
    except (TypeError, ValueError):
        lifetime = 300.0
    with _TOKENS_LOCK:
        _TOKENS[cache_key] = (token, time.time() + max(0.0, lifetime - 30))
    return token


# ----------------------------------------------------------------------
# From definition to request
# ----------------------------------------------------------------------


def join_base(base: str, path: str) -> str:
    """The environment's base URL followed by the request's path."""

    if not path:
        return base
    if path.startswith(("?", "#")):
        return base + path
    return base.rstrip("/") + "/" + path.lstrip("/")


def _with_params(url: str, params: List[Tuple[str, str]]) -> str:
    if not params:
        return url
    parts = urlsplit(url)
    query = urlencode(params)
    return urlunsplit(
        (
            parts.scheme,
            parts.netloc,
            parts.path,
            f"{parts.query}&{query}" if parts.query else query,
            parts.fragment,
        )
    )


def _has_header(headers: List[Tuple[str, str]], name: str) -> bool:
    return any(key.lower() == name.lower() for key, _ in headers)


def base_url(data: Dict[str, Any], resolver: Resolver, namespace: Optional[str]) -> str:
    """The request's full URL before query parameters."""

    url = resolver.text(data["url"]).strip()
    if _ABSOLUTE.match(url):
        return url
    if not resolver.environment:
        raise EagleRequestError(
            "Choose an environment, or enter a full URL (starting with http:// or https://)."
        )
    if not namespace:
        raise EagleRequestError("The project has no EagleAPI environment values yet.")
    try:
        base = resolver.text(f"${{entv:{namespace}/{resolver.environment}_URL}}").strip()
    except EagleReferenceError as exc:
        raise EagleRequestError(
            f"The environment {resolver.environment} has no base URL "
            f"({resolver.environment}_URL in {namespace}): {exc}"
        ) from None
    if not _ABSOLUTE.match(base):
        raise EagleRequestError(
            f"{resolver.environment}_URL must be a full URL starting with http:// or https://."
        )
    return join_base(base, url)


def prepare(
    definition: Any,
    resolver: Resolver,
    namespace: Optional[str],
    poll_url: Optional[str] = None,
) -> Prepared:
    """
    The concrete request. With `poll_url`, the poll request instead: the
    polling method, the URL found in the response (relative ones resolved
    against the request's URL) and, when chosen, the same headers and auth.
    """

    data = normalize_request(definition)
    polling = data["polling"]
    method = polling["method"] if poll_url else data["method"]
    if not _METHOD.match(method):
        raise EagleRequestError(f"'{method}' is not an HTTP method.")

    url = base_url(data, resolver, namespace)
    if poll_url:
        url = urljoin(url, poll_url.strip())
    else:
        params = [
            (resolver.text(row["key"]), resolver.text(row["value"]))
            for row in data["params"]
            if row["enabled"] and row["key"].strip()
        ]
        url = _with_params(url, params)
    if urlsplit(url).scheme.lower() not in ("http", "https"):
        raise EagleRequestError("Only http:// and https:// URLs can be called.")

    tls = Tls(verify=data["tls"]["verify"], ca=resolver.file(data["tls"]["ca_bundle"]))
    mode = data["tls"]["client_cert"]
    if mode == "pem":
        tls.cert = resolver.file(data["tls"]["cert"])
        tls.key = resolver.file(data["tls"]["key"])
        tls.password = resolver.text(data["tls"]["password"]) or None
        if not tls.cert:
            raise EagleRequestError("Choose the client certificate (PEM) from the vault.")
    elif mode == "pfx":
        tls.pfx = resolver.file(data["tls"]["pfx"])
        tls.password = resolver.text(data["tls"]["password"]) or None
        if not tls.pfx:
            raise EagleRequestError("Choose the PFX/P12 keystore from the vault.")

    prepared = Prepared(
        method=method,
        url=url,
        tls=tls,
        timeout=max(1.0, min(MAX_TIMEOUT, float(data["options"]["timeout"]))),
        follow_redirects=data["options"]["follow_redirects"],
    )

    reuse = not poll_url or polling["reuse_auth"]
    if reuse:
        prepared.headers = [
            (resolver.text(row["key"]).strip(), resolver.text(row["value"]))
            for row in data["headers"]
            if row["enabled"] and row["key"].strip()
        ]
        _apply_auth(data["auth"], prepared, resolver)

    if not poll_url:
        _apply_body(data["body"], prepared, resolver)
    return prepared


def _apply_body(body: Dict[str, Any], prepared: Prepared, resolver: Resolver) -> None:
    mode = body["mode"]
    if mode == "none":
        return
    if mode == "json":
        content, content_type = resolver.text(body["json"]), "application/json"
    elif mode == "form":
        pairs = [
            (resolver.text(row["key"]), resolver.text(row["value"]))
            for row in body["form"]
            if row["enabled"] and row["key"].strip()
        ]
        content, content_type = urlencode(pairs), "application/x-www-form-urlencoded"
    else:
        content, content_type = resolver.text(body["raw"]), body["content_type"] or "text/plain"
    prepared.body = content.encode("utf-8")
    if not _has_header(prepared.headers, "Content-Type"):
        prepared.headers.append(("Content-Type", content_type))


def _apply_auth(auth: Dict[str, Any], prepared: Prepared, resolver: Resolver) -> None:
    kind = auth["type"]
    if kind == "none" or _has_header(prepared.headers, "Authorization"):
        return
    if kind == "basic":
        pair = f"{resolver.text(auth['username'])}:{resolver.text(auth['password'])}"
        value = "Basic " + base64.b64encode(pair.encode("utf-8")).decode("ascii")
    elif kind == "bearer":
        token = resolver.text(auth["token"]).strip()
        if not token:
            raise EagleRequestError("Bearer auth needs a token.")
        value = f"Bearer {token}"
    else:
        token = client_credentials_token(
            resolver.text(auth["token_url"]).strip(),
            resolver.text(auth["client_id"]).strip(),
            resolver.text(auth["client_secret"]),
            resolver.text(auth["scope"]).strip(),
            auth["client_auth"],
            prepared.tls,
            prepared.timeout,
        )
        resolver.secrets.add(token)
        value = f"Bearer {token}"
    prepared.headers.append(("Authorization", value))


def execute(
    definition: Any,
    resolver: Resolver,
    namespace: Optional[str],
    poll_url: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Prepare, send, and describe the outcome for the browser: the response,
    the request that was sent (masked) and, when polling is on, the poll URL
    (after the main call) or whether polling is over (after a poll).
    """

    data = normalize_request(definition)
    try:
        prepared = prepare(data, resolver, namespace, poll_url)
    except EagleReferenceError as exc:
        raise EagleRequestError(str(exc)) from None
    result = send(prepared)

    result["request"] = {
        "method": prepared.method,
        "url": resolver.mask(prepared.url),
        "headers": [[key, resolver.mask_header(key, value)] for key, value in prepared.headers],
    }
    if "final_url" in result:
        result["final_url"] = resolver.mask(result["final_url"])
    if result.get("error"):
        result["error"] = resolver.mask(result["error"])

    polling = data["polling"]
    if poll_url:
        result["poll"] = stop_state(polling, result.get("status"), result.get("body") or "")
    elif polling["enabled"] and not result.get("error"):
        try:
            body = "" if result.get("is_base64") else result.get("body") or ""
            result["poll"] = {"url": extract_poll_url(polling["extract"], result["headers"], body)}
        except PollError as exc:
            result["poll"] = {"error": str(exc)}
    return result
