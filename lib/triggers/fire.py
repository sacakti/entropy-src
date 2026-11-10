"""
Start the run of a trigger: its workflow or plugin, in its project, as its owner.

With `use_payload`, a JSON object payload overrides the trigger's parameters key by
key: workflow variables take every key, plugin arguments only the ones the plugin
declares. A workflow also gets `trigger_payload` (the payload, parsed when it is
JSON), `trigger_name` and `trigger_source`.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional, Tuple

from lib.runs.schedules import RUN_PERMISSION, schedule_owner
from lib.runs.service import RunError, RunService

from .store import TriggerStore


def parse_payload(text: str) -> Any:
    """The payload as JSON when it is JSON, else the text itself."""

    if not text.strip():
        return None
    try:
        return json.loads(text)
    except ValueError:
        return text


def _plugin_arguments(context: Any, qualified_name: str) -> Optional[List[str]]:
    """Names of the arguments a plugin declares; None when they cannot be read."""

    from lib.plugins.contract import plugin_contract

    try:
        plugin = context.plugin_manager.get(qualified_name)
        return [item["name"] for item in plugin_contract(plugin.path)["arguments"]]
    except Exception:  # noqa: BLE001 - the run itself reports a missing plugin
        return None


def parameters_for(
    context: Any, trigger: Dict[str, Any], payload: Any
) -> Tuple[Dict[str, Any], List[str]]:
    """What the run is started with, and the payload keys a plugin does not take."""

    values = dict(trigger["parameters"] or {})
    ignored: List[str] = []
    fields = payload if trigger["use_payload"] and isinstance(payload, dict) else {}
    if trigger["kind"] == "workflow":
        values.update(fields)
        values.update(
            {
                "trigger_payload": payload,
                "trigger_name": trigger["name"],
                "trigger_source": trigger["source"],
            }
        )
        return values, ignored
    declared = _plugin_arguments(context, trigger["target"])
    for key, value in fields.items():
        if declared is None or key in declared:
            values[key] = value
        else:
            ignored.append(str(key))
    return values, ignored


def fire_trigger(
    context: Any,
    store: TriggerStore,
    trigger: Dict[str, Any],
    *,
    payload_text: str,
    source: str,
    caller: Optional[str],
    user: Any = None,
) -> Dict[str, Any]:
    """
    Start one run of the trigger and record it. Failures to start are recorded and
    returned (with `error`), never raised. `user` fires it as someone else (Fire now);
    otherwise it runs as the trigger's owner.
    """

    actor = user or schedule_owner(store.connection, trigger["user_id"])
    error: Optional[str] = None
    job_id: Optional[int] = None
    payload = parse_payload(payload_text)

    if actor is None:
        error = f"Owner '{trigger['username']}' no longer exists or is disabled."
    elif context.authorization is None or not context.authorization.has_permission(
        actor.id, RUN_PERMISSION[trigger["kind"]], trigger["project_id"]
    ):
        error = f"'{actor.username}' is not allowed to run this {trigger['kind']}."
    else:
        values, ignored = parameters_for(context, trigger, payload)
        service = RunService(context)
        try:
            # The run's own trigger column says manual; mark_triggered records the source.
            if trigger["kind"] == "workflow":
                run = service.start_workflow(
                    actor,
                    trigger["target"],
                    node=trigger["node"],
                    trigger="manual",
                    project_id=trigger["project_id"],
                    variables=values,
                )
            else:
                run = service.start_plugin(
                    actor,
                    trigger["target"],
                    node=trigger["node"],
                    trigger="manual",
                    project_id=trigger["project_id"],
                    arguments=values,
                )
            job_id = run.get("id")
            if job_id is not None:
                service.store.mark_triggered(int(job_id), source, trigger["id"], trigger["name"])
        except RunError as exc:
            error = str(exc)
        except Exception as exc:  # noqa: BLE001 - record any start failure
            error = str(exc) or exc.__class__.__name__
        if ignored and error is None:
            caller = f"{caller or ''} (ignored: {', '.join(sorted(ignored))})".strip()

    record = store.add_run(
        trigger["id"],
        source=source,
        job_id=job_id,
        error=error,
        payload=payload_text,
        caller=caller,
    )
    if error:
        from lib.database.repositories.notifications import notify_user

        notify_user(
            context,
            trigger["user_id"],
            f"Trigger '{trigger['name']}' could not start",
            error,
            "error",
            "triggers",
        )
    return record
