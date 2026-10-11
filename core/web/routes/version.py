"""Application version API."""

from fastapi import APIRouter

from core.version import APP_NAME, VERSION

router = APIRouter(
    prefix="/api",
    tags=["Application"],
)


@router.get("/version")
async def get_application_version() -> dict[str, str]:
    """Return the running application's version."""

    return {
        "name": APP_NAME,
        "version": VERSION,
    }
