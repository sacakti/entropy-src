"""
A tiny OpenID Connect provider for tests: discovery, keys, token and
userinfo endpoints on localhost, signing ID tokens with a fresh RSA key.
"""

from __future__ import annotations

import base64
import hashlib
import json
import threading
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Dict, Optional

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding, rsa


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _int(value: int) -> str:
    return _b64url(value.to_bytes((value.bit_length() + 7) // 8, "big"))


class FakeIdP:
    def __init__(self, client_id: str = "entropy", client_secret: str = "s3cret") -> None:
        self.client_id = client_id
        self.client_secret = client_secret
        self.key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        self.kid = "k1"
        # code -> {nonce, challenge, claims}
        self.codes: Dict[str, Dict[str, Any]] = {}
        self.claims: Dict[str, Any] = {"sub": "u-1", "preferred_username": "dana"}
        self.userinfo: Dict[str, Any] = {}
        self.tamper = False
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), self._handler())
        self.issuer = f"http://localhost:{self.server.server_address[1]}/realms/test"
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    def __enter__(self) -> FakeIdP:
        self.thread.start()
        return self

    def __exit__(self, *exc: Any) -> None:
        self.server.shutdown()
        self.server.server_close()

    # -- what the browser would do at the provider -----------------------

    def authorize(self, url: str, claims: Optional[Dict[str, Any]] = None) -> Dict[str, str]:
        """Approve an authorization request; the callback's query (code and state)."""

        query = dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(url).query))
        assert query["client_id"] == self.client_id
        assert query["code_challenge_method"] == "S256"
        code = _b64url(hashlib.sha256(query["state"].encode()).digest())[:20]
        self.codes[code] = {
            "nonce": query["nonce"],
            "challenge": query["code_challenge"],
            "redirect_uri": query["redirect_uri"],
            "claims": dict(claims or self.claims),
        }
        return {"code": code, "state": query["state"]}

    def id_token(self, claims: Dict[str, Any]) -> str:
        header = {"alg": "RS256", "kid": self.kid, "typ": "JWT"}
        signing = _b64url(json.dumps(header).encode()) + "." + _b64url(json.dumps(claims).encode())
        signature = self.key.sign(signing.encode(), padding.PKCS1v15(), hashes.SHA256())
        if self.tamper:
            signature = bytes([signature[0] ^ 1]) + signature[1:]
        return signing + "." + _b64url(signature)

    # -- HTTP -----------------------------------------------------------

    def _handler(self):
        idp = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args: Any) -> None:
                pass

            def _json(self, status: int, body: Dict[str, Any]) -> None:
                data = json.dumps(body).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def do_GET(self) -> None:  # noqa: N802
                path = urllib.parse.urlsplit(self.path).path
                base = urllib.parse.urlsplit(idp.issuer).path
                if path == f"{base}/.well-known/openid-configuration":
                    self._json(
                        200,
                        {
                            "issuer": idp.issuer,
                            "authorization_endpoint": f"{idp.issuer}/auth",
                            "token_endpoint": f"{idp.issuer}/token",
                            "jwks_uri": f"{idp.issuer}/certs",
                            "userinfo_endpoint": f"{idp.issuer}/userinfo",
                        },
                    )
                elif path == f"{base}/certs":
                    numbers = idp.key.public_key().public_numbers()
                    self._json(
                        200,
                        {
                            "keys": [
                                {
                                    "kty": "RSA",
                                    "kid": idp.kid,
                                    "use": "sig",
                                    "alg": "RS256",
                                    "n": _int(numbers.n),
                                    "e": _int(numbers.e),
                                }
                            ]
                        },
                    )
                elif path == f"{base}/userinfo":
                    self._json(200, {"sub": idp.claims.get("sub"), **idp.userinfo})
                else:
                    self._json(404, {"error": "not_found"})

            def do_POST(self) -> None:  # noqa: N802
                length = int(self.headers.get("Content-Length") or 0)
                form = dict(urllib.parse.parse_qsl(self.rfile.read(length).decode()))
                auth = self.headers.get("Authorization") or ""
                expected = base64.b64encode(
                    f"{idp.client_id}:{idp.client_secret}".encode()
                ).decode()
                if auth != f"Basic {expected}":
                    self._json(401, {"error": "invalid_client"})
                    return
                grant = idp.codes.pop(form.get("code") or "", None)
                if grant is None:
                    self._json(400, {"error": "invalid_grant"})
                    return
                challenge = _b64url(hashlib.sha256(form["code_verifier"].encode()).digest())
                if challenge != grant["challenge"] or form["redirect_uri"] != grant["redirect_uri"]:
                    self._json(
                        400, {"error": "invalid_grant", "error_description": "PKCE mismatch"}
                    )
                    return
                now = int(time.time())
                claims = {
                    "iss": idp.issuer,
                    "aud": idp.client_id,
                    "iat": now,
                    "exp": now + 300,
                    "nonce": grant["nonce"],
                    **grant["claims"],
                }
                self._json(
                    200,
                    {
                        "access_token": "at",
                        "token_type": "Bearer",
                        "id_token": idp.id_token(claims),
                    },
                )

        return Handler
