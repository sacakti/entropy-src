import { useCallback, useEffect, useState } from 'react'
import {
    AlertCircle,
    Check,
    Copy,
    Cpu,
    HardDrive,
    LoaderCircle,
    MemoryStick,
    RefreshCw,
    Server,
    Table2,
    TrendingUp,
} from 'lucide-react'

import { nodesApi, type EntropyNode, type MetricSample } from '../../api/runs.api'
import { useFeedback } from '../../components/feedback/FeedbackProvider'
import { errorMessage, formatBytes, formatDateTime, formatDuration, formatTime } from '../runs/format'
import MetricChart from './MetricChart'

const REFRESH_MS = 10_000

function level(percent: number | null): 'ok' | 'warning' | 'critical' {
    if (percent === null) return 'ok'
    if (percent >= 90) return 'critical'
    if (percent >= 75) return 'warning'
    return 'ok'
}

const LEVEL_LABEL = { ok: 'Normal', warning: 'High', critical: 'Critical' } as const

function Meter({
    icon,
    label,
    percent,
    detail,
}: {
    icon: React.ReactNode
    label: string
    percent: number | null
    detail: string
}) {
    const tone = level(percent)

    return (
        <div className={`node-meter is-${tone}`}>
            <div className="node-meter-head">
                <span className="node-meter-icon" aria-hidden="true">
                    {icon}
                </span>
                <span>{label}</span>
                <strong>{percent === null ? '—' : `${percent.toFixed(1)}%`}</strong>
            </div>
            <div
                className="node-meter-track"
                role="meter"
                aria-label={label}
                aria-valuemin={0}
                aria-valuemax={100}
                aria-valuenow={percent ?? 0}
            >
                <span style={{ width: `${Math.min(100, percent ?? 0)}%` }} />
            </div>
            <small>
                {detail}
                {tone !== 'ok' && <em> · {LEVEL_LABEL[tone]}</em>}
            </small>
        </div>
    )
}

function NodeCard({ node, history }: { node: EntropyNode; history: MetricSample[] }) {
    const { notify } = useFeedback()
    const [view, setView] = useState<'chart' | 'table'>('chart')
    const [copied, setCopied] = useState(false)
    const metrics = node.metrics
    const endpoint = `${window.location.origin}${nodesApi.metricsUrl(node.name)}`

    const copy = async () => {
        try {
            await navigator.clipboard.writeText(endpoint)
            setCopied(true)
            setTimeout(() => setCopied(false), 1500)
        } catch {
            notify.error('Unable to copy to the clipboard.')
        }
    }

    return (
        <article className="dashboard-section node-card">
            <header className="node-card-head">
                <span className="list-name-icon node-card-icon" aria-hidden="true">
                    <Server size={18} />
                </span>
                <div className="node-card-title">
                    <h2>
                        {node.name}
                        {node.kind === 'local' && <span className="list-version">Main node</span>}
                    </h2>
                    <p>
                        {node.host} · {node.info.os} {node.info.release} · {node.info.arch} · Python{' '}
                        {node.info.python}
                    </p>
                </div>
                <span className={`run-status ${node.agent_up ? 'is-completed' : 'is-failed'}`}>
                    {node.agent_up ? <Check size={13} aria-hidden="true" /> : <AlertCircle size={13} aria-hidden="true" />}
                    {node.agent_up ? 'Runnable' : node.enabled ? 'Unreachable' : 'Disabled'}
                </span>
            </header>

            {metrics ? (
                <>
                    <div className="node-meters">
                        <Meter
                            icon={<Cpu size={15} />}
                            label="CPU"
                            percent={metrics.cpu.percent}
                            detail={`${metrics.cpu.count ?? '?'} cores · load ${metrics.load
                                .map((value) => (value === null ? '—' : value.toFixed(2)))
                                .join(' / ')}`}
                        />
                        <Meter
                            icon={<MemoryStick size={15} />}
                            label="Memory"
                            percent={metrics.memory.percent}
                            detail={`${formatBytes(metrics.memory.used)} of ${formatBytes(metrics.memory.total)}`}
                        />
                        <Meter
                            icon={<HardDrive size={15} />}
                            label="Disk"
                            percent={metrics.disk.percent}
                            detail={`${formatBytes(metrics.disk.free ?? null)} free of ${formatBytes(metrics.disk.total)}`}
                        />
                    </div>

                    <dl className="run-meta node-facts">
                        <div>
                            <dt>Running jobs</dt>
                            <dd>{node.running_jobs}</dd>
                        </div>
                        <div>
                            <dt>Uptime</dt>
                            <dd>
                                {metrics.uptime_seconds === null ? '—' : formatDuration(metrics.uptime_seconds * 1000)}
                            </dd>
                        </div>
                        <div>
                            <dt>Last seen</dt>
                            <dd>{formatDateTime(node.last_seen_at)}</dd>
                        </div>
                        <div>
                            <dt>Data path</dt>
                            <dd title={metrics.disk.path}>{metrics.disk.path}</dd>
                        </div>
                    </dl>
                </>
            ) : (
                <p className="run-card-muted">This node has not reported metrics yet.</p>
            )}

            <section className="node-history">
                <header>
                    <h3>Last hour</h3>
                    <div className="seg-control" role="tablist" aria-label="History view">
                        <button
                            type="button"
                            role="tab"
                            aria-selected={view === 'chart'}
                            className={view === 'chart' ? 'is-active' : ''}
                            onClick={() => setView('chart')}
                        >
                            <TrendingUp size={13} /> Chart
                        </button>
                        <button
                            type="button"
                            role="tab"
                            aria-selected={view === 'table'}
                            className={view === 'table' ? 'is-active' : ''}
                            onClick={() => setView('table')}
                        >
                            <Table2 size={13} /> Table
                        </button>
                    </div>
                </header>

                {view === 'chart' ? (
                    <div className="node-charts">
                        <MetricChart title="CPU" field="cpu_percent" samples={history} />
                        <MetricChart title="Memory" field="memory_percent" samples={history} />
                        <MetricChart title="Disk" field="disk_percent" samples={history} />
                    </div>
                ) : (
                    <div className="list-table-wrap node-history-table">
                        <table className="list-table">
                            <thead>
                                <tr>
                                    <th scope="col">Time</th>
                                    <th scope="col">CPU</th>
                                    <th scope="col">Memory</th>
                                    <th scope="col">Disk</th>
                                    <th scope="col">Load</th>
                                    <th scope="col">Jobs</th>
                                </tr>
                            </thead>
                            <tbody>
                                {[...history].reverse().map((sample) => (
                                    <tr key={sample.sampled_at}>
                                        <td className="list-cell-text">{formatTime(sample.sampled_at)}</td>
                                        <td>{sample.cpu_percent?.toFixed(1) ?? '—'}%</td>
                                        <td>{sample.memory_percent?.toFixed(1) ?? '—'}%</td>
                                        <td>{sample.disk_percent?.toFixed(1) ?? '—'}%</td>
                                        <td>{sample.load1?.toFixed(2) ?? '—'}</td>
                                        <td>{sample.running_jobs}</td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>
                )}
            </section>

            <footer className="node-endpoint">
                <div>
                    <strong>Metrics endpoint</strong>
                    <span>Prometheus text format, for any TSDB scraper (authenticated session).</span>
                </div>
                <code>{endpoint}</code>
                <button
                    type="button"
                    className="entropy-button entropy-button-secondary entropy-button-icon entropy-button-sm"
                    aria-label="Copy metrics endpoint"
                    title="Copy"
                    onClick={() => void copy()}
                >
                    {copied ? <Check size={14} /> : <Copy size={14} />}
                </button>
            </footer>
        </article>
    )
}

export default function Nodes() {
    const [nodes, setNodes] = useState<EntropyNode[]>([])
    const [history, setHistory] = useState<Record<string, MetricSample[]>>({})
    const [loading, setLoading] = useState(true)
    const [refreshing, setRefreshing] = useState(false)
    const [error, setError] = useState<string | null>(null)

    const load = useCallback(async () => {
        try {
            const { items } = await nodesApi.list()
            const details = await Promise.all(items.map((node) => nodesApi.get(node.name, 1)))
            setNodes(details.map((detail) => detail.node))
            setHistory(Object.fromEntries(details.map((detail) => [detail.node.name, detail.history])))
            setError(null)
        } catch (cause) {
            setError(errorMessage(cause, 'Unable to load nodes.'))
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

    return (
        <section className="list-page nodes-page">
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
                            Execution nodes
                            <span className="list-count">{nodes.length}</span>
                        </h2>
                        <p>Servers that run workflows. The main node also stores users and Entropy data.</p>
                    </div>
                    <div className="entropy-panel-actions">
                        <button
                            type="button"
                            className="entropy-button entropy-button-secondary entropy-button-icon"
                            aria-label="Refresh nodes"
                            title="Refresh"
                            onClick={() => {
                                setRefreshing(true)
                                void load()
                            }}
                            disabled={loading || refreshing}
                        >
                            <RefreshCw size={16} className={refreshing ? 'entropy-spin' : ''} />
                        </button>
                    </div>
                </div>
                <p className="nodes-note">
                    Remote nodes are added by bootstrapping the Entropy agent over SSH; that arrives in the next release.
                </p>
            </section>

            {loading ? (
                <div className="list-empty" role="status">
                    <LoaderCircle size={18} className="entropy-spin" />
                    Loading nodes…
                </div>
            ) : (
                nodes.map((node) => <NodeCard key={node.name} node={node} history={history[node.name] ?? []} />)
            )}
        </section>
    )
}
