import { useState, type FormEvent } from 'react'
import { Folder, FolderInput, Pencil } from 'lucide-react'

import Dialog from '../../../components/layout/Dialog'
import type { EagleItem } from '../../../api/eagleapi.api'
import { itemPath, subtreeIds } from './model'

/** Ask for a name (new folder, new request, rename). */
export function NameDialog({
    title,
    subtitle,
    initial,
    confirmText,
    onSubmit,
    onClose,
}: {
    title: string
    subtitle?: string
    initial: string
    confirmText: string
    onSubmit: (name: string) => Promise<boolean>
    onClose: () => void
}) {
    const [name, setName] = useState(initial)
    const [busy, setBusy] = useState(false)

    const submit = async (event?: FormEvent) => {
        event?.preventDefault()
        if (!name.trim() || busy) return
        setBusy(true)
        const done = await onSubmit(name.trim())
        setBusy(false)
        if (done) onClose()
    }

    return (
        <Dialog
            title={title}
            subtitle={subtitle}
            icon={<Pencil size={18} />}
            onClose={onClose}
            className="eagle-small-dialog"
            footer={
                <>
                    <button type="button" className="entropy-button entropy-button-secondary" onClick={onClose}>
                        Cancel
                    </button>
                    <button
                        type="button"
                        className="entropy-button entropy-button-primary"
                        disabled={!name.trim() || busy}
                        onClick={() => void submit()}
                    >
                        {confirmText}
                    </button>
                </>
            }
        >
            <form onSubmit={(event) => void submit(event)}>
                <label className="eagle-field">
                    <span>Name</span>
                    <input value={name} maxLength={120} onChange={(event) => setName(event.target.value)} required />
                </label>
            </form>
        </Dialog>
    )
}

/** Pick the folder an item moves to (or the top level). */
export function MoveDialog({
    item,
    items,
    onSubmit,
    onClose,
}: {
    item: EagleItem
    items: EagleItem[]
    onSubmit: (parentId: number | null) => void
    onClose: () => void
}) {
    const excluded = item.kind === 'folder' ? subtreeIds(items, item.id) : new Set<number>()
    const folders = items
        .filter((candidate) => candidate.kind === 'folder' && !excluded.has(candidate.id))
        .map((folder) => ({ id: folder.id, path: itemPath(items, folder.id) }))
        .sort((a, b) => a.path.localeCompare(b.path))
    const [target, setTarget] = useState<number | null>(item.parent_id)

    return (
        <Dialog
            title={`Move ${item.name}`}
            subtitle="Choose the folder it goes to."
            icon={<FolderInput size={18} />}
            onClose={onClose}
            className="eagle-small-dialog"
            footer={
                <>
                    <button type="button" className="entropy-button entropy-button-secondary" onClick={onClose}>
                        Cancel
                    </button>
                    <button
                        type="button"
                        className="entropy-button entropy-button-primary"
                        disabled={target === item.parent_id}
                        onClick={() => onSubmit(target)}
                    >
                        Move
                    </button>
                </>
            }
        >
            <div className="eagle-move-list" role="radiogroup" aria-label="Destination folder">
                <label className={target === null ? 'is-selected' : ''}>
                    <input type="radio" name="eagle-move" checked={target === null} onChange={() => setTarget(null)} />
                    <span>(Top level)</span>
                </label>
                {folders.map((folder) => (
                    <label key={folder.id} className={target === folder.id ? 'is-selected' : ''}>
                        <input type="radio" name="eagle-move" checked={target === folder.id} onChange={() => setTarget(folder.id)} />
                        <Folder size={14} aria-hidden="true" />
                        <span>{folder.path}</span>
                    </label>
                ))}
            </div>
        </Dialog>
    )
}
