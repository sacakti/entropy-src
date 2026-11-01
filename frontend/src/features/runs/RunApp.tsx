import { useEffect, useMemo, useRef, useState } from 'react'
import { AppWindow, CircleStop, LoaderCircle, Search, X } from 'lucide-react'

import { runsApi, type RunApp as RunAppData, type RunAppInput, type RunAppView, type RunAppViewData } from '../../api/runs.api'
import { useFeedback } from '../../components/feedback/FeedbackProvider'
import Pagination from '../../components/layout/Pagination'
import SortHeader from '../../components/layout/SortHeader'
import { usePagination } from '../../components/layout/usePagination'
import { compareText, compareValue, type SortState } from '../../components/layout/useSort'
import { errorMessage, formatDateTime } from './format'

const TEXT_DELAY_MS = 400

const display = (value: unknown): string => {
    if (value === null || value === undefined) return ''
    if (typeof value === 'object') return JSON.stringify(value)
    return String(value)
}

/** The live pages of a run's app plugins: one per app step. */
export default function RunApps({ runId, apps, live, onChanged }: {
    runId: number
    apps: RunAppData[]
    /** The run is still going (a finished run shows its pages read-only). */
    live: boolean
    onChanged: () => void
}) {
    const running = apps.filter((app) => app.state === 'running')
    const [chosen, setChosen] = useState<number | null>(null)
    const current = apps.find((app) => app.id === chosen) ?? running[running.length - 1] ?? apps[apps.length - 1]
    if (!current) {
        return (
            <div className="list-empty">
                <AppWindow size={20} />
                <strong>No app page yet</strong>
                <span>The page opens when the app step starts.</span>
            </div>
        )
    }
    return (
        <div className="run-apps">
            {apps.length > 1 && (
                <div className="seg-control" role="tablist" aria-label="App steps">
                    {apps.map((app) => (
                        <button key={app.id} type="button" role="tab" aria-selected={app.id === current.id} className={app.id === current.id ? 'is-active' : ''} onClick={() => setChosen(app.id)}>
                            {app.definition.title || app.step}
                        </button>
                    ))}
                </div>
            )}
            <RunAppPage key={current.id} runId={runId} app={current} live={live && current.state === 'running'} onChanged={onChanged} />
        </div>
    )
}

function RunAppPage({ runId, app, live, onChanged }: { runId: number; app: RunAppData; live: boolean; onChanged: () => void }) {
    const { notify } = useFeedback()
    const { definition } = app
    // What the user typed; kept locally so polling never overwrites a field being edited.
    const [values, setValues] = useState<Record<string, unknown>>(() => ({ ...app.inputs }))
    const [selections, setSelections] = useState<Record<string, Set<string>>>({})
    const [busy, setBusy] = useState<string | null>(null)
    const timers = useRef<Record<string, ReturnType<typeof setTimeout>>>({})

    useEffect(() => () => Object.values(timers.current).forEach(clearTimeout), [])

    const send = (name: string, value: unknown) => {
        runsApi
            .setAppInputs(runId, app.id, { [name]: value })
            .then(onChanged)
            .catch((cause: unknown) => notify.error(errorMessage(cause, 'Unable to change the input.'), { title: 'App' }))
    }

    const change = (input: RunAppInput, value: unknown) => {
        setValues((current) => ({ ...current, [input.name]: value }))
        clearTimeout(timers.current[input.name])
        if (input.type === 'text' || input.type === 'number') {
            timers.current[input.name] = setTimeout(() => send(input.name, value), TEXT_DELAY_MS)
        } else {
            send(input.name, value)
        }
    }

    const press = async (input: RunAppInput) => {
        // Send the rows' own key values (numbers stay numbers), not their display text.
        const view = definition.views.find((item) => item.name === input.target)
        const keyName = view?.row_key ?? app.views[input.target ?? '']?.columns?.[0]?.key ?? view?.columns?.[0]?.key
        const chosen = input.target ? selections[input.target] ?? new Set<string>() : new Set<string>()
        const selection = (app.views[input.target ?? '']?.rows ?? [])
            .map((row) => (keyName ? row[keyName] : undefined))
            .filter((value) => chosen.has(display(value)))
        setBusy(input.name)
        try {
            await runsApi.pressAppButton(runId, app.id, input.name, selection)
            notify.success(selection.length ? `${input.label}: ${selection.length} selected.` : `${input.label} sent.`, { title: 'App' })
            onChanged()
        } catch (cause) {
            notify.error(errorMessage(cause, 'Unable to send the button press.'), { title: 'App' })
        } finally {
            setBusy(null)
        }
    }

    const stop = async () => {
        setBusy('__stop')
        try {
            await runsApi.stopApp(runId, app.id)
            notify.success('The app finishes its current refresh and the step completes.', { title: 'Stopping app' })
            onChanged()
        } catch (cause) {
            notify.error(errorMessage(cause, 'Unable to stop the app.'), { title: 'App' })
        } finally {
            setBusy(null)
        }
    }

    const fields = definition.inputs.filter((input) => input.type !== 'button')
    const buttons = definition.inputs.filter((input) => input.type === 'button')
    const state = app.state === 'running' && live ? 'live' : app.state === 'stopping' ? 'stopping' : 'finished'

    return (
        <section className="run-app" aria-label={definition.title || app.step}>
            <header className="run-app-head">
                <div>
                    <h4>
                        <AppWindow size={16} aria-hidden="true" /> {definition.title || app.step}
                        <span className={`run-app-state is-${state}`}>{state === 'live' ? 'Live' : state === 'stopping' ? 'Stopping…' : 'Finished'}</span>
                    </h4>
                    {definition.description && <p>{definition.description}</p>}
                    <small>
                        {app.plugin} · step {app.step} · updated {formatDateTime(app.updated_at)}
                    </small>
                </div>
                {state === 'live' && (
                    <button type="button" className="entropy-button entropy-button-secondary entropy-button-sm" disabled={busy !== null} onClick={() => void stop()} title="End the app's loop; the step then completes">
                        {busy === '__stop' ? <LoaderCircle size={14} className="entropy-spin" /> : <CircleStop size={14} />} Stop app
                    </button>
                )}
            </header>

            {(fields.length > 0 || buttons.length > 0) && (
                <div className="run-app-inputs">
                    {fields.map((input) => (
                        <AppField key={input.name} input={input} value={values[input.name]} disabled={state !== 'live'} onChange={(value) => change(input, value)} />
                    ))}
                    {buttons.length > 0 && (
                        <div className="run-app-buttons">
                            {buttons.map((input) => {
                                const count = input.target ? selections[input.target]?.size ?? 0 : 0
                                return (
                                    <button key={input.name} type="button" className="entropy-button entropy-button-primary entropy-button-sm" disabled={state !== 'live' || busy !== null || Boolean(input.target && !count)} title={input.description ?? (input.target && !count ? 'Select rows first' : undefined)} onClick={() => void press(input)}>
                                        {busy === input.name && <LoaderCircle size={14} className="entropy-spin" />}
                                        {input.label}
                                        {input.target ? ` (${count})` : ''}
                                    </button>
                                )
                            })}
                        </div>
                    )}
                </div>
            )}

            <div className="run-app-views">
                {definition.views.map((view) => (
                    <AppViewPanel
                        key={view.name}
                        view={view}
                        data={app.views[view.name]}
                        selected={selections[view.name] ?? new Set()}
                        onSelect={(next) => setSelections((current) => ({ ...current, [view.name]: next }))}
                        selectable={state === 'live'}
                    />
                ))}
            </div>
        </section>
    )
}

function AppField({ input, value, disabled, onChange }: {
    input: RunAppInput
    value: unknown
    disabled: boolean
    onChange: (value: unknown) => void
}) {
    if (input.type === 'toggle') {
        return (
            <label className="run-app-toggle" title={input.description}>
                <input type="checkbox" checked={Boolean(value)} disabled={disabled} onChange={(event) => onChange(event.target.checked)} />
                {input.label}
            </label>
        )
    }
    return (
        <label className="run-app-field" title={input.description}>
            <span>{input.label}</span>
            {input.type === 'select' ? (
                <select className="entropy-select" value={display(value)} disabled={disabled} onChange={(event) => onChange(event.target.value)}>
                    {!input.choices?.includes(display(value)) && <option value="">Choose…</option>}
                    {input.choices?.map((choice) => <option key={choice} value={choice}>{choice}</option>)}
                </select>
            ) : (
                <input
                    type={input.type === 'number' ? 'number' : 'text'}
                    value={display(value)}
                    placeholder={input.placeholder}
                    disabled={disabled}
                    onChange={(event) =>
                        onChange(input.type === 'number' ? (event.target.value === '' ? null : Number(event.target.value)) : event.target.value)
                    }
                />
            )}
        </label>
    )
}

function AppViewPanel({ view, data, selected, onSelect, selectable }: {
    view: RunAppView
    data: RunAppViewData | undefined
    selected: Set<string>
    onSelect: (next: Set<string>) => void
    selectable: boolean
}) {
    return (
        <article className={`run-app-view is-${view.type}`}>
            <h5>{view.title || view.label}</h5>
            {view.description && <p className="run-app-muted">{view.description}</p>}
            {!data ? (
                <p className="run-app-muted">Waiting for data…</p>
            ) : view.type === 'table' ? (
                <AppTable view={view} data={data} selected={selected} onSelect={onSelect} selectable={selectable} />
            ) : view.type === 'stats' ? (
                <div className="run-app-stats">
                    {(data.items ?? []).map((item) => (
                        <div key={item.label}>
                            <strong>{display(item.value)}</strong>
                            <span>{item.label}</span>
                        </div>
                    ))}
                </div>
            ) : view.type === 'keyvalue' ? (
                <dl className="run-app-kv">
                    {(data.items ?? []).map((item) => (
                        <div key={item.key}>
                            <dt>{item.key}</dt>
                            <dd>{display(item.value)}</dd>
                        </div>
                    ))}
                </dl>
            ) : view.type === 'log' ? (
                <AppLog lines={data.lines ?? []} />
            ) : (
                <p className="run-app-text">{data.text ?? ''}</p>
            )}
        </article>
    )
}

function AppLog({ lines }: { lines: string[] }) {
    const ref = useRef<HTMLPreElement>(null)
    useEffect(() => {
        if (ref.current) ref.current.scrollTop = ref.current.scrollHeight
    }, [lines.length])
    return <pre ref={ref} className="run-app-log">{lines.length ? lines.join('\n') : 'Nothing yet.'}</pre>
}

function AppTable({ view, data, selected, onSelect, selectable }: {
    view: RunAppView
    data: RunAppViewData
    selected: Set<string>
    onSelect: (next: Set<string>) => void
    selectable: boolean
}) {
    const columns = useMemo(() => data.columns ?? view.columns ?? [], [data.columns, view.columns])
    const rowKey = view.row_key ?? columns[0]?.key
    const keyOf = (row: Record<string, unknown>, index: number) => (rowKey ? display(row[rowKey]) : String(index))
    const [filter, setFilter] = useState('')
    const [sort, setSort] = useState<SortState<string> | null>(null)

    const rows = useMemo(() => {
        const needle = filter.trim().toLowerCase()
        const matching = needle
            ? (data.rows ?? []).filter((row) => columns.some((column) => display(row[column.key]).toLowerCase().includes(needle)))
            : [...(data.rows ?? [])]
        if (sort) {
            const compare = (left: Record<string, unknown>, right: Record<string, unknown>) => {
                const a = left[sort.field]
                const b = right[sort.field]
                return typeof a === 'number' && typeof b === 'number' ? compareValue(a, b) : compareText(display(a), display(b))
            }
            matching.sort((left, right) => (sort.order === 'asc' ? compare(left, right) : compare(right, left)))
        }
        return matching
    }, [data.rows, columns, filter, sort])
    const pages = usePagination(rows, 'run-app-table')

    const toggleSort = (field: string) => {
        setSort((current) => (current?.field === field ? { field, order: current.order === 'asc' ? 'desc' : 'asc' } : { field, order: 'asc' }))
        pages.setPage(1)
    }
    const visibleKeys = pages.pageItems.map((row, index) => keyOf(row, index))
    const allVisible = visibleKeys.length > 0 && visibleKeys.every((key) => selected.has(key))
    const toggle = (key: string) => {
        const next = new Set(selected)
        if (next.has(key)) next.delete(key)
        else next.add(key)
        onSelect(next)
    }

    return (
        <div className="run-app-table">
            <div className="run-app-table-tools">
                {view.filter !== false && (
                    <label className="list-search">
                        <Search size={15} aria-hidden="true" />
                        <input
                            type="search"
                            value={filter}
                            onChange={(event) => {
                                setFilter(event.target.value)
                                pages.setPage(1)
                            }}
                            placeholder={`Filter ${view.title || view.label}…`}
                            aria-label={`Filter ${view.title || view.label}`}
                        />
                        {filter && (
                            <button type="button" aria-label="Clear filter" onClick={() => setFilter('')}>
                                <X size={14} />
                            </button>
                        )}
                    </label>
                )}
                <small>
                    {rows.length} of {data.total ?? data.rows?.length ?? 0} rows
                    {view.selectable && selected.size > 0 && (
                        <>
                            {' '}· {selected.size} selected{' '}
                            <button type="button" className="run-app-link" onClick={() => onSelect(new Set())}>Clear</button>
                        </>
                    )}
                </small>
            </div>
            <div className="list-table-wrap">
                <table className="list-table">
                    <thead>
                        <tr>
                            {view.selectable && (
                                <th scope="col" className="list-check-cell">
                                    <input
                                        type="checkbox"
                                        className="list-check"
                                        aria-label="Select all rows on this page"
                                        checked={allVisible}
                                        disabled={!selectable || !visibleKeys.length}
                                        onChange={(event) => {
                                            const next = new Set(selected)
                                            visibleKeys.forEach((key) => (event.target.checked ? next.add(key) : next.delete(key)))
                                            onSelect(next)
                                        }}
                                    />
                                </th>
                            )}
                            {columns.map((column) => (
                                <th key={column.key} scope="col" aria-sort={sort?.field === column.key ? (sort.order === 'asc' ? 'ascending' : 'descending') : undefined}>
                                    <SortHeader label={column.label} field={column.key} sort={sort ?? { field: '', order: 'asc' }} onSort={toggleSort} />
                                </th>
                            ))}
                        </tr>
                    </thead>
                    <tbody>
                        {pages.pageItems.length === 0 ? (
                            <tr>
                                <td colSpan={columns.length + (view.selectable ? 1 : 0)} className="run-app-muted">
                                    {filter ? 'No rows match the filter.' : 'No rows.'}
                                </td>
                            </tr>
                        ) : (
                            pages.pageItems.map((row, index) => {
                                const key = keyOf(row, index)
                                return (
                                    <tr key={key} className={selected.has(key) ? 'is-selected' : undefined}>
                                        {view.selectable && (
                                            <td className="list-check-cell">
                                                <input type="checkbox" className="list-check" aria-label={`Select ${key}`} checked={selected.has(key)} disabled={!selectable} onChange={() => toggle(key)} />
                                            </td>
                                        )}
                                        {columns.map((column) => (
                                            <td key={column.key}>{display(row[column.key])}</td>
                                        ))}
                                    </tr>
                                )
                            })
                        )}
                    </tbody>
                </table>
            </div>
            <Pagination state={pages} noun="rows" />
        </div>
    )
}
