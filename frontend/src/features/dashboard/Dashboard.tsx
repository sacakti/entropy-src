
import { useCallback, useEffect, useRef, useState } from 'react'
import {
    Activity,
    AlertCircle,
    ArrowRight,
    Ban,
    CheckCircle2,
    Clock3,
    LoaderCircle,
    PlayCircle,
    RefreshCw,
    Workflow,
    XCircle,
} from 'lucide-react'

import {
    getDashboard,
    type DashboardData,
    type DashboardExecution,
    type WorkflowJobState,
} from '../../api/dashboard.api'
import { openRunsTab } from '../runs/navigation'

const stateLabels: Record<WorkflowJobState, string> = {
    queued: 'Queued',
    starting: 'Starting',
    running: 'Running',
    paused: 'Paused',
    completed: 'Completed',
    failed: 'Failed',
    cancelled: 'Cancelled',
}

function formatDate(value: string | null): string {
    if (!value) return '—'

    const date = new Date(value)

    if (Number.isNaN(date.getTime())) return '—'

    return new Intl.DateTimeFormat(undefined, {
        dateStyle: 'medium',
        timeStyle: 'short',
    }).format(date)
}

function formatDuration(
    startedAt: string | null,
    finishedAt: string | null,
): string {
    if (!startedAt) return 'Not started'

    const start = new Date(startedAt).getTime()
    const end = finishedAt
        ? new Date(finishedAt).getTime()
        : Date.now()

    if (!Number.isFinite(start) || !Number.isFinite(end) || end < start) {
        return '—'
    }

    const seconds = Math.floor((end - start) / 1000)

    if (seconds < 60) return `${seconds}s`

    const minutes = Math.floor(seconds / 60)
    if (minutes < 60) return `${minutes}m ${seconds % 60}s`

    const hours = Math.floor(minutes / 60)
    return `${hours}h ${minutes % 60}m`
}

function StateBadge({ state }: { state: WorkflowJobState }) {
    return (
        <span className={`dashboard-state dashboard-state-${state}`}>
            <span className="dashboard-state-dot" />
            {stateLabels[state]}
        </span>
    )
}

function ExecutionRow({
    execution,
}: {
    execution: DashboardExecution
}) {
    const finished = execution.finished_at !== null

    return (
        <article className="dashboard-execution">
            <span className="dashboard-execution-icon" aria-hidden="true">
                {execution.state === 'failed' ? (
                    <XCircle size={18} />
                ) : execution.state === 'completed' ? (
                    <CheckCircle2 size={18} />
                ) : execution.state === 'cancelled' ? (
                    <Ban size={18} />
                ) : execution.state === 'running' ? (
                    <PlayCircle size={18} />
                ) : (
                    <Workflow size={18} />
                )}
            </span>

            <div className="dashboard-execution-main">
                <strong title={execution.workflow}>
                    {execution.workflow}
                </strong>
                <span>
                    {finished
                        ? `Finished ${formatDate(execution.finished_at)}`
                        : `Created ${formatDate(execution.created_at)}`}
                </span>
            </div>

            <div className="dashboard-execution-meta">
                <StateBadge state={execution.state} />
                <span className="dashboard-execution-duration">
                    {formatDuration(
                        execution.started_at,
                        execution.finished_at,
                    )}
                </span>
            </div>
        </article>
    )
}

function EmptyState({
    title,
    message,
}: {
    title: string
    message: string
}) {
    return (
        <div className="dashboard-empty">
            <Activity size={22} />
            <strong>{title}</strong>
            <p>{message}</p>
        </div>
    )
}

export default function Dashboard() {
    const [data, setData] = useState<DashboardData | null>(null)
    const [loading, setLoading] = useState(true)
    const [refreshing, setRefreshing] = useState(false)
    const [error, setError] = useState<string | null>(null)
    const [refreshMode, setRefreshMode] = useState('2000')
    const [customInterval, setCustomInterval] = useState('10')
    const requestInProgress = useRef(false)


    const parsedCustomInterval = Number(customInterval)

    const validCustomInterval =
        customInterval.trim() !== '' &&
        Number.isInteger(parsedCustomInterval) &&
        parsedCustomInterval >= 1 &&
        parsedCustomInterval <= 86400

    const refreshIntervalMs =
        refreshMode === 'custom'
            ? validCustomInterval
                ? parsedCustomInterval * 1000
                : 0
            : Number(refreshMode)

    const loadDashboard = useCallback(async (manual = false) => {
        if (requestInProgress.current) return

        requestInProgress.current = true

        if (manual) {
            setRefreshing(true)
        } else {
            setLoading(true)
        }

        setError(null)

        try {
            const result = await getDashboard()
            setData(result)
        } catch {
            setError('Unable to load dashboard data. Please try again.')
        } finally {
            setLoading(false)
            setRefreshing(false)
            requestInProgress.current = false
        }
    }, [])

    useEffect(() => {
        void loadDashboard()
    }, [loadDashboard])

    useEffect(() => {
        if (refreshMode === 'off') return

        if (
            !Number.isFinite(refreshIntervalMs) ||
            refreshIntervalMs < 1000
        ) {
            return
        }

        const timer = window.setInterval(() => {
            void loadDashboard(true)
        }, refreshIntervalMs)

        return () => window.clearInterval(timer)
    }, [refreshMode, refreshIntervalMs, loadDashboard])

    const summary = data?.summary

    return (
        <section className="dashboard-page">
            <header className="page-toolbar">
                <div className="dashboard-refresh-controls">
                    {/* <label
                        className="dashboard-refresh-label"
                        htmlFor="dashboard-refresh-mode"
                    >
                        Auto-refresh
                    </label> */}

                    <select
                        id="dashboard-refresh-mode"
                        className="dashboard-refresh-select"
                        value={refreshMode}
                        onChange={(event) => setRefreshMode(event.target.value)}
                    >
                        <option value="2000">Auto (2s)</option>
                        <option value="5000">Every 5 seconds</option>
                        <option value="30000">Every 30 seconds</option>
                        <option value="custom">Custom</option>
                        <option value="off">Off</option>
                    </select>

                    {refreshMode === 'custom' && (
                        <label className="dashboard-custom-interval">
                            <input
                                type="number"
                                min="1"
                                max="86400"
                                step="1"
                                value={customInterval}
                                onChange={(event) =>
                                    setCustomInterval(event.target.value)
                                }
                                aria-label="Custom refresh interval in seconds"
                            />
                            <span>sec</span>
                        </label>
                    )}

                    <button
                        type="button"
                        className="entropy-button entropy-button-secondary"
                        onClick={() => void loadDashboard(true)}
                        disabled={loading || refreshing}
                    >
                        <RefreshCw
                            size={16}
                            className={refreshing ? 'entropy-spin' : ''}
                        />
                        Refresh
                    </button>
                </div>
            </header>

            {error && (
                <div className="dashboard-error" role="alert">
                    <AlertCircle size={18} />
                    <span>{error}</span>
                    <button
                        type="button"
                        className="entropy-button entropy-button-secondary entropy-button-sm"
                        onClick={() => void loadDashboard()}
                    >
                        Retry
                    </button>
                </div>
            )}

            <section
                className="dashboard-summary"
                aria-label="Workflow execution summary"
            >
                <SummaryCard
                    label="Total executions"
                    value={summary?.total}
                    icon={<Activity size={19} />}
                    loading={loading && !data}
                />
                <SummaryCard
                    label="Running"
                    value={summary?.running}
                    icon={<LoaderCircle size={19} />}
                    loading={loading && !data}
                />
                <SummaryCard
                    label="Queued"
                    value={summary?.queued}
                    icon={<Clock3 size={19} />}
                    loading={loading && !data}
                />
                <SummaryCard
                    label="Completed"
                    value={summary?.completed}
                    icon={<CheckCircle2 size={19} />}
                    loading={loading && !data}
                />
                <SummaryCard
                    label="Failed"
                    value={summary?.failed}
                    icon={<XCircle size={19} />}
                    loading={loading && !data}
                />
            </section>

            {loading && !data ? (
                <div className="dashboard-loading" role="status">
                    <LoaderCircle size={22} className="entropy-spin" />
                    <span>Loading workflow activity…</span>
                </div>
            ) : data ? (
                <>
                    <section className="dashboard-section">
                        <div className="dashboard-section-heading">
                            <div>
                                <h2>Active executions</h2>
                                <p>
                                    Workflows that are queued, starting,
                                    running, or paused.
                                </p>
                            </div>
                            <button
                                type="button"
                                className="entropy-button entropy-button-secondary entropy-button-sm"
                                onClick={() => openRunsTab('active')}
                            >
                                View executing runs
                                <ArrowRight size={16} />
                            </button>
                        </div>

                        <div className="dashboard-execution-list">
                            {data.active_executions.length > 0 ? (
                                data.active_executions.map((execution) => (
                                    <ExecutionRow
                                        key={execution.id}
                                        execution={execution}
                                    />
                                ))
                            ) : (
                                <EmptyState
                                    title="No active executions"
                                    message="Workflow executions will appear here when they are queued or started."
                                />
                            )}
                        </div>
                    </section>

                    <section className="dashboard-section">
                        <div className="dashboard-section-heading">
                            <div>
                                <h2>Recent executions</h2>
                                <p>
                                    Latest completed, failed, and cancelled
                                    workflows.
                                </p>
                            </div>
                            <button
                                type="button"
                                className="entropy-button entropy-button-secondary entropy-button-sm"
                                onClick={() => openRunsTab('all')}
                            >
                                View history
                                <ArrowRight size={16} />
                            </button>
                        </div>

                        <div className="dashboard-execution-list">
                            {data.recent_executions.length > 0 ? (
                                data.recent_executions.map((execution) => (
                                    <ExecutionRow
                                        key={execution.id}
                                        execution={execution}
                                    />
                                ))
                            ) : (
                                <EmptyState
                                    title="No execution history"
                                    message="Finished workflow executions will appear here."
                                />
                            )}
                        </div>
                    </section>
                </>
            ) : null}
        </section>
    )
}

function SummaryCard({
    label,
    value,
    icon,
    loading,
}: {
    label: string
    value: number | undefined
    icon: React.ReactNode
    loading: boolean
}) {
    return (
        <article className="dashboard-summary-card">
            <span className="dashboard-summary-icon" aria-hidden="true">
                {icon}
            </span>
            <span className="dashboard-summary-label">{label}</span>
            <strong className="dashboard-summary-value">
                {loading ? '—' : (value ?? 0).toLocaleString()}
            </strong>
        </article>
    )
}
