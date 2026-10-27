import { useEffect, useMemo, useState } from 'react'
import { Columns2, History, LoaderCircle, RotateCcw, Rows2 } from 'lucide-react'

import { pluginHistoryApi, workflowHistoryApi, type HistoryEntry } from '../../api/history.api'
import { pluginsApi } from '../../api/plugins.api'
import { workflowsApi } from '../../api/workflows.api'
import { useFeedback } from '../../components/feedback/FeedbackProvider'
import Dialog from '../../components/layout/Dialog'
import DiffView from '../plugins/editor/DiffView'
import { errorMessage, formatDateTime } from '../runs/format'
import '../../styles/history.css'
import EntropyLoader from '../../components/feedback/EntropyLoader'
import { useErrorToast } from '../../components/feedback/useToast'

type Kind = 'workflow' | 'plugin'

/** One side of the comparison: a single definition, or a plugin's files. */
type Snapshot = Record<string, string>

const WORKFLOW_FILE = 'definition.yaml'

function languageOf(path: string): string {
    if (path.endsWith('.py')) return 'python'
    if (path.endsWith('.json')) return 'json'
    if (path.endsWith('.yaml')) return 'yaml'
    if (path.endsWith('.md')) return 'markdown'
    return 'plaintext'
}

type FileChange = { path: string; state: 'modified' | 'added' | 'removed' }

/** Files that differ between the kept version and the current one. */
function changes(kept: Snapshot, current: Snapshot): FileChange[] {
    const paths = Array.from(new Set([...Object.keys(kept), ...Object.keys(current)])).sort()
    return paths
        .filter((path) => kept[path] !== current[path])
        .map((path) => ({
            path,
            // "added"/"removed" as restoring would do it.
            state: !(path in current) ? 'added' : !(path in kept) ? 'removed' : 'modified',
        }))
}

/**
 * Earlier versions of a workflow or plugin (the last five kept before each
 * change): compare one with the current version and restore it.
 */
export default function HistoryDialog({
    kind,
    name,
    restoreReason,
    onRestored,
    onClose,
}: {
    kind: Kind
    name: string
    /** Why the user may not restore, or null when they may. */
    restoreReason: string | null
    onRestored: (version: string) => void
    onClose: () => void
}) {
    const { notify, modal } = useFeedback()
    const api = kind === 'workflow' ? workflowHistoryApi : pluginHistoryApi

    const [entries, setEntries] = useState<HistoryEntry[] | null>(null)
    const [currentVersion, setCurrentVersion] = useState('')
    const [current, setCurrent] = useState<Snapshot | null>(null)
    const [selected, setSelected] = useState<number | null>(null)
    const [kept, setKept] = useState<Snapshot | null>(null)
    const [file, setFile] = useState<string | null>(null)
    const [sideBySide, setSideBySide] = useState(true)
    const [error, setError] = useState<string | null>(null)
    useErrorToast(error)
    const [restoring, setRestoring] = useState(false)

    const theme = document.documentElement.dataset.theme === 'light' ? 'entropy-light' : 'entropy-dark'

    // The list and the current version.
    useEffect(() => {
        let active = true
        const load = async () => {
            const list = await api.list(name)
            const now: Snapshot =
                kind === 'workflow'
                    ? { [WORKFLOW_FILE]: (await workflowsApi.get(name, 'yaml')).definition }
                    : Object.fromEntries((await pluginsApi.files(name)).files.map((item) => [item.path, item.content]))
            if (!active) return
            setEntries(list.items)
            setCurrentVersion(list.current_version)
            setCurrent(now)
            setSelected(list.items[0]?.id ?? null)
        }
        load().catch((cause: unknown) => {
            if (active) setError(errorMessage(cause, 'Unable to load the history.'))
        })
        return () => {
            active = false
        }
    }, [api, kind, name])

    // The selected kept version.
    useEffect(() => {
        if (selected === null) return
        let active = true
        const load = async () => {
            const snapshot: Snapshot =
                kind === 'workflow'
                    ? { [WORKFLOW_FILE]: (await workflowHistoryApi.get(name, selected)).definition }
                    : (await pluginHistoryApi.get(name, selected)).files
            if (active) setKept(snapshot)
        }
        load().catch((cause: unknown) => {
            if (active) setError(errorMessage(cause, 'Unable to load that version.'))
        })
        return () => {
            active = false
        }
    }, [kind, name, selected])

    const changed = useMemo(() => (kept && current ? changes(kept, current) : []), [kept, current])
    const shownFile = file && changed.some((item) => item.path === file) ? file : changed[0]?.path ?? null
    const entry = entries?.find((item) => item.id === selected) ?? null

    const restore = async () => {
        if (!entry || restoreReason) return
        const confirmed = await modal.confirm({
            title: `Restore version ${entry.version}?`,
            message:
                `The current version (${currentVersion}) is kept in the history first. ` +
                `The restored content becomes the next version.`,
            confirmText: 'Restore',
            cancelText: 'Cancel',
        })
        if (!confirmed) return

        setRestoring(true)
        setError(null)
        try {
            const result = await api.restore(name, entry.id)
            const version = 'version' in result ? result.version : result.plugin.version
            notify.success(`${name} is back to version ${entry.version}'s content, as ${version}.`, {
                title: 'Version restored',
            })
            onRestored(version)
            onClose()
        } catch (cause) {
            setError(errorMessage(cause, 'Unable to restore that version.'))
        } finally {
            setRestoring(false)
        }
    }

    return (
        <Dialog
            title={`History of ${name}`}
            subtitle="The last five versions, kept before each change. Compare one with the current version or restore it."
            icon={<History size={18} />}
            onClose={onClose}
            className="history-dialog"
            footer={
                <>
                    <button type="button" className="entropy-button entropy-button-secondary" onClick={onClose}>
                        Close
                    </button>
                    {entry && (
                        <button
                            type="button"
                            className="entropy-button entropy-button-primary"
                            aria-disabled={restoreReason ? true : undefined}
                            title={restoreReason ?? `Make version ${entry.version} current again`}
                            disabled={restoring}
                            onClick={() => void restore()}
                        >
                            {restoring ? <LoaderCircle size={15} className="entropy-spin" /> : <RotateCcw size={15} />}
                            Restore {entry.version}
                        </button>
                    )}
                </>
            }
        >

            {entries === null ? (
                !error && <EntropyLoader />
            ) : entries.length === 0 ? (
                <p className="history-empty">
                    <History size={18} aria-hidden="true" />
                    No earlier versions yet. Each save keeps the version it replaces here.
                </p>
            ) : (
                <div className="history-layout">
                    <ol className="history-versions" aria-label="Kept versions">
                        <li className="history-current">
                            <strong>{currentVersion}</strong>
                            <span>Current version</span>
                        </li>
                        {entries.map((item) => (
                            <li key={item.id}>
                                <button
                                    type="button"
                                    className={item.id === selected ? 'is-selected' : ''}
                                    aria-pressed={item.id === selected}
                                    onClick={() => {
                                        setSelected(item.id)
                                        setKept(null)
                                    }}
                                >
                                    <strong>{item.version}</strong>
                                    <span>{formatDateTime(item.created_at)}</span>
                                    <small>
                                        {item.reason === 'restore' ? 'Kept before a restore' : 'Kept before an edit'}
                                        {item.created_by ? ` · ${item.created_by}` : ''}
                                    </small>
                                </button>
                            </li>
                        ))}
                    </ol>

                    <section className="history-compare">
                        <header>
                            <span>
                                <strong>{entry?.version}</strong> (kept) ↔ <strong>{currentVersion}</strong> (current)
                            </span>
                            <button
                                type="button"
                                className="entropy-button entropy-button-ghost entropy-button-sm"
                                onClick={() => setSideBySide((value) => !value)}
                            >
                                {sideBySide ? <Rows2 size={14} /> : <Columns2 size={14} />}
                                {sideBySide ? 'Inline' : 'Side by side'}
                            </button>
                        </header>

                        {kind === 'plugin' && changed.length > 0 && (
                            <div className="history-files" role="tablist" aria-label="Changed files">
                                {changed.map((item) => (
                                    <button
                                        key={item.path}
                                        type="button"
                                        role="tab"
                                        aria-selected={item.path === shownFile}
                                        className={`history-file is-${item.state}${item.path === shownFile ? ' is-active' : ''}`}
                                        onClick={() => setFile(item.path)}
                                    >
                                        {item.path}
                                        <em>{item.state === 'added' ? 'only in kept' : item.state === 'removed' ? 'only in current' : 'changed'}</em>
                                    </button>
                                ))}
                            </div>
                        )}

                        <div className="history-diff">
                            {!kept || !current ? (
                                <EntropyLoader />
                            ) : shownFile === null ? (
                                <p className="run-card-muted">This version is the same as the current one.</p>
                            ) : (
                                <DiffView
                                    key={shownFile}
                                    original={kept[shownFile] ?? ''}
                                    modified={current[shownFile] ?? ''}
                                    language={languageOf(shownFile)}
                                    theme={theme}
                                    sideBySide={sideBySide}
                                />
                            )}
                        </div>
                    </section>
                </div>
            )}
        </Dialog>
    )
}
