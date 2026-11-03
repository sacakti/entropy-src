import { useCallback, useEffect, useRef, useState } from 'react'
import {
    Archive,
    Puzzle,
    LoaderCircle,
    PlayCircle,
    RefreshCw,
    Search,
    Square,
    Trash2,
    Workflow as WorkflowIcon,
    X,
} from 'lucide-react'

import { runsApi, type Run, type RunListResponse, type RunSortField, type RunTab } from '../../api/runs.api'
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
import EntropyLoader from '../../components/feedback/EntropyLoader'
import { useErrorToast } from '../../components/feedback/useToast'
import Pagination from '../../components/layout/Pagination'
import SelectionBar from '../../components/layout/SelectionBar'
import SortHeader from '../../components/layout/SortHeader'
import { usePageSize } from '../../components/layout/usePagination'
import { useSortState } from '../../components/layout/useSort'
import { inChunks } from '../../services/chunks'

const RUN_SORTS: RunSortField[] = ['id', 'run', 'status', 'user', 'node', 'started', 'duration']

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

/** What the runs list and bulk endpoints accept per request. */
const RUNS_PER_REQUEST = 200
const BULK_LIMIT = 500
const MAX_SELECTED_RUNS = 5000

export default function Runs() {
    const { notify, modal } = useFeedback()

    // A tab in the address (`#/runs?tab=all`, e.g. from the dashboard) wins.
    const [tab, setTab] = useState<RunTab>(() => runsTabFromHash(window.location.hash) ?? 'active')
    const [search, setSearch] = useState('')
    const [page, setPage] = useState(0)
    const [pageSize, setPageSize] = usePageSize('runs')
    const { sort, toggle, ariaSort } = useSortState<RunSortField>('runs', RUN_SORTS, { field: 'started', order: 'desc' }, ['id', 'started', 'duration'])
    const [data, setData] = useState<RunListResponse | null>(null)
    const [loading, setLoading] = useState(true)
    const [refreshing, setRefreshing] = useState(false)
    const [error, setError] = useState<string | null>(null)
    useErrorToast(error)
    const [stopping, setStopping] = useState<number | null>(null)
    const [housekeepingOpen, setHousekeepingOpen] = useState(false)
    const [purgeOpen, setPurgeOpen] = useState(false)
    // Across pages, with each run, as the other pages' runs are not loaded.
    const [selected, setSelected] = useState<Map<number, Run>>(() => new Map())
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
                setSelected(new Map())
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
                limit: pageSize,
                offset: page * pageSize,
                sort: sort.field,
                order: sort.order,
            })

            if (!pickedTab.current) {
                pickedTab.current = true
                if (tab === 'active' && response.counts.active === 0 && response.counts.all > 0) {
                    setTab('all')
                    return
                }
            }

            setData(response)
            // Keep what is selected on other pages; refresh what is shown here.
            setSelected((current) => {
                const shown = response.items.filter((run) => current.has(run.id))
                if (!shown.length) return current
                const next = new Map(current)
                shown.forEach((run) => next.set(run.id, run))
                return next
            })
            setError(null)
        } catch (cause) {
            setError(errorMessage(cause, 'Unable to load runs.'))
        } finally {
            setLoading(false)
            setRefreshing(false)
        }
    }, [page, search, tab, pageSize, sort.field, sort.order])

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
    const selectedRuns = [...selected.values()]
    const pageSelected = items.filter((run) => selected.has(run.id)).length
    const selectedFinishedRuns = selectedRuns.filter(
        (run) => run.state === 'completed' || run.state === 'failed' || run.state === 'cancelled',
    )
    const allVisibleSelected = items.length > 0 && pageSelected === items.length
    const total = data?.total ?? 0
    const pages = Math.max(1, Math.ceil(total / pageSize))
    const changeSort = (field: RunSortField) => {
        toggle(field)
        setPage(0)
        setSelected(new Map())
    }

    const changeTab = (next: RunTab) => {
        pickedTab.current = true
        // Keep the tab in the address so reloads and shared links keep it.
        window.history.replaceState(null, '', `#/runs?tab=${next}`)
        setTab(next)
        setPage(0)
        setSelected(new Map())
        setLoading(true)
    }

    const toggleVisibleSelection = (checked: boolean) => {
        setSelected((current) => {
            const next = new Map(current)
            items.forEach((run) => (checked ? next.set(run.id, run) : next.delete(run.id)))
            return next
        })
    }

    /** Every run matching the tab and search, page by page, up to MAX_SELECTED_RUNS. */
    const selectAllRuns = async () => {
        try {
            const everything = new Map<number, Run>()
            for (let offset = 0; offset < MAX_SELECTED_RUNS; offset += RUNS_PER_REQUEST) {
                const response = await runsApi.list({
                    tab,
                    search: search.trim(),
                    limit: RUNS_PER_REQUEST,
                    offset,
                    sort: sort.field,
                    order: sort.order,
                })
                response.items.forEach((run) => everything.set(run.id, run))
                if (offset + RUNS_PER_REQUEST >= response.total) break
            }
            setSelected(everything)
            if (total > MAX_SELECTED_RUNS) {
                notify.warning(
                    `Selected the first ${MAX_SELECTED_RUNS.toLocaleString()} of ${total.toLocaleString()} runs. ` +
                        'Run this again for the rest, or use housekeeping for rules across all runs.',
                    { title: 'Large selection' },
                )
            }
        } catch (cause) {
            notify.error(errorMessage(cause, 'Unable to select all runs.'), { title: 'Not selected' })
        }
    }

    const archiveSelected = async () => {
        if (!selectedFinishedRuns.length) return
        setBulkBusy(true)
        try {
            // The server takes BULK_LIMIT ids per request.
            let jobs = 0
            for (const part of inChunks(selectedFinishedRuns.map((run) => run.id), BULK_LIMIT)) {
                jobs += (await runsApi.archiveSelected(part)).result.jobs
            }
            notify.success(`${jobs} finished run${jobs === 1 ? '' : 's'} archived.`, {
                title: 'Runs archived',
            })
            setSelected(new Map())
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
            // The server takes BULK_LIMIT ids per request, so a large selection downloads several files;
            // each part is purged only after its own download has started.
            let purged = 0
            for (const part of inChunks(ids, BULK_LIMIT)) {
                if (downloadFirst) await runsApi.exportSelected(part)
                purged += (await runsApi.purgeSelected(part)).purged_jobs
            }
            notify.success(`${purged} archived run${purged === 1 ? '' : 's'} purged.`, {
                title: downloadFirst ? 'Download started and runs purged' : 'Runs purged',
            })
            setSelected(new Map())
            void load()
        } catch (cause) {
            notify.error(errorMessage(cause, 'Unable to purge selected runs.'), { title: 'Purge failed' })
        } finally {
            setBulkBusy(false)
        }
    }

    return (
        <section className="list-page runs-page">

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
                                setSelected(new Map())
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
                                    setSelected(new Map())
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
                            onClick={() => setSelected(new Map())}
                            disabled={bulkBusy}
                        >
                            Clear selection
                        </button>
                    </div>
                )}

                <SelectionBar
                    noun="runs"
                    pageCount={items.length}
                    total={total}
                    pageSelected={pageSelected}
                    selectedCount={selected.size}
                    onSelectPage={() => setSelected(new Map(items.map((run) => [run.id, run])))}
                    onSelectAll={selectAllRuns}
                    onClear={() => setSelected(new Map())}
                    disabled={bulkBusy}
                />

                <div className="list-table-wrap">
                    <table className="list-table runs-table">
                        <thead>
                            <tr>
                                <th scope="col" className="runs-select-cell">
                                    <input
                                        type="checkbox"
                                        checked={allVisibleSelected}
                                        aria-label="Select the runs on this page"
                                        aria-checked={allVisibleSelected ? true : selectedRuns.length > 0 ? 'mixed' : false}
                                        onChange={(event) => toggleVisibleSelection(event.target.checked)}
                                    />
                                </th>
                                <th scope="col" aria-sort={ariaSort('run')}><SortHeader label="Run" field="run" sort={sort} onSort={changeSort} /></th>
                                <th scope="col" aria-sort={ariaSort('status')}><SortHeader label="Status" field="status" sort={sort} onSort={changeSort} /></th>
                                <th scope="col" aria-sort={ariaSort('user')}><SortHeader label="Executed by" field="user" sort={sort} onSort={changeSort} /></th>
                                <th scope="col" aria-sort={ariaSort('node')}><SortHeader label="Node" field="node" sort={sort} onSort={changeSort} /></th>
                                <th scope="col" aria-sort={ariaSort('started')}><SortHeader label="Started" field="started" sort={sort} onSort={changeSort} /></th>
                                <th scope="col" aria-sort={ariaSort('duration')}><SortHeader label="Duration" field="duration" sort={sort} onSort={changeSort} /></th>
                                <th scope="col" className="list-operations-cell">
                                    <span className="list-operations-heading">Operations</span>
                                </th>
                            </tr>
                        </thead>
                        <tbody>
                            {loading && !data ? (
                                <tr>
                                    <td colSpan={8}>
                                        <EntropyLoader label={`Loading runs…`} />
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
                                                checked={selected.has(run.id)}
                                                aria-label={`Select run ${run.id}`}
                                                onKeyDown={(event) => event.stopPropagation()}
                                                onChange={(event) => {
                                                    setSelected((current) => {
                                                        const next = new Map(current)
                                                        if (event.target.checked) next.set(run.id, run)
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
                                                        <Puzzle size={16} />
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

                <Pagination
                    noun="runs"
                    state={{
                        page: page + 1,
                        pages,
                        pageSize,
                        total,
                        pageItems: items,
                        setPage: (next) => setPage(next - 1),
                        setPageSize: (size) => {
                            setPageSize(size)
                            setPage(0)
                        },
                    }}
                />
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
