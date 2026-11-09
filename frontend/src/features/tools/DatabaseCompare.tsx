import { useEffect, useMemo, useState } from 'react'
import { AlertCircle, Database, FileDown, LoaderCircle, Play, ShieldCheck, Square, X } from 'lucide-react'

import {
    clashApi,
    compareLabel,
    isCompareActive,
    type ClashCompareJob,
    type ClashDatabaseResult,
    type ClashDatabaseSide,
    type ClashDataItem,
    type ClashDdlItem,
    type ClashRowsResult,
    type ClashStatus,
    type ClashVaultReference,
} from '../../api/clash.api'
import { vaultApi, type VaultNamespace } from '../../api/vault.api'
import { ApiError } from '../../services/api'
import { VISION_REFRESH_EVENT } from '../vision/bus'
import DiffPanel from './DiffPanel'
import type { LanguageId } from './files'

const STATUS_LABELS: Record<ClashStatus, string> = {
    same: 'Same',
    different: 'Different',
    only_left: 'Only left',
    only_right: 'Only right',
    error: 'Error',
    not_compared: 'Not compared',
}

const EMPTY_SIDE: ClashDatabaseSide = { host: '', port: 1521, sid: '', schema_name: '', namespace: '', key: '' }

/** The server's OBJECT_TYPES, in the order people think of them. */
const OBJECT_TYPES: { id: string; label: string }[] = [
    { id: 'TABLE', label: 'Tables' },
    { id: 'VIEW', label: 'Views' },
    { id: 'MATERIALIZED VIEW', label: 'Materialized views' },
    { id: 'INDEX', label: 'Indexes' },
    { id: 'SEQUENCE', label: 'Sequences' },
    { id: 'TRIGGER', label: 'Triggers' },
    { id: 'SYNONYM', label: 'Synonyms' },
    { id: 'PROCEDURE', label: 'Procedures' },
    { id: 'FUNCTION', label: 'Functions' },
    { id: 'PACKAGE', label: 'Packages' },
    { id: 'PACKAGE BODY', label: 'Package bodies' },
    { id: 'TYPE', label: 'Types' },
    { id: 'TYPE BODY', label: 'Type bodies' },
]
const ALL_OBJECT_TYPES = OBJECT_TYPES.map((item) => item.id)

const POLL_MS = 1_500
/** Quiet this long, and the page says what that can mean. */
const QUIET_NOTICE_SECONDS = 60

function tellVision(): void {
    window.dispatchEvent(new Event(VISION_REFRESH_EVENT))
}

function duration(seconds: number): string {
    const minutes = Math.floor(seconds / 60)
    if (minutes === 0) return `${seconds}s`
    const hours = Math.floor(minutes / 60)
    return hours === 0 ? `${minutes}m ${seconds % 60}s` : `${hours}h ${minutes % 60}m`
}

function sideIsComplete(side: ClashDatabaseSide): boolean {
    return Boolean(side.host.trim() && side.sid.trim() && side.schema_name.trim() && side.namespace && side.key)
}

function messageOf(error: unknown): string {
    return error instanceof Error ? error.message : 'The comparison failed.'
}

function SideForm({
    title,
    side,
    namespaces,
    onChange,
}: {
    title: string
    side: ClashDatabaseSide
    namespaces: VaultNamespace[]
    onChange: (side: ClashDatabaseSide) => void
}) {
    const [keys, setKeys] = useState<string[]>([])

    useEffect(() => {
        if (!side.namespace) return
        let active = true
        vaultApi
            .listEntries(side.namespace)
            .then((result) => {
                if (active) setKeys(result.items.map((item) => item.key))
            })
            .catch(() => {
                if (active) setKeys([])
            })
        return () => {
            active = false
        }
    }, [side.namespace])

    const text = (label: string, field: 'host' | 'sid' | 'schema_name', placeholder: string) => (
        <label className="admin-field">
            <span>{label}</span>
            <input
                value={side[field]}
                placeholder={placeholder}
                autoComplete="off"
                spellCheck={false}
                onChange={(event) => onChange({ ...side, [field]: event.target.value })}
            />
        </label>
    )

    return (
        <fieldset className="tools-db-side">
            <legend>{title}</legend>
            <div className="admin-form-grid">
                {text('Host', 'host', 'db1.example.com')}
                <label className="admin-field">
                    <span>Port</span>
                    <input
                        type="number"
                        min={1}
                        max={65535}
                        value={side.port}
                        onChange={(event) => onChange({ ...side, port: Number(event.target.value) })}
                    />
                </label>
                {text('SID', 'sid', 'SID1')}
                {text('Schema', 'schema_name', 'APP1')}
                <label className="admin-field">
                    <span>Vault namespace</span>
                    <select
                        className="entropy-select"
                        value={side.namespace}
                        onChange={(event) => {
                            setKeys([])
                            onChange({ ...side, namespace: event.target.value, key: '' })
                        }}
                    >
                        <option value="">Choose…</option>
                        {namespaces.map((item) => (
                            <option key={item.id} value={item.name}>
                                {item.name}
                            </option>
                        ))}
                    </select>
                </label>
                <label className="admin-field">
                    <span>Credentials key</span>
                    <select
                        className="entropy-select"
                        value={side.key}
                        disabled={!side.namespace}
                        onChange={(event) => onChange({ ...side, key: event.target.value })}
                    >
                        <option value="">Choose…</option>
                        {keys.map((key) => (
                            <option key={key} value={key}>
                                {key}
                            </option>
                        ))}
                    </select>
                </label>
            </div>
        </fieldset>
    )
}

/** Names typed as "A, B" or one per line, as the server reads them. */
function typedTables(text: string): string[] {
    const names = text
        .split(/[,;\s]+/)
        .map((name) => name.trim().toUpperCase())
        .filter(Boolean)
    return [...new Set(names)]
}

/**
 * Which tables to compare by name: typed, or a list kept in the Vault (a comma separated
 * value, a JSON list, or {"tables": [...]}), or both. With the name pattern, an object in
 * the list or like the pattern is compared.
 */
function TablesPicker({
    text,
    onText,
    vault,
    onVault,
    namespaces,
    disabled,
}: {
    text: string
    onText: (text: string) => void
    vault: ClashVaultReference | null
    onVault: (vault: ClashVaultReference | null) => void
    namespaces: VaultNamespace[]
    disabled: boolean
}) {
    const [keys, setKeys] = useState<string[]>([])
    const namespace = vault?.namespace ?? ''
    const typed = typedTables(text)

    useEffect(() => {
        if (!namespace) return
        let active = true
        vaultApi
            .listEntries(namespace)
            .then((result) => {
                if (active) setKeys(result.items.map((item) => item.key))
            })
            .catch(() => {
                if (active) setKeys([])
            })
        return () => {
            active = false
        }
    }, [namespace])

    return (
        <fieldset className="tools-db-types tools-db-tables" disabled={disabled}>
            <legend>Tables</legend>
            <div className="tools-db-tables-grid">
                <label className="admin-field">
                    <span>
                        Table names {typed.length > 0 && <small className="tools-db-note">({typed.length})</small>}
                    </span>
                    <textarea
                        rows={2}
                        value={text}
                        placeholder="ORDERS, ORDER_ITEMS, CUSTOMERS"
                        spellCheck={false}
                        onChange={(event) => onText(event.target.value)}
                    />
                </label>
                <label className="admin-field">
                    <span>List in the Vault (optional)</span>
                    <select
                        className="entropy-select"
                        value={namespace}
                        onChange={(event) => {
                            setKeys([])
                            onVault(event.target.value ? { namespace: event.target.value, key: '' } : null)
                        }}
                    >
                        <option value="">None</option>
                        {namespaces.map((item) => (
                            <option key={item.id} value={item.name}>
                                {item.name}
                            </option>
                        ))}
                    </select>
                </label>
                <label className="admin-field">
                    <span>Key</span>
                    <select
                        className="entropy-select"
                        value={vault?.key ?? ''}
                        disabled={!namespace}
                        onChange={(event) => onVault({ namespace, key: event.target.value })}
                    >
                        <option value="">Choose…</option>
                        {keys.map((key) => (
                            <option key={key} value={key}>
                                {key}
                            </option>
                        ))}
                    </select>
                </label>
            </div>
            <p className="tools-db-note">
                Separate names with commas or new lines; the Vault entry may hold the same, or a JSON list. Leave
                everything empty to compare the whole schema. A table in the list <em>or</em> like the name pattern
                is compared; for DDL, its indexes and triggers come too.
            </p>
        </fieldset>
    )
}

function CompareProgressPanel({
    job,
    unreachable,
    onStop,
}: {
    job: ClashCompareJob
    unreachable: boolean
    onStop: () => void
}) {
    const measured = job.phase !== 'analyze' && job.total > 0

    return (
        <div className="tools-db-progress" role="status">
            <div className="tools-db-progress-heading">
                <LoaderCircle size={16} className="entropy-spin" aria-hidden="true" />
                <strong>{compareLabel(job)}</strong>
                <span className="tools-db-note">{duration(job.elapsed_seconds)}</span>
                <button
                    type="button"
                    className="entropy-button entropy-button-secondary entropy-button-sm"
                    disabled={job.stopping}
                    onClick={onStop}
                >
                    <Square size={13} />
                    Stop
                </button>
            </div>
            {measured ? (
                <progress max={job.total} value={job.done} aria-label="Comparison progress" />
            ) : (
                <progress aria-label="Comparison progress" />
            )}
            <p className="tools-db-note">
                {job.left} and {job.right}
                {job.current ? `. Now on ${job.current}` : ''}
                {job.phase === 'data' && job.rows_total > 0
                    ? `. About ${job.rows_done.toLocaleString()} of ${job.rows_total.toLocaleString()} rows.`
                    : '.'}
            </p>
            {job.stopping && <p className="tools-db-note">Stopping once the step under way finishes. A large table can take a while.</p>}
            {unreachable && <p className="tools-db-note">Can not reach the server just now. Trying again.</p>}
            {!job.stopping && job.quiet_seconds >= QUIET_NOTICE_SECONDS && (
                <p className="tools-db-note">
                    No step has finished for {duration(job.quiet_seconds)}. A large table can take this long; one step
                    stops by itself after 30 minutes. You can leave this page: Vision keeps showing the progress.
                </p>
            )}
        </div>
    )
}

function ConsentPanel({
    job,
    busy,
    onConfirm,
    onCancel,
}: {
    job: ClashCompareJob
    busy: boolean
    onConfirm: (skipLarge: boolean) => void
    onCancel: () => void
}) {
    const estimate = job.estimate
    if (!estimate) return null
    const skippable = estimate.large_count + estimate.unknown_count

    return (
        <div className="tools-db-consent" role="alertdialog" aria-labelledby="tools-db-consent-title">
            <strong id="tools-db-consent-title">This data comparison may take a long time</strong>
            <p className="tools-db-note">
                It reads every row of {estimate.tables.toLocaleString()} tables on both databases: about{' '}
                {estimate.rows.toLocaleString()} rows a side, according to Oracle's statistics, which can be out of date.
                {estimate.unknown_count > 0 &&
                    ` ${estimate.unknown_count.toLocaleString()} more tables have no statistics, so their size is unknown.`}{' '}
                Nothing has been compared yet.
            </p>
            {estimate.largest.length > 0 && (
                <div className="tools-db-scroll">
                    <table>
                        <thead>
                            <tr>
                                <th>Largest tables</th>
                                <th>Estimated rows</th>
                            </tr>
                        </thead>
                        <tbody>
                            {estimate.largest.map((item) => (
                                <tr key={item.table}>
                                    <td>{item.table}</td>
                                    <td>{item.rows.toLocaleString()}</td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                </div>
            )}
            <div className="tools-db-consent-actions">
                <button type="button" className="entropy-button entropy-button-primary" disabled={busy} onClick={() => onConfirm(false)}>
                    Compare everything
                </button>
                {skippable > 0 && (
                    <button type="button" className="entropy-button entropy-button-secondary" disabled={busy} onClick={() => onConfirm(true)}>
                        Skip {skippable.toLocaleString()} large or unknown {skippable === 1 ? 'table' : 'tables'}
                    </button>
                )}
                <button type="button" className="entropy-button entropy-button-ghost" disabled={busy} onClick={onCancel}>
                    Cancel
                </button>
            </div>
        </div>
    )
}

function Counts({ items, label }: { items: { status: ClashStatus }[]; label: string }) {
    const count = (status: ClashStatus) => items.filter((item) => item.status === status).length
    const problems = count('error') + count('not_compared')

    return (
        <div className="tools-folder-counts" aria-live="polite">
            <span className="tools-count-chip">
                <strong>{items.length.toLocaleString()}</strong> {label}
            </span>
            <span className="tools-count-chip is-identical">
                <strong>{count('same').toLocaleString()}</strong> same
            </span>
            <span className="tools-count-chip is-different">
                <strong>{count('different').toLocaleString()}</strong> different
            </span>
            <span className="tools-count-chip is-left-only">
                <strong>{count('only_left').toLocaleString()}</strong> only left
            </span>
            <span className="tools-count-chip is-right-only">
                <strong>{count('only_right').toLocaleString()}</strong> only right
            </span>
            {problems > 0 && (
                <span className="tools-count-chip is-different">
                    <strong>{problems.toLocaleString()}</strong> not checked
                </span>
            )}
        </div>
    )
}

function RowTable({
    title,
    columns,
    rows,
    total,
}: {
    title: string
    columns: string[]
    rows: string[][]
    total: number
}) {
    if (total === 0) return null

    return (
        <section className="tools-db-rows">
            <h4>
                {title}: {total.toLocaleString()}
                {rows.length < total ? ` (first ${rows.length.toLocaleString()} shown)` : ''}
            </h4>
            <div className="tools-db-scroll">
                <table>
                    <thead>
                        <tr>
                            {columns.map((column) => (
                                <th key={column}>{column}</th>
                            ))}
                        </tr>
                    </thead>
                    <tbody>
                        {rows.map((row, index) => (
                            <tr key={index}>
                                {row.map((value, cell) => (
                                    <td key={cell}>{value}</td>
                                ))}
                            </tr>
                        ))}
                    </tbody>
                </table>
            </div>
        </section>
    )
}

function RowsView({ rows, left, right }: { rows: ClashRowsResult; left: string; right: string }) {
    return (
        <>
            <p className="tools-db-note">
                {rows.key.length > 0
                    ? `Rows are matched on the primary key (${rows.key.join(', ')}).`
                    : 'No shared primary key: rows are matched whole, so a changed row shows on both sides.'}{' '}
                {rows.same.toLocaleString()} rows are the same.
            </p>
            {rows.truncated && (
                <div className="entropy-alert entropy-alert-warning" role="status">
                    <AlertCircle size={16} />
                    <span>
                        This table has more than {rows.limit.toLocaleString()} rows on a side, so only the first
                        rows in key order were compared. There may be more differences.
                    </span>
                </div>
            )}
            {rows.changed_count > 0 && (
                <section className="tools-db-rows">
                    <h4>
                        Changed rows: {rows.changed_count.toLocaleString()}
                        {rows.changed.length < rows.changed_count
                            ? ` (first ${rows.changed.length.toLocaleString()} shown)`
                            : ''}
                    </h4>
                    <div className="tools-db-scroll">
                        <table>
                            <thead>
                                <tr>
                                    <th>Key</th>
                                    <th>Column</th>
                                    <th>{left}</th>
                                    <th>{right}</th>
                                </tr>
                            </thead>
                            <tbody>
                                {rows.changed.flatMap((row) =>
                                    row.columns.map((column) => {
                                        const position = rows.columns.indexOf(column)
                                        return (
                                            <tr key={`${row.key.join('|')}:${column}`}>
                                                <td>{row.key.join(', ')}</td>
                                                <td>{column}</td>
                                                <td>{row.left[position]}</td>
                                                <td>{row.right[position]}</td>
                                            </tr>
                                        )
                                    }),
                                )}
                            </tbody>
                        </table>
                    </div>
                </section>
            )}
            <RowTable title={`Only in ${left}`} columns={rows.columns} rows={rows.only_left} total={rows.only_left_count} />
            <RowTable title={`Only in ${right}`} columns={rows.columns} rows={rows.only_right} total={rows.only_right_count} />
            {rows.changed_count + rows.only_left_count + rows.only_right_count === 0 && (
                <p className="tools-db-note">No differing rows were found among the rows read.</p>
            )}
        </>
    )
}

function DataDetails({ item }: { item: ClashDataItem }) {
    const lists: [string, string[] | undefined][] = [
        ['Columns only left', item.columns_only_left],
        ['Columns only right', item.columns_only_right],
        ['Columns not compared (LOB, LONG or object types)', item.columns_not_compared],
    ]

    return (
        <>
            {lists.map(([label, values]) =>
                values && values.length > 0 ? (
                    <p key={label} className="tools-db-note">
                        {label}: {values.join(', ')}
                    </p>
                ) : null,
            )}
        </>
    )
}

export default function DatabaseCompare() {
    const [namespaces, setNamespaces] = useState<VaultNamespace[]>([])
    const [left, setLeft] = useState<ClashDatabaseSide>(EMPTY_SIDE)
    const [right, setRight] = useState<ClashDatabaseSide>(EMPTY_SIDE)
    const [ddl, setDdl] = useState(true)
    const [data, setData] = useState(true)
    const [nameFilter, setNameFilter] = useState('')
    const [tablesText, setTablesText] = useState('')
    const [tablesVault, setTablesVault] = useState<ClashVaultReference | null>(null)
    const [objectTypes, setObjectTypes] = useState<string[]>(ALL_OBJECT_TYPES)
    const [job, setJob] = useState<ClashCompareJob | null>(null)
    const [starting, setStarting] = useState(false)
    const [answering, setAnswering] = useState(false)
    const [exporting, setExporting] = useState(false)
    const [unreachable, setUnreachable] = useState(false)
    const [error, setError] = useState('')
    const [result, setResult] = useState<ClashDatabaseResult | null>(null)
    const [view, setView] = useState<'ddl' | 'data'>('ddl')
    const [differencesOnly, setDifferencesOnly] = useState(true)
    const [selectedDdl, setSelectedDdl] = useState<ClashDdlItem | null>(null)
    const [selectedTable, setSelectedTable] = useState<ClashDataItem | null>(null)
    const [rows, setRows] = useState<ClashRowsResult | null>(null)
    const [rowsLoading, setRowsLoading] = useState(false)
    const [rowsError, setRowsError] = useState('')
    const [language, setLanguage] = useState<LanguageId>('sql')

    useEffect(() => {
        let active = true
        vaultApi
            .listNamespaces()
            .then((response) => {
                if (active) setNamespaces(response.items)
            })
            .catch(() => {
                if (active) setNamespaces([])
            })
        return () => {
            active = false
        }
    }, [])

    // Pick up what this person has under way, or last finished, in this project.
    useEffect(() => {
        let active = true
        clashApi
            .current()
            .then(({ job: current }) => {
                if (!active || !current) return
                setJob((existing) => existing ?? current)
                setLeft(current.sides.left)
                setRight(current.sides.right)
                setDdl(current.ddl)
                setData(current.data)
                setNameFilter(current.name_filter ?? '')
                setTablesText((current.tables ?? []).join(', '))
                setTablesVault(current.tables_vault ?? null)
                setObjectTypes(current.object_types ?? ALL_OBJECT_TYPES)
            })
            .catch(() => undefined)
        return () => {
            active = false
        }
    }, [])

    const jobId = job?.id ?? null
    const jobActive = job !== null && isCompareActive(job)

    useEffect(() => {
        if (!jobId || !jobActive) return
        let alive = true
        let timer: number | undefined

        const tick = async () => {
            if (!document.hidden) {
                try {
                    const next = await clashApi.job(jobId)
                    if (!alive) return
                    setUnreachable(false)
                    setJob(next)
                    if (!isCompareActive(next)) return
                } catch (caught) {
                    if (!alive) return
                    if (caught instanceof ApiError && caught.status === 404) {
                        setJob(null)
                        setError('The comparison is gone: the Entropy server may have restarted. Start it again.')
                        return
                    }
                    setUnreachable(true)
                }
            }
            timer = window.setTimeout(() => void tick(), POLL_MS)
        }

        timer = window.setTimeout(() => void tick(), POLL_MS)
        return () => {
            alive = false
            window.clearTimeout(timer)
        }
    }, [jobId, jobActive])

    const finishedId = job?.state === 'done' ? job.id : null

    useEffect(() => {
        if (!finishedId) return
        let alive = true
        clashApi
            .result(finishedId)
            .then((response) => {
                if (!alive) return
                setResult(response)
                setView(response.ddl ? 'ddl' : 'data')
            })
            .catch((caught: unknown) => {
                if (alive) setError(messageOf(caught))
            })
        return () => {
            alive = false
        }
    }, [finishedId])

    const hasTables = objectTypes.includes('TABLE')
    const compareData = data && hasTables
    const ready =
        sideIsComplete(left) &&
        sideIsComplete(right) &&
        (ddl ? objectTypes.length > 0 : compareData) &&
        // A Vault namespace chosen for the table list needs its key too.
        (!tablesVault || Boolean(tablesVault.key)) &&
        !jobActive &&
        !starting

    const toggleType = (id: string, on: boolean) =>
        setObjectTypes((current) => ALL_OBJECT_TYPES.filter((item) => (item === id ? on : current.includes(item))))

    const run = async () => {
        setStarting(true)
        setError('')
        setResult(null)
        setSelectedDdl(null)
        setSelectedTable(null)
        setRows(null)
        try {
            const started = await clashApi.compare({
                left,
                right,
                ddl,
                data: compareData,
                name_filter: nameFilter.trim() || null,
                tables: typedTables(tablesText),
                tables_vault: tablesVault?.key ? tablesVault : null,
                object_types: ddl && objectTypes.length < ALL_OBJECT_TYPES.length ? objectTypes : null,
            })
            setJob(started)
            tellVision()
        } catch (caught) {
            setError(messageOf(caught))
        } finally {
            setStarting(false)
        }
    }

    const answer = async (action: () => Promise<ClashCompareJob>) => {
        setAnswering(true)
        try {
            setJob(await action())
            tellVision()
        } catch (caught) {
            setError(messageOf(caught))
        } finally {
            setAnswering(false)
        }
    }

    const exportReport = async () => {
        if (!job) return
        setExporting(true)
        try {
            await clashApi.downloadReport(job)
        } catch (caught) {
            setError(messageOf(caught))
        } finally {
            setExporting(false)
        }
    }

    const openTable = async (item: ClashDataItem) => {
        setSelectedTable(item)
        setRows(null)
        setRowsError('')
        if (item.status !== 'different' || !job) return
        setRowsLoading(true)
        try {
            // The sides the result was made with: the form may have changed since.
            setRows(await clashApi.rows({ ...job.sides, table: item.table }))
        } catch (caught) {
            setRowsError(messageOf(caught))
        } finally {
            setRowsLoading(false)
        }
    }

    const ddlItems = useMemo(
        () => (result?.ddl ?? []).filter((item) => !differencesOnly || item.status !== 'same'),
        [result, differencesOnly],
    )
    const dataItems = useMemo(
        () => (result?.data ?? []).filter((item) => !differencesOnly || item.status !== 'same'),
        [result, differencesOnly],
    )

    return (
        <div className="tools-db-compare">
            <div className="tools-folder-local-notice" role="note">
                <ShieldCheck size={16} aria-hidden="true" />
                <span>
                    Runs on the Entropy server with SQL*Plus and only reads. Credentials come from this project's
                    Vault as JSON with <code>username</code> and <code>password</code>, and you need Vault read
                    access. Rows are only read when you open a table.
                </span>
            </div>

            <div className="tools-db-sides">
                <SideForm title="Left" side={left} namespaces={namespaces} onChange={setLeft} />
                <SideForm title="Right" side={right} namespaces={namespaces} onChange={setRight} />
            </div>

            <div className="tools-db-actions">
                <label className="tools-check">
                    <input type="checkbox" checked={ddl} onChange={(event) => setDdl(event.target.checked)} /> DDL
                </label>
                <label className="tools-check" title={hasTables ? undefined : 'Data is compared for tables: choose Tables below.'}>
                    <input
                        type="checkbox"
                        checked={compareData}
                        disabled={!hasTables}
                        onChange={(event) => setData(event.target.checked)}
                    />{' '}
                    Data
                </label>
                <label className="admin-field tools-db-filter">
                    <span>Names like</span>
                    <input
                        value={nameFilter}
                        placeholder="ORDER%"
                        spellCheck={false}
                        onChange={(event) => setNameFilter(event.target.value)}
                    />
                </label>
                <button type="button" className="entropy-button entropy-button-primary" disabled={!ready} onClick={() => void run()}>
                    {jobActive || starting ? <LoaderCircle size={15} className="entropy-spin" /> : <Play size={15} />}
                    {jobActive || starting ? 'Comparing…' : 'Compare'}
                </button>
            </div>

            <TablesPicker
                text={tablesText}
                onText={setTablesText}
                vault={tablesVault}
                onVault={setTablesVault}
                namespaces={namespaces}
                disabled={jobActive || starting}
            />

            <fieldset className="tools-db-types" disabled={!ddl}>
                <legend>Object types</legend>
                <div className="tools-db-types-list">
                    {OBJECT_TYPES.map((item) => (
                        <label key={item.id} className="tools-check">
                            <input
                                type="checkbox"
                                checked={objectTypes.includes(item.id)}
                                onChange={(event) => toggleType(item.id, event.target.checked)}
                            />{' '}
                            {item.label}
                        </label>
                    ))}
                </div>
                <div className="tools-db-types-actions">
                    <button type="button" className="tools-db-link" onClick={() => setObjectTypes(ALL_OBJECT_TYPES)}>
                        All
                    </button>
                    <button type="button" className="tools-db-link" onClick={() => setObjectTypes([])}>
                        None
                    </button>
                </div>
            </fieldset>

            {job && job.state === 'waiting' && (
                <ConsentPanel
                    job={job}
                    busy={answering}
                    onConfirm={(skipLarge) => void answer(() => clashApi.confirm(job.id, skipLarge))}
                    onCancel={() => void answer(() => clashApi.stop(job.id))}
                />
            )}

            {job && (job.state === 'analyzing' || job.state === 'running') && (
                <CompareProgressPanel
                    job={job}
                    unreachable={unreachable}
                    onStop={() => void answer(() => clashApi.stop(job.id))}
                />
            )}

            {job?.state === 'stopped' && (
                <p className="tools-db-note" role="status">
                    {job.error ?? 'The comparison was stopped.'}
                </p>
            )}

            {job?.state === 'failed' && (
                <div className="entropy-alert entropy-alert-error" role="alert">
                    <AlertCircle size={16} />
                    <span>{job.error}</span>
                </div>
            )}

            {error && (
                <div className="entropy-alert entropy-alert-error" role="alert">
                    <AlertCircle size={16} />
                    <span>{error}</span>
                </div>
            )}

            {!result && !job && !starting && !error && (
                <div className="tools-empty">
                    <Database size={22} aria-hidden="true" />
                    <strong>Choose two schemas to compare</strong>
                    <span>For example SID1-APP1 and SID2-APP1.</span>
                </div>
            )}

            {result && (
                <>
                    <div className="tools-folder-summary">
                        <Counts
                            items={view === 'ddl' ? result.ddl ?? [] : result.data ?? []}
                            label={view === 'ddl' ? 'objects' : 'tables'}
                        />
                        <button
                            type="button"
                            className="entropy-button entropy-button-secondary entropy-button-sm"
                            disabled={exporting || !job}
                            onClick={() => void exportReport()}
                        >
                            {exporting ? <LoaderCircle size={14} className="entropy-spin" /> : <FileDown size={14} />}
                            Export report (HTML)
                        </button>
                        <div className="tools-segmented" role="group" aria-label="Show">
                            {result.ddl && result.data && (
                                <>
                                    <button type="button" aria-pressed={view === 'ddl'} onClick={() => setView('ddl')}>
                                        DDL
                                    </button>
                                    <button type="button" aria-pressed={view === 'data'} onClick={() => setView('data')}>
                                        Data
                                    </button>
                                </>
                            )}
                            <button
                                type="button"
                                aria-pressed={differencesOnly}
                                onClick={() => setDifferencesOnly((value) => !value)}
                            >
                                Differences only
                            </button>
                        </div>
                    </div>

                    {view === 'ddl' && selectedDdl && (
                        <div className="tools-folder-diff">
                            <div className="tools-folder-diff-heading">
                                <strong>
                                    {selectedDdl.type} {selectedDdl.name}
                                </strong>
                                <button
                                    type="button"
                                    className="entropy-button entropy-button-ghost entropy-button-icon"
                                    aria-label="Close differences"
                                    title="Close"
                                    onClick={() => setSelectedDdl(null)}
                                >
                                    <X size={14} />
                                </button>
                            </div>
                            {selectedDdl.error ? (
                                <div className="entropy-alert entropy-alert-warning" role="alert">
                                    <AlertCircle size={16} />
                                    <span>{selectedDdl.error}</span>
                                </div>
                            ) : (
                                <DiffPanel
                                    original={selectedDdl.left ?? ''}
                                    modified={selectedDdl.right ?? ''}
                                    originalLabel={result.left}
                                    modifiedLabel={result.right}
                                    language={language}
                                    onLanguageChange={setLanguage}
                                />
                            )}
                        </div>
                    )}

                    {view === 'data' && selectedTable && (
                        <div className="tools-folder-diff">
                            <div className="tools-folder-diff-heading">
                                <strong>{selectedTable.table}</strong>
                                <button
                                    type="button"
                                    className="entropy-button entropy-button-ghost entropy-button-icon"
                                    aria-label="Close rows"
                                    title="Close"
                                    onClick={() => setSelectedTable(null)}
                                >
                                    <X size={14} />
                                </button>
                            </div>
                            {selectedTable.error && (
                                <div className="entropy-alert entropy-alert-warning" role="alert">
                                    <AlertCircle size={16} />
                                    <span>{selectedTable.error}</span>
                                </div>
                            )}
                            <DataDetails item={selectedTable} />
                            {rowsLoading && (
                                <div className="tools-empty" role="status">
                                    <LoaderCircle size={20} className="entropy-spin" aria-hidden="true" />
                                    <strong>Reading rows…</strong>
                                </div>
                            )}
                            {rowsError && (
                                <div className="entropy-alert entropy-alert-warning" role="alert">
                                    <AlertCircle size={16} />
                                    <span>{rowsError}</span>
                                </div>
                            )}
                            {rows && <RowsView rows={rows} left={result.left} right={result.right} />}
                        </div>
                    )}

                    <div className="tools-db-scroll tools-db-results">
                        {view === 'ddl' ? (
                            <table>
                                <thead>
                                    <tr>
                                        <th>Type</th>
                                        <th>Name</th>
                                        <th>Result</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {ddlItems.map((item) => (
                                        <tr key={`${item.type}:${item.name}`}>
                                            <td>{item.type}</td>
                                            <td>
                                                {item.status === 'same' ? (
                                                    item.name
                                                ) : (
                                                    <button type="button" className="tools-db-link" onClick={() => setSelectedDdl(item)}>
                                                        {item.name}
                                                    </button>
                                                )}
                                            </td>
                                            <td>
                                                <span className={`tools-db-status is-${item.status}`}>{STATUS_LABELS[item.status]}</span>
                                                {item.error ? ` ${item.error}` : ''}
                                            </td>
                                        </tr>
                                    ))}
                                </tbody>
                            </table>
                        ) : (
                            <table>
                                <thead>
                                    <tr>
                                        <th>Table</th>
                                        <th>{result.left} rows</th>
                                        <th>{result.right} rows</th>
                                        <th>Result</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {dataItems.map((item) => (
                                        <tr key={item.table}>
                                            <td>
                                                {item.status === 'same' && !item.columns_not_compared?.length ? (
                                                    item.table
                                                ) : (
                                                    <button type="button" className="tools-db-link" onClick={() => void openTable(item)}>
                                                        {item.table}
                                                    </button>
                                                )}
                                            </td>
                                            <td>{item.left_rows?.toLocaleString() ?? '—'}</td>
                                            <td>{item.right_rows?.toLocaleString() ?? '—'}</td>
                                            <td>
                                                <span className={`tools-db-status is-${item.status}`}>{STATUS_LABELS[item.status]}</span>
                                                {item.error ? ` ${item.error}` : ''}
                                                {item.columns_not_compared?.length
                                                    ? ` (${item.columns_not_compared.length} column(s) not compared)`
                                                    : ''}
                                            </td>
                                        </tr>
                                    ))}
                                </tbody>
                            </table>
                        )}
                        {(view === 'ddl' ? ddlItems : dataItems).length === 0 && (
                            <div className="tools-empty">
                                <strong>{differencesOnly ? 'No differences found' : 'Nothing to compare'}</strong>
                            </div>
                        )}
                    </div>
                </>
            )}
        </div>
    )
}
