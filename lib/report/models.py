from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass(frozen=True)
class ReportTimelineEvent:
    timestamp: datetime | None
    event_type: str
    message: str | None = None
    node_type: str | None = None
    node_id: str | None = None
    node_name: str | None = None
    duration_ms: int | None = None
    level: str | None = None
    payload: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ActivityReport:
    name: str
    node_id: str | None
    status: str
    started_at: datetime | None = None
    finished_at: datetime | None = None
    duration_ms: int | None = None
    activities: list["ActivityReport"] = field(default_factory=list)
    messages: list[ReportTimelineEvent] = field(default_factory=list)


@dataclass(frozen=True)
class StageReport:
    name: str
    node_id: str | None
    status: str
    started_at: datetime | None = None
    finished_at: datetime | None = None
    duration_ms: int | None = None
    activities: list[ActivityReport] = field(default_factory=list)
    messages: list[ReportTimelineEvent] = field(default_factory=list)


@dataclass(frozen=True)
class StepReport:
    name: str
    plugin: str
    node_id: str | None
    status: str
    index: int | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    duration_ms: int | None = None
    changed: bool = False
    stages: list[StageReport] = field(default_factory=list)
    activities: list[ActivityReport] = field(default_factory=list)
    messages: list[ReportTimelineEvent] = field(default_factory=list)
    result: dict[str, Any] | None = None
    failure: dict[str, Any] | None = None


@dataclass(frozen=True)
class ReportSummary:
    total_steps: int = 0
    successful_steps: int = 0
    failed_steps: int = 0
    skipped_steps: int = 0
    changed_steps: int = 0
    unchanged_steps: int = 0
    warning_steps: int = 0
    error_steps: int = 0
    total_duration_ms: int = 0
    average_step_duration_ms: int = 0
    slowest_step: str | None = None
    slowest_step_duration_ms: int = 0


@dataclass(frozen=True)
class ExecutionReport:
    execution_id: str
    workflow: str
    status: str
    started_at: datetime | None = None
    finished_at: datetime | None = None
    duration_ms: int | None = None
    summary: ReportSummary = field(default_factory=ReportSummary)
    steps: list[StepReport] = field(default_factory=list)
    timeline: list[ReportTimelineEvent] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
