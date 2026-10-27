import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
    Bird,
    Download,
    FilePlus,
    FolderPlus,
    Globe,
    History,
    LoaderCircle,
    Lock,
    Save,
    Send,
    ShieldCheck,
    Square,
    Upload,
} from 'lucide-react'

import { useFeedback } from '../../../components/feedback/FeedbackProvider'
import { missingPermission } from '../../administration/permissionReason'
import { usePermissions } from '../../administration/usePermissions'
import { currentProject } from '../../../services/project'
import {
    eagleApi,
    type EagleEnvironment,
    type EagleHistoryEntry,
    type EagleItem,
    type EagleRequestData,
    type EagleResult,
    type EagleSettings,
} from '../../../api/eagleapi.api'
import AccessDialog from './AccessDialog'
import CollectionTree, { type TreeAction } from './CollectionTree'
import EnvironmentDialog from './EnvironmentDialog'
import { ExportDialog, ImportDialog } from './ExchangeDialogs'
import HistoryPanel from './HistoryPanel'
import { MoveDialog, NameDialog } from './ItemDialogs'
import RequestEditor from './RequestEditor'
import ResponseViewer, { type PollRun } from './ResponseViewer'
import { FILE_SUGGESTIONS, VALUE_SUGGESTIONS } from './TlsFields'
import TlsSettingsDialog from './TlsSettingsDialog'
import { defaultRequest, ENV_STORAGE_KEY, itemPath, itemReadOnlyReason, METHODS, sameRequest, vaultRef } from './model'
import '../../../styles/eagleapi.css'
import EntropyLoader from '../../../components/feedback/EntropyLoader'
import { useErrorToast } from '../../../components/feedback/useToast'

type NameRequest =
    | { kind: 'new-folder' | 'new-request'; parentId: number | null; data?: EagleRequestData; name?: string }
    | { kind: 'rename'; item: EagleItem }

const RECORD_KEY = 'entropy.eagleapi.history.record'

function storedRecord(): boolean {
    try {
        return window.localStorage.getItem(RECORD_KEY) !== 'off'
    } catch {
        return true
    }
}

function errorText(cause: unknown, fallback: string): string {
    return cause instanceof Error && cause.message ? cause.message : fallback
}

function envStorageKey(): string {
    return `${ENV_STORAGE_KEY}.${currentProject() ?? 'default'}`
}

function storedEnvironment(): string | null {
    try {
        return window.localStorage.getItem(envStorageKey())
    } catch {
        return null
    }
}

function rememberEnvironment(name: string | null) {
    try {
        if (name) window.localStorage.setItem(envStorageKey(), name)
        else window.localStorage.removeItem(envStorageKey())
    } catch {
        // Storage refused (private window): the choice lasts this visit.
    }
}

/** Resolves after `ms`, or rejects at once when `signal` aborts. */
function wait(ms: number, signal: AbortSignal): Promise<void> {
    return new Promise((resolve, reject) => {
        if (signal.aborted) {
            reject(new DOMException('Aborted', 'AbortError'))
            return
        }
        const timer = window.setTimeout(resolve, ms)
        signal.addEventListener(
            'abort',
            () => {
                window.clearTimeout(timer)
                reject(new DOMException('Aborted', 'AbortError'))
            },
            { once: true },
        )
    })
}

const isAbort = (cause: unknown) => cause instanceof DOMException && cause.name === 'AbortError'

/**
 * EagleAPI: a Postman-like API tester. Collections (folders and requests)
 * are kept per project on the server; environment values (base URLs,
 * client ids, secrets, certificates) live in the project's vault namespace
 * `eagleapi-<project>`. Requests are sent by the Entropy server.
 */
export default function EagleApi() {
    const { notify, modal } = useFeedback()
    const permissions = usePermissions()
    const writeReason = missingPermission(permissions, ['workflows.write'], 'Changing collections and the environment')
    const sendReason = missingPermission(permissions, ['workflows.execute'], 'Sending requests')

    const [items, setItems] = useState<EagleItem[]>([])
    const [loading, setLoading] = useState(true)
    const [loadError, setLoadError] = useState<string | null>(null)
    useErrorToast(loadError)
    const [expanded, setExpanded] = useState<Set<number>>(new Set())

    const [selected, setSelected] = useState<EagleItem | null>(null)
    const [saved, setSaved] = useState<EagleRequestData | null>(null)
    const [draft, setDraft] = useState<EagleRequestData | null>(null)
    const [opening, setOpening] = useState(false)
    const [saving, setSaving] = useState(false)

    const [environment, setEnvironment] = useState<EagleEnvironment | null>(null)
    const [envName, setEnvName] = useState<string | null>(storedEnvironment)
    const [envOpen, setEnvOpen] = useState(false)
    const [settings, setSettings] = useState<EagleSettings | null>(null)
    const [tlsOpen, setTlsOpen] = useState(false)

    const [result, setResult] = useState<EagleResult | null>(null)
    const [sendError, setSendError] = useState<string | null>(null)
    useErrorToast(sendError)
    const [sending, setSending] = useState(false)
    const [poll, setPoll] = useState<PollRun | null>(null)
    const [shown, setShown] = useState<number | null>(null)
    const abortRef = useRef<AbortController | null>(null)

    const [nameRequest, setNameRequest] = useState<NameRequest | null>(null)
    const [moving, setMoving] = useState<EagleItem | null>(null)

    const [sidebarTab, setSidebarTab] = useState<'collections' | 'history'>('collections')
    const [historyKey, setHistoryKey] = useState(0)
    const [historyView, setHistoryView] = useState<EagleHistoryEntry | null>(null)
    const [recordHistory, setRecordHistory] = useState(storedRecord)
    const [accessItem, setAccessItem] = useState<EagleItem | null>(null)
    const [exportIds, setExportIds] = useState<number[] | null>(null)
    const [importOpen, setImportOpen] = useState(false)

    const dirty = Boolean(selected && draft && !sameRequest(draft, saved))
    // Read-only collections, or no write permission in the project.
    const selectedReadOnlyReason = selected ? itemReadOnlyReason(selected, writeReason) : writeReason

    // ------------------------------------------------------------------
    // Loading
    // ------------------------------------------------------------------

    // The feedback functions change every render; effects read the latest.
    const notifyRef = useRef(notify)
    useEffect(() => {
        notifyRef.current = notify
    })

    const applyEnvironment = useCallback((next: EagleEnvironment) => {
        setEnvironment(next)
        setEnvName((current) => {
            const chosen = current && next.environments.includes(current) ? current : (next.environments[0] ?? null)
            rememberEnvironment(chosen)
            return chosen
        })
    }, [setEnvironment, setEnvName])

    const loadEnvironment = useCallback(async () => {
        try {
            applyEnvironment(await eagleApi.environment())
        } catch (cause) {
            notifyRef.current.error(errorText(cause, 'The environment could not be loaded.'))
        }
    }, [applyEnvironment])

    useEffect(() => {
        let active = true
        eagleApi
            .listItems()
            .then((list) => {
                if (!active) return
                setItems(list)
                // Open the folders on the first visit.
                setExpanded(new Set(list.filter((item) => item.kind === 'folder').map((item) => item.id)))
            })
            .catch((cause) => {
                if (active) setLoadError(errorText(cause, 'Collections could not be loaded.'))
            })
            .finally(() => {
                if (active) setLoading(false)
            })
        eagleApi
            .environment()
            .then((next) => {
                if (active) applyEnvironment(next)
            })
            .catch((cause) => {
                if (active) notifyRef.current.error(errorText(cause, 'The environment could not be loaded.'))
            })
        eagleApi
            .settings()
            .then((next) => {
                if (active) setSettings(next)
            })
            .catch((cause) => {
                if (active) notifyRef.current.error(errorText(cause, 'The TLS settings could not be loaded.'))
            })
        return () => {
            active = false
        }
    }, [applyEnvironment])

    useEffect(
        () => () => {
            abortRef.current?.abort()
        },
        [],
    )

    useEffect(() => {
        if (!dirty) return
        const warn = (event: BeforeUnloadEvent) => {
            event.preventDefault()
        }
        window.addEventListener('beforeunload', warn)
        return () => window.removeEventListener('beforeunload', warn)
    }, [dirty])

    const refreshItems = async () => {
        try {
            setItems(await eagleApi.listItems())
        } catch (cause) {
            notify.error(errorText(cause, 'Collections could not be loaded.'))
        }
    }

    // ------------------------------------------------------------------
    // Opening and saving
    // ------------------------------------------------------------------

    const confirmDiscard = async (): Promise<boolean> => {
        if (!dirty) return true
        return modal.confirm({
            title: 'Discard unsaved changes?',
            message: `${selected?.name ?? 'The request'} has changes that are not saved.`,
            confirmText: 'Discard',
            destructive: true,
        })
    }

    const stopSending = () => {
        abortRef.current?.abort()
        abortRef.current = null
    }

    const openItem = async (item: EagleItem, force = false) => {
        if (item.kind !== 'request') return
        if (!force && item.id === selected?.id) return
        if (!force && !(await confirmDiscard())) return
        setOpening(true)
        try {
            const full = await eagleApi.getItem(item.id)
            const data = full.data ?? defaultRequest()
            stopSending()
            setHistoryView(null)
            setSelected(full)
            setSaved(data)
            setDraft(data)
            setResult(null)
            setPoll(null)
            setSendError(null)
            setShown(null)
        } catch (cause) {
            notify.error(errorText(cause, 'The request could not be opened.'))
        } finally {
            setOpening(false)
        }
    }

    const openHistory = async (id: number) => {
        if (!(await confirmDiscard())) return
        setOpening(true)
        try {
            const entry = await eagleApi.historyEntry(id)
            const data = entry.definition ?? defaultRequest()
            stopSending()
            setSelected(null)
            setSaved(null)
            setHistoryView(entry)
            setDraft(data)
            setResult(entry.result)
            setPoll(null)
            setSendError(null)
            setShown(null)
        } catch (cause) {
            notify.error(errorText(cause, 'The history entry could not be opened.'))
        } finally {
            setOpening(false)
        }
    }

    const changeRecord = (value: boolean) => {
        setRecordHistory(value)
        try {
            window.localStorage.setItem(RECORD_KEY, value ? 'on' : 'off')
        } catch {
            // Storage refused: the choice lasts this visit.
        }
    }

    const save = async () => {
        if (!selected || !draft || selectedReadOnlyReason || saving) return
        setSaving(true)
        try {
            const item = await eagleApi.updateItem(selected.id, { data: draft })
            setSelected(item)
            setSaved(item.data ?? draft)
            setDraft(item.data ?? draft)
            setItems((list) => list.map((entry) => (entry.id === item.id ? { ...entry, method: item.method, updated_at: item.updated_at } : entry)))
            notify.success(`${item.name} saved.`)
        } catch (cause) {
            notify.error(errorText(cause, 'The request was not saved.'))
        } finally {
            setSaving(false)
        }
    }

    const saveRef = useRef(save)
    useEffect(() => {
        saveRef.current = save
    })

    useEffect(() => {
        const handler = (event: KeyboardEvent) => {
            if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 's') {
                event.preventDefault()
                void saveRef.current()
            }
        }
        window.addEventListener('keydown', handler)
        return () => window.removeEventListener('keydown', handler)
    }, [])

    // ------------------------------------------------------------------
    // Tree actions
    // ------------------------------------------------------------------

    const submitName = async (request: NameRequest, name: string): Promise<boolean> => {
        try {
            if (request.kind === 'rename') {
                const item = await eagleApi.updateItem(request.item.id, { name })
                setItems((list) => list.map((entry) => (entry.id === item.id ? { ...entry, name: item.name } : entry)))
                if (selected?.id === item.id) setSelected((current) => (current ? { ...current, name: item.name } : current))
                return true
            }
            if (request.kind === 'new-request' && !(await confirmDiscard())) return false
            const item = await eagleApi.createItem({
                kind: request.kind === 'new-folder' ? 'folder' : 'request',
                name,
                parent_id: request.parentId,
                data: request.kind === 'new-request' ? (request.data ?? defaultRequest()) : undefined,
            })
            await refreshItems()
            if (request.parentId !== null) {
                const parentId = request.parentId
                setExpanded((current) => new Set(current).add(parentId))
            }
            if (item.kind === 'folder') setExpanded((current) => new Set(current).add(item.id))
            else await openItem(item, true)
            return true
        } catch (cause) {
            notify.error(errorText(cause, 'The change was not saved.'))
            return false
        }
    }

    const moveItem = async (id: number, parentId: number | null, position?: number) => {
        try {
            await eagleApi.moveItem(id, parentId, position)
            await refreshItems()
            if (parentId !== null) setExpanded((current) => new Set(current).add(parentId))
        } catch (cause) {
            notify.error(errorText(cause, 'The item could not be moved.'))
        }
    }

    const onTreeAction = async (action: TreeAction) => {
        if (action.kind === 'new-folder' || action.kind === 'new-request') {
            setNameRequest(action)
        } else if (action.kind === 'rename') {
            setNameRequest({ kind: 'rename', item: action.item })
        } else if (action.kind === 'move') {
            setMoving(action.item)
        } else if (action.kind === 'access') {
            setAccessItem(action.item)
        } else if (action.kind === 'export') {
            setExportIds([action.item.id])
        } else if (action.kind === 'duplicate') {
            try {
                const copy = await eagleApi.duplicateItem(action.item.id)
                await refreshItems()
                notify.success(`${copy.name} created.`)
            } catch (cause) {
                notify.error(errorText(cause, 'The item could not be duplicated.'))
            }
        } else if (action.kind === 'delete') {
            const folder = action.item.kind === 'folder'
            const confirmed = await modal.confirm({
                title: `Delete ${action.item.name}?`,
                message: folder ? 'The folder and everything in it are deleted.' : 'The request is deleted.',
                confirmText: 'Delete',
                destructive: true,
            })
            if (!confirmed) return
            try {
                await eagleApi.deleteItem(action.item.id)
                const list = await eagleApi.listItems()
                setItems(list)
                if (selected && !list.some((item) => item.id === selected.id)) {
                    stopSending()
                    setSelected(null)
                    setSaved(null)
                    setDraft(null)
                    setResult(null)
                    setPoll(null)
                }
            } catch (cause) {
                notify.error(errorText(cause, 'The item could not be deleted.'))
            }
        }
    }

    // ------------------------------------------------------------------
    // Sending and polling
    // ------------------------------------------------------------------

    const runPolling = async (request: EagleRequestData, url: string, signal: AbortSignal) => {
        const { interval, max_attempts: maxAttempts } = request.polling
        const run: PollRun = { url, attempts: [], finished: null }
        setPoll({ ...run })
        for (let attempt = 1; attempt <= maxAttempts; attempt += 1) {
            await wait(interval * 1000, signal)
            const response = await eagleApi.send(request, envName, { pollUrl: url, itemId: selected?.id ?? null, record: recordHistory, signal })
            if (response.history_id) setHistoryKey((value) => value + 1)
            run.attempts = [...run.attempts, { attempt, at: new Date(), result: response }]
            if (response.poll?.done) {
                run.finished = response.poll.reason ?? 'Stop condition reached.'
            } else if (attempt === maxAttempts) {
                run.finished = `Stopped after ${maxAttempts} attempts (${response.poll?.reason ?? 'no stop condition reached'}).`
            }
            setPoll({ ...run })
            setShown(attempt)
            if (run.finished) return
        }
    }

    const send = async () => {
        if (!draft || sendReason) return
        stopSending()
        const controller = new AbortController()
        abortRef.current = controller
        const request = draft
        setSending(true)
        setSendError(null)
        setResult(null)
        setPoll(null)
        setShown(null)
        try {
            const response = await eagleApi.send(request, envName, { itemId: selected?.id ?? null, record: recordHistory, signal: controller.signal })
            setResult(response)
            if (response.history_id) setHistoryKey((value) => value + 1)
            if (request.polling.enabled && response.poll) {
                if (response.poll.url) await runPolling(request, response.poll.url, controller.signal)
                else setPoll({ url: null, attempts: [], finished: null, error: response.poll.error ?? 'No poll URL found.' })
            }
        } catch (cause) {
            if (isAbort(cause)) {
                setPoll((current) => (current && !current.finished && !current.error ? { ...current, finished: 'Stopped by you.' } : current))
            } else {
                setSendError(errorText(cause, 'The request could not be sent.'))
            }
        } finally {
            if (abortRef.current === controller) abortRef.current = null
            setSending(false)
        }
    }

    // ------------------------------------------------------------------
    // Rendering
    // ------------------------------------------------------------------

    const namespace = environment?.namespace ?? ''
    const suggestions = useMemo(() => {
        const values: string[] = []
        const files: string[] = []
        for (const entry of environment?.entries ?? []) {
            const target = entry.type === 'file' ? files : values
            target.push(vaultRef(namespace, entry.key, entry.type === 'file'))
            const match = /^([A-Z0-9]+)_(.+)$/.exec(entry.key)
            if (match && environment?.environments.includes(match[1])) {
                const generic = vaultRef(namespace, `{{ENV}}_${match[2]}`, entry.type === 'file')
                if (!target.includes(generic)) target.push(generic)
            }
        }
        return { values, files }
    }, [environment, namespace])

    const absolute = /^[a-z][a-z0-9+.-]*:\/\//i.test(draft?.url.trim() ?? '')
    const urlHint = !draft
        ? null
        : absolute
          ? 'Full URL: the environment base URL is not used.'
          : envName
            ? `Sent to ${envName}_URL + ${draft.url.trim() || '/'}`
            : 'Choose an environment (or type a full URL starting with https://).'

    const path = selected ? itemPath(items, selected.parent_id) : ''
    const readOnly = Boolean(writeReason)
    // A request from the history is a scratch copy: it can be changed and sent, not saved.
    const editorReadOnly = historyView ? false : Boolean(selectedReadOnlyReason)
    const savedItem = historyView?.item_id ? items.find((item) => item.id === historyView.item_id) : undefined

    return (
        <div className="eagle-app">
            <datalist id={VALUE_SUGGESTIONS}>
                {suggestions.values.map((value) => (
                    <option key={value} value={value} />
                ))}
            </datalist>
            <datalist id={FILE_SUGGESTIONS}>
                {suggestions.files.map((value) => (
                    <option key={value} value={value} />
                ))}
            </datalist>

            <div className="eagle-topbar">
                <label className="eagle-env-select">
                    <Globe size={15} aria-hidden="true" />
                    <span className="eagle-sr">Environment</span>
                    <select
                        value={envName ?? ''}
                        onChange={(event) => {
                            const next = event.target.value || null
                            setEnvName(next)
                            rememberEnvironment(next)
                        }}
                        aria-label="Environment"
                    >
                        <option value="">No environment</option>
                        {(environment?.environments ?? []).map((name) => (
                            <option key={name} value={name}>
                                {name}
                            </option>
                        ))}
                    </select>
                </label>
                <button type="button" className="entropy-button entropy-button-secondary entropy-button-sm" onClick={() => setEnvOpen(true)}>
                    Environment…
                </button>
                <button
                    type="button"
                    className="entropy-button entropy-button-secondary entropy-button-sm"
                    disabled={!settings}
                    onClick={() => setTlsOpen(true)}
                    title="TLS profiles that requests can inherit"
                >
                    <ShieldCheck size={14} aria-hidden="true" /> TLS settings…
                </button>
                <span className="eagle-topbar-ns" title="The vault namespace that holds this project's EagleAPI values">
                    <Lock size={13} aria-hidden="true" /> {namespace || '…'}
                </span>
                {(writeReason || sendReason) && (
                    <span className="eagle-topbar-readonly" title={[writeReason, sendReason].filter(Boolean).join(' ')}>
                        {writeReason ? 'Read only' : 'Cannot send'}
                    </span>
                )}
            </div>

            <div className="eagle-layout">
                <aside className="eagle-sidebar" aria-label="Collections and history">
                    <div className="eagle-tabs eagle-sidebar-tabs" role="tablist" aria-label="Sidebar">
                        <button
                            type="button"
                            role="tab"
                            aria-selected={sidebarTab === 'collections'}
                            className={sidebarTab === 'collections' ? 'is-active' : undefined}
                            onClick={() => setSidebarTab('collections')}
                        >
                            Collections
                        </button>
                        <button
                            type="button"
                            role="tab"
                            aria-selected={sidebarTab === 'history'}
                            className={sidebarTab === 'history' ? 'is-active' : undefined}
                            onClick={() => setSidebarTab('history')}
                        >
                            <History size={14} aria-hidden="true" /> History
                        </button>
                    </div>
                    {sidebarTab === 'history' ? (
                        <HistoryPanel
                            refreshKey={historyKey}
                            activeId={historyView?.id ?? null}
                            record={recordHistory}
                            onRecordChange={changeRecord}
                            onOpen={(id) => void openHistory(id)}
                        />
                    ) : (
                    <>
                    <div className="eagle-sidebar-head">
                        <h3>Collections</h3>
                        <div className="eagle-inline-actions">
                            <button
                                type="button"
                                className="entropy-button entropy-button-ghost entropy-button-icon entropy-button-sm"
                                aria-label="New folder"
                                title={writeReason ?? 'New folder (top level)'}
                                disabled={readOnly}
                                onClick={() => setNameRequest({ kind: 'new-folder', parentId: null })}
                            >
                                <FolderPlus size={16} />
                            </button>
                            <button
                                type="button"
                                className="entropy-button entropy-button-ghost entropy-button-icon entropy-button-sm"
                                aria-label="New request"
                                title={writeReason ?? 'New request (top level)'}
                                disabled={readOnly}
                                onClick={() => setNameRequest({ kind: 'new-request', parentId: null })}
                            >
                                <FilePlus size={16} />
                            </button>
                            <button
                                type="button"
                                className="entropy-button entropy-button-ghost entropy-button-icon entropy-button-sm"
                                aria-label="Import collections"
                                title={writeReason ?? 'Import (EagleAPI, Postman, Insomnia, SoapUI)'}
                                disabled={readOnly}
                                onClick={() => setImportOpen(true)}
                            >
                                <Upload size={16} />
                            </button>
                            <button
                                type="button"
                                className="entropy-button entropy-button-ghost entropy-button-icon entropy-button-sm"
                                aria-label="Export collections"
                                title="Export (EagleAPI, Postman, SoapUI)"
                                disabled={!items.length}
                                onClick={() => setExportIds([])}
                            >
                                <Download size={16} />
                            </button>
                        </div>
                    </div>
                    {loading ? (
                        <EntropyLoader />
                    ) : loadError ? (
                        <p className="entropy-unavailable">Not available.</p>
                    ) : (
                        <CollectionTree
                            items={items}
                            selectedId={selected?.id ?? null}
                            dirtyId={dirty ? (selected?.id ?? null) : null}
                            expanded={expanded}
                            onToggle={(id) =>
                                setExpanded((current) => {
                                    const next = new Set(current)
                                    if (next.has(id)) next.delete(id)
                                    else next.add(id)
                                    return next
                                })
                            }
                            onSelect={(item) => void openItem(item)}
                            onAction={(action) => void onTreeAction(action)}
                            onMove={(id, parentId, position) => void moveItem(id, parentId, position)}
                            readOnlyReason={writeReason}
                        />
                    )}
                    </>
                    )}
                </aside>

                <section className="eagle-main" aria-label="Request">
                    {(!selected && !historyView) || !draft ? (
                        <div className="eagle-blank">
                            {opening ? <LoaderCircle size={22} className="entropy-spin" aria-hidden="true" /> : <Bird size={28} aria-hidden="true" />}
                            <strong>{opening ? 'Opening…' : 'Pick a request'}</strong>
                            <p>Choose a request in the collections, or create one. Values such as base URLs and secrets go in the environment.</p>
                            {!readOnly && (
                                <button
                                    type="button"
                                    className="entropy-button entropy-button-primary entropy-button-sm"
                                    onClick={() => setNameRequest({ kind: 'new-request', parentId: null })}
                                >
                                    <FilePlus size={14} /> New request
                                </button>
                            )}
                        </div>
                    ) : (
                        <>
                            <div className="eagle-request-head">
                                {selected ? (
                                    <div className="eagle-request-title">
                                        {path && <span className="eagle-muted">{path} /</span>}
                                        <strong>{selected.name}</strong>
                                        {selected.access === 'read' && <span className="eagle-unsaved">Read only</span>}
                                        {dirty && <span className="eagle-unsaved">Unsaved</span>}
                                    </div>
                                ) : (
                                    <div className="eagle-request-title">
                                        <History size={15} aria-hidden="true" />
                                        <span className="eagle-muted">History ·</span>
                                        <strong>{historyView?.item_name || 'Request'}</strong>
                                        <span className="eagle-muted">{historyView ? new Date(historyView.created_at).toLocaleString() : ''}</span>
                                    </div>
                                )}
                                {selected ? (
                                    <button
                                        type="button"
                                        className="entropy-button entropy-button-secondary entropy-button-sm"
                                        onClick={() => void save()}
                                        disabled={!dirty || saving || Boolean(selectedReadOnlyReason)}
                                        title={selectedReadOnlyReason ?? 'Save (Ctrl+S)'}
                                    >
                                        {saving ? <LoaderCircle size={14} className="entropy-spin" /> : <Save size={14} />} Save
                                    </button>
                                ) : (
                                    <div className="eagle-inline-actions">
                                        {savedItem && (
                                            <button
                                                type="button"
                                                className="entropy-button entropy-button-secondary entropy-button-sm"
                                                onClick={() => void openItem(savedItem, true)}
                                            >
                                                Open {savedItem.name}
                                            </button>
                                        )}
                                        <button
                                            type="button"
                                            className="entropy-button entropy-button-secondary entropy-button-sm"
                                            disabled={readOnly}
                                            title={writeReason ?? 'Save this request in the collections'}
                                            onClick={() =>
                                                setNameRequest({
                                                    kind: 'new-request',
                                                    parentId: null,
                                                    data: draft,
                                                    name: historyView?.item_name ? `${historyView.item_name} (history)` : 'From history',
                                                })
                                            }
                                        >
                                            <Save size={14} /> Save as request…
                                        </button>
                                    </div>
                                )}
                            </div>

                            <form
                                className="eagle-urlbar"
                                onSubmit={(event) => {
                                    event.preventDefault()
                                    void send()
                                }}
                            >
                                <select
                                    className={`eagle-method-select eagle-method-${draft.method.toLowerCase()}`}
                                    value={draft.method}
                                    aria-label="Method"
                                    disabled={editorReadOnly}
                                    onChange={(event) => setDraft({ ...draft, method: event.target.value })}
                                >
                                    {METHODS.map((method) => (
                                        <option key={method}>{method}</option>
                                    ))}
                                </select>
                                <input
                                    className="eagle-url-input"
                                    value={draft.url}
                                    placeholder="/context/uri  or  https://host/path"
                                    aria-label="URL or path"
                                    spellCheck={false}
                                    autoComplete="off"
                                    readOnly={editorReadOnly}
                                    list={VALUE_SUGGESTIONS}
                                    onChange={(event) => setDraft({ ...draft, url: event.target.value })}
                                />
                                {sending ? (
                                    <button type="button" className="entropy-button entropy-button-danger eagle-send" onClick={stopSending}>
                                        <Square size={14} /> Stop
                                    </button>
                                ) : (
                                    <button
                                        type="submit"
                                        className="entropy-button entropy-button-primary eagle-send"
                                        disabled={Boolean(sendReason)}
                                        title={sendReason ?? 'Send the request'}
                                    >
                                        <Send size={14} /> Send
                                    </button>
                                )}
                            </form>
                            {urlHint && <p className={`eagle-url-hint${!absolute && !envName ? ' eagle-warn-text' : ''}`}>{urlHint}</p>}

                            <RequestEditor
                                draft={draft}
                                onChange={setDraft}
                                readOnly={editorReadOnly}
                                settings={settings}
                                onOpenSettings={settings ? () => setTlsOpen(true) : undefined}
                            />

                            <ResponseViewer
                                result={result}
                                sending={sending}
                                poll={poll}
                                onStopPolling={stopSending}
                                shown={shown}
                                onShow={setShown}
                            />
                        </>
                    )}
                </section>
            </div>

            {envOpen && (
                <EnvironmentDialog
                    environment={environment}
                    selected={envName}
                    readOnlyReason={writeReason}
                    onChanged={loadEnvironment}
                    onClose={() => setEnvOpen(false)}
                />
            )}
            {accessItem && (
                <AccessDialog item={accessItem} onSaved={() => void refreshItems()} onClose={() => setAccessItem(null)} />
            )}
            {exportIds && <ExportDialog items={items} initial={exportIds} onClose={() => setExportIds(null)} />}
            {importOpen && (
                <ImportDialog
                    items={items}
                    onImported={(summary) => {
                        void refreshItems()
                        if (summary.created) setExpanded((current) => new Set([...current, ...(summary.created ?? [])]))
                        if (summary.added_profiles?.length) void eagleApi.settings().then(setSettings).catch(() => undefined)
                    }}
                    onClose={() => setImportOpen(false)}
                />
            )}
            {tlsOpen && settings && (
                <TlsSettingsDialog
                    settings={settings}
                    readOnlyReason={writeReason}
                    onSaved={setSettings}
                    onClose={() => setTlsOpen(false)}
                />
            )}
            {nameRequest && (
                <NameDialog
                    title={
                        nameRequest.kind === 'rename'
                            ? `Rename ${nameRequest.item.name}`
                            : nameRequest.kind === 'new-folder'
                              ? 'New folder'
                              : 'New request'
                    }
                    subtitle={
                        nameRequest.kind !== 'rename' && nameRequest.parentId !== null
                            ? `In ${itemPath(items, nameRequest.parentId)}`
                            : undefined
                    }
                    initial={nameRequest.kind === 'rename' ? nameRequest.item.name : (nameRequest.name ?? '')}
                    confirmText={nameRequest.kind === 'rename' ? 'Rename' : 'Create'}
                    onSubmit={(name) => submitName(nameRequest, name)}
                    onClose={() => setNameRequest(null)}
                />
            )}
            {moving && (
                <MoveDialog
                    item={moving}
                    items={items}
                    onClose={() => setMoving(null)}
                    onSubmit={(parentId) => {
                        setMoving(null)
                        void moveItem(moving.id, parentId)
                    }}
                />
            )}
        </div>
    )
}
