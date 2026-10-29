"""
Moving and copying work between projects, and project dumps.

A dump is a zip that can be restored into any project, on this Entropy or
another one:

    manifest.json           what is inside, where it came from
    workflows/<name>.json   workflow definitions
    schedules.json          schedules (restored paused)
    plugins/<ns.name>/...   plugins the workflows use (optional)
    vault.entvault          vault namespaces, passphrase-encrypted (optional)
"""

from __future__ import annotations

import io
import json
import re
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from lib.runs.schedules import ScheduleError, ScheduleStore

FORMAT = "entropy-project-dump"
VERSION = 1
MAX_DUMP_BYTES = 200 * 1024 * 1024
SCHEDULE_FIELDS = (
    "name",
    "description",
    "kind",
    "target",
    "cron",
    "timezone",
    "node",
    "parameters",
)


class TransferError(ValueError):
    """The transfer or restore cannot be done; the message says why."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def unique(name: str, taken: Callable[[str], bool], limit: int = 80) -> str:
    """`name`, or `name-2`, `name-3` … whichever is free."""

    if not taken(name):
        return name
    base = re.sub(r"-\d+$", "", name)[: limit - 4]
    for number in range(2, 1000):
        candidate = f"{base}-{number}"
        if not taken(candidate):
            return candidate
    raise TransferError(f"No free name like '{name}'.")


class ProjectTransfer:
    def __init__(self, context: Any) -> None:
        self.context = context
        self.connection = context.database_manager.connection
        self.workflows = context.workflow_manager
        from lib.authorization.projects import Projects

        self.projects = Projects(self.connection)
        self.schedules = ScheduleStore(self.connection)

    # -- helpers --------------------------------------------------------

    def _workflow_exists(self, name: str, project_id: int) -> bool:
        """Whether the project has a workflow of this name (names are per project)."""

        return bool(self.workflows.exists(name, project_id=project_id))

    def _schedule_name_taken(self, name: str) -> bool:
        return (
            self.connection.fetchone("SELECT 1 FROM schedules WHERE name = ?", (name,)) is not None
        )

    def _definition(self, name: str, project_id: int) -> Dict[str, Any]:
        return json.loads(
            self.workflows.serialize(self.workflows.get(name, project_id=project_id), "json")
        )

    def _add_definition(self, definition: Dict[str, Any], project_id: int) -> str:
        with tempfile.TemporaryDirectory(prefix="entropy-transfer-") as directory:
            path = Path(directory) / "definition.json"
            path.write_text(json.dumps(definition, indent=2), encoding="utf-8")
            workflow = self.workflows.add(path, project_id=project_id)
        return workflow.name

    def _move_workflow(self, name: str, source_id: int, target_id: int) -> None:
        """Move a workflow, with its alerts and kept versions (keyed by project)."""

        from lib.authorization.projects import workflow_key

        self.workflows.move(name, source_project_id=source_id, target_project_id=target_id)
        old, new = workflow_key(source_id, name), workflow_key(target_id, name)
        with self.connection.transaction():
            for table, column in (("run_alerts", "target"), ("definition_history", "name")):
                if self.connection.fetchone(
                    "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?", (table,)
                ):
                    self.connection.execute(
                        f"UPDATE {table} SET {column} = ? WHERE kind = 'workflow' AND {column} = ?",
                        (new, old),
                    )

    def _set_schedule_project(self, schedule_id: int, project_id: int) -> None:
        with self.connection.transaction():
            self.connection.execute(
                "UPDATE schedules SET project_id = ? WHERE id = ?", (project_id, schedule_id)
            )

    def _copy_schedule(
        self, schedule: Dict[str, Any], project_id: int, user: Any, target: Optional[str] = None
    ) -> Dict[str, Any]:
        data = {field: schedule.get(field) for field in SCHEDULE_FIELDS}
        if target:
            data["target"] = target
        data["name"] = unique(str(data["name"]), self._schedule_name_taken)
        # A copy starts paused: it runs only once someone turns it on.
        data["enabled"] = False
        return self.schedules.create(data, user.id, user.username, project_id)

    # -- move / copy ----------------------------------------------------

    def transfer(
        self,
        source_id: int,
        target_id: int,
        *,
        workflows: List[str],
        schedule_ids: List[int],
        mode: str,
        with_schedules: bool,
        user: Any,
    ) -> Dict[str, Any]:
        """
        Move or copy workflows and schedules from one project to another.
        Workflow copies get a free name; schedule copies start paused.
        """

        if source_id == target_id:
            raise TransferError("Choose a different project to move or copy to.")
        result: Dict[str, Any] = {"workflows": [], "schedules": [], "errors": []}
        renamed: Dict[str, str] = {}

        for name in dict.fromkeys(workflows):
            if not self._workflow_exists(name, source_id):
                result["errors"].append(f"Workflow '{name}' is not in the source project.")
                continue
            if mode == "move":
                if self._workflow_exists(name, target_id):
                    result["errors"].append(
                        f"Workflow '{name}': the target project already has one of that name."
                    )
                    continue
                self._move_workflow(name, source_id, target_id)
                result["workflows"].append({"name": name, "as": name})
            else:
                definition = self._definition(name, source_id)
                # Only names in the target project are taken.
                new_name = unique(
                    name, lambda candidate: self._workflow_exists(candidate, target_id)
                )
                definition["name"] = new_name
                try:
                    created = self._add_definition(definition, target_id)
                except Exception as exc:  # noqa: BLE001 - report and go on
                    result["errors"].append(f"Workflow '{name}': {exc}")
                    continue
                renamed[name] = created
                result["workflows"].append({"name": name, "as": created})

        chosen = {int(item) for item in schedule_ids}
        if with_schedules:
            moved = {item["name"] for item in result["workflows"]}
            for schedule in self.schedules.list(source_id):
                if schedule["kind"] == "workflow" and schedule["target"] in moved:
                    chosen.add(int(schedule["id"]))

        for schedule_id in sorted(chosen):
            schedule = self.schedules.get(schedule_id)
            if schedule is None or self.schedules.project_of(schedule) != source_id:
                result["errors"].append(f"Schedule {schedule_id} is not in the source project.")
                continue
            try:
                if mode == "move":
                    self._set_schedule_project(schedule_id, target_id)
                    result["schedules"].append({"name": schedule["name"], "as": schedule["name"]})
                else:
                    target = (
                        renamed.get(schedule["target"]) if schedule["kind"] == "workflow" else None
                    )
                    copy = self._copy_schedule(schedule, target_id, user, target)
                    result["schedules"].append({"name": schedule["name"], "as": copy["name"]})
            except ScheduleError as exc:
                result["errors"].append(f"Schedule '{schedule['name']}': {exc}")
        return result

    # -- dump -----------------------------------------------------------

    def dump(
        self,
        project: Dict[str, Any],
        *,
        workflows: Optional[List[str]],
        include_schedules: bool,
        plugin_files: Callable[[List[str]], bytes],
        include_plugins: bool,
        vault: Optional[bytes],
        user: Any,
    ) -> bytes:
        """The project's (or the chosen) workflows and more, as one zip."""

        owned = sorted(entry.name for entry in self.workflows.list(project_id=project["id"]))
        names = [name for name in (workflows if workflows is not None else owned) if name in owned]

        buffer = io.BytesIO()
        plugins_used: List[str] = []
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
            for name in names:
                workflow = self.workflows.get(name, project_id=project["id"])
                archive.writestr(
                    f"workflows/{name}.json", self.workflows.serialize(workflow, "json")
                )
                for step in workflow.steps:
                    if step.plugin not in plugins_used:
                        plugins_used.append(step.plugin)

            schedules = []
            if include_schedules:
                for schedule in self.schedules.list(project["id"]):
                    if schedule["kind"] == "workflow" and schedule["target"] not in names:
                        continue
                    schedules.append({field: schedule.get(field) for field in SCHEDULE_FIELDS})
                    schedules[-1]["enabled"] = bool(schedule.get("enabled"))
                    if schedule["kind"] == "plugin" and schedule["target"] not in plugins_used:
                        plugins_used.append(schedule["target"])
                archive.writestr("schedules.json", json.dumps(schedules, indent=2))

            included_plugins: List[str] = []
            if include_plugins and plugins_used:
                installed = [name for name in plugins_used if self._plugin_installed(name)]
                if installed:
                    with zipfile.ZipFile(io.BytesIO(plugin_files(installed))) as plugins:
                        for member in plugins.infolist():
                            archive.writestr(f"plugins/{member.filename}", plugins.read(member))
                    included_plugins = installed

            if vault is not None:
                archive.writestr("vault.entvault", vault)

            from core.version import VERSION as ENTROPY_VERSION

            archive.writestr(
                "manifest.json",
                json.dumps(
                    {
                        "format": FORMAT,
                        "version": VERSION,
                        "entropy_version": ENTROPY_VERSION,
                        "project": {
                            "key": project["key"],
                            "name": project["name"],
                            "description": project.get("description") or "",
                        },
                        "created_at": _now(),
                        "created_by": user.username,
                        "workflows": names,
                        "schedules": len(schedules),
                        "plugins": included_plugins,
                        "plugins_used": plugins_used,
                        "vault": vault is not None,
                    },
                    indent=2,
                ),
            )
        return buffer.getvalue()

    def _plugin_installed(self, name: str) -> bool:
        try:
            self.context.plugin_manager.get(name)
        except Exception:  # noqa: BLE001
            return False
        return True

    # -- restore --------------------------------------------------------

    @staticmethod
    def read(data: bytes) -> zipfile.ZipFile:
        if len(data) > MAX_DUMP_BYTES:
            raise TransferError("The dump is too large.")
        try:
            archive = zipfile.ZipFile(io.BytesIO(data))
        except zipfile.BadZipFile:
            raise TransferError("This is not a project dump (not a zip file).") from None
        total = 0
        for member in archive.infolist():
            if member.filename.startswith("/") or ".." in Path(member.filename).parts:
                raise TransferError(f"Unsafe path '{member.filename}' in the dump.")
            total += member.file_size
            if total > MAX_DUMP_BYTES * 5:
                raise TransferError("The dump expands too large.")
        try:
            manifest = json.loads(archive.read("manifest.json"))
        except (KeyError, ValueError):
            raise TransferError("This is not a project dump (no manifest.json).") from None
        if manifest.get("format") != FORMAT:
            raise TransferError("This is not an Entropy project dump.")
        if int(manifest.get("version") or 0) > VERSION:
            raise TransferError("This dump was made by a newer Entropy.")
        return archive

    @staticmethod
    def manifest(archive: zipfile.ZipFile) -> Dict[str, Any]:
        return json.loads(archive.read("manifest.json"))

    def restore(
        self,
        archive: zipfile.ZipFile,
        project_id: int,
        *,
        conflict: str,
        can_write_workflow: Callable[[str], bool],
        restore_schedules: bool,
        install_plugins: Optional[Callable[[bytes], List[str]]],
        user: Any,
    ) -> Dict[str, Any]:
        """
        Put a dump's workflows (and schedules, and missing plugins) into a
        project. `conflict` decides what happens when a workflow name exists:
        skip it, overwrite it (only if you may change that workflow) or
        rename the restored one.
        """

        result: Dict[str, Any] = {
            "workflows": [],
            "skipped": [],
            "skipped_schedules": [],
            "schedules": [],
            "plugins": [],
            "errors": [],
        }
        renamed: Dict[str, str] = {}

        if install_plugins is not None:
            members = [item for item in archive.infolist() if item.filename.startswith("plugins/")]
            if members:
                buffer = io.BytesIO()
                with zipfile.ZipFile(buffer, "w") as plugins:
                    for member in members:
                        name = member.filename[len("plugins/") :]
                        if name:
                            plugins.writestr(name, archive.read(member))
                try:
                    result["plugins"] = install_plugins(buffer.getvalue())
                except Exception as exc:  # noqa: BLE001 - workflows still restore
                    result["errors"].append(f"Plugins: {exc}")

        for member in sorted(archive.namelist()):
            if not (member.startswith("workflows/") and member.endswith(".json")):
                continue
            try:
                definition = json.loads(archive.read(member))
                name = str(definition["name"])
            except (ValueError, KeyError, TypeError):
                result["errors"].append(f"{member} is not a workflow definition.")
                continue
            try:
                # Only this project's names conflict.
                if self._workflow_exists(name, project_id):
                    if conflict == "skip":
                        result["skipped"].append(name)
                        continue
                    if conflict == "overwrite" and can_write_workflow(name):
                        self._replace(name, definition, user, project_id)
                        result["workflows"].append({"name": name, "as": name, "replaced": True})
                        continue
                    definition["name"] = unique(
                        name, lambda candidate: self._workflow_exists(candidate, project_id)
                    )
                created = self._add_definition(definition, project_id)
                renamed[name] = created
                result["workflows"].append({"name": name, "as": created, "replaced": False})
            except Exception as exc:  # noqa: BLE001 - report each workflow
                result["errors"].append(f"Workflow '{name}': {exc}")

        if restore_schedules and "schedules.json" in archive.namelist():
            try:
                schedules = json.loads(archive.read("schedules.json"))
            except ValueError:
                schedules = []
                result["errors"].append("schedules.json is damaged.")
            restored = {item["name"]: item["as"] for item in result["workflows"]}
            for schedule in schedules if isinstance(schedules, list) else []:
                if conflict == "skip" and self._schedule_name_taken(str(schedule.get("name"))):
                    result["skipped_schedules"].append(str(schedule.get("name")))
                    continue
                if schedule.get("kind") == "workflow" and schedule.get("target") not in restored:
                    result["errors"].append(
                        f"Schedule '{schedule.get('name')}' skipped: its workflow was not restored."
                    )
                    continue
                target = (
                    restored.get(schedule.get("target"))
                    if schedule.get("kind") == "workflow"
                    else None
                )
                try:
                    copy = self._copy_schedule(schedule, project_id, user, target)
                    result["schedules"].append({"name": schedule.get("name"), "as": copy["name"]})
                except ScheduleError as exc:
                    result["errors"].append(f"Schedule '{schedule.get('name')}': {exc}")
        return result

    def _replace(self, name: str, definition: Dict[str, Any], user: Any, project_id: int) -> None:
        from lib.authorization.projects import workflow_key
        from lib.history import DefinitionHistory

        previous = self.workflows.get(name, project_id=project_id)
        with tempfile.TemporaryDirectory(prefix="entropy-transfer-") as directory:
            path = Path(directory) / "definition.json"
            path.write_text(json.dumps(definition, indent=2), encoding="utf-8")
            self.workflows.replace(name, path, project_id=project_id)
        # The replaced version stays in the workflow's History.
        DefinitionHistory(self.connection, "workflow").record(
            workflow_key(project_id, name),
            previous.version,
            self.workflows.serialize(previous, "json"),
            user=user.username,
        )
