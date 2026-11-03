import { useRef, useState, type ClipboardEvent } from 'react'
import { Check, ImagePlus, LoaderCircle, Paperclip, Pencil, X } from 'lucide-react'

import MarkupEditor from './MarkupEditor'
import MarkupView from './MarkupView'
import { toggleCheckbox } from './markupEdit'
import {
    attachmentReference,
    previewKind,
    tasksApi,
    type Attachment,
    type Member,
    type Task,
} from './model'

/** An attachment placed in the text: the image itself, or a button that opens the file. */
function PlacedAttachment({ task, id, caption, onOpen }: {
    task: Task
    id: number
    caption: string
    onOpen: (attachment: Attachment) => void
}) {
    const attachment = task.attachments.find((item) => item.id === id)
    const label = caption || attachment?.filename || 'attachment'
    if (!attachment) return <p className="task-md-p task-muted">[{label} — removed]</p>
    if (previewKind(attachment) === 'image') {
        return (
            <figure className="task-description-image">
                <button type="button" onClick={() => onOpen(attachment)} title={`View ${attachment.filename}`}>
                    <img src={tasksApi.attachmentUrl(task.id, attachment.id)} alt={label} loading="lazy" />
                </button>
                <figcaption>{label}</figcaption>
            </figure>
        )
    }
    return (
        <button type="button" className="task-description-file" onClick={() => previewKind(attachment) && onOpen(attachment)} disabled={!previewKind(attachment)}>
            <Paperclip size={13} /> {label}
        </button>
    )
}

/**
 * The task description: formatted text with attachments shown in place. Editors
 * format it from the toolbar, insert attachments or paste a screenshot, and can
 * tick its checklists without opening the editor.
 */
export default function Description({ task, members, editable, onSave, onAttach, onOpen }: {
    task: Task
    members: Member[]
    editable: boolean
    onSave: (description: string) => Promise<boolean>
    // Uploads pasted files and resolves to the attachments created.
    onAttach: (files: File[]) => Promise<Attachment[]>
    onOpen: (attachment: Attachment) => void
}) {
    const [draft, setDraft] = useState<string | null>(null)
    const [busy, setBusy] = useState<'save' | 'upload' | null>(null)
    const area = useRef<HTMLTextAreaElement>(null)
    const images = task.attachments.filter((attachment) => previewKind(attachment) === 'image')

    const placed = (id: number, caption: string) => (
        <PlacedAttachment key={`${id}-${caption}`} task={task} id={id} caption={caption} onOpen={onOpen} />
    )

    const tick = async (line: number) => {
        setBusy('save')
        try {
            await onSave(toggleCheckbox(task.description, line))
        } finally {
            setBusy(null)
        }
    }

    // Each attachment goes on its own line, where the cursor is.
    const insert = (attachments: Attachment[], value: string) => {
        if (!attachments.length) return
        const element = area.current
        const start = element?.selectionStart ?? value.length
        const end = element?.selectionEnd ?? value.length
        const before = value.slice(0, start)
        const block = attachments.map(attachmentReference).join('\n')
        const text = `${before && !before.endsWith('\n') ? '\n' : ''}${block}\n`
        setDraft(before + text + value.slice(end))
        const caret = start + text.length
        window.requestAnimationFrame(() => {
            area.current?.focus()
            area.current?.setSelectionRange(caret, caret)
        })
    }

    const paste = async (event: ClipboardEvent<HTMLTextAreaElement>) => {
        const files = Array.from(event.clipboardData.files)
        if (!files.length || draft === null) return
        // Handled here, so the task-wide paste does not attach them again.
        event.preventDefault()
        const value = draft
        setBusy('upload')
        try {
            insert(await onAttach(files), value)
        } finally {
            setBusy(null)
        }
    }

    const save = async () => {
        if (draft === null) return
        setBusy('save')
        try {
            if (draft === task.description || (await onSave(draft))) setDraft(null)
        } finally {
            setBusy(null)
        }
    }

    if (draft === null) {
        return (
            <section className="task-description-block">
                <h4>
                    Description
                    {editable && (
                        <button type="button" className="entropy-button entropy-button-ghost entropy-button-sm" onClick={() => setDraft(task.description)}>
                            <Pencil size={14} /> Edit
                        </button>
                    )}
                </h4>
                {task.description.trim() ? (
                    <MarkupView
                        text={task.description}
                        members={members}
                        attachment={placed}
                        onToggle={editable && busy === null ? (line) => void tick(line) : undefined}
                    />
                ) : (
                    <p className="task-description task-muted">No description.</p>
                )}
            </section>
        )
    }

    return (
        <section className="task-description-block is-editing">
            <h4>Description</h4>
            <MarkupEditor
                value={draft}
                onChange={setDraft}
                members={members}
                rows={10}
                ariaLabel="Description"
                autoFocus
                inputRef={area}
                attachment={placed}
                onPaste={(event) => void paste(event)}
                onSubmitShortcut={() => void save()}
                onCancel={() => setDraft(null)}
                tools={
                    <select className="entropy-select task-editor-style" value="" onChange={(event) => {
                        const attachment = images.find((item) => item.id === Number(event.target.value))
                        if (attachment) insert([attachment], draft)
                    }} disabled={!images.length} aria-label="Insert an attached image">
                        <option value="">{images.length ? 'Insert image…' : 'No images attached'}</option>
                        {images.map((attachment) => <option key={attachment.id} value={attachment.id}>{attachment.filename}</option>)}
                    </select>
                }
            />
            <small className="task-muted task-description-hint">
                {busy === 'upload' ? <><LoaderCircle size={12} className="entropy-spin" /> Attaching…</> : <><ImagePlus size={12} /> Paste a screenshot to place it here · Tab moves between table cells · Enter continues a list</>}
            </small>
            <div className="task-description-actions">
                <button type="button" className="entropy-button entropy-button-secondary entropy-button-sm" onClick={() => setDraft(null)} disabled={busy !== null}>
                    <X size={14} /> Cancel
                </button>
                <button type="button" className="entropy-button entropy-button-primary entropy-button-sm" onClick={() => void save()} disabled={busy !== null} title="Save (Ctrl+Enter / ⌘Enter)">
                    {busy === 'save' ? <LoaderCircle size={14} className="entropy-spin" /> : <Check size={14} />} Save
                </button>
            </div>
        </section>
    )
}
