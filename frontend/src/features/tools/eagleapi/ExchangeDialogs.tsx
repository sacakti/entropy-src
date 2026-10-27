import { useRef, useState } from 'react'
import { Download, FileUp, LoaderCircle, Lock, Upload } from 'lucide-react'

import Dialog from '../../../components/layout/Dialog'
import { useFeedback } from '../../../components/feedback/FeedbackProvider'
import { eagleApi, type EagleItem, type ExportFormat, type ImportSummary } from '../../../api/eagleapi.api'
import { itemPath } from './model'
import { useErrorToast } from '../../../components/feedback/useToast'

function errorText(cause: unknown, fallback: string): string {
    return cause instanceof Error && cause.message ? cause.message : fallback
}

const FORMATS: { id: ExportFormat; label: string; detail: string; extension: string }[] = [
    { id: 'eagleapi', label: 'EagleAPI', detail: 'Everything, for another Entropy project or installation.', extension: 'eagleapi.json' },
    { id: 'postman', label: 'Postman (v2.1)', detail: 'Also opens in Insomnia, Bruno, Hoppscotch and Thunder Client.', extension: 'postman_collection.json' },
    { id: 'soapui', label: 'SoapUI / ReadyAPI', detail: 'A SoapUI project with one REST service per collection.', extension: 'soapui-project.xml' },
]

const IMPORT_NAMES: Record<ImportSummary['format'], string> = {
    eagleapi: 'EagleAPI',
    postman: 'Postman',
    soapui: 'SoapUI',
    insomnia: 'Insomnia',
}

function PreserveField({ value, onChange, importing }: { value: boolean; onChange: (value: boolean) => void; importing?: boolean }) {
    return (
        <label className="eagle-check eagle-check-block">
            <input type="checkbox" checked={value} onChange={(event) => onChange(event.target.checked)} />
            <span>
                <strong>Preserve settings</strong>
                <small>
                    Auth, TLS, polling and options of each request
                    {importing ? ', and the TLS profiles of an EagleAPI file' : ' (EagleAPI also keeps the project’s TLS profiles)'}. Otherwise
                    only method, URL, parameters, headers and body. Secrets stay in the vault: references are exported, never values.
                </small>
            </span>
        </label>
    )
}

/** Export chosen collections in EagleAPI's, Postman's or SoapUI's format. */
export function ExportDialog({ items, initial, onClose }: { items: EagleItem[]; initial: number[]; onClose: () => void }) {
    const { notify } = useFeedback()
    const collections = items.filter((item) => item.parent_id === null)
    const [chosen, setChosen] = useState<Set<number>>(() => new Set(initial.length ? initial : collections.map((item) => item.id)))
    const [format, setFormat] = useState<ExportFormat>('eagleapi')
    const [preserve, setPreserve] = useState(true)
    const [busy, setBusy] = useState(false)
    const [error, setError] = useState<string | null>(null)
    useErrorToast(error)
    // An item inside a collection (opened from its menu) is offered as is.
    const extra = initial.filter((id) => !collections.some((item) => item.id === id)).map((id) => items.find((item) => item.id === id)).filter(Boolean) as EagleItem[]
    const choices = [...extra, ...collections]

    const run = async () => {
        const ids = choices.filter((item) => chosen.has(item.id)).map((item) => item.id)
        const first = choices.find((item) => item.id === ids[0])
        const base = (ids.length === 1 && first ? first.name : 'collections').replace(/[^A-Za-z0-9._-]+/g, '-')
        const extension = FORMATS.find((entry) => entry.id === format)?.extension ?? 'json'
        setBusy(true)
        setError(null)
        try {
            await eagleApi.exportCollections(ids, format, preserve, `${base}.${extension}`)
            notify.success(`Exported ${ids.length} collection${ids.length === 1 ? '' : 's'}.`)
            onClose()
        } catch (cause) {
            setError(errorText(cause, 'The export failed.'))
        } finally {
            setBusy(false)
        }
    }

    const toggle = (id: number) =>
        setChosen((current) => {
            const next = new Set(current)
            if (next.has(id)) next.delete(id)
            else next.add(id)
            return next
        })

    return (
        <Dialog
            title="Export collections"
            subtitle="Download collections to share them or open them in another API tool."
            icon={<Download size={18} />}
            onClose={onClose}
            className="eagle-exchange-dialog"
            footer={
                <>
                    <button type="button" className="entropy-button entropy-button-secondary" onClick={onClose}>
                        Cancel
                    </button>
                    <button type="button" className="entropy-button entropy-button-primary" disabled={busy || chosen.size === 0} onClick={() => void run()}>
                        {busy ? <LoaderCircle size={14} className="entropy-spin" /> : <Download size={14} />} Export
                    </button>
                </>
            }
        >
            <div className="eagle-exchange">
                <fieldset>
                    <legend>Collections</legend>
                    {choices.length === 0 ? (
                        <p className="eagle-muted">There are no collections to export.</p>
                    ) : (
                        <ul className="eagle-exchange-list">
                            {choices.map((item) => (
                                <li key={item.id}>
                                    <label className="eagle-check">
                                        <input type="checkbox" checked={chosen.has(item.id)} onChange={() => toggle(item.id)} />
                                        <span>
                                            {item.parent_id !== null ? `${itemPath(items, item.parent_id)} / ` : ''}
                                            {item.name}
                                            {item.restricted && <Lock size={12} className="eagle-inline-icon" aria-label="restricted" />}
                                        </span>
                                    </label>
                                </li>
                            ))}
                        </ul>
                    )}
                </fieldset>
                <fieldset>
                    <legend>Format</legend>
                    {FORMATS.map((entry) => (
                        <label key={entry.id} className="eagle-check eagle-check-block">
                            <input type="radio" name="eagle-export-format" checked={format === entry.id} onChange={() => setFormat(entry.id)} />
                            <span>
                                <strong>{entry.label}</strong>
                                <small>{entry.detail}</small>
                            </span>
                        </label>
                    ))}
                </fieldset>
                <PreserveField value={preserve} onChange={setPreserve} />
                {format !== 'eagleapi' && (
                    <p className="eagle-muted">
                        Vault references become the tool’s variables ({format === 'postman' ? '{{KEY}}' : '${#Project#KEY}'}), and paths use a{' '}
                        <code>baseUrl</code> variable for the environment’s base URL.
                    </p>
                )}
            </div>
        </Dialog>
    )
}

/** Import an EagleAPI, Postman, Insomnia or SoapUI export. */
export function ImportDialog({
    items,
    onImported,
    onClose,
}: {
    items: EagleItem[]
    onImported: (summary: ImportSummary) => void
    onClose: () => void
}) {
    const { notify } = useFeedback()
    const fileRef = useRef<HTMLInputElement>(null)
    const [file, setFile] = useState<File | null>(null)
    const [preserve, setPreserve] = useState(true)
    const [parentId, setParentId] = useState<number | null>(null)
    const [preview, setPreview] = useState<ImportSummary | null>(null)
    const [busy, setBusy] = useState(false)
    const [error, setError] = useState<string | null>(null)
    useErrorToast(error)
    const folders = items.filter((item) => item.kind === 'folder' && item.access !== 'read')

    const inspect = async (next: File | null, keep = preserve) => {
        setFile(next)
        setPreview(null)
        setError(null)
        if (!next) return
        setBusy(true)
        try {
            setPreview(await eagleApi.importCollections(next, { parentId: null, preserve: keep, preview: true }))
        } catch (cause) {
            setError(errorText(cause, 'The file cannot be read.'))
        } finally {
            setBusy(false)
        }
    }

    const run = async () => {
        if (!file) return
        setBusy(true)
        setError(null)
        try {
            const summary = await eagleApi.importCollections(file, { parentId, preserve, preview: false })
            const profiles = summary.added_profiles?.length ? ` and ${summary.added_profiles.length} TLS profile(s)` : ''
            notify.success(`Imported ${summary.requests} request(s) in ${summary.folders} folder(s)${profiles}.`)
            onImported(summary)
            onClose()
        } catch (cause) {
            setError(errorText(cause, 'The import failed.'))
        } finally {
            setBusy(false)
        }
    }

    return (
        <Dialog
            title="Import collections"
            subtitle="From EagleAPI, Postman (v2.0, v2.1), Insomnia (v4) or SoapUI / ReadyAPI (REST and SOAP)."
            icon={<Upload size={18} />}
            onClose={onClose}
            className="eagle-exchange-dialog"
            footer={
                <>
                    <button type="button" className="entropy-button entropy-button-secondary" onClick={onClose}>
                        Cancel
                    </button>
                    <button type="button" className="entropy-button entropy-button-primary" disabled={busy || !preview} onClick={() => void run()}>
                        {busy ? <LoaderCircle size={14} className="entropy-spin" /> : <Upload size={14} />} Import
                    </button>
                </>
            }
        >
            <div className="eagle-exchange">
                <input
                    ref={fileRef}
                    type="file"
                    accept=".json,.xml,application/json,application/xml,text/xml"
                    hidden
                    onChange={(event) => void inspect(event.target.files?.[0] ?? null)}
                />
                <button type="button" className="eagle-drop" onClick={() => fileRef.current?.click()}>
                    <FileUp size={20} aria-hidden="true" />
                    <span>{file ? file.name : 'Choose an export file…'}</span>
                </button>
                {preview && (
                    <div className="eagle-import-preview" role="status">
                        <p>
                            <strong>{IMPORT_NAMES[preview.format]}</strong> · {preview.name}
                        </p>
                        <p className="eagle-muted">
                            {preview.collections.length} collection(s): {preview.collections.join(', ')} — {preview.folders} folder(s),{' '}
                            {preview.requests} request(s)
                            {preview.tls_profiles ? `, ${preview.tls_profiles} TLS profile(s)` : ''}.
                        </p>
                        {preview.warnings.length > 0 && (
                            <ul className="eagle-import-warnings">
                                {preview.warnings.map((warning) => (
                                    <li key={warning}>{warning}</li>
                                ))}
                            </ul>
                        )}
                    </div>
                )}
                <label className="eagle-field">
                    <span>Import into</span>
                    <select value={parentId ?? ''} onChange={(event) => setParentId(event.target.value ? Number(event.target.value) : null)}>
                        <option value="">Top level (new collections)</option>
                        {folders.map((folder) => (
                            <option key={folder.id} value={folder.id}>
                                {itemPath(items, folder.id)}
                            </option>
                        ))}
                    </select>
                </label>
                <PreserveField
                    value={preserve}
                    importing
                    onChange={(value) => {
                        setPreserve(value)
                        if (file) void inspect(file, value)
                    }}
                />
                <p className="eagle-muted">
                    Variables become references to this project’s EagleAPI vault namespace; add their values in Environment. A leading{' '}
                    <code>{'{{baseUrl}}'}</code> is replaced by the environment’s base URL.
                </p>
            </div>
        </Dialog>
    )
}
