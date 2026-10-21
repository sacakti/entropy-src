
"""
Browser authentication endpoints.
"""

from __future__ import annotations

import secrets
from typing import Optional, Tuple

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field, ConfigDict

from lib.auth.exceptions import AuthenticationRequiredError
from lib.models.session import Session
from lib.models.users import User
from lib.users.exceptions import AuthenticationError, CurrentPasswordMismatchError, PasswordReuseError, UserInactiveError, WeakPasswordError

router = APIRouter(prefix="/api/auth", tags=["authentication"])

SESSION_COOKIE = "entropy_session"
CSRF_COOKIE = "entropy_csrf"


class LoginRequest(BaseModel):
    username: str
    password: str

class ChangePasswordRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    current_password: str = Field(min_length=1)
    new_password: str = Field(min_length=8)

def _cookie_options(request: Request) -> dict:
    return {
        "path": "/",
        "secure": request.app.state.web_cookie_secure,
        "samesite": "strict",
    }


def bearer_token(request: Request) -> Optional[str]:
    """The token of an `Authorization: Bearer` header (command line clients)."""

    header = request.headers.get("authorization") or ""
    if header[:7].lower() == "bearer ":
        return header[7:].strip() or None
    return None


def _current_session(
    request: Request,
) -> Tuple[Session, str, User]:
    store = request.app.state.web_session_store
    # Browsers send the session cookie; the ent command line a bearer token.
    record = store.get(bearer_token(request) or request.cookies.get(SESSION_COOKIE))

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

    # Cross-site requests cannot set an Authorization header, so bearer
    # requests need no CSRF token; the token itself is checked on use.
    if bearer_token(request):
        return

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
    # Global permissions plus those of the user's roles in the current project.
    from core.web.projects import current_project

    project = current_project(request, user)
    permissions = context.authorization.permissions(
        user.id, project["id"] if project else None
    )

    response.headers["Cache-Control"] = "no-store"

    avatar_version = None

    if context.database_manager is not None:
        from lib.database.repositories.user_web_settings import (
            UserWebSettingsRepository,
        )

        avatar_version = UserWebSettingsRepository(
            context.database_manager.connection,
        ).avatar_version(user.id)

    return {
        "user": {
            "id": user.id,
            "username": user.username,
            "full_name": user.full_name,
            "email": user.email,
            "avatar_url": (
                f"/api/profile/avatar?v={avatar_version}"
                if avatar_version
                else None
            ),
        },
        "permissions": permissions,
        "project": (
            {"key": project["key"], "name": project["name"]} if project else None
        ),
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


@router.post("/change-password")
async def change_password(
    payload: ChangePasswordRequest,
    request: Request,
    _: None = Depends(verify_csrf),
    record: Tuple[Session, str, User] = Depends(_current_session),
) -> dict:
    _, _, user = record

    context = request.app.state.entropy_context

    try:
        context.user_manager.change_password(
            user=user,
            current_password=payload.current_password,
            new_password=payload.new_password,
        )
    except CurrentPasswordMismatchError:
        raise HTTPException(
            status_code=400,
            detail="Current password is incorrect.",
        ) from None
    except PasswordReuseError:
        raise HTTPException(
            status_code=400,
            detail="Choose a password different from your current password.",
        ) from None
    except WeakPasswordError as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        ) from None

    return {"message": "Password changed successfully."}


# ----------------------------------------------------------------------
# Command line tokens
# ----------------------------------------------------------------------


class TokenRequest(BaseModel):
    username: str
    password: str


def _token_payload(session: Session) -> dict:
    return {
        "token": session.token,
        "expires_at": session.expires_at.isoformat(),
        "user": {
            "id": session.user_id,
            "username": session.username,
            "full_name": session.full_name,
        },
    }


@router.post("/token")
async def create_token(payload: TokenRequest, request: Request, response: Response) -> dict:
    """Exchange a username and password for a command line token (`ent login`)."""

    store = request.app.state.web_session_store

    try:
        session, _ = store.login(
            payload.username, payload.password, seconds=store.cli_timeout_seconds
        )
    except (AuthenticationError, UserInactiveError):
        raise HTTPException(status_code=401, detail="Invalid username or password.") from None

    response.headers["Cache-Control"] = "no-store"
    return _token_payload(session)


@router.post("/cli-token", dependencies=[Depends(verify_csrf)])
async def create_cli_token(
    request: Request,
    response: Response,
    record: Tuple[Session, str, User] = Depends(_current_session),
) -> dict:
    """A command line token for the signed-in user ("Copy login command")."""

    _, _, user = record
    store = request.app.state.web_session_store
    session, _ = store.issue(user, seconds=store.cli_timeout_seconds)

    response.headers["Cache-Control"] = "no-store"
    return _token_payload(session)


@router.delete("/token")
async def revoke_token(request: Request, response: Response) -> dict:
    """Revoke the bearer token of this request (`ent logout`)."""

    token = bearer_token(request)
    if not token:
        raise HTTPException(status_code=400, detail="Send the token as a Bearer token.")

    request.app.state.web_session_store.logout(token)
    response.headers["Cache-Control"] = "no-store"
    return {"revoked": True}
