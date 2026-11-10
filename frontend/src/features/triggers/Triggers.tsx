import { useCallback, useEffect, useMemo, useState } from 'react'
import {
    AlertTriangle,
    CheckCircle2,
    Copy,
    History,
    KeyRound,
    LoaderCircle,
    Pencil,
    Play,
    Plus,
    Puzzle,
    Radio,
    RefreshCw,
    Search,
    Trash2,
    Webhook,
    Workflow as WorkflowIcon,
    X,
} from 'lucide-react'

import { triggersApi, type ListenerStatus, type Trigger, type TriggerRun } from '../../api/triggers.api'
import EntropyLoader from '../../components/feedback/EntropyLoader'
import { useFeedback } from '../../components/feedback/FeedbackProvider'
import { useErrorToast } from '../../components/feedback/useToast'
import Dialog from '../../components/layout/Dialog'
import { useShortcuts } from '../../components/layout/useShortcuts'
import { missingPermission } from '../administration/permissionReason'
import { usePermissions } from '../administration/usePermissions'
import { errorMessage, formatDateTime } from '../runs/format'
import { openRun } from '../runs/navigation'
import TriggerDialog from './TriggerDialog'
import '../../styles/triggers.css'

async function copy(text: string, notify: ReturnType<typeof useFeedback>['notify'], what: string) {
    try {
        await navigator.clipboard.writeText(text)
        notify.success(`${what} copied.`)
    } catch {
        notify.error(`Unable to copy the ${what.toLowerCase()}; select it and copy it instead.`)
    }
}

/** The URL and secret token of a webhook, shown once, with a call to try it. */
function TokenDialog({ trigger, token, onClose }: { trigger: Trigger; token: string; onClose: () => void }) {
    const { notify } = useFeedback()
    const url = trigger.hook_url ?? ''
    const example = `curl -X POST '${url}' \\\n  -H 'X-Entropy-Token: ${token}' \\\n  -H 'Content-Type: application/json' \\\n  -d '{"version": "1.2.3"}'`
    return (
        <Dialog
            title={`Webhook for ${trigger.name}`}
            subtitle="Copy the token now: it is not shown again. Make a new one if it is lost."
            icon={<KeyRound size={18} />}
            onClose={onClose}
            className="trigger-token-dialog"
            footer={
                <button type="button" className="entropy-button entropy-button-primary" onClick={onClose}>
                    Done
                </button>
            }
        >
            <div className="trigger-secret">
                <span>Address</span>
                <div>
                    <code>{url}</code>
                    <button type="button" className="entropy-button entropy-button-secondary entropy-button-icon entropy-button-sm" aria-label="Copy the address" onClick={() => void copy(url, notify, 'Address')}>
                        <Copy size={14} />
                    </button>
                </div>
            </div>
            <div className="trigger-secret">
                <span>Secret token (header X-Entropy-Token)</span>
                <div>
                    <code>{token}</code>
                    <button type="button" className="entropy-button entropy-button-secondary entropy-button-icon entropy-button-sm" aria-label="Copy the token" onClick={() => void copy(token, notify, 'Token')}>
                        <Copy size={14} />
                    </button>
                </div>
            </div>
            <div className="trigger-secret">
                <span>Try it</span>
                <div>
                    <pre>{example}</pre>
                    <button type="button" className="entropy-button entropy-button-secondary entropy-button-icon entropy-button-sm" aria-label="Copy the example" onClick={() => void copy(example, notify, 'Example')}>
                        <Copy size={14} />
                    </button>
                </div>
                <small>
                    A JSON object body overrides the trigger’s parameters key by key. The answer is 202 with the run’s id,
                    401 for a wrong token, 409 while paused and 422 when the run cannot start.
                </small>
            </div>
        </Dialog>
    )
}

/** Fire a trigger by hand, as you, with a payload to try. */
function FireDialog({ trigger, onClose, onFired }: { trigger: Trigger; onClose: () => void; onFired: (run: TriggerRun) => void }) {
    const [payload, setPayload] = useState('{\n  \n}')
    const [busy, setBusy] = useState(false)
    const [error, setError] = useState<string | null>(null)
    useErrorToast(error)
    const fire = async () => {
        setBusy(true)
        setError(null)
        try {
            const result = await triggersApi.fire(trigger.id, payload)
            onFired(result.run)
        } catch (cause) {
            setError(errorMessage(cause, 'Unable to fire the trigger.'))
        } finally {
            setBusy(false)
        }
    }
    return (
        <Dialog
            title={`Fire ${trigger.name}`}
            subtitle={`Runs ${trigger.target} now, as you, as if this payload had arrived.`}
            icon={<Play size={18} />}
            onClose={onClose}
            className="trigger-fire-dialog"
            footer={
                <>
                    <button type="button" className="entropy-button entropy-button-secondary" onClick={onClose}>
                        Cancel
                    </button>
                    <button type="button" className="entropy-button entropy-button-primary" onClick={() => void fire()} disabled={busy}>
                        {busy ? <LoaderCircle size={15} className="entropy-spin" /> : <Play size={15} />}
                        Fire now
                    </button>
                </>
            }
        >
            <label className="admin-field">
                <span>Payload (JSON or text; may be empty)</span>
                <textarea className="trigger-payload" value={payload} onChange={(event) => setPayload(event.target.value)} rows={8} spellCheck={false} />
            </label>
        </Dialog>
    )
}

function FiringState({ run }: { run: TriggerRun }) {
    const state = run.error ? 'error' : run.state ?? 'started'
    return <span className={`trigger-state is-${state}`}>{run.error ? 'Did not start' : state}</span>
}

/** Each firing: when, from where, the payload, and the run it started. */
function HistoryDialog({ trigger, onClose }: { trigger: Trigger; onClose: () => void }) {
    const [runs, setRuns] = useState<TriggerRun[] | null>(null)
    const [error, setError] = useState<string | null>(null)
    useErrorToast(error)
    useEffect(() => {
        let active = true
        triggersApi
            .get(trigger.id)
            .then((result) => active && setRuns(result.runs))
            .catch((cause: unknown) => active && setError(errorMessage(cause, 'Unable to load the firings.')))
        return () => {
            active = false
        }
    }, [trigger.id])
    return (
        <Dialog title={`Firings of ${trigger.name}`} subtitle="The newest 100." icon={<History size={18} />} onClose={onClose} className="trigger-history-dialog">
            {runs === null ? (
                <EntropyLoader label="Loading firings…" />
            ) : runs.length === 0 ? (
                <p className="trigger-muted">Not fired yet.</p>
            ) : (
                <ul className="trigger-history">
                    {runs.map((run) => (
                        <li key={run.id}>
                            <div>
                                <FiringState run={run} />
                                <strong>{formatDateTime(run.created_at)}</strong>
                                <span>{run.source === 'manual' ? 'Fired by hand' : run.source === 'queue' ? 'Queue message' : 'Webhook'}</span>
                                {run.job_id && (
                                    <button type="button" className="entropy-button entropy-button-ghost entropy-button-sm" onClick={() => openRun(run.job_id as number)}>
                                        Run #{run.job_id}
                                    </button>
                                )}
                            </div>
                            {run.caller && <small>{run.caller}</small>}
                            {run.error && <p className="trigger-error">{run.error}</p>}
                            {run.payload && <pre>{run.payload}</pre>}
                        </li>
                    ))}
                </ul>
            )}
        </Dialog>
    )
}

function ListenerLine({ status, queues }: { status: ListenerStatus | null; queues: number }) {
    if (!status || queues === 0) return null
    const Icon = status.state === 'listening' ? CheckCircle2 : AlertTriangle
    return (
        <p className={`trigger-listener is-${status.state}`} role="status">
            <Icon size={15} aria-hidden="true" />
            <span>
                <strong>Queue listener:</strong> {status.detail || 'Starting…'}
            </span>
        </p>
    )
}

export default function Triggers() {
    const permissions = usePermissions()
    const manageReason = missingPermission(permissions, ['triggers.manage'], 'changing triggers')
    const deleteReason = missingPermission(permissions, ['triggers.delete'], 'deleting triggers')
    const { notify, modal } = useFeedback()

    const [triggers, setTriggers] = useState<Trigger[]>([])
    const [listener, setListener] = useState<ListenerStatus | null>(null)
    const [loading, setLoading] = useState(true)
    const [refreshing, setRefreshing] = useState(false)
    const [error, setError] = useState<string | null>(null)
    useErrorToast(error)
    const [search, setSearch] = useState('')
    const [editing, setEditing] = useState<Trigger | 'new' | null>(null)
    const [secret, setSecret] = useState<{ trigger: Trigger; token: string } | null>(null)
    const [firing, setFiring] = useState<Trigger | null>(null)
    const [history, setHistory] = useState<Trigger | null>(null)
    const [busy, setBusy] = useState<string | null>(null)

    const load = useCallback(async () => {
        try {
            const result = await triggersApi.list()
            setTriggers(result.items)
            setListener(result.listener)
            setError(null)
        } catch (cause) {
            setError(errorMessage(cause, 'Unable to load triggers.'))
        } finally {
            setLoading(false)
            setRefreshing(false)
        }
    }, [])

    useEffect(() => {
        const timer = setTimeout(() => void load(), 0)
        return () => clearTimeout(timer)
    }, [load])

    useShortcuts({ 'mod+n': () => setEditing('new'), 'alt+n': () => setEditing('new') }, editing === null)

    const filtered = useMemo(() => {
        const needle = search.trim().toLowerCase()
        if (!needle) return triggers
        return triggers.filter((item) =>
            [item.name, item.description, item.target, item.destination ?? '', item.username].some((value) =>
                value.toLowerCase().includes(needle),
            ),
        )
    }, [triggers, search])

    const queues = triggers.filter((item) => item.source === 'queue' && item.enabled).length

    const toggleEnabled = async (trigger: Trigger) => {
        setBusy(`enable-${trigger.id}`)
        try {
            await triggersApi.update(trigger.id, { enabled: !trigger.enabled })
            await load()
        } catch (cause) {
            notify.error(errorMessage(cause, 'Unable to change the trigger.'))
        } finally {
            setBusy(null)
        }
    }

    const newToken = async (trigger: Trigger) => {
        const confirmed = await modal.confirm({
            title: `New token for ${trigger.name}?`,
            message: 'Callers using the current token are refused from now on.',
            confirmText: 'Make a new token',
            destructive: true,
        })
        if (!confirmed) return
        setBusy(`token-${trigger.id}`)
        try {
            const result = await triggersApi.newToken(trigger.id)
            setSecret({ trigger: result.trigger, token: result.token })
            await load()
        } catch (cause) {
            notify.error(errorMessage(cause, 'Unable to make a new token.'))
        } finally {
            setBusy(null)
        }
    }

    const remove = async (trigger: Trigger) => {
        const confirmed = await modal.confirm({
            title: `Delete ${trigger.name}?`,
            message:
                trigger.source === 'webhook'
                    ? 'Its address stops working, and its firing history is removed. Runs it started are kept.'
                    : 'Messages on its destination are no longer read, and its firing history is removed.',
            confirmText: 'Delete',
            destructive: true,
        })
        if (!confirmed) return
        setBusy(`delete-${trigger.id}`)
        try {
            await triggersApi.remove([trigger.id])
            notify.success(`Deleted ${trigger.name}.`)
            await load()
        } catch (cause) {
            notify.error(errorMessage(cause, 'Unable to delete the trigger.'))
        } finally {
            setBusy(null)
        }
    }

    return (
        <section className="list-page triggers-page">
            <section className="dashboard-section list-section">
                <div className="dashboard-section-heading list-section-heading">
                    <div>
                        <h2>
                            Triggers
                            <span className="list-count">{triggers.length}</span>
                        </h2>
                        <p>Run a workflow or plugin when a webhook is called or a message arrives on a queue.</p>
                    </div>
                    <div className="entropy-panel-actions">
                        <button
                            type="button"
                            className="entropy-button entropy-button-secondary entropy-button-icon"
                            aria-label="Refresh triggers"
                            title="Refresh"
                            onClick={() => {
                                setRefreshing(true)
                                void load()
                            }}
                            disabled={loading || refreshing}
                        >
                            <RefreshCw size={16} className={refreshing ? 'entropy-spin' : ''} />
                        </button>
                        <button
                            type="button"
                            className="entropy-button entropy-button-primary entropy-button-icon"
                            aria-label="Create trigger"
                            title={manageReason ?? 'Create trigger (Ctrl+N)'}
                            onClick={() => setEditing('new')}
                            disabled={Boolean(manageReason)}
                        >
                            <Plus size={20} />
                        </button>
                    </div>
                </div>

                <ListenerLine status={listener} queues={queues} />

                <div className="list-toolbar">
                    <div className="list-search">
                        <Search size={17} aria-hidden="true" />
                        <input
                            type="search"
                            value={search}
                            onChange={(event) => setSearch(event.target.value)}
                            placeholder="Search triggers…"
                            aria-label="Search triggers"
                        />
                        {search && (
                            <button type="button" aria-label="Clear search" onClick={() => setSearch('')}>
                                <X size={15} />
                            </button>
                        )}
                    </div>
                </div>

                <div className="list-table-wrap">
                    <table className="list-table triggers-table">
                        <thead>
                            <tr>
                                <th scope="col">Trigger</th>
                                <th scope="col">Fired by</th>
                                <th scope="col">Runs</th>
                                <th scope="col">Last fired</th>
                                <th scope="col">Status</th>
                                <th scope="col" className="list-operations-cell">
                                    <span className="list-operations-heading">Operations</span>
                                </th>
                            </tr>
                        </thead>
                        <tbody>
                            {loading ? (
                                <tr>
                                    <td colSpan={6}>
                                        <EntropyLoader label="Loading triggers…" />
                                    </td>
                                </tr>
                            ) : filtered.length === 0 ? (
                                <tr>
                                    <td colSpan={6}>
                                        <div className="list-empty">
                                            <Webhook size={22} />
                                            <strong>{triggers.length ? 'No triggers found' : 'No triggers yet'}</strong>
                                            <span>
                                                {triggers.length
                                                    ? 'Try a different search.'
                                                    : 'Create one with the + button: a webhook address, or a queue to listen on.'}
                                            </span>
                                        </div>
                                    </td>
                                </tr>
                            ) : (
                                filtered.map((trigger) => (
                                    <tr key={trigger.id}>
                                        <td>
                                            <div className="runs-who">
                                                <strong>{trigger.name}</strong>
                                                <span>{trigger.description || `by ${trigger.username}`}</span>
                                            </div>
                                        </td>
                                        <td>
                                            <div className="runs-who">
                                                <span className="schedule-target">
                                                    {trigger.source === 'webhook' ? <Webhook size={14} /> : <Radio size={14} />}
                                                    {trigger.source === 'webhook' ? 'Webhook' : 'Queue'}
                                                </span>
                                                {trigger.source === 'webhook' ? (
                                                    <button
                                                        type="button"
                                                        className="trigger-address"
                                                        title={`Copy ${trigger.hook_url ?? ''}`}
                                                        onClick={() => trigger.hook_url && void copy(trigger.hook_url, notify, 'Address')}
                                                    >
                                                        <code>{trigger.hook_url}</code>
                                                        <Copy size={12} aria-hidden="true" />
                                                    </button>
                                                ) : (
                                                    <code className="schedule-cron-code">{trigger.destination}</code>
                                                )}
                                            </div>
                                        </td>
                                        <td>
                                            <div className="runs-who">
                                                <span className="schedule-target">
                                                    {trigger.kind === 'plugin' ? <Puzzle size={14} /> : <WorkflowIcon size={14} />}
                                                    {trigger.target}
                                                </span>
                                                <span>on {trigger.node}</span>
                                            </div>
                                        </td>
                                        <td>
                                            <button type="button" className="schedule-last" onClick={() => setHistory(trigger)} title="Firings">
                                                <span className="list-cell-text">{trigger.last_fired_at ? formatDateTime(trigger.last_fired_at) : 'Never'}</span>
                                                <small>
                                                    {trigger.fired} fired
                                                    {trigger.failed_to_start > 0 && ` · ${trigger.failed_to_start} did not start`}
                                                </small>
                                            </button>
                                        </td>
                                        <td>
                                            <label className="schedule-switch">
                                                <input
                                                    type="checkbox"
                                                    checked={trigger.enabled}
                                                    onChange={() => void toggleEnabled(trigger)}
                                                    disabled={busy === `enable-${trigger.id}` || Boolean(manageReason)}
                                                    aria-label={`${trigger.enabled ? 'Pause' : 'Enable'} ${trigger.name}`}
                                                />
                                                {trigger.enabled ? 'Enabled' : 'Paused'}
                                            </label>
                                        </td>
                                        <td>
                                            <div className="list-operations">
                                                <button
                                                    type="button"
                                                    className="entropy-button entropy-button-secondary entropy-button-icon entropy-button-sm"
                                                    aria-label={`Fire ${trigger.name} now`}
                                                    title={manageReason ?? 'Fire now, with a payload to try'}
                                                    onClick={() => setFiring(trigger)}
                                                    disabled={Boolean(manageReason)}
                                                >
                                                    <Play size={15} />
                                                </button>
                                                <button
                                                    type="button"
                                                    className="entropy-button entropy-button-secondary entropy-button-icon entropy-button-sm"
                                                    aria-label={`Edit ${trigger.name}`}
                                                    title={manageReason ?? 'Edit'}
                                                    onClick={() => setEditing(trigger)}
                                                    disabled={Boolean(manageReason)}
                                                >
                                                    <Pencil size={15} />
                                                </button>
                                                {trigger.source === 'webhook' && (
                                                    <button
                                                        type="button"
                                                        className="entropy-button entropy-button-secondary entropy-button-icon entropy-button-sm"
                                                        aria-label={`New token for ${trigger.name}`}
                                                        title={manageReason ?? `New secret token (now …${trigger.token_hint ?? ''})`}
                                                        onClick={() => void newToken(trigger)}
                                                        disabled={busy === `token-${trigger.id}` || Boolean(manageReason)}
                                                    >
                                                        <KeyRound size={15} />
                                                    </button>
                                                )}
                                                <button
                                                    type="button"
                                                    className="entropy-button entropy-button-secondary entropy-button-icon entropy-button-sm"
                                                    aria-label={`Firings of ${trigger.name}`}
                                                    title="Firings"
                                                    onClick={() => setHistory(trigger)}
                                                >
                                                    <History size={15} />
                                                </button>
                                                <button
                                                    type="button"
                                                    className="entropy-button entropy-button-danger-quiet entropy-button-icon entropy-button-sm"
                                                    aria-label={`Delete ${trigger.name}`}
                                                    title={deleteReason ?? 'Delete'}
                                                    aria-disabled={deleteReason ? true : undefined}
                                                    onClick={() => {
                                                        if (!deleteReason) void remove(trigger)
                                                    }}
                                                    disabled={busy === `delete-${trigger.id}`}
                                                >
                                                    <Trash2 size={15} />
                                                </button>
                                            </div>
                                        </td>
                                    </tr>
                                ))
                            )}
                        </tbody>
                    </table>
                </div>
            </section>

            {editing !== null && (
                <TriggerDialog
                    trigger={editing === 'new' ? null : editing}
                    onClose={() => setEditing(null)}
                    onSaved={(saved, token) => {
                        setEditing(null)
                        notify.success(`Saved ${saved.name}.`)
                        if (token) setSecret({ trigger: saved, token })
                        void load()
                    }}
                />
            )}
            {secret && <TokenDialog trigger={secret.trigger} token={secret.token} onClose={() => setSecret(null)} />}
            {firing && (
                <FireDialog
                    trigger={firing}
                    onClose={() => setFiring(null)}
                    onFired={(run) => {
                        setFiring(null)
                        if (run.error) notify.error(run.error, { title: `${firing.name} did not start` })
                        else notify.success(`${firing.name} started run #${run.job_id}.`)
                        void load()
                    }}
                />
            )}
            {history && <HistoryDialog trigger={history} onClose={() => setHistory(null)} />}
        </section>
    )
}
