import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
    AlertCircle,
    ArrowLeft,
    Ban,
    Blocks,
    CheckCircle2,
    ChevronDown,
    CircleDashed,
    LayoutGrid,
    Network,
    LoaderCircle,
    RotateCcw,
    ScrollText,
    SkipForward,
    Square,
    Terminal,
    Workflow as WorkflowIcon,
    XCircle,
} from 'lucide-react'

import {
    runsApi,
    type PlannedStep,
    type Run,
    type RunEvent,
    type RunStep,
} from '../../api/runs.api'
import { useFeedback } from '../../components/feedback/FeedbackProvider'
import RunDiagram from './RunDiagram'
import RunOptionsSummary from './RunOptionsSummary'
import RunStatus from './RunStatus'
import StartRunDialog from './StartRunDialog'
import {
    TRIGGER_LABELS,
    errorMessage,
    formatDateTime,
    formatDuration,
    formatTime,
    isActive,
    levelName,
    runDuration,
    runnerName,
} from './format'

const POLL_MS = 1000

type View = 'progress' | 'diagram' | 'log'
type LogSource = 'events' | 'output'
type CardStatus = 'pending' | 'running' | 'completed' | 'failed' | 'skipped' | 'cancelled'

interface StepCard {
    key: string
    index: number
    name: string
    plugin: string
    tags: string[]
    node: string | null
    status: CardStatus
    startedAt: string | null
    durationMs: number | null
    events: RunEvent[]
    result: Record<string, unknown> | null
    error: string | null
}

const CARD_ICONS = {
    pending: CircleDashed,
    running: LoaderCircle,
    completed: CheckCircle2,
    failed: XCircle,
    skipped: SkipForward,
    cancelled: Ban,
} as const

const CARD_LABELS: Record<CardStatus, string> = {
    pending: 'Pending',
    running: 'Running',
    completed: 'Completed',
    failed: 'Failed',
    skipped: 'Skipped',
    cancelled: 'Cancelled',
}

function payloadMetadata(event: RunEvent): Record<string, unknown> {
    const metadata = event.payload?.metadata
    return metadata && typeof metadata === 'object' ? (metadata as Record<string, unknown>) : {}
}

/** Messages and results belong to the step that was running when they arrived. */
function eventsByStep(events: RunEvent[]): Map<string, RunEvent[]> {
    const groups = new Map<string, RunEvent[]>()
    let current: string | null = null

    for (const event of events) {
        let key: string | null = null

        if (event.node_type === 'step') {
            key = event.node_name
            if (event.type === 'step.started') current = event.node_name
        } else if (event.node_type !== 'workflow') {
            key = current
        }

        if (key) {
            const list = groups.get(key) ?? []
            list.push(event)
            groups.set(key, list)
        }

        if (event.node_type === 'step' && event.type !== 'step.started' && event.type.startsWith('step.')) {
            current = null
        }
    }

    return groups
}

function buildCards(
    plan: PlannedStep[],
    steps: RunStep[],
    grouped: Map<string, RunEvent[]>,
    run: Run,
): StepCard[] {
    const byName = new Map(steps.map((step) => [step.name, step]))
    // Runs that recorded their plan list the steps they selected.
    const names = [
        ...plan.filter((step) => step.selected ?? step.enabled).map((step) => step.name),
        ...steps.map((step) => step.name).filter((name) => !plan.some((step) => step.name === name)),
    ]
    const pluginOf = new Map(plan.map((step) => [step.name, step.plugin]))
    const planned = new Map(plan.map((step) => [step.name, step]))

    return names.map((name, index) => {
        const step = byName.get(name)
        const events = grouped.get(name) ?? []
        let status: CardStatus = 'pending'

        if (step) {
            status =
                step.status === 'started'
                    ? isActive(run.state)
                        ? 'running'
                        : run.state === 'cancelled'
                          ? 'cancelled'
                          : 'failed'
                    : step.status === 'completed' || step.status === 'failed' || step.status === 'skipped'
                      ? step.status
                      : 'running'
        } else if (!isActive(run.state)) {
            status = run.state === 'completed' ? 'skipped' : 'cancelled'
        }

        // A stopped run reports its interrupted step as failed.
        if (run.state === 'cancelled' && status === 'failed') status = 'cancelled'


        const resultEvent = events.find((event) => event.type === 'plugin_result')
        const failure = events.find((event) => event.type === 'step.failed')
        const startEvent = events.find((event) => event.type === 'step.started')

        return {
            key: step?.id ?? name,
            index: index + 1,
            name,
            plugin:
                pluginOf.get(name) ??
                String((startEvent && payloadMetadata(startEvent).plugin) || ''),
            tags: planned.get(name)?.tags ?? [],
            node: planned.get(name)?.node ?? null,
            status,
            startedAt: step?.started_at ?? null,
            durationMs: step?.duration_ms ?? null,
            events,
            result: (resultEvent?.payload?.result as Record<string, unknown> | undefined) ?? null,
            error:
                failure && status === 'failed' ? String(payloadMetadata(failure).exception ?? '') || null : null,
        }
    })
}

function eventText(event: RunEvent): string {
    if (event.message) return event.message

    const metadata = payloadMetadata(event)
    const duration =
        typeof event.payload?.duration_ms === 'number' ? ` in ${formatDuration(event.payload.duration_ms)}` : ''
    const subject = event.node_name ?? ''

    switch (event.type) {
        case 'execution.started':
            return `Run started: ${subject}`
        case 'execution.completed':
            return `Run completed${duration}`
        case 'execution.failed':
            return `Run failed${duration}${metadata.exception ? `: ${String(metadata.exception)}` : ''}`
        case 'execution.cancelled':
            return 'Run cancelled'
        case 'step.started':
            return `Step '${subject}' started (${String(metadata.plugin ?? '')})`
        case 'step.completed':
            return `Step '${subject}' completed${duration}`
        case 'step.failed':
            return `Step '${subject}' failed${duration}${metadata.exception ? `: ${String(metadata.exception)}` : ''}`
        case 'step.skipped':
            return `Step '${subject}' skipped`
        case 'activity.started':
            return `${subject}…`
        case 'activity.completed':
            return `${subject} done${duration}`
        case 'activity.failed':
            return `${subject} failed${metadata.exception ? `: ${String(metadata.exception)}` : ''}`
        case 'plugin_result': {
            const result = (event.payload?.result ?? {}) as Record<string, unknown>
            return `Result: ${result.success === false ? 'unsuccessful' : 'success'}${
                result.outputs ? ` · outputs ${JSON.stringify(result.outputs)}` : ''
            }`
        }
        case 'render': {
            const payload = (event.payload ?? {}) as Record<string, unknown>
            const title = payload.title ? `${String(payload.title)}\n` : ''
            if (Array.isArray(payload.lines)) return title + payload.lines.map(String).join('\n')
            if (Array.isArray(payload.rows)) {
                const columns = Array.isArray(payload.columns) ? payload.columns.map(String) : []
                const rows = (payload.rows as unknown[][]).map((row) => row.map(String).join('  ·  '))
                return title + [columns.join('  ·  '), ...rows].filter(Boolean).join('\n')
            }
            return title.trim() || 'Output'
        }
        default:
            return event.type
    }
}

function eventTone(event: RunEvent): string {
    if (event.type.endsWith('.failed')) return 'error'
    if (event.type.endsWith('.completed')) return 'success'
    if (event.type === 'message') return levelName(event.level)
    return 'meta'
}

export default function RunDetail({ runId, onBack }: { runId: number; onBack: () => void }) {
    const { notify, modal } = useFeedback()

    const [run, setRun] = useState<Run | null>(null)
    const [plan, setPlan] = useState<PlannedStep[]>([])
    const [steps, setSteps] = useState<RunStep[]>([])
    const [events, setEvents] = useState<RunEvent[]>([])
    const [output, setOutput] = useState('')
    const [error, setError] = useState<string | null>(null)
    const [view, setView] = useState<View>('progress')
    const [source, setSource] = useState<LogSource>('events')
    const [follow, setFollow] = useState(true)
    const [debugShown, setDebugShown] = useState(false)
    const [expanded, setExpanded] = useState<string | null>(null)
    const [stopping, setStopping] = useState(false)
    const [rerunOpen, setRerunOpen] = useState(false)
    const [now, setNow] = useState(() => Date.now())

    const cursor = useRef<number | null>(null)
    const outputOffset = useRef(0)
    const logRef = useRef<HTMLDivElement>(null)

    // Load the run, then follow events and worker output until it ends.
    useEffect(() => {
        let active = true
        let timer: ReturnType<typeof setTimeout> | undefined
        cursor.current = null
        outputOffset.current = 0

        const poll = async () => {
            try {
                const [update, log] = await Promise.all([
                    runsApi.events(runId, cursor.current),
                    runsApi.log(runId, outputOffset.current),
                ])
                if (!active) return

                cursor.current = update.cursor
                outputOffset.current = log.offset
                setRun(update.run)
                setSteps(update.steps)
                if (update.events.length) setEvents((previous) => [...previous, ...update.events])
                if (log.text) setOutput((previous) => previous + log.text)
                setError(null)

                // Keep reading after the end until every event has arrived.
                const finished = !isActive(update.run.state)
                if (!finished || update.events.length >= 1000) {
                    timer = setTimeout(() => void poll(), POLL_MS)
                }
            } catch (cause) {
                if (!active) return
                setError(errorMessage(cause, 'Unable to follow this run.'))
                timer = setTimeout(() => void poll(), POLL_MS * 3)
            }
        }

        runsApi
            .get(runId)
            .then((detail) => {
                if (!active) return
                setRun(detail.run)
                setPlan(detail.plan)
                setSteps(detail.steps)
                setEvents([])
                setOutput('')
                void poll()
            })
            .catch((cause: unknown) => {
                if (active) setError(errorMessage(cause, 'Unable to load this run.'))
            })

        return () => {
            active = false
            if (timer) clearTimeout(timer)
        }
    }, [runId])

    const running = run ? isActive(run.state) : false

    useEffect(() => {
        if (!running) return
        const timer = setInterval(() => setNow(Date.now()), 1000)
        return () => clearInterval(timer)
    }, [running])

    // Stick to the newest line while following.
    useEffect(() => {
        if (follow && view === 'log' && logRef.current) {
            logRef.current.scrollTop = logRef.current.scrollHeight
        }
    }, [events, output, follow, view, source])

    // Debug messages are kept for every run; shown for debug runs or on request.
    const showDebug = debugShown || Boolean(run?.debug)
    const shown = useMemo(
        () =>
            showDebug
                ? events
                : events.filter((event) => !(event.type === 'message' && levelName(event.level) === 'debug')),
        [events, showDebug],
    )
    const grouped = useMemo(() => eventsByStep(shown), [shown])
    const cards = useMemo(
        () => (run ? buildCards(plan, steps, grouped, run) : []),
        [grouped, plan, run, steps],
    )
    const done = cards.filter((card) => card.status === 'completed' || card.status === 'skipped').length
    const multiNode = (run?.options?.nodes?.length ?? 1) > 1
    const progress = cards.length ? Math.round((done / cards.length) * 100) : 0
    const runFailure =
        run?.state === 'failed' ? events.find((event) => event.type === 'execution.failed') : undefined

    const stop = useCallback(async () => {
        if (!run) return
        const confirmed = await modal.confirm({
            title: `Stop run #${run.id}?`,
            message: 'The step in progress is cancelled and later steps do not run.',
            confirmText: 'Stop run',
            cancelText: 'Keep running',
            destructive: true,
        })
        if (!confirmed) return

        setStopping(true)
        try {
            await runsApi.stop(run.id)
            notify.info('Stop requested. The run ends after the current activity.', { title: 'Stopping' })
        } catch (cause) {
            notify.error(errorMessage(cause, 'Unable to stop the run.'), { title: 'Stop failed' })
        } finally {
            setStopping(false)
        }
    }, [modal, notify, run])

    if (!run) {
        return (
            <section className="list-page run-detail">
                <button type="button" className="entropy-button entropy-button-ghost run-back" onClick={onBack}>
                    <ArrowLeft size={16} /> Runs
                </button>
                {error ? (
                    <div className="entropy-alert entropy-alert-error" role="alert">
                        <AlertCircle size={16} />
                        <span>{error}</span>
                    </div>
                ) : (
                    <div className="list-empty" role="status">
                        <LoaderCircle size={18} className="entropy-spin" />
                        Loading run #{runId}…
                    </div>
                )}
            </section>
        )
    }

    return (
        <section className="list-page run-detail">
            <header className="dashboard-section run-header">
                <div className="run-header-top">
                    <button
                        type="button"
                        className="entropy-button entropy-button-secondary entropy-button-icon"
                        aria-label="Back to runs"
                        title="Back to runs"
                        onClick={onBack}
                    >
                        <ArrowLeft size={16} />
                    </button>
                    <span className="list-name-icon run-header-icon" aria-hidden="true">
                        {run.kind === 'plugin' ? <Blocks size={18} /> : <WorkflowIcon size={18} />}
                    </span>
                    <div className="run-title">
                        <h2>{run.target}</h2>
                        <p>
                            Run #{run.id} · {run.kind === 'plugin' ? 'Plugin test run' : 'Workflow'} ·{' '}
                            {run.execution_id}
                        </p>
                    </div>
                    <RunStatus state={run.state} />
                    {run.kind === 'workflow' &&
                        (run.state === 'completed' || run.state === 'failed' || run.state === 'cancelled') && (
                            <button
                                type="button"
                                className="entropy-button entropy-button-secondary"
                                onClick={() => setRerunOpen(true)}
                            >
                                <RotateCcw size={15} /> Run again
                            </button>
                        )}
                    {running && (
                        <button
                            type="button"
                            className="entropy-button entropy-button-danger"
                            onClick={() => void stop()}
                            disabled={stopping}
                        >
                            {stopping ? <LoaderCircle size={15} className="entropy-spin" /> : <Square size={14} />}
                            Stop
                        </button>
                    )}
                </div>

                <dl className="run-meta">
                    <div>
                        <dt>Executed by</dt>
                        <dd>{runnerName(run)}</dd>
                    </div>
                    <div>
                        <dt>Trigger</dt>
                        <dd>{TRIGGER_LABELS[run.trigger] ?? run.trigger}</dd>
                    </div>
                    <div>
                        <dt>{(run.options?.nodes?.length ?? 1) > 1 ? 'Nodes' : 'Node'}</dt>
                        <dd title={run.options?.nodes?.join(', ')}>
                            {(run.options?.nodes?.length ?? 1) > 1 ? run.options?.nodes?.join(', ') : run.node}
                        </dd>
                    </div>
                    <div>
                        <dt>Started</dt>
                        <dd>{formatDateTime(run.started_at ?? run.created_at)}</dd>
                    </div>
                    <div>
                        <dt>Duration</dt>
                        <dd>{formatDuration(runDuration(run, now))}</dd>
                    </div>
                    <div>
                        <dt>Steps</dt>
                        <dd>
                            {done} / {cards.length}
                        </dd>
                    </div>
                </dl>

                {run.options?.nodes && <RunOptionsSummary options={run.options} />}

                <div
                    className={`run-progress is-${run.state}`}
                    role="progressbar"
                    aria-valuemin={0}
                    aria-valuemax={100}
                    aria-valuenow={progress}
                    aria-label="Run progress"
                >
                    <span style={{ width: `${run.state === 'completed' ? 100 : progress}%` }} />
                </div>

                {run.state === 'cancelled' && (
                    <div className="entropy-alert entropy-alert-warning" role="status">
                        <Ban size={16} />
                        <span>
                            Stopped
                            {run.finished_at ? ` at ${formatDateTime(run.finished_at)}` : ''}. Steps after the
                            interrupted one did not run.
                        </span>
                    </div>
                )}
                {runFailure && (
                    <div className="entropy-alert entropy-alert-error" role="alert">
                        <AlertCircle size={16} />
                        <span>{eventText(runFailure)}</span>
                    </div>
                )}
                {error && (
                    <div className="entropy-alert entropy-alert-error" role="alert">
                        <AlertCircle size={16} />
                        <span>{error}</span>
                    </div>
                )}
            </header>

            <section className="dashboard-section run-body">
                <div className="run-body-toolbar">
                    <div className="seg-control" role="tablist" aria-label="Run view">
                        <button
                            type="button"
                            role="tab"
                            aria-selected={view === 'progress'}
                            className={view === 'progress' ? 'is-active' : ''}
                            onClick={() => setView('progress')}
                        >
                            <LayoutGrid size={13} /> Progress
                        </button>
                        <button
                            type="button"
                            role="tab"
                            aria-selected={view === 'diagram'}
                            className={view === 'diagram' ? 'is-active' : ''}
                            onClick={() => setView('diagram')}
                        >
                            <Network size={13} /> Diagram
                        </button>
                        <button
                            type="button"
                            role="tab"
                            aria-selected={view === 'log'}
                            className={view === 'log' ? 'is-active' : ''}
                            onClick={() => setView('log')}
                        >
                            <ScrollText size={13} /> Live log
                        </button>
                    </div>

                    {view === 'log' && (
                        <div className="run-log-options">
                            <div className="seg-control" role="tablist" aria-label="Log source">
                                <button
                                    type="button"
                                    role="tab"
                                    aria-selected={source === 'events'}
                                    className={source === 'events' ? 'is-active' : ''}
                                    onClick={() => setSource('events')}
                                >
                                    Steps
                                </button>
                                <button
                                    type="button"
                                    role="tab"
                                    aria-selected={source === 'output'}
                                    className={source === 'output' ? 'is-active' : ''}
                                    onClick={() => setSource('output')}
                                >
                                    <Terminal size={13} /> Console
                                </button>
                            </div>
                            <label className="run-follow">
                                <input
                                    type="checkbox"
                                    checked={follow}
                                    onChange={(event) => setFollow(event.target.checked)}
                                />
                                Follow
                            </label>
                            <label className="run-follow" title="Messages plugins log at debug level">
                                <input
                                    type="checkbox"
                                    checked={showDebug}
                                    disabled={Boolean(run.debug)}
                                    onChange={(event) => setDebugShown(event.target.checked)}
                                />
                                Debug messages
                            </label>
                        </div>
                    )}
                </div>

                {view === 'diagram' ? (
                    <RunDiagram
                        workflow={run.target}
                        plan={
                            plan.length
                                ? plan
                                : cards.map((card) => ({ name: card.name, plugin: card.plugin, enabled: true }))
                        }
                        statuses={Object.fromEntries(cards.map((card) => [card.name, card.status]))}
                        onSelect={(name) => {
                            const card = cards.find((item) => item.name === name)
                            setView('progress')
                            if (card) setExpanded(card.key)
                        }}
                    />
                ) : view === 'progress' ? (
                    <ol className="run-cards">
                        {cards.length === 0 && (
                            <li className="list-empty">
                                <CircleDashed size={20} />
                                <strong>No steps reported yet</strong>
                            </li>
                        )}
                        {cards.map((card) => {
                            const Icon = CARD_ICONS[card.status]
                            const messages = card.events.filter((event) => event.type === 'message')
                            const last = messages[messages.length - 1]
                            const open = expanded === card.key
                            const duration =
                                card.status === 'running' && card.startedAt
                                    ? now - new Date(card.startedAt).getTime()
                                    : card.durationMs

                            return (
                                <li key={card.key} className={`run-card is-${card.status}`}>
                                    <button
                                        type="button"
                                        className="run-card-head"
                                        aria-expanded={open}
                                        onClick={() => setExpanded(open ? null : card.key)}
                                    >
                                        <span className="run-card-index">{card.index}</span>
                                        <span className="run-card-icon" aria-hidden="true">
                                            <Icon
                                                size={18}
                                                className={card.status === 'running' ? 'entropy-spin' : undefined}
                                            />
                                        </span>
                                        <span className="run-card-title">
                                            <strong>{card.name}</strong>
                                            <span>
                                                {card.plugin}
                                                {multiNode && card.node ? ` · on ${card.node}` : ''}
                                            </span>
                                        </span>
                                        {card.tags.length > 0 && (
                                            <span className="run-card-tags">
                                                {card.tags.map((tag) => (
                                                    <span key={tag} className="run-tag">
                                                        {tag}
                                                    </span>
                                                ))}
                                            </span>
                                        )}
                                        <span className="run-card-state">
                                            {CARD_LABELS[card.status]}
                                            {duration !== null && card.status !== 'pending' && (
                                                <small>{formatDuration(duration)}</small>
                                            )}
                                        </span>
                                        <ChevronDown size={16} className="run-card-chevron" aria-hidden="true" />
                                    </button>

                                    {card.status === 'running' && <span className="run-card-bar" aria-hidden="true" />}

                                    {!open && (card.error || last) && (
                                        <p className={`run-card-last is-${card.error ? 'error' : levelName(last?.level ?? null)}`}>
                                            {card.error ?? last?.message}
                                        </p>
                                    )}

                                    {open && (
                                        <div className="run-card-body">
                                            {card.events.length === 0 ? (
                                                <p className="run-card-muted">Nothing reported yet.</p>
                                            ) : (
                                                <ul className="run-lines">
                                                    {card.events.map((event) => (
                                                        <li key={event.id} className={`is-${eventTone(event)}`}>
                                                            <time>{formatTime(event.created_at)}</time>
                                                            <span>{eventText(event)}</span>
                                                        </li>
                                                    ))}
                                                </ul>
                                            )}
                                            {card.result && (
                                                <pre className="run-result">{JSON.stringify(card.result, null, 2)}</pre>
                                            )}
                                        </div>
                                    )}
                                </li>
                            )
                        })}
                    </ol>
                ) : (
                    <div className="run-log" ref={logRef} aria-live="off">
                        {source === 'output' ? (
                            output ? (
                                <pre>{output}</pre>
                            ) : (
                                <p className="run-card-muted">The worker has not written any console output.</p>
                            )
                        ) : shown.length === 0 ? (
                            <p className="run-card-muted">Waiting for the first event…</p>
                        ) : (
                            <ul className="run-lines">
                                {shown.map((event) => {
                                    const step = event.node_type === 'step' ? event.node_name : null
                                    return (
                                        <li key={event.id} className={`is-${eventTone(event)}`}>
                                            <time>{formatTime(event.created_at)}</time>
                                            {step && <em>{step}</em>}
                                            <span>{eventText(event)}</span>
                                        </li>
                                    )
                                })}
                                {running && (
                                    <li className="is-meta run-cursor" aria-hidden="true">
                                        <span />
                                    </li>
                                )}
                            </ul>
                        )}
                    </div>
                )}
            </section>
            {rerunOpen && (
                <StartRunDialog
                    kind="workflow"
                    target={run.workflow}
                    rerunFrom={run.id}
                    onClose={() => setRerunOpen(false)}
                />
            )}
        </section>
    )
}
