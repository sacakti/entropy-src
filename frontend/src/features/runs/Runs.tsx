import { useCallback, useEffect, useRef, useState } from 'react'
import {
    AlertCircle,
    Archive,
    Blocks,
    ChevronLeft,
    ChevronRight,
    LoaderCircle,
    PlayCircle,
    RefreshCw,
    Search,
    Square,
    Trash2,
    Workflow as WorkflowIcon,
    X,
} from 'lucide-react'

import { runsApi, type Run, type RunListResponse, type RunTab } from '../../api/runs.api'
import { useFeedback } from '../../components/feedback/FeedbackProvider'
import { useShortcuts } from '../../components/layout/useShortcuts'
import { Tabs } from '../administration/AdminPanel'
import HousekeepingDialog from './HousekeepingDialog'
import PurgeArchiveDialog from './PurgeArchiveDialog'
import RunStatus from './RunStatus'
import {
    TRIGGER_LABELS,
    errorMessage,
    formatDateTime,
    formatDuration,
    isActive,
    runDuration,
    runnerName,
} from './format'
import { openRun, runsTabFromHash } from './navigation'

const PAGE_SIZE = 25

// Active runs change quickly; the rest only when something finishes.
const POLL_ACTIVE_MS = 2000
const POLL_IDLE_MS = 8000

const TAB_LABELS: { id: RunTab; label: string }[] = [
    { id: 'active', label: 'Executing' },
    { id: 'completed', label: 'Completed' },
    { id: 'failed', label: 'Failed' },
    { id: 'cancelled', label: 'Cancelled' },
    { id: 'all', label: 'All' },
    { id: 'archived', label: 'Archived' },
]

export default function Runs() {
    const { notify, modal } = useFeedback()

    // A tab in the address (`#/runs?tab=all`, e.g. from the dashboard) wins.
    const [tab, setTab] = useState<RunTab>(() => runsTabFromHash(window.location.hash) ?? 'active')
    const [search, setSearch] = useState('')
    const [page, setPage] = useState(0)
    const [data, setData] = useState<RunListResponse | null>(null)
    const [loading, setLoading] = useState(true)
    const [refreshing, setRefreshing] = useState(false)
    const [error, setError] = useState<string | null>(null)
    const [stopping, setStopping] = useState<number | null>(null)
    const [housekeepingOpen, setHousekeepingOpen] = useState(false)
    const [purgeOpen, setPurgeOpen] = useState(false)
    const [selectedIds, setSelectedIds] = useState<Set<number>>(() => new Set())
    const [bulkBusy, setBulkBusy] = useState(false)
    const [now, setNow] = useState(() => Date.now())
    const searchRef = useRef<HTMLInputElement>(null)

    // The first visit lands on Executing; with nothing running, show history.
    const pickedTab = useRef(runsTabFromHash(window.location.hash) !== null)

    // Back/Forward between tabs, or a link to another tab while mounted.
    useEffect(() => {
        const follow = () => {
            const next = runsTabFromHash(window.location.hash)
            if (next) {
                pickedTab.current = true
                setTab(next)
                setPage(0)
                setSelectedIds(new Set())
            }
        }
        window.addEventListener('popstate', follow)
        return () => window.removeEventListener('popstate', follow)
    }, [])

    const load = useCallback(async () => {
        try {
            const response = await runsApi.list({
                tab,
                search: search.trim(),
                limit: PAGE_SIZE,
                offset: page * PAGE_SIZE,
            })

            if (!pickedTab.current) {
                pickedTab.current = true
                if (tab === 'active' && response.counts.active === 0 && response.counts.all > 0) {
                    setTab('all')
                    return
                }
            }

            setData(response)
            setSelectedIds((current) => new Set([...current].filter((id) => response.items.some((run) => run.id === id))))
            setError(null)
        } catch (cause) {
            setError(errorMessage(cause, 'Unable to load runs.'))
        } finally {
            setLoading(false)
            setRefreshing(false)
        }
    }, [page, search, tab])

    useEffect(() => {
        const first = setTimeout(() => void load(), search ? 250 : 0)
        return () => clearTimeout(first)
    }, [load, search])

    const anyActive = (data?.counts.active ?? 0) > 0

    useEffect(() => {
        const timer = setInterval(() => void load(), anyActive ? POLL_ACTIVE_MS : POLL_IDLE_MS)
        return () => clearInterval(timer)
    }, [anyActive, load])

    // Durations of executing runs tick every second.
    useEffect(() => {
        if (!anyActive) return
        const timer = setInterval(() => setNow(Date.now()), 1000)
        return () => clearInterval(timer)
    }, [anyActive])

    const refresh = () => {
        setRefreshing(true)
        void load()
    }

    const stop = async (run: Run) => {
        const confirmed = await modal.confirm({
            title: `Stop run #${run.id}?`,
            message: `${run.target} is interrupted; the step in progress is cancelled and later steps do not run.`,
            confirmText: 'Stop run',
            cancelText: 'Keep running',
            destructive: true,
        })
        if (!confirmed) return

        setStopping(run.id)
        try {
            await runsApi.stop(run.id)
            notify.success(`Stop requested for run #${run.id}.`, { title: 'Stopping run' })
            void load()
        } catch (cause) {
            notify.error(errorMessage(cause, 'Unable to stop the run.'), { title: 'Stop failed' })
        } finally {
            setStopping(null)
        }
    }

    useShortcuts({
        'mod+f': () => {
            searchRef.current?.focus()
            searchRef.current?.select()
        },
    })

    const items = data?.items ?? []
    const selectedRuns = items.filter((run) => selectedIds.has(run.id))
    const selectedFinishedRuns = selectedRuns.filter(
        (run) => run.state === 'completed' || run.state === 'failed' || run.state === 'cancelled',
    )
    const allVisibleSelected = items.length > 0 && items.every((run) => selectedIds.has(run.id))
    const total = data?.total ?? 0
    const pages = Math.max(1, Math.ceil(total / PAGE_SIZE))

    const changeTab = (next: RunTab) => {
        pickedTab.current = true
        // Keep the tab in the address so reloads and shared links keep it.
        window.history.replaceState(null, '', `#/runs?tab=${next}`)
        setTab(next)
        setPage(0)
        setSelectedIds(new Set())
        setLoading(true)
    }

    const toggleVisibleSelection = (checked: boolean) => {
        setSelectedIds((current) => {
            const next = new Set(current)
            items.forEach((run) => (checked ? next.add(run.id) : next.delete(run.id)))
            return next
        })
    }

    const archiveSelected = async () => {
        if (!selectedFinishedRuns.length) return
        setBulkBusy(true)
        try {
            const result = await runsApi.archiveSelected(selectedFinishedRuns.map((run) => run.id))
            notify.success(`${result.result.jobs} finished run${result.result.jobs === 1 ? '' : 's'} archived.`, {
                title: 'Runs archived',
            })
            setSelectedIds(new Set())
            void load()
        } catch (cause) {
            notify.error(errorMessage(cause, 'Unable to archive selected runs.'), { title: 'Archive failed' })
        } finally {
            setBulkBusy(false)
        }
    }

    const purgeSelected = async (downloadFirst: boolean) => {
        if (!selectedRuns.length) return
        const ids = selectedRuns.map((run) => run.id)
        const confirmed = await modal.confirm({
            title: `${downloadFirst ? 'Download and purge' : 'Purge'} ${ids.length} selected run${ids.length === 1 ? '' : 's'}?`,
            message: downloadFirst
                ? 'The selected runs and their events will be downloaded as a .tar.gz file. After the download starts, they will be permanently removed from the archive.'
                : 'The selected runs and their saved events will be permanently removed from the archive.',
            confirmText: downloadFirst ? 'Download and purge' : 'Purge selected',
            cancelText: 'Cancel',
            destructive: true,
        })
        if (!confirmed) return
        setBulkBusy(true)
        try {
            if (downloadFirst) await runsApi.exportSelected(ids)
            const result = await runsApi.purgeSelected(ids)
            notify.success(`${result.purged_jobs} archived run${result.purged_jobs === 1 ? '' : 's'} purged.`, {
                title: downloadFirst ? 'Download started and runs purged' : 'Runs purged',
            })
            setSelectedIds(new Set())
            void load()
        } catch (cause) {
            notify.error(errorMessage(cause, 'Unable to purge selected runs.'), { title: 'Purge failed' })
        } finally {
            setBulkBusy(false)
        }
    }

    return (
        <section className="list-page runs-page">
            {error && (
                <div className="entropy-alert entropy-alert-error" role="alert">
                    <AlertCircle size={16} />
                    <span>{error}</span>
                </div>
            )}

            <section className="dashboard-section list-section">
                <div className="dashboard-section-heading list-section-heading">
                    <div>
                        <h2>
                            Workflow runs
                            <span className="list-count" aria-label={`${tab === 'archived' ? data?.counts.archived ?? 0 : data?.counts.all ?? 0} runs in total`}>
                                {tab === 'archived' ? data?.counts.archived ?? 0 : data?.counts.all ?? 0}
                            </span>
                        </h2>
                        <p>
                            {anyActive
                                ? `${data?.counts.active} executing now · updates live`
                                : 'Every workflow and plugin run, newest first'}
                        </p>
                    </div>

                    <div className="entropy-panel-actions">
                        {tab === 'archived' && (
                            <button
                                type="button"
                                className="entropy-button entropy-button-danger-quiet"
                                onClick={() => setPurgeOpen(true)}
                                disabled={(data?.counts.archived ?? 0) === 0}
                                title="Purge archived runs"
                            >
                                <Trash2 size={15} /> Purge
                            </button>
                        )}
                        <button
                            type="button"
                            className="entropy-button entropy-button-secondary entropy-button-icon"
                            aria-label="Housekeeping"
                            title="Housekeeping: archive old runs"
                            onClick={() => setHousekeepingOpen(true)}
                        >
                            <Archive size={16} />
                        </button>
                        <button
                            type="button"
                            className="entropy-button entropy-button-secondary entropy-button-icon"
                            aria-label="Refresh runs"
                            title="Refresh"
                            onClick={refresh}
                            disabled={loading || refreshing}
                        >
                            <RefreshCw size={16} className={refreshing ? 'entropy-spin' : ''} />
                        </button>
                    </div>
                </div>

                <Tabs
                    tabs={TAB_LABELS.map((item) => ({ ...item, count: data?.counts[item.id] }))}
                    active={tab}
                    onChange={changeTab}
                />

                <div className="list-toolbar">
                    <div className="list-search">
                        <Search size={17} aria-hidden="true" />
                        <input
                            ref={searchRef}
                            type="search"
                            value={search}
                            onChange={(event) => {
                                setSearch(event.target.value)
                                setPage(0)
                                setSelectedIds(new Set())
                            }}
                            placeholder="Search by workflow, plugin or #run…"
                            aria-label="Search runs"
                        />
                        {search && (
                            <button
                                type="button"
                                aria-label="Clear search"
                                onClick={() => {
                                    setSearch('')
                                    setSelectedIds(new Set())
                                }}
                            >
                                <X size={15} />
                            </button>
                        )}
                    </div>
                </div>

                {selectedRuns.length > 0 && (
                    <div className="runs-selection-toolbar" role="toolbar" aria-label="Selected run actions">
                        <span>{selectedRuns.length} selected</span>
                        {tab === 'archived' ? (
                            <>
                                <button
                                    type="button"
                                    className="entropy-button entropy-button-danger-quiet entropy-button-sm"
                                    onClick={() => void purgeSelected(true)}
                                    disabled={bulkBusy}
                                >
                                    Download .tar.gz & purge selected
                                </button>
                                <button
                                    type="button"
                                    className="entropy-button entropy-button-danger-quiet entropy-button-sm"
                                    onClick={() => void purgeSelected(false)}
                                    disabled={bulkBusy}
                                >
                                    Purge selected
                                </button>
                            </>
                        ) : (
                            <button
                                type="button"
                                className="entropy-button entropy-button-secondary entropy-button-sm"
                                onClick={() => void archiveSelected()}
                                disabled={bulkBusy || selectedFinishedRuns.length === 0}
                                title="Only completed, failed or cancelled runs can be archived"
                            >
                                {bulkBusy && <LoaderCircle size={14} className="entropy-spin" />}
                                Archive finished ({selectedFinishedRuns.length})
                            </button>
                        )}
                        <button
                            type="button"
                            className="entropy-button entropy-button-ghost entropy-button-sm"
                            onClick={() => setSelectedIds(new Set())}
                            disabled={bulkBusy}
                        >
                            Clear selection
                        </button>
                    </div>
                )}

                <div className="list-table-wrap">
                    <table className="list-table runs-table">
                        <thead>
                            <tr>
                                <th scope="col" className="runs-select-cell">
                                    <input
                                        type="checkbox"
                                        checked={allVisibleSelected}
                                        aria-label="Select all runs on this page"
                                        aria-checked={allVisibleSelected ? true : selectedRuns.length > 0 ? 'mixed' : false}
                                        onChange={(event) => toggleVisibleSelection(event.target.checked)}
                                    />
                                </th>
                                <th scope="col">Run</th>
                                <th scope="col">Status</th>
                                <th scope="col">Executed by</th>
                                <th scope="col">Node</th>
                                <th scope="col">Started</th>
                                <th scope="col">Duration</th>
                                <th scope="col" className="list-operations-cell">
                                    <span className="list-operations-heading">Operations</span>
                                </th>
                            </tr>
                        </thead>
                        <tbody>
                            {loading && !data ? (
                                <tr>
                                    <td colSpan={8}>
                                        <div className="list-empty" role="status">
                                            <LoaderCircle size={18} className="entropy-spin" />
                                            Loading runs…
                                        </div>
                                    </td>
                                </tr>
                            ) : items.length === 0 ? (
                                <tr>
                                    <td colSpan={8}>
                                        <div className="list-empty">
                                            <PlayCircle size={22} />
                                            <strong>
                                                {tab === 'active' ? 'Nothing is executing' : 'No runs found'}
                                            </strong>
                                            <span>
                                                {search
                                                    ? 'Try a different search.'
                                                    : 'Start one with the play button on a workflow or plugin.'}
                                            </span>
                                        </div>
                                    </td>
                                </tr>
                            ) : (
                                items.map((run) => (
                                    <tr
                                        key={run.id}
                                        className="runs-row"
                                        tabIndex={0}
                                        onClick={() => openRun(run.id)}
                                        onKeyDown={(event) => {
                                            if (event.key === 'Enter') openRun(run.id)
                                        }}
                                    >
                                        <td className="runs-select-cell" onClick={(event) => event.stopPropagation()}>
                                            <input
                                                type="checkbox"
                                                checked={selectedIds.has(run.id)}
                                                aria-label={`Select run ${run.id}`}
                                                onKeyDown={(event) => event.stopPropagation()}
                                                onChange={(event) => {
                                                    setSelectedIds((current) => {
                                                        const next = new Set(current)
                                                        if (event.target.checked) next.add(run.id)
                                                        else next.delete(run.id)
                                                        return next
                                                    })
                                                }}
                                            />
                                        </td>
                                        <td>
                                            <div className="list-name">
                                                <span className="list-name-icon" aria-hidden="true">
                                                    {run.kind === 'plugin' ? (
                                                        <Blocks size={16} />
                                                    ) : (
                                                        <WorkflowIcon size={16} />
                                                    )}
                                                </span>
                                                <div className="list-name-content">
                                                    <strong>{run.target}</strong>
                                                    <span>
                                                        #{run.id} · {run.kind === 'plugin' ? 'Plugin run' : 'Workflow'}
                                                    </span>
                                                </div>
                                            </div>
                                        </td>
                                        <td>
                                            <RunStatus state={run.state} />
                                        </td>
                                        <td>
                                            <div className="runs-who">
                                                <strong>{runnerName(run)}</strong>
                                                <span>{TRIGGER_LABELS[run.trigger] ?? run.trigger}</span>
                                            </div>
                                        </td>
                                        <td>
                                            <span className="list-version">{run.node}</span>
                                        </td>
                                        <td className="list-cell-text">
                                            {formatDateTime(run.started_at ?? run.created_at)}
                                        </td>
                                        <td className="list-cell-text runs-duration">
                                            {formatDuration(runDuration(run, now))}
                                        </td>
                                        <td onClick={(event) => event.stopPropagation()}>
                                            <div className="list-operations">
                                                <button
                                                    type="button"
                                                    className="entropy-button entropy-button-secondary entropy-button-icon entropy-button-sm"
                                                    aria-label={`Open run ${run.id}`}
                                                    title={isActive(run.state) ? 'Watch live' : 'Open'}
                                                    onClick={() => openRun(run.id)}
                                                >
                                                    <PlayCircle size={15} />
                                                </button>
                                                {isActive(run.state) && (
                                                    <button
                                                        type="button"
                                                        className="entropy-button entropy-button-danger-quiet entropy-button-icon entropy-button-sm"
                                                        aria-label={`Stop run ${run.id}`}
                                                        title="Stop"
                                                        onClick={() => void stop(run)}
                                                        disabled={stopping === run.id}
                                                    >
                                                        {stopping === run.id ? (
                                                            <LoaderCircle size={15} className="entropy-spin" />
                                                        ) : (
                                                            <Square size={14} />
                                                        )}
                                                    </button>
                                                )}
                                            </div>
                                        </td>
                                    </tr>
                                ))
                            )}
                        </tbody>
                    </table>
                </div>

                {pages > 1 && (
                    <div className="runs-pager">
                        <span>
                            {page * PAGE_SIZE + 1}–{Math.min(total, (page + 1) * PAGE_SIZE)} of {total}
                        </span>
                        <button
                            type="button"
                            className="entropy-button entropy-button-secondary entropy-button-icon entropy-button-sm"
                            aria-label="Previous page"
                            onClick={() => {
                                setSelectedIds(new Set())
                                setPage((value) => Math.max(0, value - 1))
                            }}
                            disabled={page === 0}
                        >
                            <ChevronLeft size={15} />
                        </button>
                        <button
                            type="button"
                            className="entropy-button entropy-button-secondary entropy-button-icon entropy-button-sm"
                            aria-label="Next page"
                            onClick={() => {
                                setSelectedIds(new Set())
                                setPage((value) => Math.min(pages - 1, value + 1))
                            }}
                            disabled={page >= pages - 1}
                        >
                            <ChevronRight size={15} />
                        </button>
                    </div>
                )}
            </section>

            {housekeepingOpen && <HousekeepingDialog onClose={() => setHousekeepingOpen(false)} onApplied={refresh} />}
            {purgeOpen && (
                <PurgeArchiveDialog
                    archivedJobs={data?.counts.archived ?? 0}
                    onClose={() => setPurgeOpen(false)}
                    onPurged={refresh}
                />
            )}
        </section>
    )
}
