"""
Sign-in options shown on the login page, and single sign-on (OpenID Connect).
"""

from __future__ import annotations

import logging
import secrets
import urllib.parse
from typing import Any, Dict

from fastapi import APIRouter, Request, Response
from fastapi.responses import RedirectResponse

from core.web.routes.auth import CSRF_COOKIE, SESSION_COOKIE, _cookie_options
from lib.auth.external import ExternalAccounts, SignInRefused
from lib.auth.ldap_directory import mapped_groups
from lib.auth.oidc import OidcError, claim_list, finish, start
from lib.system.settings import settings_for
from lib.users.exceptions import AuthenticationError, UserInactiveError

LOGGER = logging.getLogger("entropy.auth")

router = APIRouter(prefix="/api/auth", tags=["authentication"])

STATE_COOKIE = "entropy_oidc_state"
CALLBACK_PATH = "/api/auth/oidc/callback"


def redirect_uri(request: Request, public_url: str) -> str:
    """Where the identity provider sends the browser back (register it there)."""

    base = public_url.rstrip("/") if public_url else str(request.base_url).rstrip("/")
    return base + CALLBACK_PATH


def _login_page(message: str) -> RedirectResponse:
    response = RedirectResponse(
        "/?" + urllib.parse.urlencode({"sso_error": message[:300]}), status_code=303
    )
    response.delete_cookie(STATE_COOKIE, path="/api/auth/oidc")
    return response


@router.get("/providers")
def providers(request: Request, response: Response) -> Dict[str, Any]:
    """How people can sign in (public: the login page needs it)."""

    store = settings_for(request.app.state.entropy_context)
    oidc = store.get("oidc")
    response.headers["Cache-Control"] = "no-store"
    return {
        "ldap": bool(store.get("ldap")["enabled"]),
        "oidc": {
            "enabled": bool(oidc["enabled"]),
            "label": oidc["button_label"] or "Sign in with SSO",
        },
    }


@router.get("/oidc/start")
def oidc_start(request: Request) -> Response:
    store = settings_for(request.app.state.entropy_context)
    settings = store.values("oidc")
    if not settings.get("enabled"):
        return _login_page("Single sign-on is not set up.")
    try:
        url, state = start(settings, redirect_uri(request, store.get("general")["public_url"]))
    except OidcError as exc:
        LOGGER.warning("Single sign-on could not start: %s", exc)
        return _login_page("The identity provider cannot be reached; try again later.")
    response = RedirectResponse(url, status_code=303)
    # Ties the callback to this browser (login CSRF); Lax so the provider's
    # redirect back carries it.
    response.set_cookie(
        STATE_COOKIE,
        state,
        max_age=600,
        httponly=True,
        secure=request.app.state.web_cookie_secure,
        samesite="lax",
        path="/api/auth/oidc",
    )
    response.headers["Cache-Control"] = "no-store"
    return response


@router.get("/oidc/callback")
def oidc_callback(request: Request) -> Response:
    params = request.query_params
    if params.get("error"):
        return _login_page(
            f"The identity provider refused the sign-in: "
            f"{params.get('error_description') or params['error']}"
        )
    state, code = params.get("state") or "", params.get("code") or ""
    cookie = request.cookies.get(STATE_COOKIE) or ""
    if not state or not code or not cookie or not secrets.compare_digest(state, cookie):
        return _login_page("The sign-in could not be matched to this browser; try again.")

    context = request.app.state.entropy_context
    settings = settings_for(context).values("oidc")
    if not settings.get("enabled"):
        return _login_page("Single sign-on is not set up.")
    try:
        claims = finish(settings, state, code)
    except OidcError as exc:
        LOGGER.warning("Single sign-on failed: %s", exc)
        return _login_page(str(exc))

    username = str(
        claims.get(settings["claim_username"]) or claims.get("email") or claims["sub"]
    ).strip()
    mappings = settings.get("group_mappings") or []
    try:
        user = ExternalAccounts(context).account(
            "oidc",
            str(claims["sub"]),
            username=username,
            full_name=claims.get(settings["claim_full_name"]) or None,
            email=claims.get(settings["claim_email"]) or None,
            auto_create=bool(settings.get("auto_create_users")),
            groups=mapped_groups(
                mappings, claim_list(claims.get(settings["claim_groups"])), dn=False
            ),
            managed_groups=[mapping["group"] for mapping in mappings],
        )
    except SignInRefused as exc:
        return _login_page(str(exc))
    except UserInactiveError:
        return _login_page("Your Entropy account is disabled.")
    except AuthenticationError:
        return _login_page("Sign-in failed.")

    store = request.app.state.web_session_store
    session, csrf = store.issue(user)
    response = RedirectResponse("/", status_code=303)
    options = _cookie_options(request)
    response.set_cookie(
        SESSION_COOKIE, session.token, max_age=store.timeout_seconds, httponly=True, **options
    )
    response.set_cookie(CSRF_COOKIE, csrf, max_age=store.timeout_seconds, httponly=False, **options)
    response.delete_cookie(STATE_COOKIE, path="/api/auth/oidc")
    response.headers["Cache-Control"] = "no-store"
    return response
