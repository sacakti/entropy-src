
"""
Browser authentication endpoints.
"""

from __future__ import annotations

import secrets
from typing import Tuple

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel

from lib.auth.exceptions import AuthenticationRequiredError
from lib.models.session import Session
from lib.models.users import User
from lib.users.exceptions import AuthenticationError, UserInactiveError

router = APIRouter(prefix="/api/auth", tags=["authentication"])

SESSION_COOKIE = "entropy_session"
CSRF_COOKIE = "entropy_csrf"


class LoginRequest(BaseModel):
    username: str
    password: str


def _cookie_options(request: Request) -> dict:
    return {
        "path": "/",
        "secure": request.app.state.web_cookie_secure,
        "samesite": "strict",
    }


def _current_session(
    request: Request,
) -> Tuple[Session, str, User]:
    store = request.app.state.web_session_store
    record = store.get(request.cookies.get(SESSION_COOKIE))

    if record is None:
        raise HTTPException(
            status_code=401,
            detail="Authentication required.",
        )

    return record

@router.get("/csrf")
async def csrf_token(request: Request, response: Response) -> dict:
    """Issue or reuse a CSRF token for the current browser."""

    record = request.app.state.web_session_store.get(
        request.cookies.get(SESSION_COOKIE)
    )

    if record is not None:
        token = record[1]
    else:
        token = request.cookies.get(CSRF_COOKIE)

        if not token or len(token) != 64:
            token = secrets.token_hex(32)

    response.set_cookie(
        CSRF_COOKIE,
        token,
        max_age=request.app.state.web_session_store.timeout_seconds,
        httponly=False,
        **_cookie_options(request),
    )
    response.headers["Cache-Control"] = "no-store"

    return {"csrf_token": token}


def verify_csrf(request: Request) -> None:
    """Validate the browser's double-submit CSRF token."""

    cookie_token = request.cookies.get(CSRF_COOKIE)
    header_token = request.headers.get("X-CSRF-Token")

    if (
        not cookie_token
        or not header_token
        or not secrets.compare_digest(cookie_token, header_token)
    ):
        raise HTTPException(
            status_code=403,
            detail="Invalid CSRF token.",
        )

@router.post("/login")
async def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    _: None = Depends(verify_csrf),
) -> dict:
    """Authenticate a browser user without altering the CLI session."""

    store = request.app.state.web_session_store

    try:
        session, csrf = store.login(payload.username, payload.password)
    except (AuthenticationError, UserInactiveError):
        raise HTTPException(
            status_code=401,
            detail="Invalid username or password.",
        ) from None

    options = _cookie_options(request)

    response.set_cookie(
        SESSION_COOKIE,
        session.token,
        max_age=store.timeout_seconds,
        httponly=True,
        **options,
    )
    response.set_cookie(
        CSRF_COOKIE,
        csrf,
        max_age=store.timeout_seconds,
        httponly=False,
        **options,
    )
    response.headers["Cache-Control"] = "no-store"

    return {
        "authenticated": True,
        "user": {
            "id": session.user_id,
            "username": session.username,
            "full_name": session.full_name,
        },
        "expires_at": session.expires_at.isoformat(),
    }


@router.get("/me")
async def me(
    request: Request,
    response: Response,
    record: Tuple[Session, str, User] = Depends(_current_session),
) -> dict:
    """Return the current user's identity and effective permissions."""

    session, _, user = record
    context = request.app.state.entropy_context

    if context.authorization is None:
        raise HTTPException(status_code=503, detail="Authorization unavailable.")

    assert user.id is not None
    permissions = context.authorization.permissions(user.id)

    response.headers["Cache-Control"] = "no-store"

    return {
        "user": {
            "id": user.id,
            "username": user.username,
            "full_name": user.full_name,
            "email": user.email,
        },
        "permissions": permissions,
        "expires_at": session.expires_at.isoformat(),
    }


@router.post("/logout")
async def logout(
    request: Request,
    response: Response,
    _: None = Depends(verify_csrf),
) -> dict:
    """Revoke the current browser session and clear browser cookies."""

    store = request.app.state.web_session_store
    store.logout(request.cookies.get(SESSION_COOKIE))

    options = _cookie_options(request)
    response.delete_cookie(SESSION_COOKIE, **options)
    response.delete_cookie(CSRF_COOKIE, **options)
    response.headers["Cache-Control"] = "no-store"

    return {"authenticated": False}
