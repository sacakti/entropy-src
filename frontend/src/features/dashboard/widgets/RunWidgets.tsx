import { Activity, Ban, CheckCircle2, Clock3, LoaderCircle, PlayCircle, Workflow, XCircle } from 'lucide-react'

import { getDashboard, type DashboardData, type DashboardExecution, type WorkflowJobState } from '../../../api/dashboard.api'
import { openRun } from '../../runs/navigation'
import { formatWhen, limitOf, sharedRequest, useWidgetData, type WidgetProps } from './core'
import { WidgetBody, WidgetEmpty } from './WidgetBody'

const stateLabels: Record<WorkflowJobState, string> = {
    queued: 'Queued',
    starting: 'Starting',
    running: 'Running',
    paused: 'Paused',
    completed: 'Completed',
    failed: 'Failed',
    cancelled: 'Cancelled',
}

/** The run widgets share one request per refresh. */
function useRuns(props: WidgetProps) {
    return useWidgetData<DashboardData>(() => sharedRequest('runs', getDashboard), props)
}

function duration(startedAt: string | null, finishedAt: string | null): string {
    if (!startedAt) return 'Not started'
    const start = new Date(startedAt).getTime()
    const end = finishedAt ? new Date(finishedAt).getTime() : Date.now()
    if (!Number.isFinite(start) || !Number.isFinite(end) || end < start) return '—'
    const seconds = Math.floor((end - start) / 1000)
    if (seconds < 60) return `${seconds}s`
    const minutes = Math.floor(seconds / 60)
    if (minutes < 60) return `${minutes}m ${seconds % 60}s`
    return `${Math.floor(minutes / 60)}h ${minutes % 60}m`
}

function ExecutionRow({ execution }: { execution: DashboardExecution }) {
    const finished = execution.finished_at !== null
    return (
        <button type="button" className="dashboard-execution" onClick={() => openRun(execution.id)} title="Open the run">
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
            <span className="dashboard-execution-main">
                <strong title={execution.workflow}>{execution.workflow}</strong>
                <span>{finished ? `Finished ${formatWhen(execution.finished_at)}` : `Created ${formatWhen(execution.created_at)}`}</span>
            </span>
            <span className="dashboard-execution-meta">
                <span className={`dashboard-state dashboard-state-${execution.state}`}>
                    <span className="dashboard-state-dot" />
                    {stateLabels[execution.state]}
                </span>
                <span className="dashboard-execution-duration">{duration(execution.started_at, execution.finished_at)}</span>
            </span>
        </button>
    )
}

export function RunSummaryWidget(props: WidgetProps) {
    const state = useRuns(props)
    const cards: Array<[string, keyof DashboardData['summary'], React.ReactNode]> = [
        ['Total', 'total', <Activity size={18} />],
        ['Running', 'running', <LoaderCircle size={18} />],
        ['Queued', 'queued', <Clock3 size={18} />],
        ['Completed', 'completed', <CheckCircle2 size={18} />],
        ['Failed', 'failed', <XCircle size={18} />],
    ]
    return (
        <WidgetBody state={state} tool="runs">
            {(data) => (
                <div className="dashboard-summary">
                    {cards.map(([label, key, icon]) => (
                        <article key={key} className="dashboard-summary-card">
                            <span className="dashboard-summary-icon" aria-hidden="true">
                                {icon}
                            </span>
                            <span className="dashboard-summary-label">{label}</span>
                            <strong className="dashboard-summary-value">{(data.summary[key] ?? 0).toLocaleString()}</strong>
                        </article>
                    ))}
                </div>
            )}
        </WidgetBody>
    )
}

function RunList({ props, active }: { props: WidgetProps; active: boolean }) {
    const state = useRuns(props)
    const limit = limitOf(props.settings, 8)
    return (
        <WidgetBody state={state} tool="runs">
            {(data) => {
                const items = (active ? data.active_executions : data.recent_executions).slice(0, limit)
                return items.length ? (
                    <div className="dashboard-execution-list">
                        {items.map((execution) => (
                            <ExecutionRow key={execution.id} execution={execution} />
                        ))}
                    </div>
                ) : (
                    <WidgetEmpty>
                        {active ? 'Nothing is queued or running.' : 'Finished runs will appear here.'}
                    </WidgetEmpty>
                )
            }}
        </WidgetBody>
    )
}

export function ActiveRunsWidget(props: WidgetProps) {
    return <RunList props={props} active />
}

export function RecentRunsWidget(props: WidgetProps) {
    return <RunList props={props} active={false} />
}
