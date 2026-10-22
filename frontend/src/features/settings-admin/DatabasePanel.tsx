import { useEffect, useState } from 'react'
import { CheckCircle2, Database, Download, LoaderCircle, Save, ShieldAlert, ShieldCheck } from 'lucide-react'

import { apiRequest } from '../../services/api'
import { useFeedback } from '../../components/feedback/FeedbackProvider'

interface Backup {
    name: string
    size: number
    created_at: string
}

interface DatabaseStatus {
    database: string
    size: number
    guarded: boolean
    locked: boolean
    backup_dir: string
    settings: { backup_dir: string; interval_hours: number; keep: number }
    backups: Backup[]
    last_backup: string | null
    events: { kind: string; message: string; at: string }[]
}

const BASE = '/api/admin/database'

function size(bytes: number): string {
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`
    if (bytes < 1024 * 1024 * 1024) return `${(bytes / 1024 / 1024).toFixed(1)} MB`
    return `${(bytes / 1024 / 1024 / 1024).toFixed(2)} GB`
}

function when(iso: string | null): string {
    return iso ? new Date(iso).toLocaleString() : 'never'
}

function message(error: unknown, fallback: string): string {
    return error instanceof Error ? error.message : fallback
}

/**
 * Administration -> Settings -> Database: the guard against deletion, the
 * server lock, automatic backups and checks of entropy.db.
 */
export default function DatabasePanel() {
    const { notify } = useFeedback()
    const [status, setStatus] = useState<DatabaseStatus | null>(null)
    const [error, setError] = useState<string | null>(null)
    const [form, setForm] = useState({ backup_dir: '', interval_hours: '6', keep: '28' })
    const [busy, setBusy] = useState<string | null>(null)

    const apply = (next: DatabaseStatus) => {
        setStatus(next)
        setForm({
            backup_dir: next.settings.backup_dir,
            interval_hours: String(next.settings.interval_hours),
            keep: String(next.settings.keep),
        })
    }

    useEffect(() => {
        apiRequest<DatabaseStatus>(BASE)
            .then(apply)
            .catch((cause: unknown) => setError(message(cause, 'Unable to load the database status.')))
    }, [])

    const run = async (key: string, action: () => Promise<void>) => {
        setBusy(key)
        try {
            await action()
        } catch (cause) {
            notify.error(message(cause, 'The action failed.'))
        } finally {
            setBusy(null)
        }
    }

    const reload = async () => apply(await apiRequest<DatabaseStatus>(BASE))

    if (error) {
        return (
            <div className="entropy-alert entropy-alert-error" role="alert">
                <span>{error}</span>
            </div>
        )
    }
    if (!status) {
        return (
            <p className="settings-muted" role="status">
                <LoaderCircle size={14} className="entropy-spin" aria-hidden="true" /> Loading…
            </p>
        )
    }

    return (
        <>
            <header className="settings-admin-head">
                <div>
                    <h2>Database</h2>
                    <p>
                        Everything Entropy knows lives in entropy.db. It is guarded against deletion, checked when the server starts,
                        and backed up automatically.
                    </p>
                </div>
            </header>

            <div className="database-cards">
                <div className="database-card">
                    <Database size={18} aria-hidden="true" />
                    <div>
                        <strong>{size(status.size)}</strong>
                        <code title={status.database}>{status.database}</code>
                    </div>
                </div>
                <div className={`database-card${status.guarded ? '' : ' is-warn'}`}>
                    {status.guarded ? <ShieldCheck size={18} aria-hidden="true" /> : <ShieldAlert size={18} aria-hidden="true" />}
                    <div>
                        <strong>{status.guarded ? 'Guarded' : 'Not guarded'}</strong>
                        <span>
                            {status.guarded
                                ? 'If entropy.db is deleted, it is back within seconds, with nothing lost.'
                                : 'This file system has no hard links; backups protect the data.'}
                        </span>
                    </div>
                </div>
                <div className="database-card">
                    <CheckCircle2 size={18} aria-hidden="true" />
                    <div>
                        <strong>{status.locked ? 'Locked to this server' : 'Not locked'}</strong>
                        <span>A second Entropy server cannot start on this database.</span>
                    </div>
                </div>
            </div>

            {status.events.length > 0 && (
                <ul className="database-events" aria-label="Recoveries">
                    {status.events.map((event) => (
                        <li key={event.at + event.message}>
                            <strong>{when(event.at)}</strong> {event.message}
                        </li>
                    ))}
                </ul>
            )}

            <div className="settings-grid">
                <label className="admin-field admin-field-wide">
                    <span>Backup folder</span>
                    <input
                        value={form.backup_dir}
                        placeholder={status.backup_dir}
                        onChange={(event) => setForm({ ...form, backup_dir: event.target.value })}
                        spellCheck={false}
                    />
                    <small>Best on another disk, so a failed disk does not take the backups too. Empty: a backups folder next to the database.</small>
                </label>
                <label className="admin-field">
                    <span>Back up every (hours)</span>
                    <input
                        type="number"
                        min={0.25}
                        max={168}
                        step={0.25}
                        value={form.interval_hours}
                        onChange={(event) => setForm({ ...form, interval_hours: event.target.value })}
                    />
                </label>
                <label className="admin-field">
                    <span>Backups kept</span>
                    <input type="number" min={1} max={1000} value={form.keep} onChange={(event) => setForm({ ...form, keep: event.target.value })} />
                </label>
            </div>

            <div className="database-actions">
                <button
                    type="button"
                    className="entropy-button entropy-button-primary"
                    disabled={busy !== null}
                    onClick={() =>
                        void run('save', async () => {
                            apply(
                                await apiRequest<DatabaseStatus>(`${BASE}/settings`, {
                                    method: 'PUT',
                                    headers: { 'Content-Type': 'application/json' },
                                    body: JSON.stringify({
                                        backup_dir: form.backup_dir.trim(),
                                        interval_hours: Number(form.interval_hours),
                                        keep: Number(form.keep),
                                    }),
                                }),
                            )
                            notify.success('Backup settings saved.')
                        })
                    }
                >
                    {busy === 'save' ? <LoaderCircle size={15} className="entropy-spin" /> : <Save size={15} />} Save
                </button>
                <button
                    type="button"
                    className="entropy-button entropy-button-secondary"
                    disabled={busy !== null}
                    onClick={() =>
                        void run('backup', async () => {
                            const result = await apiRequest<{ backup: Backup }>(`${BASE}/backups`, { method: 'POST' })
                            notify.success(`Backup ${result.backup.name} made and checked.`)
                            await reload()
                        })
                    }
                >
                    {busy === 'backup' && <LoaderCircle size={15} className="entropy-spin" />} Back up now
                </button>
                <button
                    type="button"
                    className="entropy-button entropy-button-secondary"
                    disabled={busy !== null}
                    onClick={() =>
                        void run('check', async () => {
                            const result = await apiRequest<{ ok: boolean; result: string }>(`${BASE}/check`, { method: 'POST' })
                            if (result.ok) notify.success('The database passed its integrity check.')
                            else notify.error(`The database is damaged: ${result.result}`)
                        })
                    }
                >
                    {busy === 'check' && <LoaderCircle size={15} className="entropy-spin" />} Check now
                </button>
            </div>

            <h3 className="database-subhead">
                Backups <span className="settings-muted">· last {when(status.last_backup)}</span>
            </h3>
            {status.backups.length === 0 ? (
                <p className="settings-muted">No backups yet; the first one is made shortly after the server starts.</p>
            ) : (
                <ul className="database-backups">
                    {status.backups.map((backup) => (
                        <li key={backup.name}>
                            <code>{backup.name}</code>
                            <span className="settings-muted">
                                {when(backup.created_at)} · {size(backup.size)}
                            </span>
                            <a
                                className="entropy-button entropy-button-ghost entropy-button-icon entropy-button-sm"
                                href={`${BASE}/backups/${encodeURIComponent(backup.name)}`}
                                download={backup.name}
                                aria-label={`Download ${backup.name}`}
                                title="Download"
                            >
                                <Download size={15} />
                            </a>
                        </li>
                    ))}
                </ul>
            )}
            <p className="settings-muted database-restore">
                To go back to a backup, stop Entropy and run <code>ent database restore</code> (the newest good one) or{' '}
                <code>ent database restore &lt;name&gt;</code>. The current file is kept beside it. A damaged database is replaced by
                the newest good backup automatically when the server starts.
            </p>
        </>
    )
}
