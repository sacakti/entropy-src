import { useId, useState, type PointerEvent } from 'react'

import type { MetricSample } from '../../api/runs.api'
import { formatTime } from '../runs/format'

const WIDTH = 320
const HEIGHT = 96
const PAD_TOP = 8
const PAD_BOTTOM = 4

type Field = 'cpu_percent' | 'memory_percent' | 'disk_percent'

/**
 * One metric over time on a fixed 0–100 % scale. A single series, so the
 * title names it; hover shows the nearest sample, and the latest value is
 * printed beside the title.
 */
export default function MetricChart({
    title,
    field,
    samples,
}: {
    title: string
    field: Field
    samples: MetricSample[]
}) {
    const id = useId()
    const [hover, setHover] = useState<number | null>(null)

    const points = samples
        .map((sample, index) => ({ index, value: sample[field], at: sample.sampled_at }))
        .filter((point): point is { index: number; value: number; at: string } => point.value !== null)

    const latest = points[points.length - 1]
    const x = (position: number) =>
        points.length < 2 ? WIDTH : (position / (points.length - 1)) * WIDTH
    const y = (value: number) =>
        PAD_TOP + (1 - Math.min(100, Math.max(0, value)) / 100) * (HEIGHT - PAD_TOP - PAD_BOTTOM)

    const path = points.map((point, position) => `${position ? 'L' : 'M'}${x(position).toFixed(1)},${y(point.value).toFixed(1)}`).join(' ')
    const area = points.length > 1 ? `${path} L${WIDTH},${HEIGHT} L0,${HEIGHT} Z` : ''

    const onMove = (event: PointerEvent<SVGSVGElement>) => {
        if (points.length === 0) return
        const box = event.currentTarget.getBoundingClientRect()
        const ratio = (event.clientX - box.left) / box.width
        setHover(Math.round(Math.min(1, Math.max(0, ratio)) * (points.length - 1)))
    }

    const focused = hover !== null ? points[hover] : null

    return (
        <figure className="node-chart" aria-labelledby={`${id}-title`}>
            <figcaption>
                <span id={`${id}-title`}>{title}</span>
                <strong>{focused ? `${focused.value.toFixed(1)}%` : latest ? `${latest.value.toFixed(1)}%` : '—'}</strong>
                {focused && <small>{formatTime(focused.at)}</small>}
            </figcaption>
            {points.length < 2 ? (
                <p className="node-chart-empty">Collecting samples…</p>
            ) : (
                <svg
                    viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
                    preserveAspectRatio="none"
                    role="img"
                    aria-label={`${title}: latest ${latest?.value.toFixed(1)}%, ${points.length} samples`}
                    onPointerMove={onMove}
                    onPointerLeave={() => setHover(null)}
                >
                    {[25, 50, 75].map((line) => (
                        <line key={line} className="node-chart-grid" x1={0} x2={WIDTH} y1={y(line)} y2={y(line)} />
                    ))}
                    <path className="node-chart-area" d={area} />
                    <path className="node-chart-line" d={path} vectorEffect="non-scaling-stroke" />
                    {focused && hover !== null && (
                        <line
                                className="node-chart-cross"
                                x1={x(hover)}
                                x2={x(hover)}
                                y1={0}
                                y2={HEIGHT}
                            vectorEffect="non-scaling-stroke"
                        />
                    )}
                </svg>
            )}
        </figure>
    )
}
