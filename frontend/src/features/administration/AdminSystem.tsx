import { useCallback, useEffect, useRef, useState } from 'react'
import {
    AlertCircle,
    ArrowUpCircle,
    CheckCircle2,
    Circle,
    History,
    LoaderCircle,
    PackageOpen,
    RotateCcw,
    Upload,
    XCircle,
} from 'lucide-react'

import { systemApi, type PackageInfo, type SystemInfo, type UpgradeJob } from '../../api/system.api'
import Dialog from '../../components/layout/Dialog'
import { errorMessage, formatDateTime, formatTime } from '../runs/format'

const DEPS_LABELS: Record<SystemInfo['deps'], string> = {
    bundled: 'Bundled wheels',
    index: 'Package index',
    manual: 'Installed manually',
}

function formatSize(bytes: number): string {
    return bytes >= 1 << 20 ? `${(bytes / (1 << 20)).toFixed(1)} MB` : `${Math.ceil(bytes / 1024)} KB`
}

/** Administration → System: installation details, upgrades and rollback. */
export default function AdminSystem() {
    const [info, setInfo] = useState<SystemInfo | null>(null)
    const [error, setError] = useState<string | null>(null)
    const [uploading, setUploading] = useState<number | null>(null)
    const [selected, setSelected] = useState<PackageInfo | null>(null)
    const [allowDowngrade, setAllowDowngrade] = useState(false)
    const [job, setJob] = useState<UpgradeJob | null>(null)
    const [confirmRollback, setConfirmRollback] = useState(false)
    const [busy, setBusy] = useState(false)
    const [dragging, setDragging] = useState(false)
    const fileRef = useRef<HTMLInputElement>(null)
    const logRef = useRef<HTMLOListElement>(null)

    const [revision, setRevision] = useState(0)
    const load = useCallback(() => setRevision((value) => value + 1), [])

    useEffect(() => {
        let active = true
        systemApi
            .info()
            .then((result) => {
                if (!active) return
                setInfo(result)
                if (result.job.state === 'running' || result.job.state === 'restarting') setJob(result.job)
            })
            .catch((cause: unknown) => {
                if (active) setError(errorMessage(cause, 'Unable to load the system details.'))
            })
        return () => {
            active = false
        }
    }, [revision])

    const following = job !== null && (job.state === 'running' || job.state === 'restarting')

    // Follow the job; requests fail while the server restarts, so keep trying.
    useEffect(() => {
        if (!following) return
        let active = true
        const timer = window.setInterval(() => {
            systemApi
                .status()
                .then((result) => {
                    if (!active) return
                    setJob(result)
                    if (result.state === 'succeeded') {
                        // The new server serves a new UI build: load it.
                        window.setTimeout(() => window.location.reload(), 1500)
                    } else if (result.state === 'failed') {
                        load()
                    }
                })
                .catch(() => {
                    if (active) setJob((current) => (current ? { ...current, state: 'restarting' } : current))
                })
        }, 1000)
        return () => {
            active = false
            window.clearInterval(timer)
        }
    }, [following, load])

    useEffect(() => {
        if (logRef.current) logRef.current.scrollTop = logRef.current.scrollHeight
    }, [job?.log.length])

    const upload = async (file: File) => {
        setError(null)
        setSelected(null)
        setAllowDowngrade(false)
        setUploading(0)
        try {
            setSelected(await systemApi.upload(file, setUploading))
        } catch (cause) {
            setError(errorMessage(cause, 'Unable to upload the package.'))
        } finally {
            setUploading(null)
            if (fileRef.current) fileRef.current.value = ''
        }
    }

    const discard = async () => {
        if (!selected) return
        const id = selected.id
        setSelected(null)
        try {
            await systemApi.discard(id)
        } catch {
            // Replaced by the next upload anyway.
        }
    }

    const apply = async () => {
        if (!selected) return
        setBusy(true)
        setError(null)
        try {
            setJob(await systemApi.apply(selected.id, allowDowngrade))
            setSelected(null)
        } catch (cause) {
            setError(errorMessage(cause, 'Unable to start the upgrade.'))
        } finally {
            setBusy(false)
        }
    }

    const rollback = async () => {
        setBusy(true)
        setError(null)
        try {
            setJob(await systemApi.rollback())
            setConfirmRollback(false)
        } catch (cause) {
            setError(errorMessage(cause, 'Unable to start the rollback.'))
            setConfirmRollback(false)
        } finally {
            setBusy(false)
        }
    }

    const lastUpgrade = info?.upgrades.find((entry) => !entry.rollback)

    return (
        <div className="list-page admin-page system-page">
            {error && (
                <div className="entropy-alert entropy-alert-error" role="alert">
                    <AlertCircle size={16} />
                    <span>{error}</span>
                </div>
            )}

            <section className="dashboard-section">
                <header className="system-section-head">
                    <h3>Installation</h3>
                </header>
                {!info ? (
                    <p className="run-card-muted">Loading…</p>
                ) : (
                    <dl className="run-meta system-facts">
                        <div>
                            <dt>Version</dt>
                            <dd>{info.version}</dd>
                        </div>
                        <div>
                            <dt>Platform</dt>
                            <dd>{info.platform ?? 'Source checkout'}</dd>
                        </div>
                        <div>
                            <dt>Python</dt>
                            <dd title={info.python_executable}>{info.python}</dd>
                        </div>
                        <div>
                            <dt>Packages</dt>
                            <dd title={info.index_url ?? undefined}>{DEPS_LABELS[info.deps] ?? info.deps}</dd>
                        </div>
                        <div>
                            <dt>Web server</dt>
                            <dd title={info.web.log}>
                                {info.web.service === 'systemd' ? 'systemd service' : 'Background process'}
                            </dd>
                        </div>
                        <div>
                            <dt>Installed</dt>
                            <dd>{formatDateTime(info.installed_at)}</dd>
                        </div>
                        <div className="system-fact-wide">
                            <dt>Application</dt>
                            <dd title={info.application}>{info.application}</dd>
                        </div>
                        <div className="system-fact-wide">
                            <dt>Data</dt>
                            <dd title={info.home}>{info.home}</dd>
                        </div>
                    </dl>
                )}
            </section>

            <section className="dashboard-section">
                <header className="system-section-head">
                    <h3>Upgrade</h3>
                    <p className="run-card-muted">
                        Upload a release package (entropy-&lt;version&gt;-&lt;platform&gt;.tar.gz). The database is
                        backed up and migrated, and the server restarts on the new version. From a terminal:{' '}
                        <code>ent upgrade --source &lt;package&gt;</code>
                    </p>
                </header>

                {job && job.state !== 'idle' ? (
                    <UpgradeProgress job={job} logRef={logRef} onDismiss={() => setJob(null)} />
                ) : info && !info.installed ? (
                    <p className="run-card-muted">
                        This server runs from a source checkout; release packages upgrade installations only.
                    </p>
                ) : selected ? (
                    <div className="system-package">
                        <div className="system-package-head">
                            <span className="list-name-icon" aria-hidden="true">
                                <PackageOpen size={18} />
                            </span>
                            <div>
                                <strong>Entropy {selected.version}</strong>
                                <span className="run-card-muted">
                                    {selected.filename} · {formatSize(selected.size)} · {selected.platform} · Python{' '}
                                    {selected.python} · built {formatDateTime(selected.built_at)}
                                </span>
                            </div>
                        </div>
                        {selected.problems.map((problem) => (
                            <div key={problem} className="entropy-alert entropy-alert-error" role="alert">
                                <AlertCircle size={16} />
                                <span>{problem}</span>
                            </div>
                        ))}
                        {selected.problems.length === 0 && !selected.newer && (
                            <label className="system-check">
                                <input
                                    type="checkbox"
                                    checked={allowDowngrade}
                                    onChange={(event) => setAllowDowngrade(event.target.checked)}
                                />
                                <span>
                                    {selected.same
                                        ? `Reinstall ${selected.version}, the installed version`
                                        : `Downgrade from ${selected.current} to ${selected.version}`}
                                </span>
                            </label>
                        )}
                        <div className="entropy-panel-actions">
                            <button type="button" className="entropy-button entropy-button-secondary" onClick={() => void discard()}>
                                Discard
                            </button>
                            <button
                                type="button"
                                className="entropy-button entropy-button-primary"
                                disabled={busy || selected.problems.length > 0 || (!selected.newer && !allowDowngrade)}
                                onClick={() => void apply()}
                            >
                                {busy ? <LoaderCircle size={15} className="entropy-spin" /> : <ArrowUpCircle size={15} />}
                                {selected.newer
                                    ? `Upgrade ${selected.current} → ${selected.version}`
                                    : `Install ${selected.version}`}
                            </button>
                        </div>
                    </div>
                ) : (
                    <label
                        className={`system-drop${dragging ? ' is-dragging' : ''}${uploading !== null ? ' is-busy' : ''}`}
                        onDragOver={(event) => {
                            event.preventDefault()
                            setDragging(true)
                        }}
                        onDragLeave={() => setDragging(false)}
                        onDrop={(event) => {
                            event.preventDefault()
                            setDragging(false)
                            const file = event.dataTransfer.files[0]
                            if (file && uploading === null) void upload(file)
                        }}
                    >
                        <input
                            ref={fileRef}
                            type="file"
                            accept=".tar.gz,.tgz,application/gzip"
                            disabled={uploading !== null}
                            onChange={(event) => {
                                const file = event.target.files?.[0]
                                if (file) void upload(file)
                            }}
                        />
                        {uploading !== null ? (
                            <>
                                <LoaderCircle size={22} className="entropy-spin" />
                                <strong>Uploading… {Math.round(uploading * 100)}%</strong>
                                <span className="system-drop-bar">
                                    <span style={{ width: `${Math.round(uploading * 100)}%` }} />
                                </span>
                            </>
                        ) : (
                            <>
                                <Upload size={22} />
                                <strong>Choose a release package</strong>
                                <span className="run-card-muted">or drop it here</span>
                            </>
                        )}
                    </label>
                )}
            </section>

            <section className="dashboard-section">
                <header className="system-section-head">
                    <h3>History</h3>
                    {info?.can_rollback && lastUpgrade && !following && (
                        <button
                            type="button"
                            className="entropy-button entropy-button-secondary entropy-button-sm"
                            onClick={() => setConfirmRollback(true)}
                        >
                            <RotateCcw size={14} />
                            Roll back to {lastUpgrade.from}
                        </button>
                    )}
                </header>
                {!info || info.upgrades.length === 0 ? (
                    <p className="run-card-muted">
                        <History size={14} /> No upgrades yet.
                    </p>
                ) : (
                    <div className="list-table-wrap">
                        <table className="list-table">
                            <thead>
                                <tr>
                                    <th>When</th>
                                    <th>Change</th>
                                    <th>By</th>
                                    <th>Database backup</th>
                                </tr>
                            </thead>
                            <tbody>
                                {info.upgrades.map((entry) => (
                                    <tr key={entry.at}>
                                        <td>{formatDateTime(entry.at)}</td>
                                        <td>
                                            {entry.from} → {entry.to}
                                            {entry.rollback && <span className="list-version">rollback</span>}
                                        </td>
                                        <td>{entry.by || '—'}</td>
                                        <td className="list-cell-text" title={entry.database_backup ?? undefined}>
                                            {entry.database_backup ? entry.database_backup.split(/[\\/]/).pop() : '—'}
                                        </td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>
                )}
            </section>

            {confirmRollback && lastUpgrade && (
                <Dialog
                    title={`Roll back to ${lastUpgrade.from}?`}
                    subtitle="The previous application returns and the database goes back to its backup from before the upgrade."
                    icon={<RotateCcw size={18} />}
                    onClose={() => setConfirmRollback(false)}
                    footer={
                        <>
                            <button
                                type="button"
                                className="entropy-button entropy-button-secondary"
                                onClick={() => setConfirmRollback(false)}
                            >
                                Cancel
                            </button>
                            <button
                                type="button"
                                className="entropy-button entropy-button-danger"
                                disabled={busy}
                                onClick={() => void rollback()}
                            >
                                {busy && <LoaderCircle size={15} className="entropy-spin" />}
                                Roll back
                            </button>
                        </>
                    }
                >
                    <div className="entropy-alert entropy-alert-warning" role="alert">
                        <AlertCircle size={16} />
                        <span>
                            Changes made since the upgrade on {formatDateTime(lastUpgrade.at)} (users, workflows, runs)
                            are lost.
                        </span>
                    </div>
                </Dialog>
            )}
        </div>
    )
}

function UpgradeProgress({
    job,
    logRef,
    onDismiss,
}: {
    job: UpgradeJob
    logRef: React.RefObject<HTMLOListElement | null>
    onDismiss: () => void
}) {
    const verb = job.action === 'rollback' ? 'Rolling back' : 'Upgrading'
    const status =
        job.state === 'running'
            ? `${verb} to ${job.target}…`
            : job.state === 'restarting'
              ? `Restarting on ${job.target}…`
              : job.state === 'succeeded'
                ? `Entropy ${job.target} is running. Reloading…`
                : `${job.action === 'rollback' ? 'Rollback' : 'Upgrade'} failed: ${job.error ?? 'unknown error'}`

    return (
        <div className="provision-log">
            <div
                className={`start-run-check is-${job.state === 'succeeded' ? 'valid' : job.state === 'failed' ? 'invalid' : 'checking'}`}
                role="status"
            >
                {job.state === 'succeeded' ? (
                    <CheckCircle2 size={16} />
                ) : job.state === 'failed' ? (
                    <XCircle size={16} />
                ) : (
                    <LoaderCircle size={16} className="entropy-spin" />
                )}
                <span>{status}</span>
            </div>
            <ol ref={logRef} className="provision-steps" aria-live="polite">
                {job.log.map((line, index) => (
                    <li key={index}>
                        <Circle size={14} aria-hidden="true" />
                        <span>{line.message}</span>
                        <time>{formatTime(line.at)}</time>
                    </li>
                ))}
            </ol>
            {job.state === 'failed' && (
                <div className="entropy-panel-actions">
                    <button type="button" className="entropy-button entropy-button-secondary" onClick={onDismiss}>
                        Close
                    </button>
                </div>
            )}
        </div>
    )
}
