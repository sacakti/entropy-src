import { useCallback, useEffect, useMemo, useState } from 'react'
import {
    ArrowRightLeft,
    BellRing,
    Blocks,
    CalendarClock,
    LoaderCircle,
    Pencil,
    Play,
    Plus,
    RefreshCw,
    RotateCcw,
    Search,
    Trash2,
    Workflow as WorkflowIcon,
    X,
} from 'lucide-react'

import { schedulesApi, type Schedule, type ScheduleRun } from '../../api/runs.api'
import { useFeedback } from '../../components/feedback/FeedbackProvider'
import { useShortcuts } from '../../components/layout/useShortcuts'
import { Tabs } from '../administration/AdminPanel'
import { consumeCreateIntent, useCreateIntent } from '../quickCreate'
import { errorMessage, formatDateTime } from '../runs/format'
import { openRun } from '../runs/navigation'
import ScheduleDialog from './ScheduleDialog'
import RunAlertsDialog from '../runs/RunAlertsDialog'
import { MoveToProjectDialog } from '../transfer/TransferDialogs'
import { missingPermission } from '../administration/permissionReason'
import { usePermissions } from '../administration/usePermissions'
import EntropyLoader from '../../components/feedback/EntropyLoader'
import { useErrorToast } from '../../components/feedback/useToast'

const REFRESH_MS = 15_000

const RUN_STATE_LABELS: Record<ScheduleRun['state'], string> = {
    running: 'Running',
    completed: 'Completed',
    failed: 'Failed',
    cancelled: 'Cancelled',
    error: 'Did not start',
    retried: 'Retried',
}

const RUN_STATE_CLASS: Record<ScheduleRun['state'], string> = {
    running: 'is-running',
    completed: 'is-completed',
    failed: 'is-failed',
    cancelled: 'is-cancelled',
    error: 'is-failed',
    retried: 'is-paused',
}

function RunState({ run }: { run: ScheduleRun }) {
    return <span className={`run-status ${RUN_STATE_CLASS[run.state]}`}>{RUN_STATE_LABELS[run.state]}</span>
}

/** Select-all checkbox that shows a partial selection. */
function SelectAll({
    total,
    selected,
    onChange,
    label,
}: {
    total: number
    selected: number
    onChange: (all: boolean) => void
    label: string
}) {
    return (
        <input
            type="checkbox"
            className="list-check"
            aria-label={label}
            checked={total > 0 && selected === total}
            ref={(element) => {
                if (element) element.indeterminate = selected > 0 && selected < total
            }}
            onChange={(event) => onChange(event.target.checked)}
            disabled={total === 0}
        />
    )
}

export default function Schedules() {
    const permissions = usePermissions()
    const deleteReason = missingPermission(permissions, ['schedules.delete'], 'deleting schedules')
    const manageReason = missingPermission(permissions, ['schedules.manage'], 'changing schedules')
    const [alerting, setAlerting] = useState<Schedule | null>(null)
    const [moving, setMoving] = useState<Schedule[] | null>(null)
    const { notify, modal } = useFeedback()

    const [tab, setTab] = useState<'schedules' | 'failed'>('schedules')
    const [schedules, setSchedules] = useState<Schedule[]>([])
    const [failed, setFailed] = useState<ScheduleRun[]>([])
    const [loading, setLoading] = useState(true)
    const [refreshing, setRefreshing] = useState(false)
    const [error, setError] = useState<string | null>(null)
    useErrorToast(error)
    const [search, setSearch] = useState('')
    const [editing, setEditing] = useState<Schedule | 'new' | null>(() =>
        consumeCreateIntent('schedule') ? 'new' : null,
    )
    const [selected, setSelected] = useState<Set<number>>(new Set())
    const [selectedRuns, setSelectedRuns] = useState<Set<number>>(new Set())
    const [busy, setBusy] = useState<string | null>(null)

    const load = useCallback(async () => {
        try {
            const response = await schedulesApi.list()
            setSchedules(response.items)
            setFailed(response.failed)
            setError(null)
            // Drop selections that no longer exist.
            setSelected((current) => new Set([...current].filter((id) => response.items.some((item) => item.id === id))))
            setSelectedRuns(
                (current) => new Set([...current].filter((id) => response.failed.some((item) => item.id === id))),
            )
        } catch (cause) {
            setError(errorMessage(cause, 'Unable to load schedules.'))
        } finally {
            setLoading(false)
            setRefreshing(false)
        }
    }, [])

    useEffect(() => {
        const first = setTimeout(() => void load(), 0)
        const timer = setInterval(() => void load(), REFRESH_MS)
        return () => {
            clearTimeout(first)
            clearInterval(timer)
        }
    }, [load])

    const filtered = useMemo(() => {
        const query = search.trim().toLowerCase()
        return query
            ? schedules.filter((item) =>
                  `${item.name} ${item.description} ${item.target} ${item.cron}`.toLowerCase().includes(query),
              )
            : schedules
    }, [schedules, search])

    const toggle = (set: Set<number>, id: number) => {
        const next = new Set(set)
        if (next.has(id)) next.delete(id)
        else next.add(id)
        return next
    }

    const removeSelected = async (ids: number[]) => {
        if (!ids.length) return
        const names = schedules.filter((item) => ids.includes(item.id)).map((item) => item.name)
        const confirmed = await modal.confirm({
            title: ids.length === 1 ? `Delete ${names[0]}?` : `Delete ${ids.length} schedules?`,
            message: 'They stop firing and their run history is removed. Runs already started are kept.',
            confirmText: ids.length === 1 ? 'Delete schedule' : `Delete ${ids.length} schedules`,
            cancelText: 'Cancel',
            destructive: true,
        })
        if (!confirmed) return

        setBusy('delete')
        try {
            const result = await schedulesApi.remove(ids)
            notify.success(`${result.deleted} schedule${result.deleted === 1 ? '' : 's'} deleted.`)
            setSelected(new Set())
            void load()
        } catch (cause) {
            notify.error(errorMessage(cause, 'Unable to delete schedules.'))
        } finally {
            setBusy(null)
        }
    }

    const toggleEnabled = async (schedule: Schedule) => {
        setBusy(`enable-${schedule.id}`)
        try {
            await schedulesApi.update(schedule.id, { enabled: !schedule.enabled })
            void load()
        } catch (cause) {
            notify.error(errorMessage(cause, 'Unable to update the schedule.'))
        } finally {
            setBusy(null)
        }
    }

    const trigger = async (schedule: Schedule) => {
        const confirmed = await modal.confirm({
            title: `Run ${schedule.name} now?`,
            message: `${schedule.target} starts on ${schedule.node} as you, outside its schedule.`,
            confirmText: 'Run now',
            cancelText: 'Cancel',
        })
        if (!confirmed) return

        setBusy(`run-${schedule.id}`)
        try {
            const { run } = await schedulesApi.trigger(schedule.id)
            if (run.job_id) {
                notify.success(`Run #${run.job_id} started.`, { title: schedule.name })
                openRun(run.job_id)
            } else {
                notify.error(run.error ?? 'The run did not start.', { title: schedule.name })
                void load()
            }
        } catch (cause) {
            notify.error(errorMessage(cause, 'Unable to start the schedule.'))
        } finally {
            setBusy(null)
        }
    }

    const retry = async (ids: number[]) => {
        if (!ids.length) return
        setBusy('retry')
        try {
            const result = await schedulesApi.retry(ids)
            const started = result.runs.filter((run) => run.job_id).length
            const failedToStart = result.runs.length - started
            if (started) notify.success(`${started} run${started === 1 ? '' : 's'} retriggered.`)
            if (failedToStart) notify.error(`${failedToStart} could not start; see Failed runs.`)
            setSelectedRuns(new Set())
            void load()
        } catch (cause) {
            notify.error(errorMessage(cause, 'Unable to retrigger runs.'))
        } finally {
            setBusy(null)
        }
    }

    const dismiss = async (ids: number[]) => {
        if (!ids.length) return
        const confirmed = await modal.confirm({
            title: ids.length === 1 ? 'Dismiss this failure?' : `Dismiss ${ids.length} failures?`,
            message: 'They are removed from the retry list. The runs themselves stay in Runs.',
            confirmText: 'Dismiss',
            cancelText: 'Cancel',
        })
        if (!confirmed) return

        setBusy('dismiss')
        try {
            await schedulesApi.dismiss(ids)
            setSelectedRuns(new Set())
            void load()
        } catch (cause) {
            notify.error(errorMessage(cause, 'Unable to dismiss failures.'))
        } finally {
            setBusy(null)
        }
    }

    useCreateIntent('schedule', () => setEditing('new'))

    useShortcuts({ 'mod+n': () => setEditing('new'), 'alt+n': () => setEditing('new') }, editing === null)

    const selection = tab === 'schedules' ? selected.size : selectedRuns.size

    return (
        <section className="list-page schedules-page">

            <section className="dashboard-section list-section">
                <div className="dashboard-section-heading list-section-heading">
                    <div>
                        <h2>
                            Schedules
                            <span className="list-count">{schedules.length}</span>
                        </h2>
                        <p>
                            {schedules.filter((item) => item.enabled).length} active ·{' '}
                            {failed.length} failed run{failed.length === 1 ? '' : 's'} to review
                        </p>
                    </div>
                    <div className="entropy-panel-actions">
                        <button
                            type="button"
                            className="entropy-button entropy-button-secondary entropy-button-icon"
                            aria-label="Refresh schedules"
                            title="Refresh"
                            onClick={() => {
                                setRefreshing(true)
                                void load()
                            }}
                            disabled={loading || refreshing}
                        >
                            <RefreshCw size={16} className={refreshing ? 'entropy-spin' : ''} />
                        </button>
                        <button
                            type="button"
                            className="entropy-button entropy-button-primary entropy-button-icon"
                            aria-label="Create schedule"
                            title="Create schedule (Ctrl+N)"
                            onClick={() => setEditing('new')}
                        >
                            <Plus size={20} />
                        </button>
                    </div>
                </div>

                <Tabs
                    tabs={[
                        { id: 'schedules', label: 'Schedules', count: schedules.length },
                        { id: 'failed', label: 'Failed runs', count: failed.length },
                    ]}
                    active={tab}
                    onChange={setTab}
                />

                <div className="list-toolbar">
                    {tab === 'schedules' && (
                        <div className="list-search">
                            <Search size={17} aria-hidden="true" />
                            <input
                                type="search"
                                value={search}
                                onChange={(event) => setSearch(event.target.value)}
                                placeholder="Search schedules…"
                                aria-label="Search schedules"
                            />
                            {search && (
                                <button type="button" aria-label="Clear search" onClick={() => setSearch('')}>
                                    <X size={15} />
                                </button>
                            )}
                        </div>
                    )}
                    {selection > 0 && (
                        <div className="list-bulk" role="toolbar" aria-label="Selected items">
                            <span>{selection} selected</span>
                            {tab === 'schedules' ? (
                                <>
                                    <button
                                        type="button"
                                        className="entropy-button entropy-button-secondary entropy-button-sm"
                                        onClick={() => setMoving(schedules.filter((item) => selected.has(item.id)))}
                                        disabled={busy !== null || Boolean(manageReason)}
                                        title={manageReason ?? 'Move or copy to another project'}
                                    >
                                        <ArrowRightLeft size={14} /> Move or copy
                                    </button>
                                    <button
                                        type="button"
                                        className="entropy-button entropy-button-danger-quiet entropy-button-sm"
                                        onClick={() => {
                                            if (!deleteReason) void removeSelected([...selected])
                                        }}
                                        disabled={busy !== null}
                                        aria-disabled={deleteReason ? true : undefined}
                                        title={deleteReason ?? undefined}
                                    >
                                        <Trash2 size={14} /> Delete
                                    </button>
                                </>
                            ) : (
                                <>
                                    <button
                                        type="button"
                                        className="entropy-button entropy-button-primary entropy-button-sm"
                                        onClick={() => void retry([...selectedRuns])}
                                        disabled={busy !== null}
                                    >
                                        {busy === 'retry' ? (
                                            <LoaderCircle size={14} className="entropy-spin" />
                                        ) : (
                                            <RotateCcw size={14} />
                                        )}
                                        Retrigger
                                    </button>
                                    <button
                                        type="button"
                                        className="entropy-button entropy-button-secondary entropy-button-sm"
                                        onClick={() => void dismiss([...selectedRuns])}
                                        disabled={busy !== null}
                                    >
                                        Dismiss
                                    </button>
                                </>
                            )}
                            <button
                                type="button"
                                className="entropy-button entropy-button-ghost entropy-button-sm"
                                onClick={() => (tab === 'schedules' ? setSelected(new Set()) : setSelectedRuns(new Set()))}
                            >
                                Clear
                            </button>
                        </div>
                    )}
                </div>

                <div className="list-table-wrap">
                    {tab === 'schedules' ? (
                        <table className="list-table schedules-table">
                            <thead>
                                <tr>
                                    <th scope="col" className="list-check-cell">
                                        <SelectAll
                                            label="Select all schedules"
                                            total={filtered.length}
                                            selected={filtered.filter((item) => selected.has(item.id)).length}
                                            onChange={(all) =>
                                                setSelected(all ? new Set(filtered.map((item) => item.id)) : new Set())
                                            }
                                        />
                                    </th>
                                    <th scope="col">Schedule</th>
                                    <th scope="col">Runs</th>
                                    <th scope="col">When</th>
                                    <th scope="col">Next run</th>
                                    <th scope="col">Last run</th>
                                    <th scope="col">Status</th>
                                    <th scope="col" className="list-operations-cell">
                                        <span className="list-operations-heading">Operations</span>
                                    </th>
                                </tr>
                            </thead>
                            <tbody>
                                {loading ? (
                                    <tr>
                                        <td colSpan={8}>
                                            <EntropyLoader label={`Loading schedules…`} />
                                        </td>
                                    </tr>
                                ) : filtered.length === 0 ? (
                                    <tr>
                                        <td colSpan={8}>
                                            <div className="list-empty">
                                                <CalendarClock size={22} />
                                                <strong>{schedules.length ? 'No schedules found' : 'No schedules yet'}</strong>
                                                <span>
                                                    {schedules.length
                                                        ? 'Try a different search.'
                                                        : 'Create one with the + button to run a workflow or plugin on a cron schedule.'}
                                                </span>
                                            </div>
                                        </td>
                                    </tr>
                                ) : (
                                    filtered.map((schedule) => (
                                        <tr key={schedule.id} className={selected.has(schedule.id) ? 'is-selected' : undefined}>
                                            <td className="list-check-cell">
                                                <input
                                                    type="checkbox"
                                                    className="list-check"
                                                    aria-label={`Select ${schedule.name}`}
                                                    checked={selected.has(schedule.id)}
                                                    onChange={() => setSelected((current) => toggle(current, schedule.id))}
                                                />
                                            </td>
                                            <td>
                                                <div className="runs-who">
                                                    <strong>{schedule.name}</strong>
                                                    <span>{schedule.description || `by ${schedule.username}`}</span>
                                                </div>
                                            </td>
                                            <td>
                                                <span className="schedule-target">
                                                    {schedule.kind === 'plugin' ? <Blocks size={14} /> : <WorkflowIcon size={14} />}
                                                    {schedule.target}
                                                </span>
                                            </td>
                                            <td>
                                                <div className="runs-who">
                                                    <code className="schedule-cron-code">{schedule.cron}</code>
                                                    <span>{schedule.timezone} · {schedule.node}</span>
                                                </div>
                                            </td>
                                            <td className="list-cell-text">
                                                {schedule.enabled ? formatDateTime(schedule.next_run_at) : 'Paused'}
                                            </td>
                                            <td>
                                                {schedule.last_run ? (
                                                    <button
                                                        type="button"
                                                        className="schedule-last"
                                                        onClick={() => schedule.last_run?.job_id && openRun(schedule.last_run.job_id)}
                                                        disabled={!schedule.last_run.job_id}
                                                        title={schedule.last_run.error ?? 'Open run'}
                                                    >
                                                        <RunState run={schedule.last_run} />
                                                        <small>{formatDateTime(schedule.last_run.created_at)}</small>
                                                    </button>
                                                ) : (
                                                    <span className="list-cell-text">Never</span>
                                                )}
                                            </td>
                                            <td>
                                                <label className="schedule-switch">
                                                    <input
                                                        type="checkbox"
                                                        checked={schedule.enabled}
                                                        onChange={() => void toggleEnabled(schedule)}
                                                        disabled={busy === `enable-${schedule.id}`}
                                                        aria-label={`${schedule.enabled ? 'Pause' : 'Enable'} ${schedule.name}`}
                                                    />
                                                    {schedule.enabled ? 'Enabled' : 'Paused'}
                                                </label>
                                            </td>
                                            <td>
                                                <div className="list-operations">
                                                    <button
                                                        type="button"
                                                        className="entropy-button entropy-button-secondary entropy-button-icon entropy-button-sm"
                                                        aria-label={`Run ${schedule.name} now`}
                                                        title="Run now"
                                                        onClick={() => void trigger(schedule)}
                                                        disabled={busy === `run-${schedule.id}`}
                                                    >
                                                        {busy === `run-${schedule.id}` ? (
                                                            <LoaderCircle size={15} className="entropy-spin" />
                                                        ) : (
                                                            <Play size={15} />
                                                        )}
                                                    </button>
                                                    <button
                                                        type="button"
                                                        className="entropy-button entropy-button-secondary entropy-button-icon entropy-button-sm"
                                                        aria-label={`Edit ${schedule.name}`}
                                                        title="Edit"
                                                        onClick={() => setEditing(schedule)}
                                                    >
                                                        <Pencil size={15} />
                                                    </button>
                                                    <button
                                                        type="button"
                                                        className="entropy-button entropy-button-secondary entropy-button-icon entropy-button-sm"
                                                        aria-label={`Alerts for ${schedule.name}`}
                                                        title="E-mail alerts"
                                                        onClick={() => setAlerting(schedule)}
                                                    >
                                                        <BellRing size={15} />
                                                    </button>
                                                    <button
                                                        type="button"
                                                        className="entropy-button entropy-button-danger-quiet entropy-button-icon entropy-button-sm"
                                                        aria-label={`Delete ${schedule.name}`}
                                                        title={deleteReason ?? 'Delete'}
                                                        aria-disabled={deleteReason ? true : undefined}
                                                        onClick={() => {
                                                            if (!deleteReason) void removeSelected([schedule.id])
                                                        }}
                                                    >
                                                        <Trash2 size={15} />
                                                    </button>
                                                </div>
                                            </td>
                                        </tr>
                                    ))
                                )}
                            </tbody>
                        </table>
                    ) : (
                        <table className="list-table">
                            <thead>
                                <tr>
                                    <th scope="col" className="list-check-cell">
                                        <SelectAll
                                            label="Select all failed runs"
                                            total={failed.length}
                                            selected={selectedRuns.size}
                                            onChange={(all) =>
                                                setSelectedRuns(all ? new Set(failed.map((item) => item.id)) : new Set())
                                            }
                                        />
                                    </th>
                                    <th scope="col">Schedule</th>
                                    <th scope="col">Run</th>
                                    <th scope="col">Result</th>
                                    <th scope="col">When</th>
                                    <th scope="col" className="list-operations-cell">
                                        <span className="list-operations-heading">Operations</span>
                                    </th>
                                </tr>
                            </thead>
                            <tbody>
                                {failed.length === 0 ? (
                                    <tr>
                                        <td colSpan={6}>
                                            <div className="list-empty">
                                                <CalendarClock size={22} />
                                                <strong>No failed runs</strong>
                                                <span>Scheduled runs that fail stay here until you retrigger or dismiss them.</span>
                                            </div>
                                        </td>
                                    </tr>
                                ) : (
                                    failed.map((run) => (
                                        <tr key={run.id} className={selectedRuns.has(run.id) ? 'is-selected' : undefined}>
                                            <td className="list-check-cell">
                                                <input
                                                    type="checkbox"
                                                    className="list-check"
                                                    aria-label={`Select failure ${run.id}`}
                                                    checked={selectedRuns.has(run.id)}
                                                    onChange={() => setSelectedRuns((current) => toggle(current, run.id))}
                                                />
                                            </td>
                                            <td>
                                                <div className="runs-who">
                                                    <strong>{run.schedule ?? `Schedule ${run.schedule_id}`}</strong>
                                                    <span>{run.trigger === 'schedule' ? 'Scheduled' : run.trigger === 'retry' ? 'Retry' : 'Run now'}</span>
                                                </div>
                                            </td>
                                            <td>
                                                {run.job_id ? (
                                                    <button type="button" className="schedule-last" onClick={() => openRun(run.job_id as number)}>
                                                        #{run.job_id}
                                                    </button>
                                                ) : (
                                                    <span className="list-cell-text">—</span>
                                                )}
                                            </td>
                                            <td>
                                                <div className="schedule-failure">
                                                    <RunState run={run} />
                                                    {run.error && <span>{run.error}</span>}
                                                </div>
                                            </td>
                                            <td className="list-cell-text">{formatDateTime(run.created_at)}</td>
                                            <td>
                                                <div className="list-operations">
                                                    <button
                                                        type="button"
                                                        className="entropy-button entropy-button-secondary entropy-button-icon entropy-button-sm"
                                                        aria-label="Retrigger"
                                                        title="Retrigger"
                                                        onClick={() => void retry([run.id])}
                                                        disabled={busy !== null}
                                                    >
                                                        <RotateCcw size={15} />
                                                    </button>
                                                    <button
                                                        type="button"
                                                        className="entropy-button entropy-button-ghost entropy-button-icon entropy-button-sm"
                                                        aria-label="Dismiss"
                                                        title="Dismiss"
                                                        onClick={() => void dismiss([run.id])}
                                                        disabled={busy !== null}
                                                    >
                                                        <X size={15} />
                                                    </button>
                                                </div>
                                            </td>
                                        </tr>
                                    ))
                                )}
                            </tbody>
                        </table>
                    )}
                </div>
            </section>

            {moving && (
                <MoveToProjectDialog
                    kind="schedules"
                    schedules={moving.map((item) => item.id)}
                    labels={moving.map((item) => item.name)}
                    onClose={() => setMoving(null)}
                    onDone={() => {
                        setSelected(new Set())
                        void load()
                    }}
                />
            )}
            {alerting && (
                <RunAlertsDialog
                    kind="schedule"
                    target={alerting.id}
                    name={alerting.name}
                    canEdit={!manageReason}
                    onClose={() => setAlerting(null)}
                />
            )}
            {editing && (
                <ScheduleDialog
                    schedule={editing === 'new' ? null : editing}
                    onClose={() => setEditing(null)}
                    onSaved={(saved) => {
                        notify.success(
                            saved.enabled && saved.next_run_at
                                ? `Next run ${formatDateTime(saved.next_run_at)}.`
                                : 'Schedule saved.',
                            { title: editing === 'new' ? 'Schedule created' : 'Schedule updated' },
                        )
                        setEditing(null)
                        void load()
                    }}
                />
            )}
        </section>
    )
}
