import { useRef, useState } from 'react'
import { FileUp, LoaderCircle, Package } from 'lucide-react'

import Dialog from '../../components/layout/Dialog'
import { extensionsApi, type BuiltinLibrary, type ExtensionVersion } from '../../api/extensions.api'
import { Tabs } from '../administration/AdminPanel'

function errorText(cause: unknown, fallback: string): string {
    return cause instanceof Error && cause.message ? cause.message : fallback
}

const canonical = (name: string) => name.toLowerCase().replace(/[-_.]+/g, '-')

/**
 * Install a library: from the package index (PyPI or your own index), or
 * your own file — a wheel, a source archive, a .py module or a zipped
 * package folder.
 */
export default function InstallExtensionDialog({
    builtin,
    installed,
    onInstalled,
    onClose,
}: {
    builtin: BuiltinLibrary[]
    installed: ExtensionVersion[]
    onInstalled: (extension: ExtensionVersion) => void
    onClose: () => void
}) {
    const [tab, setTab] = useState<'index' | 'upload'>('index')
    const [name, setName] = useState('')
    const [version, setVersion] = useState('')
    const [summary, setSummary] = useState('')
    const [dependencies, setDependencies] = useState(true)
    const [indexUrl, setIndexUrl] = useState('')
    const [file, setFile] = useState<File | null>(null)
    const [busy, setBusy] = useState(false)
    const [error, setError] = useState<string | null>(null)
    const fileRef = useRef<HTMLInputElement>(null)

    // A .py module needs a name and version; a .zip may be a package folder or a bundle of wheels.
    const plain = Boolean(file && /\.py$/i.test(file.name))
    const known = name.trim() ? builtin.find((library) => canonical(library.name) === canonical(name.trim())) : undefined
    const versions = name.trim()
        ? installed.filter((entry) => entry.canonical === canonical(name.trim())).map((entry) => entry.version)
        : []

    const submit = async () => {
        setBusy(true)
        setError(null)
        try {
            const extension =
                tab === 'index'
                    ? await extensionsApi.install({
                          name: name.trim(),
                          version: version.trim() || undefined,
                          dependencies,
                          index_url: indexUrl.trim() || undefined,
                      })
                    : await extensionsApi.upload(file as File, {
                          name: name.trim() || undefined,
                          version: version.trim() || undefined,
                          summary: summary.trim() || undefined,
                          dependencies,
                          index_url: indexUrl.trim() || undefined,
                      })
            onInstalled(extension)
            onClose()
        } catch (cause) {
            setError(errorText(cause, 'The library was not installed.'))
        } finally {
            setBusy(false)
        }
    }

    const ready = tab === 'index' ? Boolean(name.trim()) : Boolean(file)

    return (
        <Dialog
            title="Install a library"
            subtitle="Libraries are kept per version: plugins that need different versions of one library each get theirs."
            icon={<Package size={18} />}
            onClose={busy ? () => undefined : onClose}
            className="extension-dialog"
            footer={
                <>
                    <button type="button" className="entropy-button entropy-button-secondary" onClick={onClose} disabled={busy}>
                        Cancel
                    </button>
                    <button type="button" className="entropy-button entropy-button-primary" disabled={!ready || busy} onClick={() => void submit()}>
                        {busy && <LoaderCircle size={15} className="entropy-spin" />} {busy ? 'Installing…' : 'Install'}
                    </button>
                </>
            }
        >
            <Tabs
                tabs={[
                    { id: 'index', label: 'From the package index' },
                    { id: 'upload', label: 'Upload your own' },
                ]}
                active={tab}
                onChange={(next) => {
                    setTab(next)
                    setError(null)
                }}
            />
            <div className="admin-form-grid extension-form">
                {tab === 'upload' && (
                    <div className="admin-field admin-field-wide">
                        <span>File</span>
                        <input
                            ref={fileRef}
                            type="file"
                            accept=".whl,.tar.gz,.tgz,.zip,.py"
                            hidden
                            onChange={(event) => setFile(event.target.files?.[0] ?? null)}
                        />
                        <button type="button" className="extension-drop" onClick={() => fileRef.current?.click()}>
                            <FileUp size={18} aria-hidden="true" />
                            <span>{file ? file.name : 'Choose a wheel, a .zip of wheels, a source archive, a .py module or a zipped package folder…'}</span>
                        </button>
                        <small>
                            No package index here? Zip the wheels of the library and its dependencies (
                            <code>pip download paramiko -d wheels</code>) and upload the zip. Wheels and source archives carry their
                            own name and version; a .py module or a zipped package folder needs them below.
                        </small>
                    </div>
                )}
                <label className="admin-field">
                    <span>Library{tab === 'upload' ? (plain ? '' : ' (optional)') : ''}</span>
                    <input
                        value={name}
                        onChange={(event) => setName(event.target.value)}
                        placeholder={tab === 'index' ? 'e.g. paramiko' : 'e.g. acme-tools'}
                        spellCheck={false}
                        autoComplete="off"
                    />
                </label>
                <label className="admin-field">
                    <span>Version{tab === 'index' || !plain ? ' (optional)' : ''}</span>
                    <input
                        value={version}
                        onChange={(event) => setVersion(event.target.value)}
                        placeholder={tab === 'index' ? 'newest, or 3.0, or >=2,<3' : 'e.g. 1.0.0'}
                        spellCheck={false}
                        autoComplete="off"
                    />
                </label>
                {(known || versions.length > 0) && (
                    <p className="extension-known admin-field-wide" role="status">
                        {known && (
                            <>
                                Entropy already has <strong>{known.name} {known.version}</strong>: plugins use it as it is. Install another
                                version only if a plugin needs one.{' '}
                            </>
                        )}
                        {versions.length > 0 && <>Installed here: {versions.join(', ')}.</>}
                    </p>
                )}
                {tab === 'upload' && plain && (
                    <label className="admin-field admin-field-wide">
                        <span>Description (optional)</span>
                        <input value={summary} onChange={(event) => setSummary(event.target.value)} maxLength={300} />
                    </label>
                )}
                {!(tab === 'upload' && plain) && (
                    <label className="admin-field admin-field-wide extension-check">
                        <input type="checkbox" checked={dependencies} onChange={(event) => setDependencies(event.target.checked)} />
                        <span>
                            Install its dependencies too
                            <small>Dependencies Entropy already has at the same version are shared, not copied.</small>
                        </span>
                    </label>
                )}
                {!(tab === 'upload' && plain) && (
                    <label className="admin-field admin-field-wide">
                        <span>Package index (optional)</span>
                        <input
                            value={indexUrl}
                            onChange={(event) => setIndexUrl(event.target.value)}
                            placeholder="Default: the index pip is configured with (PyPI)"
                            spellCheck={false}
                        />
                    </label>
                )}
            </div>
            {busy && (
                <p className="extension-progress" role="status">
                    <LoaderCircle size={14} className="entropy-spin" aria-hidden="true" /> Fetching and installing; large libraries take a
                    while…
                </p>
            )}
            {error && (
                <div className="entropy-alert entropy-alert-error extension-error" role="alert">
                    <pre>{error}</pre>
                </div>
            )}
        </Dialog>
    )
}
