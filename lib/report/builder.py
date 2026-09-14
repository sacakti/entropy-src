"""
Build a useful execution report from persisted workflow events.
"""

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
    """Transform persisted workflow events into an ExecutionReport."""

    def build(
        self,
        job: WorkflowJob,
        events: list[WorkflowEvent],
    ) -> ExecutionReport:
        ordered = sorted(events, key=self._event_sort_key)
        steps = self._build_steps(ordered)

        workflow_started = self._first_event(ordered, "execution.started")
        workflow_finished = self._last_event(
            ordered,
            {"execution.completed", "execution.failed", "execution.cancelled"},
        )

        started_at = job.started_at or (
            workflow_started.created_at if workflow_started else None
        )
        finished_at = job.finished_at or (
            workflow_finished.created_at if workflow_finished else None
        )

        summary = self._build_summary(
            job=job,
            steps=steps,
            selected_steps=self._selected_step_count(ordered),
        )

        return ExecutionReport(
            execution_id=job.execution_id,
            workflow=job.workflow,
            status=self._execution_status(job, ordered),
            started_at=started_at,
            finished_at=finished_at,
            duration_ms=self._duration(started_at, finished_at),
            summary=summary,
            steps=steps,
            timeline=[self._timeline(event) for event in ordered],
            metadata={
                "job_id": job.id,
                "pid": job.pid,
                "exit_code": job.exit_code,
                "workspace": str(job.workspace),
                "selected_steps": self._selected_step_count(ordered),
            },
        )

    # ------------------------------------------------------------------
    # Steps
    # ------------------------------------------------------------------

    def _build_steps(self, events: list[WorkflowEvent]) -> list[StepReport]:
        data: dict[str, dict[str, Any]] = {}
        current_step: str | None = None
        current_stage: str | None = None
        activity_stage: dict[str, str | None] = {}

        for event in events:
            node_id = event.node_id
            kind = event.event_type

            if event.node_type == "step" and node_id:
                step = data.setdefault(node_id, self._new_step(event))

                if kind == "step.started":
                    current_step = node_id
                    current_stage = None
                    metadata = self._metadata(event)
                    step["index"] = metadata.get("index")
                    step["plugin"] = metadata.get("plugin", "")
                    step["status"] = "RUNNING"
                    step["started_at"] = event.created_at

                elif kind == "step.completed":
                    step["finished_at"] = event.created_at
                    step["duration_ms"] = self._event_duration(event)
                    if step["status"] != "FAILED":
                        step["status"] = "COMPLETED"

                elif kind == "step.failed":
                    step["status"] = "FAILED"
                    step["finished_at"] = event.created_at
                    step["duration_ms"] = self._event_duration(event)

                elif kind == "step.skipped":
                    step["status"] = "SKIPPED"
                    step["finished_at"] = event.created_at

                elif kind == "step.cancelled":
                    step["status"] = "CANCELLED"
                    step["finished_at"] = event.created_at

                elif kind == "message":
                    step["messages"].append(self._timeline(event))

                if kind in {
                    "step.completed",
                    "step.failed",
                    "step.skipped",
                    "step.cancelled",
                }:
                    if current_step == node_id:
                        current_step = None
                        current_stage = None
                continue

            if event.node_type == "stage" and node_id and current_step:
                step = data[current_step]
                stage = step["stage_map"].setdefault(
                    node_id,
                    self._new_stage(event),
                )

                if kind == "stage.started":
                    current_stage = node_id
                    stage["status"] = "RUNNING"
                    stage["started_at"] = event.created_at

                elif kind == "stage.completed":
                    stage["status"] = "COMPLETED"
                    stage["finished_at"] = event.created_at
                    stage["duration_ms"] = self._event_duration(event)

                elif kind == "stage.failed":
                    stage["status"] = "FAILED"
                    stage["finished_at"] = event.created_at
                    stage["duration_ms"] = self._event_duration(event)

                elif kind == "stage.cancelled":
                    stage["status"] = "CANCELLED"
                    stage["finished_at"] = event.created_at

                elif kind == "message":
                    stage["messages"].append(self._timeline(event))

                if kind in {
                    "stage.completed",
                    "stage.failed",
                    "stage.cancelled",
                } and current_stage == node_id:
                    current_stage = None
                continue

            if event.node_type == "activity" and node_id and current_step:
                step = data[current_step]

                container = (
                    step["stage_map"]
                    .get(current_stage, {})
                    .setdefault("activity_map", {})
                    if current_stage
                    else step["activity_map"]
                )

                activity = container.setdefault(
                    node_id,
                    self._new_activity(event),
                )

                if kind == "activity.started":
                    activity_stage[node_id] = current_stage
                    activity["status"] = "RUNNING"
                    activity["started_at"] = event.created_at

                elif kind == "activity.completed":
                    activity["status"] = "COMPLETED"
                    activity["finished_at"] = event.created_at
                    activity["duration_ms"] = self._event_duration(event)

                elif kind == "activity.failed":
                    activity["status"] = "FAILED"
                    activity["finished_at"] = event.created_at
                    activity["duration_ms"] = self._event_duration(event)

                elif kind == "activity.cancelled":
                    activity["status"] = "CANCELLED"
                    activity["finished_at"] = event.created_at

                elif kind == "message":
                    activity["messages"].append(self._timeline(event))
                continue

            if kind == "message" and current_step:
                data[current_step]["messages"].append(self._timeline(event))
                continue

            if kind == "plugin_result" and current_step:
                result = (event.payload or {}).get("result")
                if isinstance(result, dict):
                    data[current_step]["result"] = result
                    data[current_step]["changed"] = bool(result.get("changed"))
                    if result.get("success") is False:
                        data[current_step]["status"] = "FAILED"

        reports: list[StepReport] = []
        for item in data.values():
            stages = [
                self._to_stage_report(stage)
                for stage in item["stage_map"].values()
            ]
            activities = [
                self._to_activity_report(activity)
                for activity in item["activity_map"].values()
            ]

            reports.append(
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
                    stages=stages,
                    activities=activities,
                    messages=item["messages"],
                    result=item["result"],
                )
            )

        return sorted(
            reports,
            key=lambda step: (
                step.index if step.index is not None else 999999,
                step.started_at or datetime.min,
            ),
        )

    @staticmethod
    def _new_step(event: WorkflowEvent) -> dict[str, Any]:
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
            "messages": [],
            "activity_map": {},
            "stage_map": {},
            "result": None,
        }

    @staticmethod
    def _new_stage(event: WorkflowEvent) -> dict[str, Any]:
        return {
            "name": event.node_name or "Workflow stage",
            "node_id": event.node_id,
            "status": "UNKNOWN",
            "started_at": None,
            "finished_at": None,
            "duration_ms": None,
            "messages": [],
            "activity_map": {},
        }

    @staticmethod
    def _new_activity(event: WorkflowEvent) -> dict[str, Any]:
        return {
            "name": event.node_name or "Workflow activity",
            "node_id": event.node_id,
            "status": "UNKNOWN",
            "started_at": None,
            "finished_at": None,
            "duration_ms": None,
            "messages": [],
        }

    def _to_stage_report(self, stage: dict[str, Any]) -> StageReport:
        return StageReport(
            name=stage["name"],
            node_id=stage["node_id"],
            status=stage["status"],
            started_at=stage["started_at"],
            finished_at=stage["finished_at"],
            duration_ms=stage["duration_ms"],
            activities=[
                self._to_activity_report(activity)
                for activity in stage["activity_map"].values()
            ],
            messages=stage["messages"],
        )

    @staticmethod
    def _to_activity_report(activity: dict[str, Any]) -> ActivityReport:
        return ActivityReport(
            name=activity["name"],
            node_id=activity["node_id"],
            status=activity["status"],
            started_at=activity["started_at"],
            finished_at=activity["finished_at"],
            duration_ms=activity["duration_ms"],
            messages=activity["messages"],
        )

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------

    def _build_summary(
        self,
        *,
        job: WorkflowJob,
        steps: list[StepReport],
        selected_steps: int,
    ) -> ReportSummary:
        durations = [
            (step.name, step.duration_ms)
            for step in steps
            if step.duration_ms is not None
        ]

        successful = sum(step.status == "COMPLETED" for step in steps)
        failed = sum(step.status == "FAILED" for step in steps)
        skipped = sum(step.status == "SKIPPED" for step in steps)
        changed = sum(step.changed for step in steps)

        warnings = sum(self._has_level(step, "WARNING") for step in steps)
        errors = sum(self._has_level(step, "ERROR") for step in steps)

        total = sum(duration for _, duration in durations)
        average = int(total / len(durations)) if durations else 0
        slowest = max(durations, key=lambda item: item[1]) if durations else (None, 0)

        execution_duration = self._duration(job.started_at, job.finished_at)

        return ReportSummary(
            total_steps=len(steps),
            successful_steps=successful,
            failed_steps=failed,
            skipped_steps=skipped,
            changed_steps=changed,
            unchanged_steps=sum(
                step.status == "COMPLETED" and not step.changed
                for step in steps
            ),
            warning_steps=warnings,
            error_steps=errors,
            total_duration_ms=execution_duration or total,
            average_step_duration_ms=average,
            slowest_step=slowest[0],
            slowest_step_duration_ms=slowest[1] or 0,
        )

    def _has_level(self, step: StepReport, wanted: str) -> bool:
        messages = list(step.messages)
        for stage in step.stages:
            messages.extend(stage.messages)
            for activity in stage.activities:
                messages.extend(activity.messages)
        for activity in step.activities:
            messages.extend(activity.messages)

        return any(self._level(message.level) == wanted for message in messages)

    @staticmethod
    def _level(level: str | None) -> str:
        value = str(level or "").upper()
        return {
            "10": "DEBUG",
            "20": "INFO",
            "30": "WARNING",
            "40": "ERROR",
            "50": "CRITICAL",
        }.get(value, value)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _metadata(event: WorkflowEvent) -> dict[str, Any]:
        payload = event.payload or {}
        metadata = payload.get("metadata")
        return metadata if isinstance(metadata, dict) else {}

    @staticmethod
    def _event_duration(event: WorkflowEvent) -> int | None:
        duration = (event.payload or {}).get("duration_ms")
        return duration if isinstance(duration, int) else None

    @staticmethod
    def _duration(
        started_at: datetime | None,
        finished_at: datetime | None,
    ) -> int | None:
        if not started_at or not finished_at:
            return None
        return int((finished_at - started_at).total_seconds() * 1000)

    @staticmethod
    def _event_sort_key(event: WorkflowEvent) -> tuple:
        return (event.created_at or datetime.min, event.id or 0)

    @staticmethod
    def _timeline(event: WorkflowEvent) -> ReportTimelineEvent:
        return ReportTimelineEvent(
            timestamp=event.created_at,
            event_type=event.event_type,
            message=event.message,
            node_type=event.node_type,
            node_id=event.node_id,
            node_name=event.node_name,
            duration_ms=ReportBuilder._event_duration(event),
            level=event.level,
            payload=event.payload or {},
        )

    @staticmethod
    def _first_event(
        events: list[WorkflowEvent],
        event_type: str,
    ) -> WorkflowEvent | None:
        return next((event for event in events if event.event_type == event_type), None)

    @staticmethod
    def _last_event(
        events: list[WorkflowEvent],
        event_types: set[str],
    ) -> WorkflowEvent | None:
        for event in reversed(events):
            if event.event_type in event_types:
                return event
        return None

    @staticmethod
    def _selected_step_count(events: list[WorkflowEvent]) -> int:
        totals = []
        for event in events:
            if event.event_type != "step.started":
                continue
            total = ReportBuilder._metadata(event).get("total")
            if isinstance(total, int):
                totals.append(total)
        return max(totals, default=0)

    @staticmethod
    def _execution_status(
        job: WorkflowJob,
        events: list[WorkflowEvent],
    ) -> str:
        state = str(job.state.value).upper()
        if state not in {"COMPLETED", "FAILED", "CANCELLED"}:
            terminal = ReportBuilder._last_event(
                events,
                {"execution.completed", "execution.failed", "execution.cancelled"},
            )
            if terminal:
                state = terminal.event_type.rsplit(".", 1)[-1].upper()
        return state
