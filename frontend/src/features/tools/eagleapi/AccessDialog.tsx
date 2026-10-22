import { useEffect, useState } from 'react'
import { LoaderCircle, Lock, Plus, Trash2, Users } from 'lucide-react'

import Dialog from '../../../components/layout/Dialog'
import { useFeedback } from '../../../components/feedback/FeedbackProvider'
import { eagleApi, type EagleAccessEntry, type EagleAccessInfo, type EagleItem } from '../../../api/eagleapi.api'

function errorText(cause: unknown, fallback: string): string {
    return cause instanceof Error && cause.message ? cause.message : fallback
}

/**
 * Who may use a collection: everyone in the project, or only its owner and
 * the members chosen here (read: see and send; write: also change).
 */
export default function AccessDialog({
    item,
    onSaved,
    onClose,
}: {
    item: EagleItem
    onSaved: () => void
    onClose: () => void
}) {
    const { notify } = useFeedback()
    const [info, setInfo] = useState<EagleAccessInfo | null>(null)
    const [loadError, setLoadError] = useState<string | null>(null)
    const [restricted, setRestricted] = useState(false)
    const [entries, setEntries] = useState<EagleAccessEntry[]>([])
    const [pick, setPick] = useState('')
    const [saving, setSaving] = useState(false)
    const [error, setError] = useState<string | null>(null)

    useEffect(() => {
        let active = true
        eagleApi
            .access(item.id)
            .then((next) => {
                if (!active) return
                setInfo(next)
                setRestricted(next.restricted)
                setEntries(next.entries)
            })
            .catch((cause) => {
                if (active) setLoadError(errorText(cause, 'Access could not be loaded.'))
            })
        return () => {
            active = false
        }
    }, [item.id])

    const readOnly = !info?.can_manage
    const taken = new Set(entries.map((entry) => `${entry.kind}:${entry.name}`))
    const choices = [
        ...(info?.candidates.users ?? [])
            .filter((user) => user.name !== info?.owner)
            .map((user) => ({ key: `user:${user.name}`, label: user.full_name ? `${user.full_name} (${user.name})` : user.name })),
        ...(info?.candidates.groups ?? []).map((group) => ({ key: `group:${group.name}`, label: `Group: ${group.name}` })),
    ].filter((choice) => !taken.has(choice.key))

    const add = () => {
        if (!pick) return
        const [kind, ...rest] = pick.split(':')
        const name = rest.join(':')
        const user = info?.candidates.users.find((candidate) => candidate.name === name)
        setEntries((current) => [
            ...current,
            { kind: kind as EagleAccessEntry['kind'], name, full_name: kind === 'user' ? user?.full_name : null, level: 'read' },
        ])
        setPick('')
    }

    const save = async () => {
        setSaving(true)
        setError(null)
        try {
            await eagleApi.setAccess(item.id, restricted, restricted ? entries : [])
            notify.success(restricted ? `${item.name} is restricted.` : `${item.name} is open to the project.`)
            onSaved()
            onClose()
        } catch (cause) {
            setError(errorText(cause, 'Access was not saved.'))
        } finally {
            setSaving(false)
        }
    }

    return (
        <Dialog
            title={`Access to ${item.name}`}
            subtitle="Who in this project may see and use this collection."
            icon={<Users size={18} />}
            onClose={onClose}
            className="eagle-access-dialog"
            footer={
                <>
                    <button type="button" className="entropy-button entropy-button-secondary" onClick={onClose}>
                        {readOnly ? 'Close' : 'Cancel'}
                    </button>
                    {!readOnly && (
                        <button type="button" className="entropy-button entropy-button-primary" disabled={saving || !info} onClick={() => void save()}>
                            {saving && <LoaderCircle size={14} className="entropy-spin" />} Save
                        </button>
                    )}
                </>
            }
        >
            {loadError ? (
                <p className="eagle-warn-text" role="alert">
                    {loadError}
                </p>
            ) : !info ? (
                <p className="eagle-muted" role="status">
                    <LoaderCircle size={14} className="entropy-spin" aria-hidden="true" /> Loading…
                </p>
            ) : (
                <div className="eagle-access">
                    {readOnly && (
                        <p className="eagle-muted">
                            Only the owner ({info.owner || 'unknown'}) or an administrator can change who may use this collection.
                        </p>
                    )}
                    <div className="eagle-access-modes" role="radiogroup" aria-label="Who may use it">
                        <label className="eagle-check">
                            <input type="radio" name="eagle-access" checked={!restricted} disabled={readOnly} onChange={() => setRestricted(false)} />
                            <span>
                                <strong>Everyone in the project</strong>
                                <small>What each person may do follows their project role.</small>
                            </span>
                        </label>
                        <label className="eagle-check">
                            <input type="radio" name="eagle-access" checked={restricted} disabled={readOnly} onChange={() => setRestricted(true)} />
                            <span>
                                <strong>
                                    <Lock size={13} aria-hidden="true" /> Only the people chosen here
                                </strong>
                                <small>Others in the project do not see it. The owner and administrators always do.</small>
                            </span>
                        </label>
                    </div>

                    {restricted && (
                        <>
                            <ul className="eagle-access-list">
                                <li>
                                    <span>
                                        <strong>{info.owner || 'Owner'}</strong>
                                        <small>Owner</small>
                                    </span>
                                    <span className="eagle-muted">Full access</span>
                                </li>
                                {entries.map((entry) => (
                                    <li key={`${entry.kind}:${entry.name}`}>
                                        <span>
                                            <strong>{entry.kind === 'group' ? `Group: ${entry.name}` : entry.full_name || entry.name}</strong>
                                            {entry.kind === 'user' && entry.full_name && <small>{entry.name}</small>}
                                        </span>
                                        <select
                                            value={entry.level}
                                            disabled={readOnly}
                                            aria-label={`Access for ${entry.name}`}
                                            onChange={(event) =>
                                                setEntries((current) =>
                                                    current.map((other) =>
                                                        other === entry ? { ...other, level: event.target.value as EagleAccessEntry['level'] } : other,
                                                    ),
                                                )
                                            }
                                        >
                                            <option value="read">Can use (read and send)</option>
                                            <option value="write">Can change</option>
                                        </select>
                                        {!readOnly && (
                                            <button
                                                type="button"
                                                className="entropy-button entropy-button-ghost entropy-button-icon entropy-button-sm"
                                                aria-label={`Remove ${entry.name}`}
                                                onClick={() => setEntries((current) => current.filter((other) => other !== entry))}
                                            >
                                                <Trash2 size={14} />
                                            </button>
                                        )}
                                    </li>
                                ))}
                            </ul>
                            {!readOnly && (
                                <div className="eagle-access-add">
                                    <select value={pick} aria-label="Add a project member" onChange={(event) => setPick(event.target.value)}>
                                        <option value="">{choices.length ? 'Add a project member…' : 'Every project member is listed'}</option>
                                        {choices.map((choice) => (
                                            <option key={choice.key} value={choice.key}>
                                                {choice.label}
                                            </option>
                                        ))}
                                    </select>
                                    <button type="button" className="entropy-button entropy-button-secondary entropy-button-sm" disabled={!pick} onClick={add}>
                                        <Plus size={14} /> Add
                                    </button>
                                </div>
                            )}
                            <p className="eagle-muted">Only members of this project can be given access.</p>
                        </>
                    )}
                    {error && (
                        <p className="eagle-warn-text" role="alert">
                            {error}
                        </p>
                    )}
                </div>
            )}
        </Dialog>
    )
}
