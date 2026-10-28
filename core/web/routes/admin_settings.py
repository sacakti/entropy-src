"""
Administration -> Settings: e-mail (SMTP), sign-in (LDAP, single sign-on),
the public address, data retention and purging, and the connections for a
database migration target, a Redis cache and a message queue.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from fastapi import APIRouter, Body, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field

from core.web.projects import require
from core.web.routes.auth import _current_session, verify_csrf
from core.web.routes.sso import redirect_uri
from lib.auth.ldap_directory import Directory, DirectoryError, mapped_groups
from lib.auth.oidc import OidcError, discover, forget_cache
from lib.models.session import Session
from lib.models.users import User
from lib.runs.housekeeping import DEFAULTS as RETENTION_DEFAULTS
from lib.runs.housekeeping import Housekeeping
from lib.system.connections import CHECKS, ConnectionCheckError
from lib.system.mailer import MailError, addresses, send_mail
from lib.system.settings import SECTIONS, SettingsError, settings_for

router = APIRouter(prefix="/api/admin/settings", tags=["administration"])

SessionRecord = Tuple[Session, str, User]

RETENTION_FIELDS = {
    "archive_after_days": "runs.archive_after_days",
    "purge_archive_after_days": "runs.purge_archive_after_days",
    "notifications_keep_days": "notifications.keep_days",
}


class TestMail(BaseModel):
    to: Optional[str] = Field(default=None, max_length=500)


class TestLdap(BaseModel):
    username: str = Field(min_length=1, max_length=256)
    password: str = Field(default="", max_length=1024)


def _admin(request: Request, record: SessionRecord) -> User:
    _, _, user = record
    require(request, user, "system.settings")
    return user


def _retention(request: Request) -> Dict[str, Any]:
    housekeeping = Housekeeping(request.app.state.entropy_context.database_manager.connection)
    settings = housekeeping.settings()
    return {
        **{field: settings[key] for field, key in RETENTION_FIELDS.items()},
        "archived": housekeeping.archive_counts(),
        "defaults": {field: RETENTION_DEFAULTS[key] for field, key in RETENTION_FIELDS.items()},
    }


@router.get("")
def get_settings(
    request: Request,
    response: Response,
    record: SessionRecord = Depends(_current_session),
) -> Dict[str, Any]:
    _admin(request, record)
    store = settings_for(request.app.state.entropy_context)
    response.headers["Cache-Control"] = "no-store"
    return {
        **{section: store.get(section) for section in SECTIONS},
        "retention": _retention(request),
    }


@router.put("/retention", dependencies=[Depends(verify_csrf)])
def update_retention(
    request: Request,
    values: Dict[str, Any] = Body(...),
    record: SessionRecord = Depends(_current_session),
) -> Dict[str, Any]:
    _admin(request, record)
    housekeeping = Housekeeping(request.app.state.entropy_context.database_manager.connection)
    try:
        housekeeping.update_settings(
            {
                RETENTION_FIELDS[field]: value
                for field, value in values.items()
                if field in RETENTION_FIELDS
            }
        )
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
    return _retention(request)


@router.post("/retention/run", dependencies=[Depends(verify_csrf)])
def run_retention(
    request: Request,
    record: SessionRecord = Depends(_current_session),
) -> Dict[str, Any]:
    """Archive and purge now, with the current settings."""

    _admin(request, record)
    from lib.runs.service import RunService

    context = request.app.state.entropy_context
    service = RunService(context)
    result = Housekeeping(context.database_manager.connection).run(
        plugin_runs=service.plugin_run_directory(),
        worker_logs=service.log_path(0).parent,
    )
    return {"result": result, "retention": _retention(request)}


@router.put("/{section}", dependencies=[Depends(verify_csrf)])
def update_section(
    section: str,
    request: Request,
    values: Dict[str, Any] = Body(...),
    record: SessionRecord = Depends(_current_session),
) -> Dict[str, Any]:
    _admin(request, record)
    if section not in SECTIONS:
        raise HTTPException(status_code=404, detail=f"Unknown settings section '{section}'.")
    try:
        saved = settings_for(request.app.state.entropy_context).update(section, values)
    except SettingsError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
    if section == "oidc":
        # A new issuer or client must not reuse the old provider's keys.
        forget_cache()
    return saved


@router.post("/connections/{section}/test", dependencies=[Depends(verify_csrf)])
def test_connection(
    section: str,
    request: Request,
    record: SessionRecord = Depends(_current_session),
) -> Dict[str, Any]:
    """Check the saved database target, cache or queue connection."""

    _admin(request, record)
    check = CHECKS.get(section)
    if check is None:
        raise HTTPException(status_code=404, detail=f"No connection test for '{section}'.")
    values = settings_for(request.app.state.entropy_context).values(section)
    try:
        return check(values)
    except ConnectionCheckError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from None


@router.post("/smtp/test", dependencies=[Depends(verify_csrf)])
def test_mail(
    payload: TestMail,
    request: Request,
    record: SessionRecord = Depends(_current_session),
) -> Dict[str, Any]:
    """Send a test e-mail with the saved settings (to you, or `to`)."""

    user = _admin(request, record)
    recipients: List[str] = addresses([payload.to or user.email or ""])
    if not recipients:
        raise HTTPException(
            status_code=422,
            detail="Give an address to send to (your profile has no e-mail address).",
        )
    smtp = settings_for(request.app.state.entropy_context).values("smtp")
    try:
        send_mail(
            smtp,
            recipients,
            "Entropy test e-mail",
            f"Hello,\n\nThis is a test e-mail from Entropy, sent by {user.username}.\n"
            "E-mail is set up correctly.\n",
        )
    except MailError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from None
    return {"sent_to": recipients}


@router.post("/ldap/test", dependencies=[Depends(verify_csrf)])
def test_ldap(
    payload: TestLdap,
    request: Request,
    record: SessionRecord = Depends(_current_session),
) -> Dict[str, Any]:
    """Find a user with the saved LDAP settings; with a password, also check it."""

    _admin(request, record)
    settings = settings_for(request.app.state.entropy_context).values("ldap")
    if not settings["server_url"] or not settings["user_base_dn"]:
        raise HTTPException(status_code=422, detail="Save the server URL and base DN first.")
    directory = Directory(settings)
    try:
        found = directory.find(payload.username.strip())
        authenticated = (
            directory.check_password(found, payload.password)
            if found is not None and payload.password
            else None
        )
    except DirectoryError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from None
    if found is None:
        return {
            "found": False,
            "authenticated": None,
            "dn": None,
            "username": None,
            "full_name": None,
            "email": None,
            "groups": [],
            "mapped_groups": [],
        }
    return {
        "found": True,
        "authenticated": authenticated,
        "dn": found.dn,
        "username": found.username,
        "full_name": found.full_name,
        "email": found.email,
        "groups": found.groups,
        "mapped_groups": mapped_groups(settings["group_mappings"], found.groups, dn=True),
    }


@router.post("/oidc/test", dependencies=[Depends(verify_csrf)])
def test_oidc(
    request: Request,
    record: SessionRecord = Depends(_current_session),
) -> Dict[str, Any]:
    """Read the provider's configuration with the saved settings."""

    _admin(request, record)
    store = settings_for(request.app.state.entropy_context)
    settings = store.values("oidc")
    if not settings["issuer"]:
        raise HTTPException(status_code=422, detail="Save the issuer URL first.")
    forget_cache()
    try:
        discovery = discover(settings)
    except OidcError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from None
    return {
        "issuer": discovery["issuer"],
        "authorization_endpoint": discovery["authorization_endpoint"],
        "redirect_uri": redirect_uri(request, store.get("general")["public_url"]),
    }
