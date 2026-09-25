from __future__ import annotations

from datetime import datetime
from typing import Any

from lib.workflow.jobs.events import WorkflowEvent
from lib.workflow.jobs.model import WorkflowJob

from ..models.report import (
    ActivityReport,
    ExecutionReport,
    ReportSummary,
    ReportTimelineEvent,
    StageReport,
    StepReport,
)


class ReportBuilder:
    """Build a diagnostic execution report from persisted workflow events."""

    def build(self, job: WorkflowJob, events: list[WorkflowEvent]) -> ExecutionReport:
        ordered = sorted(events, key=self._sort_key)
        steps = self._build_steps(ordered)

        started = job.started_at or self._event_time(ordered, "execution.started")
        finished = job.finished_at or self._last_event_time(
            ordered,
            {"execution.completed", "execution.failed", "execution.cancelled"},
        )

        return ExecutionReport(
            execution_id=job.execution_id,
            workflow=job.workflow,
            status=self._execution_status(job, ordered),
            user_id=job.user_id,
            username=job.username,
            workspace=str(job.workspace),
            started_at=started,
            finished_at=finished,
            duration_ms=self._duration(started, finished),
            summary=self._summary(job, ordered, steps),
            steps=steps,
            timeline=[self._timeline(e) for e in ordered],
            metadata={
                "job_id": job.id,
                "pid": job.pid,
                "exit_code": job.exit_code,
                "selected_steps": self._selected_steps(ordered),
            },
        )

    def _build_steps(self, events: list[WorkflowEvent]) -> list[StepReport]:
        steps: dict[str, dict[str, Any]] = {}
        current_step: str | None = None
        current_stage: str | None = None

        for event in events:
            if event.event_type == "plugin_result" and current_step:
                result = (event.payload or {}).get("result")
                if isinstance(result, dict):
                    step = steps[current_step]
                    step["result"] = result
                    step["changed"] = bool(result.get("changed"))
                    if result.get("success") is False:
                        step["status"] = "FAILED"
                        if not step["failure"]:
                            step["failure"] = self._failure_from_result(result)

            if event.node_type == "step" and event.node_id:
                item = steps.setdefault(event.node_id, self._new_step(event))
                current_step = event.node_id

                if event.event_type == "step.started":
                    metadata = self._metadata(event)
                    item["index"] = metadata.get("index")
                    item["plugin"] = metadata.get("plugin") or item["plugin"]
                    item["started_at"] = event.created_at
                    item["status"] = "RUNNING"

                elif event.event_type == "step.completed":
                    item["finished_at"] = event.created_at
                    item["duration_ms"] = self._duration_from_event(event)
                    if item["status"] != "FAILED":
                        item["status"] = "COMPLETED"

                elif event.event_type == "step.failed":
                    item["finished_at"] = event.created_at
                    item["duration_ms"] = self._duration_from_event(event)
                    item["status"] = "FAILED"
                    item["failure"] = self._failure_from_event(event)

                elif event.event_type == "step.skipped":
                    item["finished_at"] = event.created_at
                    item["status"] = "SKIPPED"

                elif event.event_type == "step.cancelled":
                    item["finished_at"] = event.created_at
                    item["status"] = "CANCELLED"

                elif event.event_type == "message":
                    item["messages"].append(self._timeline(event))

                if event.event_type in {
                    "step.completed",
                    "step.failed",
                    "step.skipped",
                    "step.cancelled",
                }:
                    current_stage = None
                continue

            if event.node_type == "stage" and event.node_id and current_step:
                step = steps[current_step]
                stage = step["stage_map"].setdefault(event.node_id, self._new_stage(event))

                if event.event_type == "stage.started":
                    current_stage = event.node_id
                    stage["started_at"] = event.created_at
                    stage["status"] = "RUNNING"
                elif event.event_type == "stage.completed":
                    stage["finished_at"] = event.created_at
                    stage["duration_ms"] = self._duration_from_event(event)
                    stage["status"] = "COMPLETED"
                elif event.event_type == "stage.failed":
                    stage["finished_at"] = event.created_at
                    stage["duration_ms"] = self._duration_from_event(event)
                    stage["status"] = "FAILED"
                elif event.event_type == "stage.cancelled":
                    stage["finished_at"] = event.created_at
                    stage["status"] = "CANCELLED"
                elif event.event_type == "message":
                    stage["messages"].append(self._timeline(event))
                continue

            if event.node_type == "activity" and event.node_id and current_step:
                step = steps[current_step]
                container = (
                    step["stage_map"][current_stage]["activity_map"]
                    if current_stage and current_stage in step["stage_map"]
                    else step["activity_map"]
                )
                activity = container.setdefault(event.node_id, self._new_activity(event))

                if event.event_type == "activity.started":
                    activity["started_at"] = event.created_at
                    activity["status"] = "RUNNING"
                elif event.event_type == "activity.completed":
                    activity["finished_at"] = event.created_at
                    activity["duration_ms"] = self._duration_from_event(event)
                    activity["status"] = "COMPLETED"
                elif event.event_type == "activity.failed":
                    activity["finished_at"] = event.created_at
                    activity["duration_ms"] = self._duration_from_event(event)
                    activity["status"] = "FAILED"
                    exception = self._metadata(event).get("exception")
                    if exception and not step["failure"]:
                        step["failure"] = {
                            "type": "ActivityFailure",
                            "message": str(exception),
                            "source": event.node_name,
                        }
                elif event.event_type == "activity.cancelled":
                    activity["finished_at"] = event.created_at
                    activity["status"] = "CANCELLED"
                elif event.event_type == "message":
                    activity["messages"].append(self._timeline(event))
                continue

            elif event.event_type == "message" and current_step:
                steps[current_step]["messages"].append(self._timeline(event))

        return [
            StepReport(
                name=item["name"],
                plugin=item["plugin"],
                node_id=item["node_id"],
                status=item["status"],
                index=item["index"],
                started_at=item["started_at"],
                finished_at=item["finished_at"],
                duration_ms=item["duration_ms"],
                changed=item["changed"],
                stages=[self._stage_report(s) for s in item["stage_map"].values()],
                activities=[self._activity_report(a) for a in item["activity_map"].values()],
                messages=item["messages"],
                result=item["result"],
                failure=item["failure"],
            )
            for item in sorted(
                steps.values(),
                key=lambda x: (
                    x["index"] if x["index"] is not None else 999999,
                    x["started_at"] or datetime.min,
                ),
            )
        ]

    @staticmethod
    def _new_step(event):
        return {
            "name": event.node_name or "Workflow step",
            "plugin": "",
            "node_id": event.node_id,
            "index": None,
            "status": "UNKNOWN",
            "started_at": None,
            "finished_at": None,
            "duration_ms": None,
            "changed": False,
            "stage_map": {},
            "activity_map": {},
            "messages": [],
            "result": None,
            "failure": None,
        }

    @staticmethod
    def _new_stage(event):
        return {
            "name": event.node_name or "Stage",
            "node_id": event.node_id,
            "status": "UNKNOWN",
            "started_at": None,
            "finished_at": None,
            "duration_ms": None,
            "activity_map": {},
            "messages": [],
        }

    @staticmethod
    def _new_activity(event):
        return {
            "name": event.node_name or "Activity",
            "node_id": event.node_id,
            "status": "UNKNOWN",
            "started_at": None,
            "finished_at": None,
            "duration_ms": None,
            "messages": [],
        }

    def _stage_report(self, value):
        return StageReport(
            name=value["name"],
            node_id=value["node_id"],
            status=value["status"],
            started_at=value["started_at"],
            finished_at=value["finished_at"],
            duration_ms=value["duration_ms"],
            activities=[self._activity_report(a) for a in value["activity_map"].values()],
            messages=value["messages"],
        )

    @staticmethod
    def _activity_report(value):
        return ActivityReport(
            name=value["name"],
            node_id=value["node_id"],
            status=value["status"],
            started_at=value["started_at"],
            finished_at=value["finished_at"],
            duration_ms=value["duration_ms"],
            messages=value["messages"],
        )

    def _summary(self, job, events, steps):
        durations = [s.duration_ms for s in steps if s.duration_ms is not None]
        slowest = max(
            ((s.name, s.duration_ms) for s in steps if s.duration_ms is not None),
            key=lambda x: x[1],
            default=(None, 0),
        )
        warning_steps = sum(self._step_has_level(s, "WARNING") for s in steps)
        error_steps = sum(self._step_has_level(s, "ERROR") for s in steps)

        return ReportSummary(
            total_steps=len(steps),
            successful_steps=sum(
                s.status == "COMPLETED" and not (s.result and s.result.get("success") is False)
                for s in steps
            ),
            failed_steps=sum(
                1
                for s in steps
                if s.status == "FAILED"
                or (s.result is not None and s.result.get("success") is False)
            ),
            skipped_steps=sum(s.status == "SKIPPED" for s in steps),
            changed_steps=sum(s.changed for s in steps),
            unchanged_steps=sum(s.status == "COMPLETED" and not s.changed for s in steps),
            warning_steps=warning_steps,
            error_steps=error_steps,
            total_duration_ms=self._duration(job.started_at, job.finished_at) or sum(durations),
            average_step_duration_ms=int(sum(durations) / len(durations)) if durations else 0,
            slowest_step=slowest[0],
            slowest_step_duration_ms=slowest[1] or 0,
        )

    def _step_has_level(self, step, wanted):
        return any(self._level(m.level) == wanted for m in self._messages(step))

    @staticmethod
    def _messages(step):
        values = list(step.messages)
        for stage in step.stages:
            values.extend(stage.messages)
            for activity in stage.activities:
                values.extend(activity.messages)
        for activity in step.activities:
            values.extend(activity.messages)
        return values

    @staticmethod
    def _failure_from_event(event):
        metadata = ReportBuilder._metadata(event)
        exception = metadata.get("exception")
        if exception:
            return {
                "type": "WorkflowException",
                "message": str(exception),
                "source": event.node_name,
            }
        return {
            "type": "StepFailure",
            "message": event.message or "Step execution failed.",
            "source": event.node_name,
        }

    @staticmethod
    def _failure_from_result(result):
        errors = result.get("errors") or []
        message = errors[0] if errors else "Plugin reported failure."
        if isinstance(message, dict):
            message = message.get("message") or message.get("error") or str(message)
        return {
            "type": "PluginFailure",
            "message": str(message),
            "source": "plugin_result",
        }

    @staticmethod
    def _metadata(event):
        payload = event.payload or {}
        metadata = payload.get("metadata")
        return metadata if isinstance(metadata, dict) else {}

    @staticmethod
    def _duration_from_event(event):
        value = (event.payload or {}).get("duration_ms")
        return value if isinstance(value, int) else None

    @staticmethod
    def _timeline(event):
        return ReportTimelineEvent(
            timestamp=event.created_at,
            event_type=event.event_type,
            message=event.message,
            node_type=event.node_type,
            node_id=event.node_id,
            node_name=event.node_name,
            duration_ms=ReportBuilder._duration_from_event(event),
            level=event.level,
            payload=event.payload or {},
        )

    @staticmethod
    def _selected_steps(events):
        totals = [
            ReportBuilder._metadata(e).get("total")
            for e in events
            if e.event_type == "step.started"
        ]
        return max((x for x in totals if isinstance(x, int)), default=0)

    @staticmethod
    def _execution_status(job, events):
        state = str(job.state.value).upper()
        if state in {"COMPLETED", "FAILED", "CANCELLED"}:
            return state
        for event in reversed(events):
            if event.event_type.startswith("execution."):
                return event.event_type.rsplit(".", 1)[-1].upper()
        return state

    @staticmethod
    def _event_time(events, event_type):
        for event in events:
            if event.event_type == event_type:
                return event.created_at
        return None

    @staticmethod
    def _last_event_time(events, types):
        for event in reversed(events):
            if event.event_type in types:
                return event.created_at
        return None

    @staticmethod
    def _duration(start, finish):
        if not start or not finish:
            return None
        return int((finish - start).total_seconds() * 1000)

    @staticmethod
    def _sort_key(event):
        return event.created_at or datetime.min

    @staticmethod
    def _level(value):
        return {
            "10": "DEBUG",
            "20": "INFO",
            "25": "NOTICE",
            "30": "WARNING",
            "40": "ERROR",
            "50": "CRITICAL",
        }.get(str(value or "").upper(), str(value or "").upper())
