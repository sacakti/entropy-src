import { useEffect, useMemo, useRef, useState, type KeyboardEvent, type PointerEvent, type RefObject } from 'react'
import { Play } from 'lucide-react'

import type { RunAppView, RunAppViewData } from '../../api/runs.api'
import {
    MAX_SERIES,
    QueryError,
    formatQuery,
    literalPattern,
    parseQuery,
    runQuery,
    type Aggregate,
    type ChartQuery,
    type ChartSample,
} from './chartQuery'
import { formatTime } from './format'

const HEIGHT = 260
const PAD = { top: 12, right: 12, bottom: 26, left: 52 }
/** Room for names at the line ends, when there are few enough lines to label. */
const LABEL_ROOM = 132
const MAX_DIRECT_LABELS = 4
const LABEL_GAP = 13

const AGGREGATE_LABELS: { value: Aggregate | ''; label: string }[] = [
    { value: '', label: 'Each' },
    { value: 'sum', label: 'Sum' },
    { value: 'avg', label: 'Average' },
    { value: 'max', label: 'Highest' },
    { value: 'min', label: 'Lowest' },
]
const RANKS = ['top 3', 'top 5', 'top 8', 'bottom 3', 'bottom 5', 'bottom 8']

const formatValue = (value: number | null) =>
    value === null ? '—' : Math.abs(value) >= 100 ? Math.round(value).toLocaleString() : value.toFixed(1)

const formatTick = (value: number) =>
    Number.isInteger(value) ? value.toLocaleString() : value.toLocaleString(undefined, { maximumFractionDigits: 2 })

/** A round top for the axis, and its four tick values. */
function niceScale(highest: number): { max: number; ticks: number[] } {
    if (!(highest > 0)) return { max: 1, ticks: [0, 0.25, 0.5, 0.75, 1] }
    const rough = highest / 4
    const power = 10 ** Math.floor(Math.log10(rough))
    const step = [1, 2, 2.5, 5, 10].map((factor) => factor * power).find((candidate) => candidate >= rough) ?? rough
    const max = step * Math.ceil(highest / step)
    const ticks = []
    for (let value = 0; value <= max + step / 2; value += step) ticks.push(value)
    return { max, ticks }
}

/**
 * Survivors keep their color; a newcomer takes the lowest free one. So a filter
 * that adds or removes lines never repaints the others.
 */
function assignSlots(current: Record<string, number>, names: string[]): Record<string, number> {
    const next: Record<string, number> = {}
    names.forEach((name) => {
        if (current[name] !== undefined) next[name] = current[name]
    })
    const used = new Set(Object.values(next))
    names.forEach((name) => {
        if (next[name] !== undefined) return
        let slot = 0
        while (used.has(slot)) slot += 1
        next[name] = slot
        used.add(slot)
    })
    return next
}

function useWidth<T extends HTMLElement>(): [RefObject<T | null>, number] {
    const ref = useRef<T>(null)
    const [width, setWidth] = useState(640)
    useEffect(() => {
        const node = ref.current
        if (!node || typeof ResizeObserver === 'undefined') return undefined
        const observer = new ResizeObserver(([entry]) => setWidth(Math.max(240, Math.floor(entry.contentRect.width))))
        observer.observe(node)
        return () => observer.disconnect()
    }, [])
    return [ref, width]
}

/**
 * An app's chart: one metric over the samples the plugin keeps, one line per
 * series (or one combined line). The controls write a query; the query can also
 * be typed, e.g. `sum(memory) where pod ~ api`.
 */
export default function AppChart({ view, data }: { view: RunAppView; data: RunAppViewData }) {
    const metrics = useMemo(() => data.metrics ?? view.metrics ?? [], [data.metrics, view.metrics])
    const keys = useMemo(() => metrics.map((item) => item.key), [metrics])
    const seriesLabel = data.series_label ?? view.series_label ?? 'series'
    const samples: ChartSample[] = useMemo(() => data.samples ?? [], [data.samples])

    const initial: ChartQuery = { aggregate: null, metric: keys[0] ?? '', conditions: [], order: 'top', limit: null }
    const [query, setQuery] = useState<ChartQuery>(initial)
    const [draft, setDraft] = useState(() => formatQuery(initial))
    const [problem, setProblem] = useState<string | null>(null)
    const [hidden, setHidden] = useState<Set<string>>(new Set())
    const [slots, setSlots] = useState<Record<string, number>>({})
    const [hover, setHover] = useState<number | null>(null)
    const [boxRef, width] = useWidth<HTMLDivElement>()

    const apply = (next: ChartQuery) => {
        setQuery(next)
        setDraft(formatQuery(next))
        setProblem(null)
    }

    const applyDraft = () => {
        try {
            apply(parseQuery(draft, keys, seriesLabel))
        } catch (cause) {
            setProblem(cause instanceof QueryError ? cause.message : 'The query could not be read.')
        }
    }

    const result = useMemo(() => runQuery(query, keys, samples), [query, keys, samples])
    const names = result.series.map((series) => series.name)
    // Give newcomers a color now, so no line is drawn without one.
    const missing = names.some((name) => slots[name] === undefined)
    const colors = missing ? assignSlots(slots, names) : slots
    if (missing) setSlots(colors)

    const visible = result.series.filter((series) => !hidden.has(series.name))
    const metricLabel = metrics.find((item) => item.key === query.metric)?.label ?? query.metric
    const nameFilter = query.conditions.find((item) => item.field === seriesLabel && item.op === '~')
    const filterText = typeof nameFilter?.value === 'string' ? nameFilter.value.replace(/\\(.)/g, '$1') : ''

    const setFilter = (text: string) => {
        const others = query.conditions.filter((item) => item !== nameFilter)
        apply({
            ...query,
            conditions: text.trim()
                ? [{ field: seriesLabel, op: '~', value: literalPattern(text.trim()) }, ...others]
                : others,
        })
    }

    const toggle = (name: string) =>
        setHidden((current) => {
            const next = new Set(current)
            if (next.has(name)) next.delete(name)
            else next.add(name)
            return next
        })

    // ------------------------------------------------------------------
    // Geometry
    // ------------------------------------------------------------------

    const labelled = visible.length > 1 && visible.length <= MAX_DIRECT_LABELS
    const right = PAD.right + (labelled ? LABEL_ROOM : 0)
    const plotWidth = Math.max(40, width - PAD.left - right)
    const plotHeight = HEIGHT - PAD.top - PAD.bottom
    const count = result.times.length
    const highest = Math.max(0, ...visible.flatMap((series) => series.points.filter((value): value is number => value !== null)))
    const scale = niceScale(highest)
    const x = (index: number) => PAD.left + (count < 2 ? plotWidth : (index / (count - 1)) * plotWidth)
    const y = (value: number) => PAD.top + (1 - value / scale.max) * plotHeight

    const path = (points: (number | null)[]) => {
        let text = ''
        let drawing = false
        points.forEach((value, index) => {
            if (value === null) {
                drawing = false
                return
            }
            text += `${drawing ? 'L' : 'M'}${x(index).toFixed(1)},${y(value).toFixed(1)}`
            drawing = true
        })
        return text
    }

    const lastValue = (points: (number | null)[]) => {
        for (let index = points.length - 1; index >= 0; index -= 1) if (points[index] !== null) return { index, value: points[index] as number }
        return null
    }

    // Names at the line ends, nudged apart so they never overlap.
    const labels = labelled
        ? visible
              .map((series) => ({ series, end: lastValue(series.points) }))
              .filter((item): item is { series: (typeof visible)[number]; end: { index: number; value: number } } => item.end !== null)
              .map((item) => ({ name: item.series.name, y: y(item.end.value) }))
              .sort((left, right) => left.y - right.y)
              .reduce<{ name: string; y: number }[]>((placed, item) => {
                  const previous = placed[placed.length - 1]
                  placed.push({ ...item, y: previous ? Math.max(item.y, previous.y + LABEL_GAP) : item.y })
                  return placed
              }, [])
        : []

    const timeTicks = count < 2 ? [] : [0, Math.round((count - 1) / 2), count - 1]

    const onMove = (event: PointerEvent<SVGRectElement>) => {
        if (count < 2) return
        const box = event.currentTarget.getBoundingClientRect()
        const ratio = Math.min(1, Math.max(0, (event.clientX - box.left) / box.width))
        setHover(Math.round(ratio * (count - 1)))
    }

    const onKey = (event: KeyboardEvent<SVGSVGElement>) => {
        if (count < 2) return
        if (event.key === 'ArrowLeft') setHover((current) => Math.max(0, (current ?? count - 1) - 1))
        else if (event.key === 'ArrowRight') setHover((current) => Math.min(count - 1, (current ?? count - 1) + 1))
        else if (event.key === 'Escape') setHover(null)
        else return
        event.preventDefault()
    }

    const focused = hover !== null && hover < count ? hover : null
    const readings = focused === null
        ? []
        : visible
              .map((series) => ({ name: series.name, value: series.points[focused] }))
              .sort((left, right) => (right.value ?? -Infinity) - (left.value ?? -Infinity))
    const tooltipLeft = focused === null ? 0 : x(focused)

    return (
        <div className="run-app-chart">
            <div className="run-app-chart-tools">
                <label className="run-app-field">
                    <span>Metric</span>
                    <select value={query.metric} onChange={(event) => apply({ ...query, metric: event.target.value })}>
                        {metrics.map((item) => <option key={item.key} value={item.key}>{item.label}</option>)}
                    </select>
                </label>
                <label className="run-app-field">
                    <span>Show</span>
                    <select value={query.aggregate ?? ''} onChange={(event) => apply({ ...query, aggregate: (event.target.value || null) as Aggregate | null })}>
                        {AGGREGATE_LABELS.map((item) => (
                            <option key={item.value} value={item.value}>{item.value ? `${item.label} of all` : `${item.label} ${seriesLabel}`}</option>
                        ))}
                    </select>
                </label>
                <label className="run-app-field">
                    <span>{seriesLabel[0].toUpperCase() + seriesLabel.slice(1)} contains</span>
                    <input type="text" value={filterText} placeholder="Any" onChange={(event) => setFilter(event.target.value)} />
                </label>
                <label className="run-app-field">
                    <span>Limit</span>
                    <select
                        value={query.limit === null ? '' : `${query.order} ${query.limit}`}
                        onChange={(event) => {
                            const [order, limit] = event.target.value.split(' ')
                            apply({ ...query, order: (order || 'top') as ChartQuery['order'], limit: limit ? Number(limit) : null })
                        }}
                    >
                        <option value="">Highest {MAX_SERIES}</option>
                        {RANKS.map((rank) => <option key={rank} value={rank}>{rank[0].toUpperCase() + rank.slice(1)}</option>)}
                    </select>
                </label>
            </div>

            <form
                className="run-app-chart-query"
                onSubmit={(event) => {
                    event.preventDefault()
                    applyDraft()
                }}
            >
                <label className="run-app-field">
                    <span>Query</span>
                    <input
                        type="text"
                        value={draft}
                        spellCheck={false}
                        aria-invalid={problem !== null}
                        aria-describedby={problem ? `${view.name}-query-problem` : undefined}
                        placeholder={`sum(${keys[1] ?? keys[0] ?? 'metric'}) where ${seriesLabel} ~ api and restarts > 0 top 5`}
                        onChange={(event) => setDraft(event.target.value)}
                    />
                </label>
                <button type="submit" className="entropy-button entropy-button-secondary entropy-button-sm">
                    <Play size={13} aria-hidden="true" /> Run
                </button>
            </form>
            {problem && <p id={`${view.name}-query-problem`} className="run-app-chart-problem" role="alert">{problem}</p>}

            <div ref={boxRef} className="run-app-chart-plot">
                {count < 2 ? (
                    <p className="run-app-muted">Collecting samples… the graph starts after two refreshes.</p>
                ) : result.series.length === 0 ? (
                    <p className="run-app-muted">No {seriesLabel}s match the query.</p>
                ) : (
                    <>
                        <svg
                            width={width}
                            height={HEIGHT}
                            role="img"
                            tabIndex={0}
                            aria-label={`${metricLabel} over ${count} samples, ${visible.length} line${visible.length === 1 ? '' : 's'}. Arrow keys read the values; the List tab has the table.`}
                            onKeyDown={onKey}
                            onBlur={() => setHover(null)}
                        >
                            {scale.ticks.map((tick) => (
                                <g key={tick}>
                                    <line className="run-app-chart-grid" x1={PAD.left} x2={PAD.left + plotWidth} y1={y(tick)} y2={y(tick)} />
                                    <text className="run-app-chart-axis" x={PAD.left - 8} y={y(tick)} textAnchor="end" dominantBaseline="middle">
                                        {formatTick(tick)}
                                    </text>
                                </g>
                            ))}
                            {timeTicks.map((index, position) => (
                                <text
                                    key={index}
                                    className="run-app-chart-axis"
                                    x={x(index)}
                                    y={HEIGHT - 8}
                                    textAnchor={position === 0 ? 'start' : position === timeTicks.length - 1 ? 'end' : 'middle'}
                                >
                                    {formatTime(result.times[index])}
                                </text>
                            ))}
                            {visible.map((series) => (
                                <path
                                    key={series.name}
                                    className="run-app-chart-line"
                                    d={path(series.points)}
                                    style={{ stroke: `var(--series-${(colors[series.name] % MAX_SERIES) + 1})` }}
                                />
                            ))}
                            {labels.map((label) => (
                                <g key={label.name}>
                                    <line
                                        className="run-app-chart-key"
                                        x1={PAD.left + plotWidth + 6}
                                        x2={PAD.left + plotWidth + 14}
                                        y1={label.y}
                                        y2={label.y}
                                        style={{ stroke: `var(--series-${(colors[label.name] % MAX_SERIES) + 1})` }}
                                    />
                                    <text className="run-app-chart-label" x={PAD.left + plotWidth + 18} y={label.y} dominantBaseline="middle">
                                        {label.name.length > 18 ? `${label.name.slice(0, 17)}…` : label.name}
                                    </text>
                                </g>
                            ))}
                            {focused !== null && (
                                <g>
                                    <line className="run-app-chart-cross" x1={x(focused)} x2={x(focused)} y1={PAD.top} y2={PAD.top + plotHeight} />
                                    {visible.map((series) => {
                                        const value = series.points[focused]
                                        return value === null ? null : (
                                            <circle
                                                key={series.name}
                                                className="run-app-chart-dot"
                                                cx={x(focused)}
                                                cy={y(value)}
                                                r={4}
                                                style={{ fill: `var(--series-${(colors[series.name] % MAX_SERIES) + 1})` }}
                                            />
                                        )
                                    })}
                                </g>
                            )}
                            {/* Wider than the lines, so hovering anywhere in the plot reads it. */}
                            <rect
                                x={PAD.left}
                                y={PAD.top}
                                width={plotWidth}
                                height={plotHeight}
                                fill="transparent"
                                onPointerMove={onMove}
                                onPointerLeave={() => setHover(null)}
                            />
                        </svg>
                        {focused !== null && (
                            <div
                                className={`run-app-chart-tooltip${tooltipLeft > width / 2 ? ' is-left' : ''}`}
                                style={{ left: tooltipLeft }}
                                aria-live="polite"
                            >
                                <strong>{formatTime(result.times[focused])}</strong>
                                {readings.map((reading) => (
                                    <span key={reading.name}>
                                        <i style={{ background: `var(--series-${(colors[reading.name] % MAX_SERIES) + 1})` }} aria-hidden="true" />
                                        <span className="run-app-chart-tooltip-name">{reading.name}</span>
                                        <b>{formatValue(reading.value)}</b>
                                    </span>
                                ))}
                            </div>
                        )}
                    </>
                )}
            </div>

            {result.series.length > 1 && (
                <div className="run-app-chart-legend" aria-label="Lines: press one to hide or show it">
                    {result.series.map((series) => {
                        const end = lastValue(series.points)
                        return (
                            <button key={series.name} type="button" aria-pressed={!hidden.has(series.name)} onClick={() => toggle(series.name)} title={hidden.has(series.name) ? 'Show this line' : 'Hide this line'}>
                                <i style={{ background: `var(--series-${(colors[series.name] % MAX_SERIES) + 1})` }} aria-hidden="true" />
                                <span>{series.name}</span>
                                <b>{formatValue(end?.value ?? null)}</b>
                            </button>
                        )
                    })}
                </div>
            )}
            <small className="run-app-muted">
                {metricLabel}
                {result.hidden > 0 && ` · ${result.hidden} more ${seriesLabel}${result.hidden === 1 ? '' : 's'} match; narrow the query to see them`}
            </small>
        </div>
    )
}
