import { useEffect, useMemo, useState } from 'react'
import { ArrowUp, Check, File, Folder, FolderOpen, HardDrive, Home, LoaderCircle, RefreshCw, Search } from 'lucide-react'

import { serverFilesApi, type ServerFileEntry, type ServerFolder } from '../../api/serverFiles.api'
import Dialog from '../layout/Dialog'

export type PathKind = 'file' | 'directory' | 'any'

function formatSize(size: number | null): string {
    if (size === null) return ''
    if (size < 1024) return `${size} B`
    if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`
    if (size < 1024 * 1024 * 1024) return `${(size / 1024 / 1024).toFixed(1)} MB`
    return `${(size / 1024 / 1024 / 1024).toFixed(1)} GB`
}

/**
 * Pick a file or folder on the Entropy server (where local runs execute),
 * for a path argument of a plugin or workflow step.
 */
export default function ServerFileBrowser({
    kind = 'any',
    initial = '',
    title,
    onPick,
    onClose,
}: {
    kind?: PathKind
    /** The current value: browsing starts there. */
    initial?: string
    title?: string
    onPick: (path: string) => void
    onClose: () => void
}) {
    const [folder, setFolder] = useState<ServerFolder | null>(null)
    const [loading, setLoading] = useState(true)
    const [error, setError] = useState<string | null>(null)
    const [selected, setSelected] = useState<string | null>(null)
    const [typed, setTyped] = useState(initial)
    const [filter, setFilter] = useState('')
    // Start where the current value points (its folder for a file).
    const [request, setRequest] = useState({ path: initial.includes('${') ? '' : initial, hidden: false })

    useEffect(() => {
        let active = true
        serverFilesApi
            .browse(request.path, request.hidden)
            .then((result) => {
                if (!active) return
                setFolder(result)
                setTyped(result.selected ?? result.path)
                setSelected(result.selected)
                setFilter('')
                setError(null)
            })
            .catch((cause: unknown) => {
                if (active) setError(cause instanceof Error ? cause.message : 'Unable to open the folder.')
            })
            .finally(() => {
                if (active) setLoading(false)
            })
        return () => {
            active = false
        }
    }, [request])

    const open = (path: string) => {
        setLoading(true)
        setRequest((current) => ({ ...current, path }))
    }

    const setHidden = (hidden: boolean) => {
        setLoading(true)
        setRequest((current) => ({ path: folder?.path ?? current.path, hidden }))
    }
    const hidden = request.hidden

    const entries = useMemo(() => {
        const needle = filter.trim().toLowerCase()
        return (folder?.entries ?? []).filter((entry) => !needle || entry.name.toLowerCase().includes(needle))
    }, [folder, filter])

    // What "Select" would return: the chosen entry, or the open folder itself.
    const choice = selected ?? (kind !== 'file' ? folder?.path ?? null : null)
    const choiceEntry = folder?.entries.find((entry) => entry.path === selected)
    const choiceOk =
        choice !== null &&
        (kind === 'any' ||
            (kind === 'file' && choiceEntry?.kind === 'file') ||
            (kind === 'directory' && (!choiceEntry || choiceEntry.kind === 'directory')))

    const activate = (entry: ServerFileEntry) => {
        if (entry.kind === 'directory') open(entry.path)
        else if (kind !== 'directory') onPick(entry.path)
    }

    const noun = kind === 'file' ? 'file' : kind === 'directory' ? 'folder' : 'file or folder'

    return (
        <Dialog
            title={title ?? `Choose a ${noun} on the server`}
            subtitle="Files on the Entropy server, where local runs execute. On another node, type the path as it is there."
            icon={<FolderOpen size={18} />}
            onClose={onClose}
            className="server-files-dialog"
            footer={
                <>
                    <span className="server-files-choice" title={choice ?? undefined}>
                        {choice ?? `Select a ${noun}`}
                    </span>
                    <button type="button" className="entropy-button entropy-button-secondary" onClick={onClose}>
                        Cancel
                    </button>
                    <button
                        type="button"
                        className="entropy-button entropy-button-primary"
                        disabled={!choiceOk}
                        onClick={() => choice && onPick(choice)}
                    >
                        <Check size={15} /> Select
                    </button>
                </>
            }
        >
            <form
                className="server-files-bar"
                onSubmit={(event) => {
                    event.preventDefault()
                    open(typed)
                }}
            >
                <button
                    type="button"
                    className="entropy-button entropy-button-ghost entropy-button-icon entropy-button-sm"
                    aria-label="Up one folder"
                    title="Up one folder"
                    disabled={!folder?.parent}
                    onClick={() => folder?.parent && open(folder.parent)}
                >
                    <ArrowUp size={15} />
                </button>
                <button
                    type="button"
                    className="entropy-button entropy-button-ghost entropy-button-icon entropy-button-sm"
                    aria-label="Workspace"
                    title={folder ? `Workspace: ${folder.home}` : 'Workspace'}
                    onClick={() => folder && open(folder.home)}
                >
                    <Home size={15} />
                </button>
                {(folder?.roots.length ?? 0) > 1 &&
                    folder?.roots.map((root) => (
                        <button
                            key={root}
                            type="button"
                            className="entropy-button entropy-button-ghost entropy-button-sm"
                            onClick={() => open(root)}
                        >
                            <HardDrive size={14} /> {root}
                        </button>
                    ))}
                <input
                    value={typed}
                    onChange={(event) => setTyped(event.target.value)}
                    aria-label="Path"
                    spellCheck={false}
                    placeholder="/path/on/the/server"
                />
                <button
                    type="submit"
                    className="entropy-button entropy-button-ghost entropy-button-icon entropy-button-sm"
                    aria-label="Go"
                    title="Open this path"
                >
                    {loading ? <LoaderCircle size={15} className="entropy-spin" /> : <RefreshCw size={15} />}
                </button>
            </form>

            <div className="server-files-tools">
                <label className="server-files-filter">
                    <Search size={14} aria-hidden="true" />
                    <input
                        value={filter}
                        onChange={(event) => setFilter(event.target.value)}
                        placeholder="Filter this folder"
                        aria-label="Filter this folder"
                    />
                </label>
                <label className="server-files-hidden">
                    <input type="checkbox" checked={hidden} onChange={(event) => setHidden(event.target.checked)} />
                    Hidden files
                </label>
            </div>

            {error && (
                <div className="entropy-alert entropy-alert-error" role="alert">
                    {error}
                </div>
            )}

            <ul className="server-files-list" role="listbox" aria-label={folder?.path ?? 'Folder'}>
                {!loading && entries.length === 0 && !error && (
                    <li className="server-files-empty">{filter ? 'Nothing matches.' : 'This folder is empty.'}</li>
                )}
                {entries.map((entry) => {
                    const pickable = kind === 'any' || entry.kind === kind || entry.kind === 'directory'
                    return (
                        <li key={entry.path} role="option" aria-selected={entry.path === selected}>
                            <button
                                type="button"
                                className={`server-files-entry${entry.path === selected ? ' is-selected' : ''}${
                                    pickable ? '' : ' is-muted'
                                }`}
                                onClick={() => setSelected(entry.path === selected ? null : entry.path)}
                                onDoubleClick={() => activate(entry)}
                                title={entry.readable ? entry.path : `${entry.path} (not readable by the server)`}
                            >
                                {entry.kind === 'directory' ? <Folder size={15} /> : <File size={15} />}
                                <span className="server-files-name">{entry.name}</span>
                                <span className="server-files-size">{formatSize(entry.size)}</span>
                                <span className="server-files-date">{new Date(entry.modified).toLocaleString()}</span>
                            </button>
                        </li>
                    )
                })}
            </ul>
            {folder?.truncated && (
                <p className="server-files-note">Only the first 2000 entries are listed; filter or type a path.</p>
            )}
            <p className="server-files-note">Double-click a folder to open it{kind === 'directory' ? '' : ', or a file to choose it'}.</p>
        </Dialog>
    )
}
