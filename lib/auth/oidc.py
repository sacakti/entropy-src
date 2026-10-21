"""
Single sign-on with OpenID Connect (Keycloak, Azure AD / Entra ID, Okta, ...),
using the authorization code flow with PKCE.

The browser is sent to the identity provider; it comes back to
/api/auth/oidc/callback with a code that Entropy exchanges for an ID token.
The token's signature, issuer, audience, expiry and nonce are checked
before anyone is signed in.
"""

from __future__ import annotations

import base64
import hashlib
import json
import secrets
import ssl
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional, Tuple

TIMEOUT_SECONDS = 15
DISCOVERY_TTL = 3600
FLOW_TTL = 600
CLOCK_SKEW = 120


class OidcError(RuntimeError):
    """Single sign-on failed; the message says why in plain words."""


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64url_decode(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def _ssl_context(settings: Dict[str, Any]) -> ssl.SSLContext:
    context = ssl.create_default_context()
    if not settings.get("verify_tls", True):
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
    return context


def _fetch(
    settings: Dict[str, Any],
    url: str,
    *,
    data: Optional[Dict[str, str]] = None,
    headers: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    body = urllib.parse.urlencode(data).encode("ascii") if data is not None else None
    request = urllib.request.Request(
        url, data=body, headers={"Accept": "application/json", **(headers or {})}
    )
    try:
        with urllib.request.urlopen(  # nosec B310 - URLs come from the admin's issuer
            request, timeout=TIMEOUT_SECONDS, context=_ssl_context(settings)
        ) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = ""
        try:
            error = json.loads(exc.read().decode("utf-8"))
            detail = error.get("error_description") or error.get("error") or ""
        except (ValueError, AttributeError):
            pass
        raise OidcError(f"{url} answered {exc.code}{': ' + detail if detail else ''}") from None
    except (urllib.error.URLError, OSError) as exc:
        reason = getattr(exc, "reason", exc)
        raise OidcError(f"Could not reach {url}: {reason}") from None
    except ValueError:
        raise OidcError(f"{url} did not answer with JSON.") from None
    if not isinstance(payload, dict):
        raise OidcError(f"{url} did not answer with a JSON object.")
    return payload


# ----------------------------------------------------------------------
# Discovery and keys (cached)
# ----------------------------------------------------------------------

_cache: Dict[str, Tuple[float, Dict[str, Any]]] = {}
_cache_lock = threading.Lock()


def _cached(key: str, load) -> Dict[str, Any]:
    with _cache_lock:
        hit = _cache.get(key)
        if hit and time.time() - hit[0] < DISCOVERY_TTL:
            return hit[1]
    value = load()
    with _cache_lock:
        _cache[key] = (time.time(), value)
    return value


def forget_cache() -> None:
    with _cache_lock:
        _cache.clear()


def discover(settings: Dict[str, Any]) -> Dict[str, Any]:
    issuer = str(settings["issuer"]).rstrip("/")

    def load() -> Dict[str, Any]:
        document = _fetch(settings, f"{issuer}/.well-known/openid-configuration")
        for name in ("issuer", "authorization_endpoint", "token_endpoint", "jwks_uri"):
            if not document.get(name):
                raise OidcError(f"The provider's configuration has no {name}.")
        if str(document["issuer"]).rstrip("/") != issuer:
            raise OidcError(
                f"The provider calls itself {document['issuer']}, not {issuer}; "
                "use its exact issuer URL."
            )
        return document

    return _cached(f"discovery:{issuer}", load)


def _keys(settings: Dict[str, Any], jwks_uri: str, *, fresh: bool = False) -> List[Dict[str, Any]]:
    if fresh:
        with _cache_lock:
            _cache.pop(f"jwks:{jwks_uri}", None)
    keys = _cached(f"jwks:{jwks_uri}", lambda: _fetch(settings, jwks_uri)).get("keys")
    return keys if isinstance(keys, list) else []


# ----------------------------------------------------------------------
# ID token
# ----------------------------------------------------------------------

_HASHES = {"256": "SHA256", "384": "SHA384", "512": "SHA512"}


def _public_key(jwk: Dict[str, Any]):
    from cryptography.hazmat.primitives.asymmetric import ec, rsa

    if jwk.get("kty") == "RSA":
        return rsa.RSAPublicNumbers(
            int.from_bytes(_b64url_decode(jwk["e"]), "big"),
            int.from_bytes(_b64url_decode(jwk["n"]), "big"),
        ).public_key()
    if jwk.get("kty") == "EC":
        curve = {"P-256": ec.SECP256R1(), "P-384": ec.SECP384R1(), "P-521": ec.SECP521R1()}.get(
            jwk.get("crv")
        )
        if curve is None:
            raise OidcError(f"Unsupported key curve {jwk.get('crv')}.")
        return ec.EllipticCurvePublicNumbers(
            int.from_bytes(_b64url_decode(jwk["x"]), "big"),
            int.from_bytes(_b64url_decode(jwk["y"]), "big"),
            curve,
        ).public_key()
    raise OidcError(f"Unsupported key type {jwk.get('kty')}.")


def _verify_signature(algorithm: str, jwk: Dict[str, Any], signed: bytes, signature: bytes) -> bool:
    from cryptography.exceptions import InvalidSignature
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import ec, padding, utils

    family, bits = algorithm[:2], algorithm[2:]
    if bits not in _HASHES or family not in ("RS", "PS", "ES"):
        raise OidcError(f"Unsupported ID token algorithm {algorithm}.")
    digest = getattr(hashes, _HASHES[bits])()
    key = _public_key(jwk)
    try:
        if family == "RS":
            key.verify(signature, signed, padding.PKCS1v15(), digest)
        elif family == "PS":
            key.verify(
                signature,
                signed,
                padding.PSS(mgf=padding.MGF1(digest), salt_length=digest.digest_size),
                digest,
            )
        else:
            half = len(signature) // 2
            der = utils.encode_dss_signature(
                int.from_bytes(signature[:half], "big"), int.from_bytes(signature[half:], "big")
            )
            key.verify(der, signed, ec.ECDSA(digest))
    except InvalidSignature:
        return False
    return True


def validate_id_token(
    settings: Dict[str, Any], discovery: Dict[str, Any], token: str, nonce: str
) -> Dict[str, Any]:
    try:
        header_b64, payload_b64, signature_b64 = token.split(".")
        header = json.loads(_b64url_decode(header_b64))
        claims = json.loads(_b64url_decode(payload_b64))
        signature = _b64url_decode(signature_b64)
    except (ValueError, TypeError):
        raise OidcError("The ID token is malformed.") from None
    algorithm = str(header.get("alg") or "")
    if algorithm.lower() == "none" or algorithm.startswith("HS"):
        raise OidcError(f"ID tokens signed with {algorithm or 'nothing'} are not accepted.")

    signed = f"{header_b64}.{payload_b64}".encode("ascii")
    kid = header.get("kid")
    for fresh in (False, True):
        candidates = [
            key
            for key in _keys(settings, discovery["jwks_uri"], fresh=fresh)
            if (kid is None or key.get("kid") == kid) and key.get("use", "sig") == "sig"
        ]
        if candidates:
            break
    if not candidates:
        raise OidcError("The provider's keys do not include the one that signed the ID token.")
    if not any(_verify_signature(algorithm, key, signed, signature) for key in candidates):
        raise OidcError("The ID token's signature is not valid.")

    now = time.time()
    if str(claims.get("iss") or "").rstrip("/") != str(discovery["issuer"]).rstrip("/"):
        raise OidcError("The ID token was issued by another provider.")
    audience = claims.get("aud")
    audiences = audience if isinstance(audience, list) else [audience]
    if settings["client_id"] not in audiences:
        raise OidcError("The ID token was issued for another application.")
    if len(audiences) > 1 and claims.get("azp") not in (None, settings["client_id"]):
        raise OidcError("The ID token was issued for another application.")
    if float(claims.get("exp") or 0) + CLOCK_SKEW < now:
        raise OidcError("The ID token has expired; check the server clock.")
    if not secrets.compare_digest(str(claims.get("nonce") or ""), nonce):
        raise OidcError("The sign-in could not be matched to this browser; try again.")
    return claims


# ----------------------------------------------------------------------
# Flow
# ----------------------------------------------------------------------

_flows: Dict[str, Dict[str, Any]] = {}
_flows_lock = threading.Lock()


def start(settings: Dict[str, Any], redirect_uri: str) -> Tuple[str, str]:
    """The URL to send the browser to, and the state that identifies the flow."""

    discovery = discover(settings)
    state = secrets.token_urlsafe(32)
    nonce = secrets.token_urlsafe(32)
    verifier = secrets.token_urlsafe(64)
    challenge = _b64url(hashlib.sha256(verifier.encode("ascii")).digest())
    with _flows_lock:
        cutoff = time.time() - FLOW_TTL
        for key in [key for key, flow in _flows.items() if flow["created"] < cutoff]:
            del _flows[key]
        _flows[state] = {
            "created": time.time(),
            "nonce": nonce,
            "verifier": verifier,
            "redirect_uri": redirect_uri,
        }
    query = urllib.parse.urlencode(
        {
            "response_type": "code",
            "client_id": settings["client_id"],
            "redirect_uri": redirect_uri,
            "scope": settings.get("scopes") or "openid",
            "state": state,
            "nonce": nonce,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
        }
    )
    endpoint = discovery["authorization_endpoint"]
    return f"{endpoint}{'&' if '?' in endpoint else '?'}{query}", state


def finish(settings: Dict[str, Any], state: str, code: str) -> Dict[str, Any]:
    """Exchange the code; the verified claims (with userinfo merged in)."""

    with _flows_lock:
        flow = _flows.pop(state, None)
    if flow is None or time.time() - flow["created"] > FLOW_TTL:
        raise OidcError("The sign-in took too long or was already used; try again.")
    discovery = discover(settings)
    form = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": flow["redirect_uri"],
        "client_id": settings["client_id"],
        "code_verifier": flow["verifier"],
    }
    headers: Dict[str, str] = {}
    if settings.get("client_secret"):
        methods = discovery.get("token_endpoint_auth_methods_supported") or ["client_secret_basic"]
        if "client_secret_basic" in methods:
            pair = (
                f"{urllib.parse.quote_plus(settings['client_id'])}:"
                f"{urllib.parse.quote_plus(settings['client_secret'])}"
            )
            headers["Authorization"] = "Basic " + base64.b64encode(pair.encode()).decode("ascii")
        else:
            form["client_secret"] = settings["client_secret"]
    tokens = _fetch(settings, discovery["token_endpoint"], data=form, headers=headers)
    if not tokens.get("id_token"):
        raise OidcError("The provider returned no ID token; is 'openid' among the scopes?")
    claims = validate_id_token(settings, discovery, tokens["id_token"], flow["nonce"])

    if discovery.get("userinfo_endpoint") and tokens.get("access_token"):
        try:
            info = _fetch(
                settings,
                discovery["userinfo_endpoint"],
                headers={"Authorization": f"Bearer {tokens['access_token']}"},
            )
        except OidcError:
            info = {}
        # Userinfo only adds; it never replaces who the ID token says this is.
        if info.get("sub") == claims.get("sub"):
            for key, value in info.items():
                claims.setdefault(key, value)
    return claims


def claim_list(value: Any) -> List[str]:
    if isinstance(value, list):
        return [str(item) for item in value]
    if isinstance(value, str) and value:
        return [part.strip() for part in value.replace(",", " ").split() if part.strip()]
    return []
