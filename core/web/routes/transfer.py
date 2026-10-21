"""
Move or copy workflows and schedules between projects; dump a project to
a zip and restore a dump into a project.
"""

from __future__ import annotations

from datetime import date
from typing import Any, Dict, List, Literal, Optional, Tuple

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, Response, UploadFile
from pydantic import BaseModel, Field

from core.web.projects import authorization, projects, require
from core.web.routes.auth import _current_session, verify_csrf
from core.web.transfer import MAX_DUMP_BYTES, ProjectTransfer, TransferError
from lib.models.session import Session
from lib.models.users import User

router = APIRouter(prefix="/api/projects", tags=["projects"])

SessionRecord = Tuple[Session, str, User]


class TransferRequest(BaseModel):
    target: str = Field(min_length=1, max_length=40)
    mode: Literal["move", "copy"] = "move"
    workflows: List[str] = Field(default_factory=list, max_length=1000)
    schedules: List[int] = Field(default_factory=list, max_length=1000)
    # Also take the schedules that run the chosen workflows.
    with_schedules: bool = True


class DumpRequest(BaseModel):
    # None: every workflow of the project.
    workflows: Optional[List[str]] = Field(default=None, max_length=1000)
    schedules: bool = True
    plugins: bool = True
    vault: List[str] = Field(default_factory=list, max_length=500)
    passphrase: str = Field(default="", max_length=1024)


def _project(request: Request, key: str) -> Dict[str, Any]:
    project = projects(request).get(key)
    if project is None:
        raise HTTPException(status_code=404, detail=f"Project '{key}' not found.")
    return project


def _transfer(request: Request) -> ProjectTransfer:
    context = request.app.state.entropy_context
    if context.workflow_manager is None or context.database_manager is None:
        raise HTTPException(status_code=503, detail="Workflow service unavailable.")
    return ProjectTransfer(context)


@router.post("/{key}/transfer", dependencies=[Depends(verify_csrf)])
def transfer(
    key: str,
    payload: TransferRequest,
    request: Request,
    record: SessionRecord = Depends(_current_session),
) -> Dict[str, Any]:
    """Move (or copy) workflows and schedules from this project to `target`."""

    _, _, user = record
    source = _project(request, key)
    target = _project(request, payload.target)
    move = payload.mode == "move"
    if payload.workflows:
        require(request, user, "workflows.read", source["id"])
        if move:
            require(request, user, "workflows.write", source["id"])
            require(request, user, "workflows.delete", source["id"])
        require(request, user, "workflows.write", target["id"])
    if payload.schedules or (payload.workflows and payload.with_schedules):
        require(request, user, "schedules.list", source["id"])
        if move:
            require(request, user, "schedules.manage", source["id"])
        require(request, user, "schedules.manage", target["id"])
    try:
        result = _transfer(request).transfer(
            source["id"],
            target["id"],
            workflows=payload.workflows,
            schedule_ids=payload.schedules,
            mode=payload.mode,
            with_schedules=payload.with_schedules,
            user=user,
        )
    except TransferError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
    return {**result, "source": source["key"], "target": target["key"], "mode": payload.mode}


@router.post("/{key}/dump", dependencies=[Depends(verify_csrf)])
def dump(
    key: str,
    payload: DumpRequest,
    request: Request,
    record: SessionRecord = Depends(_current_session),
) -> Response:
    """Download the project's workflows, schedules, plugins and vault as a zip."""

    from core.web.plugin_studio.workspace import PluginStudio
    from core.web.routes.vault import _readable_namespaces, _vault_components
    from lib.vault.portable import PortableVaultError, collect, seal

    _, _, user = record
    project = _project(request, key)
    require(request, user, "workflows.read", project["id"])
    if payload.schedules:
        require(request, user, "schedules.list", project["id"])
    if payload.plugins:
        require(request, user, "plugins.read")

    vault = None
    if payload.vault:
        namespaces = _readable_namespaces(request, user, payload.vault)
        vault_manager, _ = _vault_components(request)
        try:
            vault = seal(collect(vault_manager, namespaces, user.username), payload.passphrase)
        except PortableVaultError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from None

    context = request.app.state.entropy_context
    data = _transfer(request).dump(
        project,
        workflows=payload.workflows,
        include_schedules=payload.schedules,
        plugin_files=lambda names: PluginStudio(context).export(names),
        include_plugins=payload.plugins,
        vault=vault,
        user=user,
    )
    return Response(
        content=data,
        media_type="application/zip",
        headers={
            "Content-Disposition": (
                f'attachment; filename="entropy-{project["key"]}-{date.today().isoformat()}.zip"'
            ),
            "Cache-Control": "no-store",
        },
    )


@router.post("/{key}/restore", dependencies=[Depends(verify_csrf)])
async def restore(
    key: str,
    request: Request,
    file: UploadFile = File(...),
    conflict: Literal["skip", "overwrite", "rename"] = Form("rename"),
    schedules: bool = Form(True),
    plugins: bool = Form(True),
    vault: bool = Form(True),
    vault_overwrite: bool = Form(False),
    passphrase: str = Form(""),
    preview: bool = Form(False),
    record: SessionRecord = Depends(_current_session),
) -> Dict[str, Any]:
    """
    Restore a dump into this project. With `preview`, only say what is in it.
    Schedules come back paused; plugins are installed only when missing.
    """

    _, _, user = record
    project = _project(request, key)
    raw = await file.read(MAX_DUMP_BYTES + 1)
    service = _transfer(request)
    try:
        archive = service.read(raw)
    except TransferError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
    manifest = service.manifest(archive)
    if preview:
        return {"manifest": manifest}

    require(request, user, "workflows.write", project["id"])
    if schedules:
        require(request, user, "schedules.manage", project["id"])
    context = request.app.state.entropy_context
    service_auth = authorization(request)

    def can_write_workflow(name: str) -> bool:
        owner = projects(request).workflow_project(name)
        return bool(service_auth.has_permission(user.id, "workflows.write", owner))

    install = None
    if plugins and service_auth.has_permission(user.id, "plugins.write"):
        from core.web.plugin_studio.workspace import PluginStudio

        def install(data: bytes) -> List[str]:
            return _install_missing_plugins(context, data, PluginStudio(context))

    result = service.restore(
        archive,
        project["id"],
        conflict=conflict,
        can_write_workflow=can_write_workflow,
        restore_schedules=schedules,
        install_plugins=install,
        user=user,
    )
    if plugins and install is None and manifest.get("plugins"):
        result["errors"].append("Plugins were not installed: that needs plugins.write.")

    result["vault"] = None
    if vault and "vault.entvault" in archive.namelist():
        from core.web.routes.vault import _has_permission, _may_write, _vault_components
        from lib.vault.portable import PortableVaultError, unseal
        from lib.vault.portable import restore as restore_vault

        try:
            payload = unseal(archive.read("vault.entvault"), passphrase)
            vault_manager, namespace_manager = _vault_components(request)
            result["vault"] = restore_vault(
                vault_manager,
                namespace_manager,
                payload,
                owner_user_id=user.id,
                can_create=_has_permission(request, user, "vault.namespace.create"),
                can_write=_may_write(request, user),
                overwrite=vault_overwrite,
            )
        except PortableVaultError as exc:
            result["errors"].append(f"Vault: {exc}")
    return {**result, "manifest": manifest}


def _install_missing_plugins(context: Any, data: bytes, studio: Any) -> List[str]:
    """Install the dump's plugins that are not installed here; others stay as they are."""

    import io
    import json
    import zipfile

    installed: List[str] = []
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        groups: Dict[str, List[str]] = {}
        for name in archive.namelist():
            top = name.split("/", 1)[0]
            groups.setdefault(top, []).append(name)
        for top, members in groups.items():
            manifest_name = f"{top}/plugin.json"
            if manifest_name not in members:
                continue
            manifest = json.loads(archive.read(manifest_name))
            qualified = f"{manifest.get('namespace')}.{manifest.get('name')}"
            try:
                context.plugin_manager.get(qualified)
                continue  # installed already: never replaced by a restore
            except Exception:  # noqa: BLE001 - not installed
                pass
            buffer = io.BytesIO()
            with zipfile.ZipFile(buffer, "w") as single:
                for member in members:
                    single.writestr(member, archive.read(member))
            for plugin in studio.import_archive(buffer.getvalue(), install=True):
                installed.append(getattr(plugin, "qualified_name", qualified))
    return installed
