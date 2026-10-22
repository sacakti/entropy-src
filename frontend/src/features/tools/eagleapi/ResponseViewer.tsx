import { lazy, Suspense, useState } from 'react'
import { AlertCircle, Check, Copy, LoaderCircle, Radio, Square } from 'lucide-react'

import type { EagleResult } from '../../../api/eagleapi.api'
import { formatBytes, prettyJson } from './model'

const CodeEditor = lazy(() => import('./CodeEditor'))

export type PollAttempt = {
    attempt: number
    at: Date
    result: EagleResult
}

export type PollRun = {
    url: string | null
    attempts: PollAttempt[]
    /** null while polling. */
    finished: string | null
    error?: string
    nextAt?: number
}

type View = 'body' | 'headers' | 'request' | 'polling'

function statusTone(status: number | undefined): string {
    if (status === undefined) return 'error'
    if (status < 300) return 'ok'
    if (status < 400) return 'info'
    if (status < 500) return 'warn'
    return 'error'
}

function languageOf(result: EagleResult): string {
    const type = (result.headers ?? []).find(([key]) => key.toLowerCase() === 'content-type')?.[1] ?? ''
    if (type.includes('json')) return 'json'
    if (type.includes('xml')) return 'xml'
    if (type.includes('html')) return 'html'
    return 'plaintext'
}

function snippet(result: EagleResult): string {
    if (result.error) return result.error
    if (result.is_base64) return '(binary)'
    const text = (result.body ?? '').replace(/\s+/g, ' ').trim()
    return text.length > 140 ? `${text.slice(0, 140)}…` : text
}

function StatusBadge({ result }: { result: EagleResult }) {
    return (
        <span className={`eagle-status eagle-status-${statusTone(result.error ? undefined : result.status)}`}>
            {result.error ? 'Error' : `${result.status} ${result.reason ?? ''}`.trim()}
        </span>
    )
}

/**
 * The response: status, time, size; the body (pretty JSON or raw), the
 * headers, the request that was really sent (secrets masked) and, when the
 * request polls, every poll attempt.
 */
export default function ResponseViewer({
    result,
    sending,
    poll,
    onStopPolling,
    shown,
    onShow,
}: {
    result: EagleResult | null
    sending: boolean
    poll: PollRun | null
    onStopPolling: () => void
    /** Which response is shown: null for the main call, else a poll attempt number. */
    shown: number | null
    onShow: (attempt: number | null) => void
}) {
    const [view, setView] = useState<View>('body')
    const [pretty, setPretty] = useState(true)
    const [copied, setCopied] = useState(false)

    const current = shown === null ? result : (poll?.attempts.find((item) => item.attempt === shown)?.result ?? result)

    if (!current && !sending) {
        return (
            <section className="eagle-response eagle-response-empty" aria-label="Response">
                <Radio size={20} aria-hidden="true" />
                <p>Send the request to see the response here.</p>
            </section>
        )
    }

    if (!current) {
        return (
            <section className="eagle-response eagle-response-empty" aria-label="Response" role="status">
                <LoaderCircle size={20} className="entropy-spin" aria-hidden="true" />
                <p>Waiting for the response…</p>
            </section>
        )
    }

    const body = current.body ?? ''
    const formatted = !current.is_base64 && pretty ? prettyJson(body) : null
    const views: { id: View; label: string }[] = [
        { id: 'body', label: 'Body' },
        { id: 'headers', label: `Headers${current.headers ? ` (${current.headers.length})` : ''}` },
        { id: 'request', label: 'Request sent' },
    ]
    if (poll) views.push({ id: 'polling', label: `Polling (${poll.attempts.length})` })
    const activeView = views.some((item) => item.id === view) ? view : 'body'

    const copy = async () => {
        try {
            await navigator.clipboard.writeText(formatted ?? body)
            setCopied(true)
            window.setTimeout(() => setCopied(false), 1500)
        } catch {
            setCopied(false)
        }
    }

    return (
        <section className="eagle-response" aria-label="Response">
            <div className="eagle-response-summary">
                <StatusBadge result={current} />
                <span>
                    <strong>{current.elapsed_ms}</strong> ms
                </span>
                {current.size !== undefined && <span>{formatBytes(current.size)}</span>}
                {current.truncated && <span className="eagle-warn-text">Truncated at 10 MB</span>}
                {shown !== null && (
                    <button type="button" className="entropy-button entropy-button-link" onClick={() => onShow(null)}>
                        Poll attempt {shown} · show main response
                    </button>
                )}
                {sending && <LoaderCircle size={15} className="entropy-spin" aria-label="Sending" />}
            </div>

            <div className="eagle-tabs eagle-tabs-sm" role="tablist" aria-label="Response views">
                {views.map((item) => (
                    <button
                        key={item.id}
                        type="button"
                        role="tab"
                        aria-selected={activeView === item.id}
                        className={activeView === item.id ? 'is-active' : ''}
                        onClick={() => setView(item.id)}
                    >
                        {item.label}
                    </button>
                ))}
            </div>

            {activeView === 'body' &&
                (current.error ? (
                    <div className="entropy-alert entropy-alert-error" role="alert">
                        <AlertCircle size={16} />
                        <span>{current.error}</span>
                    </div>
                ) : (
                    <div className="eagle-body-view">
                        <div className="eagle-body-tools">
                            {!current.is_base64 && (
                                <div className="eagle-segmented" role="group" aria-label="Body format">
                                    <button type="button" className={pretty ? 'is-active' : ''} onClick={() => setPretty(true)}>
                                        Pretty
                                    </button>
                                    <button type="button" className={!pretty ? 'is-active' : ''} onClick={() => setPretty(false)}>
                                        Raw
                                    </button>
                                </div>
                            )}
                            {current.is_base64 && <span className="eagle-muted">Binary body, shown as base64.</span>}
                            <button type="button" className="entropy-button entropy-button-ghost entropy-button-sm" onClick={() => void copy()}>
                                {copied ? <Check size={14} /> : <Copy size={14} />} {copied ? 'Copied' : 'Copy body'}
                            </button>
                        </div>
                        {body ? (
                            formatted !== null || (pretty && !current.is_base64) ? (
                                <div className="eagle-code">
                                    <Suspense fallback={<pre className="eagle-pre">{formatted ?? body}</pre>}>
                                        <CodeEditor
                                            value={formatted ?? body}
                                            language={formatted !== null ? 'json' : languageOf(current)}
                                            readOnly
                                            label="Response body"
                                        />
                                    </Suspense>
                                </div>
                            ) : (
                                <pre className="eagle-pre">{body}</pre>
                            )
                        ) : (
                            <p className="eagle-muted">Empty body.</p>
                        )}
                    </div>
                ))}

            {activeView === 'headers' && (
                <div className="eagle-table-wrap">
                    <table className="eagle-table">
                        <thead>
                            <tr>
                                <th>Header</th>
                                <th>Value</th>
                            </tr>
                        </thead>
                        <tbody>
                            {(current.headers ?? []).map(([key, value], index) => (
                                <tr key={`${key}-${index}`}>
                                    <td>{key}</td>
                                    <td>{value}</td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                    {!current.headers?.length && <p className="eagle-muted">No headers.</p>}
                </div>
            )}

            {activeView === 'request' && (
                <div className="eagle-sent">
                    <p className="eagle-sent-line">
                        <span className={`eagle-method eagle-method-${current.request.method.toLowerCase()}`}>
                            {current.request.method}
                        </span>
                        <code>{current.request.url}</code>
                    </p>
                    {current.final_url && current.final_url !== current.request.url && (
                        <p className="eagle-muted">Redirected to {current.final_url}</p>
                    )}
                    <div className="eagle-table-wrap">
                        <table className="eagle-table">
                            <thead>
                                <tr>
                                    <th>Header</th>
                                    <th>Value</th>
                                </tr>
                            </thead>
                            <tbody>
                                {current.request.headers.map(([key, value], index) => (
                                    <tr key={`${key}-${index}`}>
                                        <td>{key}</td>
                                        <td>{value}</td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>
                    <p className="eagle-muted">Vault secrets are shown as ••••.</p>
                </div>
            )}

            {activeView === 'polling' && poll && (
                <div className="eagle-poll">
                    <div className="eagle-poll-head">
                        <span>
                            {poll.finished ? (
                                <>
                                    <strong>Finished:</strong> {poll.finished}
                                </>
                            ) : poll.error ? (
                                <span className="eagle-warn-text">{poll.error}</span>
                            ) : (
                                <>
                                    <LoaderCircle size={14} className="entropy-spin" aria-hidden="true" /> Polling{' '}
                                    <code>{poll.url}</code>
                                </>
                            )}
                        </span>
                        {!poll.finished && !poll.error && (
                            <button type="button" className="entropy-button entropy-button-danger entropy-button-sm" onClick={onStopPolling}>
                                <Square size={13} /> Stop
                            </button>
                        )}
                    </div>
                    {poll.attempts.length > 0 ? (
                        <ol className="eagle-timeline">
                            {poll.attempts.map((item) => (
                                <li key={item.attempt} className={shown === item.attempt ? 'is-selected' : ''}>
                                    <button type="button" onClick={() => onShow(item.attempt)}>
                                        <span className="eagle-timeline-n">#{item.attempt}</span>
                                        <time>{item.at.toLocaleTimeString()}</time>
                                        <StatusBadge result={item.result} />
                                        <span className="eagle-timeline-ms">{item.result.elapsed_ms} ms</span>
                                        <span className="eagle-timeline-body">{snippet(item.result)}</span>
                                        {item.result.poll?.done && <span className="eagle-timeline-done">{item.result.poll.reason}</span>}
                                    </button>
                                </li>
                            ))}
                        </ol>
                    ) : (
                        !poll.error && <p className="eagle-muted">The first poll starts after the interval.</p>
                    )}
                </div>
            )}
        </section>
    )
}
