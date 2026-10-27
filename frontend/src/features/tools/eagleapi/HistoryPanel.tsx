import { useEffect, useRef, useState } from 'react'
import { Download, Search, Trash2 } from 'lucide-react'

import FloatingMenu from '../../../components/layout/FloatingMenu'
import { useFeedback } from '../../../components/feedback/FeedbackProvider'
import { eagleApi, type EagleHistorySummary } from '../../../api/eagleapi.api'
import EntropyLoader from '../../../components/feedback/EntropyLoader'
import { useErrorToast } from '../../../components/feedback/useToast'

function errorText(cause: unknown, fallback: string): string {
    return cause instanceof Error && cause.message ? cause.message : fallback
}

function when(iso: string): string {
    const date = new Date(iso)
    const today = new Date()
    const time = date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })
    return date.toDateString() === today.toDateString() ? time : `${date.toLocaleDateString()} ${time}`
}

function statusClass(entry: EagleHistorySummary): string {
    if (entry.error || entry.status === null) return 'is-error'
    if (entry.status >= 500) return 'is-error'
    if (entry.status >= 400) return 'is-warn'
    return 'is-ok'
}

/**
 * Your sent requests in this project (newest first): open one to see the
 * request and its response again, export them (EagleAPI JSON or HAR) or
 * purge them.
 */
export default function HistoryPanel({
    refreshKey,
    activeId,
    record,
    onRecordChange,
    onOpen,
}: {
    /** Changes after each send, to reload. */
    refreshKey: number
    activeId: number | null
    record: boolean
    onRecordChange: (value: boolean) => void
    onOpen: (id: number) => void
}) {
    const { notify, modal } = useFeedback()
    const [entries, setEntries] = useState<EagleHistorySummary[]>([])
    const [total, setTotal] = useState(0)
    const [loading, setLoading] = useState(true)
    const [error, setError] = useState<string | null>(null)
    useErrorToast(error)
    const [query, setQuery] = useState('')
    const [chosen, setChosen] = useState<Set<number>>(new Set())
    const [reload, setReload] = useState(0)
    const [exportOpen, setExportOpen] = useState(false)
    const exportRef = useRef<HTMLButtonElement>(null)

    useEffect(() => {
        let active = true
        const timer = window.setTimeout(() => {
            eagleApi
                .history(query.trim())
                .then((result) => {
                    if (!active) return
                    setEntries(result.entries)
                    setTotal(result.total)
                    setError(null)
                    setChosen((current) => new Set([...current].filter((id) => result.entries.some((entry) => entry.id === id))))
                })
                .catch((cause) => {
                    if (active) setError(errorText(cause, 'History could not be loaded.'))
                })
                .finally(() => {
                    if (active) setLoading(false)
                })
        }, query ? 250 : 0)
        return () => {
            active = false
            window.clearTimeout(timer)
        }
    }, [query, refreshKey, reload])

    const selection = chosen.size ? [...chosen] : null

    const purge = async () => {
        const count = selection ? selection.length : total
        const confirmed = await modal.confirm({
            title: selection ? `Delete ${count} history entr${count === 1 ? 'y' : 'ies'}?` : 'Clear your history?',
            message: selection
                ? 'The chosen requests and their responses are deleted from your history.'
                : `All ${count} requests and responses in your history of this project are deleted.`,
            confirmText: selection ? 'Delete' : 'Clear history',
            destructive: true,
        })
        if (!confirmed) return
        try {
            const result = await eagleApi.purgeHistory(selection)
            notify.success(`${result.deleted} entr${result.deleted === 1 ? 'y' : 'ies'} deleted.`)
            setChosen(new Set())
            setReload((value) => value + 1)
        } catch (cause) {
            notify.error(errorText(cause, 'History was not deleted.'))
        }
    }

    const download = async (format: 'json' | 'har') => {
        setExportOpen(false)
        try {
            await eagleApi.exportHistory(selection, format)
        } catch (cause) {
            notify.error(errorText(cause, 'The export failed.'))
        }
    }

    return (
        <div className="eagle-history">
            <div className="eagle-history-tools">
                <label className="eagle-history-search">
                    <Search size={14} aria-hidden="true" />
                    <input value={query} placeholder="Search URL or name" aria-label="Search history" onChange={(event) => setQuery(event.target.value)} />
                </label>
                <button
                    ref={exportRef}
                    type="button"
                    className="entropy-button entropy-button-ghost entropy-button-icon entropy-button-sm"
                    aria-label={selection ? 'Export the chosen entries' : 'Export history'}
                    title={selection ? `Export ${selection.length} chosen` : 'Export history with responses'}
                    disabled={!entries.length}
                    aria-haspopup="menu"
                    onClick={() => setExportOpen((value) => !value)}
                >
                    <Download size={15} />
                </button>
                <FloatingMenu anchorRef={exportRef} open={exportOpen} onClose={() => setExportOpen(false)} className="eagle-menu">
                    <button type="button" role="menuitem" onClick={() => void download('json')}>
                        EagleAPI JSON (requests and responses)
                    </button>
                    <button type="button" role="menuitem" onClick={() => void download('har')}>
                        HAR 1.2 (browsers, Postman, Insomnia, Charles)
                    </button>
                </FloatingMenu>
                <button
                    type="button"
                    className="entropy-button entropy-button-ghost entropy-button-icon entropy-button-sm"
                    aria-label={selection ? 'Delete the chosen entries' : 'Clear history'}
                    title={selection ? `Delete ${selection.length} chosen` : 'Clear history'}
                    disabled={!entries.length}
                    onClick={() => void purge()}
                >
                    <Trash2 size={15} />
                </button>
            </div>
            <label className="eagle-check eagle-history-record">
                <input type="checkbox" checked={record} onChange={(event) => onRecordChange(event.target.checked)} />
                <span>Save sent requests here</span>
            </label>

            {loading ? (
                <EntropyLoader />
            ) : error ? (
                <p className="entropy-unavailable">Not available.</p>
            ) : entries.length === 0 ? (
                <div className="eagle-tree-blank">
                    <p>{query ? 'Nothing matches.' : 'No history yet.'}</p>
                    <p className="eagle-muted">Requests you send are kept here, only for you.</p>
                </div>
            ) : (
                <>
                    <ul className="eagle-history-list" aria-label="History">
                        {entries.map((entry) => (
                            <li key={entry.id} className={entry.id === activeId ? 'is-selected' : undefined}>
                                <input
                                    type="checkbox"
                                    aria-label={`Choose ${entry.method} ${entry.url}`}
                                    checked={chosen.has(entry.id)}
                                    onChange={() =>
                                        setChosen((current) => {
                                            const next = new Set(current)
                                            if (next.has(entry.id)) next.delete(entry.id)
                                            else next.add(entry.id)
                                            return next
                                        })
                                    }
                                />
                                <button type="button" className="eagle-history-entry" onClick={() => onOpen(entry.id)} title={entry.url}>
                                    <span className="eagle-history-line">
                                        <span className={`eagle-method eagle-method-${entry.method.toLowerCase()}`}>{entry.method}</span>
                                        <span className="eagle-history-name">{entry.item_name || entry.url.replace(/^https?:\/\//, '')}</span>
                                    </span>
                                    <span className="eagle-history-meta">
                                        <span className={`eagle-history-status ${statusClass(entry)}`}>{entry.error ? 'Error' : entry.status}</span>
                                        <span>{entry.elapsed_ms} ms</span>
                                        {entry.poll && <span>poll</span>}
                                        {entry.environment && <span>{entry.environment}</span>}
                                        <span className="eagle-history-time">{when(entry.created_at)}</span>
                                    </span>
                                </button>
                            </li>
                        ))}
                    </ul>
                    <p className="eagle-muted eagle-pad">
                        {total > entries.length ? `Showing ${entries.length} of ${total}. ` : ''}The newest 500 are kept.
                    </p>
                </>
            )}
        </div>
    )
}
