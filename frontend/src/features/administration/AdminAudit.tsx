import { useEffect, useState } from 'react'
import { Download, ScrollText } from 'lucide-react'

import { auditApi, type AuditEntry, type AuditFilters, type AuditListResponse, type AuditSortField } from '../../api/audit.api'
import { useFeedback } from '../../components/feedback/FeedbackProvider'
import { useErrorToast } from '../../components/feedback/useToast'
import Dialog from '../../components/layout/Dialog'
import Pagination from '../../components/layout/Pagination'
import SortHeader from '../../components/layout/SortHeader'
import { usePageSize } from '../../components/layout/usePagination'
import { useSortState } from '../../components/layout/useSort'
import { AdminPanel, EmptyRow, SearchField } from './AdminPanel'
import { errorMessage } from './format'

const SORTS: AuditSortField[] = ['time', 'user', 'category', 'action', 'outcome', 'project']
const OUTCOME_LABELS: Record<AuditEntry['outcome'], string> = { success: 'Success', denied: 'Denied', failure: 'Failed' }

const when = (value: string) => {
    const date = new Date(value)
    return Number.isNaN(date.getTime()) ? value : date.toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'medium' })
}

/** "tasks.comments.create" -> "Tasks · comments · create" */
const actionLabel = (action: string) => {
    const [first, ...rest] = action.split('.')
    return [first.charAt(0).toUpperCase() + first.slice(1), ...rest].join(' · ').replace(/[-_]/g, ' ')
}

/** Local date input (YYYY-MM-DD) to the UTC bounds the server compares. */
const dayStart = (day: string) => (day ? new Date(`${day}T00:00:00`).toISOString() : '')
const dayEnd = (day: string) => (day ? new Date(`${day}T23:59:59.999`).toISOString() : '')

export default function AdminAudit() {
    const { notify } = useFeedback()
    const [data, setData] = useState<AuditListResponse | null>(null)
    const [loading, setLoading] = useState(true)
    const [refreshing, setRefreshing] = useState(false)
    const [error, setError] = useState<string | null>(null)
    useErrorToast(error)
    const [search, setSearch] = useState('')
    const [query, setQuery] = useState('')
    const [user, setUser] = useState('')
    const [category, setCategory] = useState('')
    const [outcome, setOutcome] = useState('')
    const [project, setProject] = useState('')
    const [since, setSince] = useState('')
    const [until, setUntil] = useState('')
    const [page, setPage] = useState(1)
    const [pageSize, setPageSize] = usePageSize('admin-audit')
    const { sort, toggle, ariaSort } = useSortState<AuditSortField>('admin-audit', SORTS, { field: 'time', order: 'desc' }, ['time'])
    const [selected, setSelected] = useState<AuditEntry | null>(null)
    const [retention, setRetention] = useState<string>('')
    const [savingRetention, setSavingRetention] = useState(false)

    // Typing searches after a short pause.
    useEffect(() => {
        const timer = window.setTimeout(() => setQuery(search.trim()), 300)
        return () => window.clearTimeout(timer)
    }, [search])

    const filters: AuditFilters = { search: query, user, category, outcome, project, since: dayStart(since), until: dayEnd(until) }
    const filterKey = JSON.stringify(filters)

    const [reload, setReload] = useState(0)
    const load = () => setReload((count) => count + 1)

    useEffect(() => {
        let active = true
        auditApi
            .list(JSON.parse(filterKey) as AuditFilters, {
                limit: pageSize,
                offset: (page - 1) * pageSize,
                sort: sort.field,
                order: sort.order,
            })
            .then((result) => {
                if (!active) return
                setData(result)
                setRetention((current) => current || String(result.retention_days))
                setError(null)
            })
            .catch((cause: unknown) => {
                if (active) setError(errorMessage(cause, 'Unable to load the audit log.'))
            })
            .finally(() => {
                if (!active) return
                setLoading(false)
                setRefreshing(false)
            })
        return () => {
            active = false
        }
    }, [filterKey, page, pageSize, sort.field, sort.order, reload])

    const filter = (apply: () => void) => {
        apply()
        setPage(1)
    }

    const saveRetention = async () => {
        const days = Number(retention)
        if (!Number.isInteger(days) || days < 1 || days > 3650) {
            notify.error('Keep audit entries for 1 to 3650 days.', { title: 'Audit retention' })
            return
        }
        setSavingRetention(true)
        try {
            const result = await auditApi.setRetention(days)
            notify.success(
                `Entries are kept for ${result.retention_days} days${result.removed ? `; ${result.removed} older entr${result.removed === 1 ? 'y was' : 'ies were'} removed` : ''}.`,
                { title: 'Audit retention' },
            )
            load()
        } catch (cause) {
            notify.error(errorMessage(cause, 'Unable to save the retention.'), { title: 'Audit retention' })
        } finally {
            setSavingRetention(false)
        }
    }

    const facets = data?.facets ?? { users: [], categories: [], projects: [] }
    const items = data?.items ?? []
    const total = data?.total ?? 0
    const filtering = Boolean(query || user || category || outcome || project || since || until)
    const changeSort = (field: AuditSortField) => {
        toggle(field)
        setPage(1)
    }

    return (
        <div className="list-page admin-page">
            <AdminPanel
                title="Audit"
                count={total}
                subtitle="Who did what, when and from where: every change made in the browser or with ent, sign-ins and downloads."
                error={error}
                refreshing={refreshing || loading}
                onRefresh={() => {
                    setRefreshing(true)
                    load()
                }}
                actions={
                    <a className="entropy-button entropy-button-secondary entropy-button-sm" href={auditApi.exportUrl(filters)} download title="Download the matching entries as CSV (up to 100,000)">
                        <Download size={15} /> Export CSV
                    </a>
                }
                toolbar={
                    <div className="audit-toolbar">
                        <SearchField value={search} onChange={(value) => filter(() => setSearch(value))} placeholder="Search user, action, target, path or address…" />
                        <select className="entropy-select" aria-label="User" value={user} onChange={(event) => filter(() => setUser(event.target.value))}>
                            <option value="">All users</option>
                            {facets.users.map((name) => <option key={name} value={name}>{name}</option>)}
                        </select>
                        <select className="entropy-select" aria-label="Category" value={category} onChange={(event) => filter(() => setCategory(event.target.value))}>
                            <option value="">All areas</option>
                            {facets.categories.map((name) => <option key={name} value={name}>{actionLabel(name)}</option>)}
                        </select>
                        <select className="entropy-select" aria-label="Outcome" value={outcome} onChange={(event) => filter(() => setOutcome(event.target.value))}>
                            <option value="">Any outcome</option>
                            <option value="success">Success</option>
                            <option value="denied">Denied</option>
                            <option value="failure">Failed</option>
                        </select>
                        {facets.projects.length > 0 && (
                            <select className="entropy-select" aria-label="Project" value={project} onChange={(event) => filter(() => setProject(event.target.value))}>
                                <option value="">All projects</option>
                                {facets.projects.map((name) => <option key={name} value={name}>{name}</option>)}
                            </select>
                        )}
                        <label className="audit-date">From<input type="date" value={since} max={until || undefined} onChange={(event) => filter(() => setSince(event.target.value))} /></label>
                        <label className="audit-date">To<input type="date" value={until} min={since || undefined} onChange={(event) => filter(() => setUntil(event.target.value))} /></label>
                        {filtering && (
                            <button type="button" className="entropy-button entropy-button-ghost entropy-button-sm" onClick={() => filter(() => {
                                setSearch(''); setUser(''); setCategory(''); setOutcome(''); setProject(''); setSince(''); setUntil('')
                            })}>
                                Clear filters
                            </button>
                        )}
                    </div>
                }
            >
                <div className="list-table-wrap">
                    <table className="list-table audit-table">
                        <thead>
                            <tr>
                                <th aria-sort={ariaSort('time')}><SortHeader label="When" field="time" sort={sort} onSort={changeSort} /></th>
                                <th aria-sort={ariaSort('user')}><SortHeader label="User" field="user" sort={sort} onSort={changeSort} /></th>
                                <th aria-sort={ariaSort('action')}><SortHeader label="Action" field="action" sort={sort} onSort={changeSort} /></th>
                                <th>Target</th>
                                <th aria-sort={ariaSort('outcome')}><SortHeader label="Outcome" field="outcome" sort={sort} onSort={changeSort} /></th>
                                <th aria-sort={ariaSort('project')}><SortHeader label="Project" field="project" sort={sort} onSort={changeSort} /></th>
                                <th>From</th>
                            </tr>
                        </thead>
                        <tbody>
                            {loading && !data ? (
                                <EmptyRow colSpan={7} title="Loading the audit log…" text="Fetching entries." />
                            ) : items.length === 0 ? (
                                <EmptyRow colSpan={7} title={filtering ? 'No matching entries' : 'Nothing recorded yet'} text={filtering ? 'Try other filters.' : 'Changes, sign-ins and downloads appear here as they happen.'} />
                            ) : (
                                items.map((entry) => (
                                    <tr key={entry.id} className="audit-row" onClick={() => setSelected(entry)} tabIndex={0} onKeyDown={(event) => { if (event.key === 'Enter') setSelected(entry) }}>
                                        <td className="list-cell-text audit-when">{when(entry.created_at)}</td>
                                        <td>{entry.username ?? <span className="audit-muted">unknown</span>}</td>
                                        <td><span className="audit-action">{actionLabel(entry.action)}</span></td>
                                        <td className="audit-target" title={entry.target ?? undefined}>{entry.target ?? <span className="audit-muted">—</span>}</td>
                                        <td><span className={`audit-outcome is-${entry.outcome}`}>{OUTCOME_LABELS[entry.outcome]}{entry.status ? ` · ${entry.status}` : ''}</span></td>
                                        <td>{entry.project ?? <span className="audit-muted">—</span>}</td>
                                        <td className="list-cell-text">{entry.address ?? '—'}<small className="audit-source">{entry.source === 'cli' ? 'ent' : 'browser'}</small></td>
                                    </tr>
                                ))
                            )}
                        </tbody>
                    </table>
                </div>
                <Pagination
                    noun="entries"
                    state={{
                        page,
                        pages: Math.max(1, Math.ceil(total / pageSize)),
                        pageSize,
                        total,
                        pageItems: items,
                        setPage,
                        setPageSize: (size) => {
                            setPageSize(size)
                            setPage(1)
                        },
                    }}
                />
                {data && (
                    <div className="audit-retention">
                        <ScrollText size={15} aria-hidden="true" />
                        {data.can_manage ? (
                            <>
                                <label>
                                    Keep entries for
                                    <input type="number" min={1} max={3650} value={retention} onChange={(event) => setRetention(event.target.value)} aria-label="Retention in days" />
                                    days
                                </label>
                                <button type="button" className="entropy-button entropy-button-secondary entropy-button-sm" disabled={savingRetention || Number(retention) === data.retention_days} onClick={() => void saveRetention()}>
                                    Save
                                </button>
                                <small>Older entries are removed automatically.</small>
                            </>
                        ) : (
                            <span>Entries are kept for {data.retention_days} days.</span>
                        )}
                    </div>
                )}
            </AdminPanel>

            {selected && <AuditDetails entry={selected} onClose={() => setSelected(null)} />}
        </div>
    )
}

function AuditDetails({ entry, onClose }: { entry: AuditEntry; onClose: () => void }) {
    const rows: [string, string][] = [
        ['When', when(entry.created_at)],
        ['User', entry.username ?? 'unknown'],
        ['Action', `${actionLabel(entry.action)} (${entry.action})`],
        ['Target', entry.target ?? '—'],
        ['Outcome', `${OUTCOME_LABELS[entry.outcome]}${entry.status ? ` (HTTP ${entry.status})` : ''}`],
        ['Project', entry.project ?? '—'],
        ['Request', [entry.method, entry.path].filter(Boolean).join(' ') || '—'],
        ['Duration', entry.duration_ms !== null ? `${entry.duration_ms} ms` : '—'],
        ['From', `${entry.address ?? 'unknown address'} · ${entry.source === 'cli' ? 'ent command line' : 'browser'}`],
        ['Client', entry.user_agent ?? '—'],
    ]
    const details = Object.keys(entry.details ?? {}).length ? JSON.stringify(entry.details, null, 2) : null
    return (
        <Dialog title="Audit entry" subtitle={`#${entry.id}`} icon={<ScrollText size={18} />} onClose={onClose} className="admin-dialog audit-dialog"
            footer={<button type="button" className="entropy-button entropy-button-primary" onClick={onClose} data-autofocus>Close</button>}
        >
            <dl className="audit-details">
                {rows.map(([label, value]) => (
                    <div key={label}>
                        <dt>{label}</dt>
                        <dd>{value}</dd>
                    </div>
                ))}
            </dl>
            {details && <pre className="audit-json">{details}</pre>}
        </Dialog>
    )
}
