import { Fragment, useRef, useState, type ClipboardEvent, type ReactNode } from 'react'
import { Check, ImagePlus, LoaderCircle, Paperclip, Pencil, X } from 'lucide-react'

import { MentionText } from './MentionInput'
import {
    attachmentReference,
    attachmentReferencePattern,
    previewKind,
    tasksApi,
    type Attachment,
    type Member,
    type Task,
} from './model'

// `paths or code` inside the text.
function Inline({ text, members }: { text: string; members: Member[] }) {
    return text.split(/(`[^`\n]+`)/g).map((part, index) =>
        /^`[^`\n]+`$/.test(part) ? (
            <code key={index} className="task-inline-code">{part.slice(1, -1)}</code>
        ) : (
            <Fragment key={index}>
                <MentionText text={part} members={members} />
            </Fragment>
        ),
    )
}

function DescriptionView({ task, members, onOpen }: { task: Task; members: Member[]; onOpen: (attachment: Attachment) => void }) {
    const text = task.description
    if (!text.trim()) return <p className="task-description task-muted">No description.</p>
    const byId = new Map(task.attachments.map((attachment) => [attachment.id, attachment]))
    const parts: ReactNode[] = []
    let position = 0
    // Attachments sit on their own lines; drop the line breaks around them.
    const segment = (from: number, to: number) => {
        const piece = text.slice(from, to).replace(from > 0 ? /^\n/ : /^/, '').replace(to < text.length ? /\n$/ : /$/, '')
        if (piece) parts.push(<Inline key={`t${from}`} text={piece} members={members} />)
    }
    for (const match of text.matchAll(attachmentReferencePattern())) {
        const start = match.index ?? 0
        segment(position, start)
        const attachment = byId.get(Number(match[2]))
        const caption = match[1] || attachment?.filename || 'attachment'
        if (!attachment) {
            parts.push(<span key={`m${start}`} className="task-muted">[{caption} — removed]</span>)
        } else if (previewKind(attachment) === 'image') {
            parts.push(
                <figure key={`a${start}`} className="task-description-image">
                    <button type="button" onClick={() => onOpen(attachment)} title={`View ${attachment.filename}`}>
                        <img src={tasksApi.attachmentUrl(task.id, attachment.id)} alt={caption} loading="lazy" />
                    </button>
                    <figcaption>{caption}</figcaption>
                </figure>,
            )
        } else {
            parts.push(
                <button key={`a${start}`} type="button" className="task-description-file" onClick={() => previewKind(attachment) && onOpen(attachment)} disabled={!previewKind(attachment)}>
                    <Paperclip size={13} /> {caption}
                </button>,
            )
        }
        position = start + match[0].length
    }
    segment(position, text.length)
    return <div className="task-description">{parts}</div>
}

/**
 * The task description: text with `paths` as code and attachments shown in
 * place. Editors insert attachments from the list or paste a screenshot.
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
                <DescriptionView task={task} members={members} onOpen={onOpen} />
            </section>
        )
    }

    return (
        <section className="task-description-block is-editing">
            <h4>Description</h4>
            <div className="task-description-tools">
                <select className="entropy-select" value="" onChange={(event) => {
                    const attachment = images.find((item) => item.id === Number(event.target.value))
                    if (attachment) insert([attachment], draft)
                }} disabled={!images.length} aria-label="Insert an attached image">
                    <option value="">{images.length ? 'Insert image…' : 'No images attached'}</option>
                    {images.map((attachment) => <option key={attachment.id} value={attachment.id}>{attachment.filename}</option>)}
                </select>
                <small className="task-muted">
                    {busy === 'upload' ? <><LoaderCircle size={12} className="entropy-spin" /> Attaching…</> : <><ImagePlus size={12} /> Paste a screenshot to place it here · `/path/or/code` shows as code</>}
                </small>
            </div>
            <textarea
                className="task-input"
                ref={area}
                value={draft}
                rows={8}
                autoFocus
                onChange={(event) => setDraft(event.target.value)}
                onPaste={(event) => void paste(event)}
                onKeyDown={(event) => {
                    if (event.key === 'Escape') setDraft(null)
                    if (event.key === 'Enter' && (event.metaKey || event.ctrlKey)) void save()
                }}
                aria-label="Description"
            />
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
