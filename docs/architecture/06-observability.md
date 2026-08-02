
# Observability

Version: 1.0

Status: Draft

---

# Purpose

Observability is responsible for collecting, processing, and presenting execution
information produced by the Entropy runtime.

Observability never executes business logic.
Observability never controls workflow execution.
Its responsibility is to observe runtime behavior.

---

# Design Goals

The subsystem provides:

- Console output
- Execution logs
- Reports
- Metrics
- Support bundles
- Future telemetry

without coupling itself to the execution engine.

---

# Core Principles

## 1. Events are the Source of Truth

Everything begins as an event.

```text
Plugin
    ↓
Execution Context
    ↓
Event
    ↓
Observability
```

## 2. Producers Don't Know Consumers

```text
Execution
    ↓
Publish(Event)
    ↓
Dispatcher
    ↓
Subscribers
```

The runtime publishes events without knowing who consumes them.

## 3. Everything is a Sink

- Console
- File Logs
- Reports
- Metrics
- Support Bundle

Each output is implemented as an independent sink.

---

# Architecture

```text
                    Workflow Execution
                            │
                            ▼
                    Event Publisher
                            │
                            ▼
                  +------------------+
                  | Event Dispatcher |
                  +------------------+
      ┌────────────┼────────────┬────────────┬────────────┐
      ▼            ▼            ▼            ▼            ▼
 ConsoleSink   FileSink   ReportSink   MetricSink   SupportSink
```

---

# Event Model

```python
@dataclass(frozen=True)
class Event:
    id: UUID
    timestamp: datetime
    execution_id: str
    source: str
    type: EventType
    level: LogLevel
    message: str
    payload: dict
```

## Event Types

- ExecutionStarted
- ExecutionCompleted
- ExecutionFailed
- ValidationStarted
- ValidationCompleted
- StepStarted
- StepCompleted
- PluginStarted
- PluginCompleted
- ArtifactCreated
- Warning
- Error
- Metric

---

# Event Dispatcher

Responsibilities

- Register sinks
- Publish events
- Preserve event order
- Isolate sink failures

Example

```python
dispatcher.subscribe(ConsoleSink())
dispatcher.subscribe(FileSink())
dispatcher.subscribe(HtmlReportSink())

dispatcher.publish(event)
```

---

# Sink Contract

```python
class Sink:

    def consume(self, event: Event):
        raise NotImplementedError
```

Every sink implements exactly one responsibility.

---

# Console Sink

Responsibilities

- Render execution progress
- Display colors and icons
- Render tables
- Display summaries

Does **not** write logs or generate reports.

---

# File Sink

Writes execution events into execution-scoped log files.

Example:

```text
workflow.log
validation.log
sqlplus.log
shell.log
error.log
```

---

# Report Sink

Consumes

- Events
- Execution Metadata
- Artifacts

Produces

- HTML
- JSON
- Markdown

Reports are generated entirely from events.

---

# Metric Sink

Generates metrics such as

- Execution duration
- Step duration
- Plugin duration
- Failure count
- Warning count

---

# Support Sink

Produces a diagnostic bundle containing

- Events
- Metadata
- Logs
- Reports
- Artifacts
- Configuration snapshot

---

# Logger Factory

Loggers are created dynamically.

```python
execution.logger.info(...)

sql_logger = execution.logger.get("sqlplus")
shell_logger = execution.logger.get("shell")
git_logger = execution.logger.get("git")
```

No static logging categories are required.

---

# Execution Logger

Each Workflow Execution owns one LoggerFactory.

Plugins receive loggers through the ExecutionContext.

---

# Module Structure

```text
observability/
│
├── observability.py
├── dispatcher.py
├── event.py
├── sink.py
│
├── logger/
│   ├── factory.py
│   └── logger.py
│
├── console/
│   ├── sink.py
│   ├── renderer.py
│   └── progress.py
│
├── logging/
│   ├── sink.py
│   └── rotation.py
│
├── reporting/
│   ├── sink.py
│   ├── html.py
│   └── json.py
│
├── metrics/
│   └── sink.py
│
└── support/
    └── sink.py
```

---

# Responsibilities

| Component | Responsibility |
|-----------|----------------|
| Event | Immutable runtime record |
| Dispatcher | Publish events |
| Sink | Consume events |
| Console Sink | Terminal rendering |
| File Sink | Persistent logs |
| Report Sink | Report generation |
| Metric Sink | Metrics collection |
| Support Sink | Diagnostic bundles |

---

# Future Enhancements

- OpenTelemetry exporter
- Prometheus metrics
- Grafana dashboards
- WebSocket live event streaming
- REST event API
- Remote execution monitoring

---

# Architectural Rule

> Observability observes.

It never executes workflows.
It never modifies execution state.
It never makes orchestration decisions.

It consumes events and transforms them into useful outputs.
