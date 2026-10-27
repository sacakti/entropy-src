import { useEffect, useMemo, useState, type ReactNode } from 'react'
import { AlertCircle, ArchiveRestore, ArrowRightLeft, Download, FileArchive, KeyRound, LoaderCircle, Upload } from 'lucide-react'

import { projectsApi, type ProjectSummary } from '../../api/projects.api'
import {
    transferApi,
    type DumpManifest,
    type RestoreResult,
    type TransferResult,
    type VaultRestoreSummary,
} from '../../api/transfer.api'
import { vaultApi } from '../../api/vault.api'
import { useFeedback } from '../../components/feedback/FeedbackProvider'
import Dialog from '../../components/layout/Dialog'
import { apiRequest, PROJECT_HEADER } from '../../services/api'
import { currentProject } from '../../services/project'
import '../../styles/transfer.css'
import { useErrorToast } from '../../components/feedback/useToast'

const MIN_PASSPHRASE = 12

function message(error: unknown, fallback: string): string {
    return error instanceof Error ? error.message : fallback
}

function plural(count: number, word: string): string {
    return `${count} ${word}${count === 1 ? '' : 's'}`
}

/** A passphrase with confirmation, for encrypting secrets that leave Entropy. */
function NewPassphrase({
    value,
    confirm,
    onChange,
    onConfirm,
}: {
    value: string
    confirm: string
    onChange: (value: string) => void
    onConfirm: (value: string) => void
}) {
    const short = value.length > 0 && value.length < MIN_PASSPHRASE
    const mismatch = confirm.length > 0 && confirm !== value
    return (
        <div className="transfer-passphrase">
            <label className="admin-field">
                <span>Passphrase</span>
                <input type="password" autoComplete="new-password" value={value} onChange={(event) => onChange(event.target.value)} />
                <small className={short ? 'is-error' : undefined}>
                    At least {MIN_PASSPHRASE} characters. Secrets are encrypted with it; without it the file cannot be opened.
                </small>
            </label>
            <label className="admin-field">
                <span>Repeat the passphrase</span>
                <input type="password" autoComplete="new-password" value={confirm} onChange={(event) => onConfirm(event.target.value)} />
                {mismatch && <small className="is-error">The passphrases differ.</small>}
            </label>
        </div>
    )
}

const passphraseReady = (value: string, confirm: string) => value.length >= MIN_PASSPHRASE && value === confirm

function FileField({ accept, file, onChange, label }: { accept: string; file: File | null; onChange: (file: File | null) => void; label: string }) {
    return (
        <label className="transfer-file">
            <Upload size={18} aria-hidden="true" />
            <span>
                <strong>{file ? file.name : label}</strong>
                <small>{file ? `${Math.max(1, Math.round(file.size / 1024))} KB` : 'Click to choose a file'}</small>
            </span>
            <input type="file" accept={accept} onChange={(event) => onChange(event.target.files?.[0] ?? null)} />
        </label>
    )
}

function Problems({ errors }: { errors: string[] }) {
    if (!errors.length) return null
    return (
        <div className="entropy-alert entropy-alert-warning transfer-problems" role="status">
            <AlertCircle size={15} />
            <ul>
                {errors.map((error) => (
                    <li key={error}>{error}</li>
                ))}
            </ul>
        </div>
    )
}

function Summary({ rows }: { rows: [string, ReactNode][] }) {
    return (
        <dl className="transfer-summary">
            {rows.map(([label, value]) => (
                <div key={label}>
                    <dt>{label}</dt>
                    <dd>{value}</dd>
                </div>
            ))}
        </dl>
    )
}

function renames(items: { name: string; as: string }[]): ReactNode {
    if (!items.length) return 'None'
    return items.map((item) => (item.name === item.as ? item.name : `${item.name} → ${item.as}`)).join(', ')
}

// ----------------------------------------------------------------------
// Move or copy to another project
// ----------------------------------------------------------------------

export function MoveToProjectDialog({
    kind,
    workflows = [],
    schedules = [],
    labels,
    onClose,
    onDone,
}: {
    kind: 'workflows' | 'schedules'
    workflows?: string[]
    schedules?: number[]
    /** What is being moved, for the subtitle. */
    labels: string[]
    onClose: () => void
    onDone: () => void
}) {
    const { notify } = useFeedback()
    const source = currentProject()
    const [projects, setProjects] = useState<ProjectSummary[] | null>(null)
    const [sourceKey, setSourceKey] = useState<string | null>(source)
    const [target, setTarget] = useState('')
    const [mode, setMode] = useState<'move' | 'copy'>('move')
    const [withSchedules, setWithSchedules] = useState(true)
    const [busy, setBusy] = useState(false)
    const [error, setError] = useState('')
    useErrorToast(error)
    const [result, setResult] = useState<TransferResult | null>(null)

    useEffect(() => {
        projectsApi
            .list()
            .then((list) => {
                setProjects(list.items)
                setSourceKey((key) => key ?? list.current)
            })
            .catch((cause: unknown) => setError(message(cause, 'Unable to load projects.')))
    }, [])

    const targets = (projects ?? []).filter((project) => project.key !== sourceKey)

    const run = async () => {
        if (!sourceKey || !target) return
        setBusy(true)
        setError('')
        try {
            const outcome = await transferApi.transfer(sourceKey, {
                target,
                mode,
                workflows,
                schedules,
                with_schedules: kind === 'workflows' && withSchedules,
            })
            setResult(outcome)
            const moved = outcome.workflows.length + outcome.schedules.length
            if (moved) {
                notify.success(`${mode === 'move' ? 'Moved' : 'Copied'} ${plural(moved, 'item')} to ${target}.`)
                onDone()
            }
        } catch (cause) {
            setError(message(cause, 'Unable to transfer.'))
        } finally {
            setBusy(false)
        }
    }

    return (
        <Dialog
            title={result ? 'Done' : `Move or copy to another project`}
            subtitle={labels.length > 3 ? `${labels.slice(0, 3).join(', ')} and ${labels.length - 3} more` : labels.join(', ')}
            icon={<ArrowRightLeft size={18} />}
            onClose={onClose}
            className="transfer-dialog"
            footer={
                result ? (
                    <button type="button" className="entropy-button entropy-button-primary" onClick={onClose}>
                        Close
                    </button>
                ) : (
                    <>
                        <button type="button" className="entropy-button entropy-button-secondary" onClick={onClose}>
                            Cancel
                        </button>
                        <button type="button" className="entropy-button entropy-button-primary" onClick={() => void run()} disabled={busy || !target}>
                            {busy && <LoaderCircle size={15} className="entropy-spin" />}
                            {mode === 'move' ? 'Move' : 'Copy'}
                        </button>
                    </>
                )
            }
        >
            {result ? (
                <>
                    <Summary
                        rows={[
                            ['Workflows', renames(result.workflows)],
                            ['Schedules', renames(result.schedules)],
                        ]}
                    />
                    {mode === 'copy' && result.schedules.length > 0 && (
                        <p className="transfer-note">Copied schedules start paused; turn them on in {result.target}.</p>
                    )}
                    <Problems errors={result.errors} />
                </>
            ) : (
                <div className="transfer-form">
                    <label className="admin-field">
                        <span>To project</span>
                        <select className="entropy-select" value={target} onChange={(event) => setTarget(event.target.value)} disabled={!projects}>
                            <option value="">{projects ? 'Choose a project…' : 'Loading…'}</option>
                            {targets.map((project) => (
                                <option key={project.key} value={project.key}>
                                    {project.name} ({project.key})
                                </option>
                            ))}
                        </select>
                    </label>
                    <fieldset className="transfer-choice">
                        <legend>How</legend>
                        <label>
                            <input type="radio" checked={mode === 'move'} onChange={() => setMode('move')} />
                            <span>
                                <strong>Move</strong>
                                <small>They leave {sourceKey ?? 'this project'}; names, history and alerts stay.</small>
                            </span>
                        </label>
                        <label>
                            <input type="radio" checked={mode === 'copy'} onChange={() => setMode('copy')} />
                            <span>
                                <strong>Copy</strong>
                                <small>
                                    {kind === 'workflows'
                                        ? 'Copies get a free name (e.g. deploy-2) because workflow names are unique.'
                                        : 'Copies start paused and get a free name.'}
                                </small>
                            </span>
                        </label>
                    </fieldset>
                    {kind === 'workflows' && (
                        <label className="transfer-check">
                            <input type="checkbox" checked={withSchedules} onChange={(event) => setWithSchedules(event.target.checked)} />
                            Also {mode} the schedules that run these workflows
                        </label>
                    )}
                </div>
            )}
        </Dialog>
    )
}

// ----------------------------------------------------------------------
// Vault export / import
// ----------------------------------------------------------------------

export function VaultExportDialog({ preselected, onClose }: { preselected?: string | null; onClose: () => void }) {
    const { notify } = useFeedback()
    const [names, setNames] = useState<string[] | null>(null)
    const [chosen, setChosen] = useState<Set<string>>(new Set(preselected ? [preselected] : []))
    const [passphrase, setPassphrase] = useState('')
    const [confirm, setConfirm] = useState('')
    const [busy, setBusy] = useState(false)
    const [error, setError] = useState('')
    useErrorToast(error)

    useEffect(() => {
        vaultApi
            .listNamespaces()
            .then((result) => setNames(result.items.map((item) => item.name)))
            .catch((cause: unknown) => setError(message(cause, 'Unable to load namespaces.')))
    }, [])

    const run = async () => {
        setBusy(true)
        setError('')
        try {
            await transferApi.exportVault([...chosen], passphrase)
            notify.success(`Exported ${plural(chosen.size, 'namespace')}. Keep the passphrase somewhere safe.`)
            onClose()
        } catch (cause) {
            setError(message(cause, 'Unable to export.'))
        } finally {
            setBusy(false)
        }
    }

    return (
        <Dialog
            title="Export vault"
            subtitle="Download namespaces with their secrets, encrypted with a passphrase you choose."
            icon={<KeyRound size={18} />}
            onClose={onClose}
            className="transfer-dialog"
            footer={
                <>
                    <button type="button" className="entropy-button entropy-button-secondary" onClick={onClose}>
                        Cancel
                    </button>
                    <button
                        type="button"
                        className="entropy-button entropy-button-primary"
                        onClick={() => void run()}
                        disabled={busy || chosen.size === 0 || !passphraseReady(passphrase, confirm)}
                    >
                        {busy ? <LoaderCircle size={15} className="entropy-spin" /> : <Download size={15} />}
                        Export
                    </button>
                </>
            }
        >
            <div className="transfer-form">
                <fieldset className="transfer-list">
                    <legend>Namespaces</legend>
                    {names === null && !error && <LoaderCircle size={16} className="entropy-spin" />}
                    {names?.length === 0 && <p className="transfer-note">You have no namespaces to export.</p>}
                    {names?.map((name) => (
                        <label key={name}>
                            <input
                                type="checkbox"
                                checked={chosen.has(name)}
                                onChange={() =>
                                    setChosen((current) => {
                                        const next = new Set(current)
                                        if (next.has(name)) next.delete(name)
                                        else next.add(name)
                                        return next
                                    })
                                }
                            />
                            {name}
                        </label>
                    ))}
                </fieldset>
                <NewPassphrase value={passphrase} confirm={confirm} onChange={setPassphrase} onConfirm={setConfirm} />
            </div>
        </Dialog>
    )
}

function VaultSummary({ summary }: { summary: VaultRestoreSummary }) {
    return (
        <>
            <Summary
                rows={summary.namespaces.map((item) => [
                    item.name,
                    item.error ??
                        `${item.created ? 'created; ' : ''}${item.added} added, ${item.updated} replaced, ${item.skipped} kept`,
                ])}
            />
        </>
    )
}

export function VaultImportDialog({ onClose, onDone }: { onClose: () => void; onDone: () => void }) {
    const [file, setFile] = useState<File | null>(null)
    const [passphrase, setPassphrase] = useState('')
    const [overwrite, setOverwrite] = useState(false)
    const [busy, setBusy] = useState(false)
    const [error, setError] = useState('')
    useErrorToast(error)
    const [summary, setSummary] = useState<(VaultRestoreSummary & { exported_by: string | null }) | null>(null)

    const run = async () => {
        if (!file) return
        setBusy(true)
        setError('')
        try {
            setSummary(await transferApi.importVault(file, passphrase, overwrite))
            onDone()
        } catch (cause) {
            setError(message(cause, 'Unable to import.'))
        } finally {
            setBusy(false)
        }
    }

    return (
        <Dialog
            title={summary ? 'Vault imported' : 'Import vault'}
            subtitle={
                summary
                    ? `Exported by ${summary.exported_by ?? 'someone'}: ${summary.added} added, ${summary.updated} replaced, ${summary.skipped} kept.`
                    : 'Restore an .entvault export. Missing namespaces are created and owned by you.'
            }
            icon={<KeyRound size={18} />}
            onClose={onClose}
            className="transfer-dialog"
            footer={
                summary ? (
                    <button type="button" className="entropy-button entropy-button-primary" onClick={onClose}>
                        Close
                    </button>
                ) : (
                    <>
                        <button type="button" className="entropy-button entropy-button-secondary" onClick={onClose}>
                            Cancel
                        </button>
                        <button type="button" className="entropy-button entropy-button-primary" onClick={() => void run()} disabled={busy || !file || !passphrase}>
                            {busy ? <LoaderCircle size={15} className="entropy-spin" /> : <Upload size={15} />}
                            Import
                        </button>
                    </>
                )
            }
        >
            {summary ? (
                <VaultSummary summary={summary} />
            ) : (
                <div className="transfer-form">
                    <FileField accept=".entvault,application/json" file={file} onChange={setFile} label="Choose an .entvault file" />
                    <label className="admin-field">
                        <span>Passphrase</span>
                        <input type="password" autoComplete="off" value={passphrase} onChange={(event) => setPassphrase(event.target.value)} />
                    </label>
                    <label className="transfer-check">
                        <input type="checkbox" checked={overwrite} onChange={(event) => setOverwrite(event.target.checked)} />
                        Replace secrets that already exist (otherwise they are kept)
                    </label>
                </div>
            )}
        </Dialog>
    )
}

// ----------------------------------------------------------------------
// Project dump / restore
// ----------------------------------------------------------------------

export function ProjectDumpDialog({ project, onClose }: { project: { key: string; name: string; workflows: number; schedules: number }; onClose: () => void }) {
    const { notify } = useFeedback()
    const [schedules, setSchedules] = useState(true)
    const [plugins, setPlugins] = useState(true)
    const [names, setNames] = useState<string[] | null>(null)
    const [vault, setVault] = useState<Set<string>>(new Set())
    const [passphrase, setPassphrase] = useState('')
    const [confirm, setConfirm] = useState('')
    const [busy, setBusy] = useState(false)
    const [error, setError] = useState('')
    useErrorToast(error)

    useEffect(() => {
        // The dumped project's namespaces, whichever project is current.
        apiRequest<{ items: { name: string }[] }>('/api/vault/namespaces', {
            headers: { [PROJECT_HEADER]: project.key },
        })
            .then((result) => setNames(result.items.map((item) => item.name)))
            .catch(() => setNames([]))
    }, [project.key])

    const needsPassphrase = vault.size > 0
    const ready = !needsPassphrase || passphraseReady(passphrase, confirm)

    const run = async () => {
        setBusy(true)
        setError('')
        try {
            await transferApi.dump(project.key, { schedules, plugins, vault: [...vault], passphrase: needsPassphrase ? passphrase : '' })
            notify.success(`Dump of ${project.name} downloaded.`)
            onClose()
        } catch (cause) {
            setError(message(cause, 'Unable to create the dump.'))
        } finally {
            setBusy(false)
        }
    }

    return (
        <Dialog
            title={`Dump ${project.name}`}
            subtitle={`A zip with the project's ${plural(project.workflows, 'workflow')}, to keep or to restore into any project, here or on another Entropy.`}
            icon={<FileArchive size={18} />}
            onClose={onClose}
            className="transfer-dialog"
            footer={
                <>
                    <button type="button" className="entropy-button entropy-button-secondary" onClick={onClose}>
                        Cancel
                    </button>
                    <button type="button" className="entropy-button entropy-button-primary" onClick={() => void run()} disabled={busy || !ready}>
                        {busy ? <LoaderCircle size={15} className="entropy-spin" /> : <Download size={15} />}
                        Download dump
                    </button>
                </>
            }
        >
            <div className="transfer-form">
                <fieldset className="transfer-list">
                    <legend>Include</legend>
                    <label>
                        <input type="checkbox" checked disabled />
                        Workflows ({project.workflows})
                    </label>
                    <label>
                        <input type="checkbox" checked={schedules} onChange={(event) => setSchedules(event.target.checked)} />
                        Schedules ({project.schedules}) — restored paused
                    </label>
                    <label>
                        <input type="checkbox" checked={plugins} onChange={(event) => setPlugins(event.target.checked)} />
                        Plugins the workflows use — installed on restore only where missing
                    </label>
                </fieldset>
                {names && names.length > 0 && (
                    <fieldset className="transfer-list">
                        <legend>Vault namespaces (encrypted with a passphrase)</legend>
                        {names.map((name) => (
                            <label key={name}>
                                <input
                                    type="checkbox"
                                    checked={vault.has(name)}
                                    onChange={() =>
                                        setVault((current) => {
                                            const next = new Set(current)
                                            if (next.has(name)) next.delete(name)
                                            else next.add(name)
                                            return next
                                        })
                                    }
                                />
                                {name}
                            </label>
                        ))}
                    </fieldset>
                )}
                {needsPassphrase && <NewPassphrase value={passphrase} confirm={confirm} onChange={setPassphrase} onConfirm={setConfirm} />}
            </div>
        </Dialog>
    )
}

export function ProjectRestoreDialog({ project, onClose, onDone }: { project: { key: string; name: string }; onClose: () => void; onDone: () => void }) {
    const [file, setFile] = useState<File | null>(null)
    const [manifest, setManifest] = useState<DumpManifest | null>(null)
    const [conflict, setConflict] = useState<'skip' | 'overwrite' | 'rename'>('rename')
    const [schedules, setSchedules] = useState(true)
    const [plugins, setPlugins] = useState(true)
    const [vault, setVault] = useState(true)
    const [vaultOverwrite, setVaultOverwrite] = useState(false)
    const [passphrase, setPassphrase] = useState('')
    const [busy, setBusy] = useState(false)
    const [error, setError] = useState('')
    useErrorToast(error)
    const [result, setResult] = useState<RestoreResult | null>(null)

    const choose = async (chosen: File | null) => {
        setFile(chosen)
        setManifest(null)
        setError('')
        if (!chosen) return
        setBusy(true)
        try {
            setManifest((await transferApi.preview(project.key, chosen)).manifest)
        } catch (cause) {
            setError(message(cause, 'Unable to read the dump.'))
        } finally {
            setBusy(false)
        }
    }

    const run = async () => {
        if (!file) return
        setBusy(true)
        setError('')
        try {
            setResult(
                await transferApi.restore(project.key, file, {
                    conflict,
                    schedules,
                    plugins,
                    vault: vault && Boolean(manifest?.vault),
                    vault_overwrite: vaultOverwrite,
                    passphrase,
                }),
            )
            onDone()
        } catch (cause) {
            setError(message(cause, 'Unable to restore.'))
        } finally {
            setBusy(false)
        }
    }

    const contents = useMemo(
        () =>
            manifest
                ? ([
                      ['From', `${manifest.project.name} (${manifest.project.key}), Entropy ${manifest.entropy_version}`],
                      ['Made', `${new Date(manifest.created_at).toLocaleString()} by ${manifest.created_by}`],
                      ['Workflows', manifest.workflows.join(', ') || 'None'],
                      ['Schedules', String(manifest.schedules)],
                      ['Plugins', manifest.plugins.join(', ') || 'None'],
                      ['Vault', manifest.vault ? 'Included (encrypted)' : 'Not included'],
                  ] as [string, ReactNode][])
                : [],
        [manifest],
    )

    return (
        <Dialog
            title={result ? 'Restored' : `Restore into ${project.name}`}
            subtitle={result ? undefined : 'Bring a project dump into this project. Nothing changes until you press Restore.'}
            icon={<ArchiveRestore size={18} />}
            onClose={onClose}
            className="transfer-dialog"
            footer={
                result ? (
                    <button type="button" className="entropy-button entropy-button-primary" onClick={onClose}>
                        Close
                    </button>
                ) : (
                    <>
                        <button type="button" className="entropy-button entropy-button-secondary" onClick={onClose}>
                            Cancel
                        </button>
                        <button
                            type="button"
                            className="entropy-button entropy-button-primary"
                            onClick={() => void run()}
                            disabled={busy || !manifest || (vault && Boolean(manifest?.vault) && !passphrase)}
                        >
                            {busy ? <LoaderCircle size={15} className="entropy-spin" /> : <ArchiveRestore size={15} />}
                            Restore
                        </button>
                    </>
                )
            }
        >
            {result ? (
                <>
                    <Summary
                        rows={[
                            ['Workflows', renames(result.workflows)],
                            ['Kept (existing)', result.skipped.join(', ') || 'None'],
                            ['Schedules (paused)', renames(result.schedules)],
                            ['Schedules kept', result.skipped_schedules.join(', ') || 'None'],
                            ['Plugins installed', result.plugins.join(', ') || 'None'],
                        ]}
                    />
                    {result.vault && <VaultSummary summary={result.vault} />}
                    <Problems errors={result.errors} />
                </>
            ) : (
                <div className="transfer-form">
                    <FileField accept=".zip,application/zip" file={file} onChange={(chosen) => void choose(chosen)} label="Choose a project dump (.zip)" />
                    {busy && !manifest && <LoaderCircle size={16} className="entropy-spin" />}
                    {manifest && (
                        <>
                            <Summary rows={contents} />
                            <fieldset className="transfer-choice">
                                <legend>When a workflow with the same name exists</legend>
                                <label>
                                    <input type="radio" checked={conflict === 'rename'} onChange={() => setConflict('rename')} />
                                    <span>
                                        <strong>Restore it under a new name</strong>
                                        <small>e.g. deploy-2</small>
                                    </span>
                                </label>
                                <label>
                                    <input type="radio" checked={conflict === 'skip'} onChange={() => setConflict('skip')} />
                                    <span>
                                        <strong>Keep the existing one</strong>
                                        <small>Skip it (and its schedules)</small>
                                    </span>
                                </label>
                                <label>
                                    <input type="radio" checked={conflict === 'overwrite'} onChange={() => setConflict('overwrite')} />
                                    <span>
                                        <strong>Replace it</strong>
                                        <small>Where you may change it; the old version stays in History</small>
                                    </span>
                                </label>
                            </fieldset>
                            <fieldset className="transfer-list">
                                <legend>Also restore</legend>
                                <label>
                                    <input type="checkbox" checked={schedules} onChange={(event) => setSchedules(event.target.checked)} />
                                    Schedules (they start paused)
                                </label>
                                <label>
                                    <input type="checkbox" checked={plugins} onChange={(event) => setPlugins(event.target.checked)} disabled={!manifest.plugins.length} />
                                    Plugins that are not installed here
                                </label>
                                <label>
                                    <input type="checkbox" checked={vault && manifest.vault} onChange={(event) => setVault(event.target.checked)} disabled={!manifest.vault} />
                                    Vault namespaces
                                </label>
                            </fieldset>
                            {vault && manifest.vault && (
                                <>
                                    <label className="admin-field">
                                        <span>Vault passphrase</span>
                                        <input type="password" autoComplete="off" value={passphrase} onChange={(event) => setPassphrase(event.target.value)} />
                                    </label>
                                    <label className="transfer-check">
                                        <input type="checkbox" checked={vaultOverwrite} onChange={(event) => setVaultOverwrite(event.target.checked)} />
                                        Replace secrets that already exist
                                    </label>
                                </>
                            )}
                        </>
                    )}
                </div>
            )}
        </Dialog>
    )
}
