"""Application version API, and what is new in it."""

from typing import Any, Dict, Tuple

from fastapi import APIRouter, Depends, Request, Response

from core.version import APP_NAME, VERSION
from core.web.routes.auth import _current_session, verify_csrf
from lib.database.repositories.user_web_settings import UserWebSettingsRepository
from lib.models.session import Session
from lib.models.users import User
from lib.system.release_notes import load_releases, unseen_releases
from lib.users.onboarding import Onboarding

router = APIRouter(
    prefix="/api",
    tags=["Application"],
)

SEEN_KEY = "release_notes_seen"
SessionRecord = Tuple[str, Session, User]


def _settings(request: Request) -> UserWebSettingsRepository:
    return UserWebSettingsRepository(request.app.state.entropy_context.database_manager.connection)


@router.get("/version")
async def get_application_version() -> dict[str, str]:
    """Return the running application's version."""

    return {
        "name": APP_NAME,
        "version": VERSION,
    }


@router.get("/version/notes")
def release_notes(
    request: Request,
    response: Response,
    record: SessionRecord = Depends(_current_session),  # noqa: B008
) -> Dict[str, Any]:
    """Release notes, newest first, and which of them this person has not been shown."""

    _, _, user = record
    assert user.id is not None
    response.headers["Cache-Control"] = "no-store"
    releases = load_releases(VERSION)
    settings = _settings(request)
    seen = settings.get_settings(user.id).get(SEEN_KEY)
    connection = request.app.state.entropy_context.database_manager.connection
    if seen is None and Onboarding(connection).pending(user.id):
        # A new account gets the welcome tour; everything is new, so nothing is news.
        settings.update_settings(user.id, {SEEN_KEY: VERSION})
        seen = VERSION
    return {
        "version": VERSION,
        "releases": releases,
        "unseen": unseen_releases(releases, VERSION, seen),
    }


@router.post("/version/notes/seen", dependencies=[Depends(verify_csrf)])
def mark_release_notes_seen(
    request: Request,
    record: SessionRecord = Depends(_current_session),  # noqa: B008
) -> Dict[str, str]:
    """Do not announce this version to this person again."""

    _, _, user = record
    assert user.id is not None
    _settings(request).update_settings(user.id, {SEEN_KEY: VERSION})
    return {"seen": VERSION}
