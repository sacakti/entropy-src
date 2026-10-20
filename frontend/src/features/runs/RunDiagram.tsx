import { useCallback, useEffect, useMemo, useRef, useState, type PointerEvent as ReactPointerEvent } from 'react'
import { RotateCcw } from 'lucide-react'

import type { PlannedStep } from '../../api/runs.api'

export type DiagramStatus = 'pending' | 'running' | 'completed' | 'failed' | 'skipped' | 'cancelled'

interface Point {
    x: number
    y: number
}

const BUBBLE_W = 168
const BUBBLE_H = 64
const MARGIN = 24
const STORAGE_PREFIX = 'entropy.run-diagram.'

/** Node name → a stable hue, so each node's steps share a colour. */
function nodeHue(node: string, nodes: string[]): number {
    const index = Math.max(0, nodes.indexOf(node))
    return (200 + index * 67) % 360
}

function columnsFor(width: number): number {
    return Math.max(1, Math.floor((width - MARGIN * 2 + 40) / (BUBBLE_W + 40)))
}

/** Room for every row of bubbles, plus space to drag them around. */
function heightFor(count: number, width: number): number {
    const rows = Math.ceil(count / columnsFor(width || 1))
    return Math.min(600, Math.max(300, rows * 150 + 110))
}

/** Steps left to right on a gentle wave, wrapping onto new rows. */
function initialLayout(names: string[], width: number, height: number): Record<string, Point> {
    const columns = columnsFor(width)
    const rows = Math.ceil(names.length / columns)
    const rowGap = Math.min(150, (height - MARGIN * 2 - BUBBLE_H) / Math.max(1, rows))
    const span = Math.max(1, Math.min(columns, names.length) - 1)
    const usable = width - MARGIN * 2 - BUBBLE_W

    return Object.fromEntries(
        names.map((name, index) => {
            const row = Math.floor(index / columns)
            const column = index % columns
            // Alternate rows run back, so consecutive steps stay close.
            const position = row % 2 === 0 ? column : columns - 1 - column
            const wave = index % 2 === 0 ? 0 : 36
            return [
                name,
                {
                    x: MARGIN + (span ? (usable * Math.min(position, span)) / span : usable / 2),
                    y: MARGIN + 20 + row * rowGap + wave,
                },
            ]
        }),
    )
}

function readSaved(key: string): Record<string, Point> | null {
    try {
        const raw = window.localStorage.getItem(STORAGE_PREFIX + key)
        return raw ? (JSON.parse(raw) as Record<string, Point>) : null
    } catch {
        return null
    }
}

function save(key: string, layout: Record<string, Point>): void {
    try {
        window.localStorage.setItem(STORAGE_PREFIX + key, JSON.stringify(layout))
    } catch {
        // Positions are a convenience only.
    }
}

/** Where a line from a bubble's centre towards `toward` leaves the bubble. */
function edgePoint(center: Point, toward: Point): Point {
    const dx = toward.x - center.x
    const dy = toward.y - center.y
    if (dx === 0 && dy === 0) return center
    const scale = Math.min(
        Math.abs(dx) > 0 ? BUBBLE_W / 2 / Math.abs(dx) : Infinity,
        Math.abs(dy) > 0 ? BUBBLE_H / 2 / Math.abs(dy) : Infinity,
    )
    return { x: center.x + dx * scale, y: center.y + dy * scale }
}

/**
 * The run as a map: a bubble per step, dashed arrows for the order steps
 * run in, solid arrows for outputs one step reads from another. Bubbles
 * can be dragged; their places are remembered per workflow.
 */
export default function RunDiagram({
    workflow,
    plan,
    statuses,
    onSelect,
}: {
    workflow: string
    plan: PlannedStep[]
    statuses: Record<string, DiagramStatus>
    onSelect: (name: string) => void
}) {
    const canvasRef = useRef<HTMLDivElement>(null)
    const [width, setWidth] = useState(0)
    const [layout, setLayout] = useState<Record<string, Point>>(() => readSaved(workflow) ?? {})
    const drag = useRef<{ name: string; dx: number; dy: number; moved: boolean } | null>(null)

    const steps = useMemo(() => plan.filter((step) => step.selected ?? step.enabled), [plan])
    const names = useMemo(() => steps.map((step) => step.name), [steps])
    const nodes = useMemo(() => Array.from(new Set(steps.map((step) => step.node ?? ''))).filter(Boolean), [steps])

    useEffect(() => {
        const element = canvasRef.current
        if (!element) return
        const observer = new ResizeObserver(([entry]) => setWidth(entry.contentRect.width))
        observer.observe(element)
        return () => observer.disconnect()
    }, [])

    const height = heightFor(names.length, width)

    // Place steps that have no position yet (new run, new steps, first render).
    const positions = useMemo(() => {
        if (!width) return {}
        const fallback = initialLayout(names, width, height)
        return Object.fromEntries(
            names.map((name) => {
                const saved = layout[name]
                const point = saved ?? fallback[name]
                return [
                    name,
                    {
                        x: Math.min(Math.max(point.x, 0), Math.max(0, width - BUBBLE_W)),
                        y: Math.min(Math.max(point.y, 0), height - BUBBLE_H),
                    },
                ]
            }),
        ) as Record<string, Point>
    }, [height, layout, names, width])

    const centers = useMemo(
        () =>
            Object.fromEntries(
                Object.entries(positions).map(([name, point]) => [
                    name,
                    { x: point.x + BUBBLE_W / 2, y: point.y + BUBBLE_H / 2 },
                ]),
            ) as Record<string, Point>,
        [positions],
    )

    const sequence = names.slice(1).map((name, index) => ({ from: names[index], to: name }))
    const dependencies = steps.flatMap((step) =>
        (step.depends_on ?? [])
            .filter((dependency) => names.includes(dependency.step))
            .map((dependency) => ({ from: dependency.step, to: step.name, label: `outputs.${dependency.output}` })),
    )

    const onPointerDown = useCallback(
        (name: string, event: ReactPointerEvent<HTMLButtonElement>) => {
            const point = positions[name]
            const canvas = canvasRef.current?.getBoundingClientRect()
            if (!point || !canvas) return
            event.currentTarget.setPointerCapture(event.pointerId)
            drag.current = {
                name,
                dx: event.clientX - canvas.left - point.x,
                dy: event.clientY - canvas.top - point.y,
                moved: false,
            }
        },
        [positions],
    )

    const onPointerMove = useCallback(
        (event: ReactPointerEvent<HTMLButtonElement>) => {
            const current = drag.current
            const canvas = canvasRef.current?.getBoundingClientRect()
            if (!current || !canvas) return
            current.moved = true
            const x = event.clientX - canvas.left - current.dx
            const y = event.clientY - canvas.top - current.dy
            setLayout((previous) => ({ ...positions, ...previous, [current.name]: { x, y } }))
        },
        [positions],
    )

    const onPointerUp = useCallback(
        (name: string) => {
            const current = drag.current
            drag.current = null
            if (!current) return
            if (current.moved) {
                setLayout((previous) => {
                    save(workflow, previous)
                    return previous
                })
            } else {
                onSelect(name)
            }
        },
        [onSelect, workflow],
    )

    const reset = () => {
        setLayout({})
        try {
            window.localStorage.removeItem(STORAGE_PREFIX + workflow)
        } catch {
            // ignore
        }
    }

    return (
        <div className="run-diagram">
            <div className="run-diagram-toolbar">
                <span className="run-diagram-legend">
                    <span className="is-sequence" /> runs after
                    <span className="is-dependency" /> uses output of
                    {nodes.length > 1 &&
                        nodes.map((node) => (
                            <span
                                key={node}
                                className="run-diagram-node-key"
                                style={{ '--node-hue': nodeHue(node, nodes) } as React.CSSProperties}
                            >
                                {node}
                            </span>
                        ))}
                </span>
                <button type="button" className="entropy-button entropy-button-ghost entropy-button-sm" onClick={reset}>
                    <RotateCcw size={13} /> Reset layout
                </button>
            </div>

            <div className="run-diagram-canvas" ref={canvasRef} style={{ height }}>
                <svg className="run-diagram-edges" width={width} height={height} aria-hidden="true">
                    <defs>
                        <marker id="run-arrow-seq" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
                            <path d="M0,0 L10,5 L0,10 z" className="is-sequence" />
                        </marker>
                        <marker id="run-arrow-dep" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
                            <path d="M0,0 L10,5 L0,10 z" className="is-dependency" />
                        </marker>
                    </defs>
                    {sequence.map(({ from, to }) => {
                        const a = centers[from]
                        const b = centers[to]
                        if (!a || !b) return null
                        const start = edgePoint(a, b)
                        const end = edgePoint(b, a)
                        return (
                            <line
                                key={`seq-${from}-${to}`}
                                className="run-edge is-sequence"
                                x1={start.x}
                                y1={start.y}
                                x2={end.x}
                                y2={end.y}
                                markerEnd="url(#run-arrow-seq)"
                            />
                        )
                    })}
                    {dependencies.map(({ from, to, label }, index) => {
                        const a = centers[from]
                        const b = centers[to]
                        if (!a || !b) return null
                        const start = edgePoint(a, b)
                        const end = edgePoint(b, a)
                        // Bow dependency arrows so they do not hide the order arrows.
                        const mx = (start.x + end.x) / 2
                        const my = (start.y + end.y) / 2 - 46 - (index % 3) * 14
                        return (
                            <g key={`dep-${from}-${to}-${label}`}>
                                <path
                                    className="run-edge is-dependency"
                                    d={`M${start.x},${start.y} Q${mx},${my} ${end.x},${end.y}`}
                                    markerEnd="url(#run-arrow-dep)"
                                />
                                <text className="run-edge-label" x={mx} y={(start.y + end.y) / 4 + my / 2 - 4} textAnchor="middle">
                                    {label}
                                </text>
                            </g>
                        )
                    })}
                </svg>

                {steps.map((step, index) => {
                    const point = positions[step.name]
                    if (!point) return null
                    const status = statuses[step.name] ?? 'pending'
                    return (
                        <button
                            key={step.name}
                            type="button"
                            className={`run-bubble is-${status}`}
                            style={
                                {
                                    left: point.x,
                                    top: point.y,
                                    width: BUBBLE_W,
                                    height: BUBBLE_H,
                                    '--node-hue': nodes.length > 1 && step.node ? nodeHue(step.node, nodes) : undefined,
                                } as React.CSSProperties
                            }
                            title={`${step.name} · ${status}${step.node ? ` · ${step.node}` : ''} — drag to move, click for details`}
                            onPointerDown={(event) => onPointerDown(step.name, event)}
                            onPointerMove={onPointerMove}
                            onPointerUp={() => onPointerUp(step.name)}
                            onKeyDown={(event) => {
                                if (event.key === 'Enter' || event.key === ' ') onSelect(step.name)
                            }}
                        >
                            <span className="run-bubble-index">{index + 1}</span>
                            <strong>{step.name}</strong>
                            <small>
                                {step.plugin}
                                {nodes.length > 1 && step.node ? ` · ${step.node}` : ''}
                            </small>
                        </button>
                    )
                })}
            </div>
        </div>
    )
}
