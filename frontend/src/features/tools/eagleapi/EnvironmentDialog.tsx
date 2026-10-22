import { useRef, useState, type FormEvent } from 'react'
import { Check, Copy, FileKey2, Globe, LoaderCircle, Pencil, Plus, Trash2, Upload } from 'lucide-react'

import Dialog from '../../../components/layout/Dialog'
import { useFeedback } from '../../../components/feedback/FeedbackProvider'
import { eagleApi, type EagleEnvEntry, type EagleEnvironment } from '../../../api/eagleapi.api'
import { formatBytes, vaultRef } from './model'

type Editing = { key: string; value: string; sensitive: boolean; isNew: boolean } | null

const KEY_PATTERN = /^[A-Za-z0-9_]+$/

function errorText(cause: unknown, fallback: string): string {
    return cause instanceof Error && cause.message ? cause.message : fallback
}

/**
 * The project's EagleAPI values, kept in its vault namespace: environments
 * (`<NAME>_URL`), text values and files (certificates, keys, keystores).
 */
export default function EnvironmentDialog({
    environment,
    selected,
    readOnlyReason,
    onChanged,
    onClose,
}: {
    environment: EagleEnvironment | null
    selected: string | null
    readOnlyReason: string | null
    onChanged: () => Promise<void> | void
    onClose: () => void
}) {
    const { notify, modal } = useFeedback()
    const [busy, setBusy] = useState(false)
    const [editing, setEditing] = useState<Editing>(null)
    const [newEnv, setNewEnv] = useState<{ name: string; url: string } | null>(null)
    const [upload, setUpload] = useState<{ key: string; file: File | null; sensitive: boolean } | null>(null)
    const [copied, setCopied] = useState<string | null>(null)
    const fileRef = useRef<HTMLInputElement>(null)

    const namespace = environment?.namespace ?? ''
    const entries = environment?.entries ?? []
    const readOnly = Boolean(readOnlyReason) || (environment?.exists === true && environment.access === 'read')
    const lockedReason =
        readOnlyReason ??
        (environment?.exists && environment.access === 'read'
            ? `You have read access to the '${namespace}' vault namespace; ask its owner for write access.`
            : null)
    const prefix = selected ? `${selected}_` : ''

    const run = async (action: () => Promise<unknown>, success: string) => {
        setBusy(true)
        try {
            await action()
            notify.success(success)
            await onChanged()
            return true
        } catch (cause) {
            notify.error(errorText(cause, 'The change was not saved.'))
            return false
        } finally {
            setBusy(false)
        }
    }

    const saveValue = async (event: FormEvent) => {
        event.preventDefault()
        if (!editing) return
        const key = editing.key.trim()
        if (!KEY_PATTERN.test(key)) {
            notify.error('Keys may contain only letters, numbers and underscore (_).')
            return
        }
        if (editing.isNew && entries.some((entry) => entry.key === key)) {
            notify.error(`${key} already exists; edit it instead.`)
            return
        }
        if (await run(() => eagleApi.putEntry(key, editing.value, editing.sensitive), `${key} saved in ${namespace}.`)) {
            setEditing(null)
        }
    }

    const saveEnvironment = async (event: FormEvent) => {
        event.preventDefault()
        if (!newEnv) return
        const name = newEnv.name.trim().toUpperCase()
        if (await run(() => eagleApi.createEnvironment(name, newEnv.url.trim(), false), `Environment ${name} created.`)) {
            setNewEnv(null)
        }
    }

    const saveFile = async (event: FormEvent) => {
        event.preventDefault()
        if (!upload?.file) return
        const key = upload.key.trim()
        if (!KEY_PATTERN.test(key)) {
            notify.error('Keys may contain only letters, numbers and underscore (_).')
            return
        }
        const file = upload.file
        if (await run(() => eagleApi.uploadEntryFile(key, file, upload.sensitive), `${file.name} saved as ${key}.`)) {
            setUpload(null)
        }
    }

    const remove = async (entry: EagleEnvEntry) => {
        const confirmed = await modal.confirm({
            title: `Delete ${entry.key}?`,
            message: `It is removed from the vault namespace ${namespace}. Requests that use it will fail.`,
            confirmText: 'Delete',
            destructive: true,
        })
        if (confirmed) await run(() => eagleApi.deleteEntry(entry.key), `${entry.key} deleted.`)
    }

    const copyRef = async (entry: EagleEnvEntry) => {
        const reference = vaultRef(namespace, entry.key, entry.type === 'file')
        try {
            await navigator.clipboard.writeText(reference)
            setCopied(entry.key)
            window.setTimeout(() => setCopied(null), 1500)
        } catch {
            notify.info(reference)
        }
    }

    return (
        <Dialog
            title="Environment"
            subtitle={`Values are kept in the project's vault namespace ${namespace}. Use them as \${entv:${namespace}/KEY}.`}
            icon={<Globe size={18} />}
            onClose={onClose}
            className="eagle-env-dialog"
            footer={
                <button type="button" className="entropy-button entropy-button-primary" onClick={onClose}>
                    Done
                </button>
            }
        >
            {environment?.message && (
                <div className="entropy-alert entropy-alert-warning" role="alert">
                    <span>{environment.message}</span>
                </div>
            )}
            {lockedReason && <p className="eagle-muted">{lockedReason}</p>}

            <section className="eagle-env-section" aria-labelledby="eagle-env-list">
                <div className="eagle-env-section-head">
                    <h3 id="eagle-env-list">Environments</h3>
                    {!readOnly && !newEnv && (
                        <button type="button" className="entropy-button entropy-button-secondary entropy-button-sm" onClick={() => setNewEnv({ name: '', url: '' })}>
                            <Plus size={14} /> New environment
                        </button>
                    )}
                </div>
                {environment?.environments.length ? (
                    <ul className="eagle-env-chips">
                        {environment.environments.map((name) => (
                            <li key={name} className={name === selected ? 'is-selected' : ''}>
                                {name}
                            </li>
                        ))}
                    </ul>
                ) : (
                    <p className="eagle-muted">No environment yet. An environment is a base URL kept as NAME_URL (e.g. SIT_URL).</p>
                )}
                {newEnv && (
                    <form className="eagle-inline-form" onSubmit={(event) => void saveEnvironment(event)}>
                        <label className="eagle-field">
                            <span>Name</span>
                            <input
                                value={newEnv.name}
                                onChange={(event) => setNewEnv({ ...newEnv, name: event.target.value.toUpperCase() })}
                                placeholder="SIT"
                                pattern="[A-Za-z0-9_]+"
                                required
                                autoFocus
                            />
                        </label>
                        <label className="eagle-field eagle-field-grow">
                            <span>Base URL</span>
                            <input
                                value={newEnv.url}
                                onChange={(event) => setNewEnv({ ...newEnv, url: event.target.value })}
                                placeholder="https://sit.example.com/api"
                                required
                            />
                        </label>
                        <div className="eagle-inline-actions">
                            <button type="submit" className="entropy-button entropy-button-primary entropy-button-sm" disabled={busy}>
                                {busy ? <LoaderCircle size={14} className="entropy-spin" /> : <Check size={14} />} Create
                            </button>
                            <button type="button" className="entropy-button entropy-button-ghost entropy-button-sm" onClick={() => setNewEnv(null)}>
                                Cancel
                            </button>
                        </div>
                    </form>
                )}
            </section>

            <section className="eagle-env-section" aria-labelledby="eagle-env-values">
                <div className="eagle-env-section-head">
                    <h3 id="eagle-env-values">Values and files</h3>
                    {!readOnly && (
                        <div className="eagle-inline-actions">
                            <button
                                type="button"
                                className="entropy-button entropy-button-secondary entropy-button-sm"
                                onClick={() => {
                                    setUpload(null)
                                    setEditing({ key: prefix, value: '', sensitive: true, isNew: true })
                                }}
                            >
                                <Plus size={14} /> Add value
                            </button>
                            <button
                                type="button"
                                className="entropy-button entropy-button-secondary entropy-button-sm"
                                onClick={() => {
                                    setEditing(null)
                                    setUpload({ key: prefix, file: null, sensitive: true })
                                }}
                            >
                                <Upload size={14} /> Upload file
                            </button>
                        </div>
                    )}
                </div>

                {editing && (
                    <form className="eagle-inline-form" onSubmit={(event) => void saveValue(event)}>
                        <label className="eagle-field">
                            <span>Key</span>
                            <input
                                value={editing.key}
                                readOnly={!editing.isNew}
                                onChange={(event) => setEditing({ ...editing, key: event.target.value })}
                                placeholder="SIT_CLIENT_ID"
                                required
                                autoFocus={editing.isNew}
                            />
                        </label>
                        <label className="eagle-field eagle-field-grow">
                            <span>Value</span>
                            <input
                                type={editing.sensitive ? 'password' : 'text'}
                                value={editing.value}
                                onChange={(event) => setEditing({ ...editing, value: event.target.value })}
                                placeholder={editing.isNew ? '' : 'Type the new value'}
                                autoComplete="new-password"
                                autoFocus={!editing.isNew}
                            />
                        </label>
                        <label className="eagle-check">
                            <input
                                type="checkbox"
                                checked={editing.sensitive}
                                onChange={(event) => setEditing({ ...editing, sensitive: event.target.checked })}
                            />
                            <span>Secret</span>
                        </label>
                        <div className="eagle-inline-actions">
                            <button type="submit" className="entropy-button entropy-button-primary entropy-button-sm" disabled={busy}>
                                {busy ? <LoaderCircle size={14} className="entropy-spin" /> : <Check size={14} />} Save
                            </button>
                            <button type="button" className="entropy-button entropy-button-ghost entropy-button-sm" onClick={() => setEditing(null)}>
                                Cancel
                            </button>
                        </div>
                    </form>
                )}

                {upload && (
                    <form className="eagle-inline-form" onSubmit={(event) => void saveFile(event)}>
                        <label className="eagle-field">
                            <span>Key</span>
                            <input
                                value={upload.key}
                                onChange={(event) => setUpload({ ...upload, key: event.target.value })}
                                placeholder="SIT_CERT"
                                required
                                autoFocus
                            />
                        </label>
                        <div className="eagle-field eagle-field-grow">
                            <span>File (certificate, key, PFX/P12, CA bundle)</span>
                            <div className="eagle-file-pick">
                                <button type="button" className="entropy-button entropy-button-secondary entropy-button-sm" onClick={() => fileRef.current?.click()}>
                                    <FileKey2 size={14} /> Choose file
                                </button>
                                <span className="eagle-muted">{upload.file ? `${upload.file.name} (${formatBytes(upload.file.size)})` : 'No file chosen'}</span>
                                <input
                                    ref={fileRef}
                                    type="file"
                                    hidden
                                    aria-label="File to upload"
                                    onChange={(event) => {
                                        const file = event.target.files?.[0] ?? null
                                        setUpload({ ...upload, file })
                                    }}
                                />
                            </div>
                        </div>
                        <label className="eagle-check">
                            <input
                                type="checkbox"
                                checked={upload.sensitive}
                                onChange={(event) => setUpload({ ...upload, sensitive: event.target.checked })}
                            />
                            <span>Secret</span>
                        </label>
                        <div className="eagle-inline-actions">
                            <button type="submit" className="entropy-button entropy-button-primary entropy-button-sm" disabled={busy || !upload.file}>
                                {busy ? <LoaderCircle size={14} className="entropy-spin" /> : <Upload size={14} />} Upload
                            </button>
                            <button type="button" className="entropy-button entropy-button-ghost entropy-button-sm" onClick={() => setUpload(null)}>
                                Cancel
                            </button>
                        </div>
                    </form>
                )}

                {entries.length > 0 ? (
                    <div className="eagle-table-wrap">
                        <table className="eagle-table eagle-env-table">
                            <thead>
                                <tr>
                                    <th>Key</th>
                                    <th>Value</th>
                                    <th aria-label="Actions" />
                                </tr>
                            </thead>
                            <tbody>
                                {entries.map((entry) => (
                                    <tr key={entry.key}>
                                        <td>
                                            <code>{entry.key}</code>
                                        </td>
                                        <td>
                                            {entry.file ? (
                                                <span className="eagle-env-file">
                                                    <FileKey2 size={14} aria-hidden="true" /> {entry.file.filename}{' '}
                                                    <span className="eagle-muted">{formatBytes(entry.file.size)}</span>
                                                </span>
                                            ) : entry.sensitive ? (
                                                <span className="eagle-muted" aria-label="Secret value">
                                                    ••••••••
                                                </span>
                                            ) : (
                                                <span className="eagle-env-value">{entry.value}</span>
                                            )}
                                        </td>
                                        <td>
                                            <div className="eagle-row-actions">
                                                <button
                                                    type="button"
                                                    className="entropy-button entropy-button-ghost entropy-button-icon entropy-button-sm"
                                                    aria-label={`Copy the reference to ${entry.key}`}
                                                    title={vaultRef(namespace, entry.key, entry.type === 'file')}
                                                    onClick={() => void copyRef(entry)}
                                                >
                                                    {copied === entry.key ? <Check size={14} /> : <Copy size={14} />}
                                                </button>
                                                {!readOnly && (
                                                    <>
                                                        <button
                                                            type="button"
                                                            className="entropy-button entropy-button-ghost entropy-button-icon entropy-button-sm"
                                                            aria-label={entry.file ? `Replace the file ${entry.key}` : `Edit ${entry.key}`}
                                                            onClick={() => {
                                                                if (entry.file) {
                                                                    setEditing(null)
                                                                    setUpload({ key: entry.key, file: null, sensitive: entry.sensitive })
                                                                } else {
                                                                    setUpload(null)
                                                                    setEditing({
                                                                        key: entry.key,
                                                                        value: entry.sensitive ? '' : (entry.value ?? ''),
                                                                        sensitive: entry.sensitive,
                                                                        isNew: false,
                                                                    })
                                                                }
                                                            }}
                                                        >
                                                            {entry.file ? <Upload size={14} /> : <Pencil size={14} />}
                                                        </button>
                                                        <button
                                                            type="button"
                                                            className="entropy-button entropy-button-ghost entropy-button-icon entropy-button-sm"
                                                            aria-label={`Delete ${entry.key}`}
                                                            onClick={() => void remove(entry)}
                                                        >
                                                            <Trash2 size={14} />
                                                        </button>
                                                    </>
                                                )}
                                            </div>
                                        </td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>
                ) : (
                    !environment?.message && (
                        <p className="eagle-muted">
                            Nothing yet. The namespace {namespace} is created in the vault when you add the first value.
                        </p>
                    )
                )}
            </section>
            {(editing || upload || newEnv) && busy && <span className="eagle-sr" role="status">Saving…</span>}
        </Dialog>
    )
}
