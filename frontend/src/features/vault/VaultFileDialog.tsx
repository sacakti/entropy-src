import { useState } from 'react'
import { AlertCircle, FileKey2, LoaderCircle, Upload } from 'lucide-react'

import { vaultApi } from '../../api/vault.api'
import { useFeedback } from '../../components/feedback/FeedbackProvider'
import Dialog from '../../components/layout/Dialog'

const MAX_BYTES = 5 * 1024 * 1024
const KEY_PATTERN = /^[A-Za-z0-9_]+$/

/** A suggested key from a file name: client-cert.crt -> client_cert_crt. */
function keyFor(filename: string): string {
    return filename.replace(/[^A-Za-z0-9]+/g, '_').replace(/^_+|_+$/g, '').slice(0, 120) || 'file'
}

function formatSize(bytes: number): string {
    if (bytes < 1024) return `${bytes} B`
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

/**
 * Keep a file in the vault (certificate, keystore, key ...), or replace the
 * file of an existing entry.
 */
export default function VaultFileDialog({
    namespace,
    replaceKey,
    onClose,
    onSaved,
}: {
    namespace: string
    /** Set to replace this entry's file; otherwise a new entry is created. */
    replaceKey?: string
    onClose: () => void
    onSaved: () => void
}) {
    const { notify } = useFeedback()
    const [file, setFile] = useState<File | null>(null)
    const [key, setKey] = useState(replaceKey ?? '')
    const [keyTouched, setKeyTouched] = useState(Boolean(replaceKey))
    const [sensitive, setSensitive] = useState(true)
    const [busy, setBusy] = useState(false)
    const [error, setError] = useState('')

    const tooLarge = Boolean(file && file.size > MAX_BYTES)
    const keyError = key && !KEY_PATTERN.test(key) ? 'Letters, numbers and underscore (_) only.' : ''

    const choose = (chosen: File | null) => {
        setFile(chosen)
        setError('')
        if (chosen && !keyTouched) setKey(keyFor(chosen.name))
    }

    const save = async () => {
        if (!file) return
        setBusy(true)
        setError('')
        try {
            await vaultApi.uploadFile(namespace, key, file, sensitive, Boolean(replaceKey))
            notify.success(replaceKey ? `File of "${key}" replaced.` : `"${file.name}" kept in the vault as "${key}".`)
            onSaved()
            onClose()
        } catch (cause) {
            setError(cause instanceof Error ? cause.message : 'Unable to upload the file.')
        } finally {
            setBusy(false)
        }
    }

    return (
        <Dialog
            title={replaceKey ? `Replace the file of ${replaceKey}` : 'Upload a file'}
            subtitle={`Certificates, keystores, keys or any file, in ${namespace}. Workflows use it as \${entvfile:${namespace}/${key || 'key'}} (a path) or \${entv:...} (its text).`}
            icon={<FileKey2 size={18} />}
            onClose={onClose}
            className="vault-file-dialog"
            footer={
                <>
                    <button type="button" className="entropy-button entropy-button-secondary" onClick={onClose}>
                        Cancel
                    </button>
                    <button
                        type="button"
                        className="entropy-button entropy-button-primary"
                        onClick={() => void save()}
                        disabled={busy || !file || !key || Boolean(keyError) || tooLarge}
                    >
                        {busy ? <LoaderCircle size={15} className="entropy-spin" /> : <Upload size={15} />}
                        {replaceKey ? 'Replace' : 'Upload'}
                    </button>
                </>
            }
        >
            <div className="vault-file-form">
                <label className="vault-file-drop">
                    <Upload size={18} aria-hidden="true" />
                    <span>
                        <strong>{file ? file.name : 'Choose a file'}</strong>
                        <small>
                            {file
                                ? `${formatSize(file.size)}${tooLarge ? ' — larger than the 5 MB limit' : ''}`
                                : '.crt, .pem, .pfx, .p12, .jks, id_rsa, .pub … up to 5 MB'}
                        </small>
                    </span>
                    <input type="file" onChange={(event) => choose(event.target.files?.[0] ?? null)} />
                </label>
                <label className="vault-form-field">
                    <span>Key</span>
                    <input
                        value={key}
                        onChange={(event) => {
                            setKey(event.target.value)
                            setKeyTouched(true)
                        }}
                        disabled={Boolean(replaceKey)}
                        placeholder="client_certificate"
                        autoComplete="off"
                    />
                    {keyError && <small className="vault-file-error">{keyError}</small>}
                </label>
                <label className="vault-file-check">
                    <input type="checkbox" checked={sensitive} onChange={(event) => setSensitive(event.target.checked)} />
                    Encrypt (recommended for private keys and keystores)
                </label>
            </div>
            {error && (
                <p className="entropy-alert entropy-alert-error" role="alert">
                    <AlertCircle size={15} /> {error}
                </p>
            )}
        </Dialog>
    )
}

