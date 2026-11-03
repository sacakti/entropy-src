import { useEffect, useMemo, useState } from 'react'
import { AlertCircle, Database, LoaderCircle, Play, ShieldCheck, X } from 'lucide-react'

import {
    clashApi,
    type ClashDatabaseResult,
    type ClashDatabaseSide,
    type ClashDataItem,
    type ClashDdlItem,
    type ClashRowsResult,
    type ClashStatus,
} from '../../api/clash.api'
import { vaultApi, type VaultNamespace } from '../../api/vault.api'
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
    const [running, setRunning] = useState(false)
    const [error, setError] = useState('')
    const [result, setResult] = useState<ClashDatabaseResult | null>(null)
    // The sides the result was made with: the form may have changed since.
    const [compared, setCompared] = useState<{ left: ClashDatabaseSide; right: ClashDatabaseSide } | null>(null)
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

    const ready = sideIsComplete(left) && sideIsComplete(right) && (ddl || data) && !running

    const run = async () => {
        setRunning(true)
        setError('')
        setResult(null)
        setSelectedDdl(null)
        setSelectedTable(null)
        setRows(null)
        try {
            const response = await clashApi.compare({
                left,
                right,
                ddl,
                data,
                name_filter: nameFilter.trim() || null,
            })
            setResult(response)
            setCompared({ left, right })
            setView(response.ddl ? 'ddl' : 'data')
        } catch (caught) {
            setError(messageOf(caught))
        } finally {
            setRunning(false)
        }
    }

    const openTable = async (item: ClashDataItem) => {
        setSelectedTable(item)
        setRows(null)
        setRowsError('')
        if (item.status !== 'different' || !compared) return
        setRowsLoading(true)
        try {
            setRows(await clashApi.rows({ ...compared, table: item.table }))
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
                <label className="tools-check">
                    <input type="checkbox" checked={data} onChange={(event) => setData(event.target.checked)} /> Data
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
                    {running ? <LoaderCircle size={15} className="entropy-spin" /> : <Play size={15} />}
                    {running ? 'Comparing…' : 'Compare'}
                </button>
            </div>

            {running && data && (
                <p className="tools-db-note" role="status">
                    Hashing every table can take a while on large schemas. Use a name filter to compare fewer.
                </p>
            )}

            {error && (
                <div className="entropy-alert entropy-alert-error" role="alert">
                    <AlertCircle size={16} />
                    <span>{error}</span>
                </div>
            )}

            {!result && !running && !error && (
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
