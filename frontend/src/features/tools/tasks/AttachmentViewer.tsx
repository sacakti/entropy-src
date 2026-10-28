import { useEffect, useRef, useState, type MouseEvent as ReactMouseEvent } from 'react'
import { ChevronLeft, ChevronRight, Download, Highlighter, LoaderCircle, WrapText, X } from 'lucide-react'

import AppPortal from '../../../components/layout/AppPortal'
import ImageMarkup from './ImageMarkup'
import { formatSize, previewKind, tasksApi, type Attachment, type PreviewKind } from './model'

// Larger text files are cut so the browser stays responsive; download them instead.
const TEXT_LIMIT = 2 * 1024 * 1024

// Uploads may arrive without a usable content type; the viewer needs one.
function blobType(kind: PreviewKind, attachment: Attachment, received: string) {
    if (kind === 'pdf') return 'application/pdf'
    if (kind === 'image' && /\.svg$/i.test(attachment.filename)) return 'image/svg+xml'
    if (kind === 'image' && !received.startsWith('image/')) return `image/${attachment.filename.split('.').pop()?.toLowerCase().replace('jpg', 'jpeg')}`
    return received
}

type Loaded = { id: number; source?: string; text?: string; truncated?: boolean; error?: string }

export default function AttachmentViewer({ taskId, attachments, initial, onClose, onAttach, onReplace, canReplace, onRename }: {
    taskId: number
    attachments: Attachment[]
    initial: number
    onClose: () => void
    // Given when the user may attach files: images can then be marked up.
    onAttach?: (file: File) => Promise<boolean>
    // Given for attachments the user may remove; resolves to the new attachment's id.
    onReplace?: (attachment: Attachment, file: File) => Promise<number | null>
    // The same people who may replace an attachment may rename it.
    canReplace?: (attachment: Attachment) => boolean
    onRename?: (attachment: Attachment, name: string) => Promise<boolean>
}) {
    const items = attachments.filter((attachment) => previewKind(attachment))
    // Followed by id: replacing an image removes it from the list.
    const [currentId, setCurrentId] = useState(initial)
    const found = items.findIndex((attachment) => attachment.id === currentId)
    const index = Math.max(0, found)
    const step = (offset: number) => {
        const next = items[Math.min(items.length - 1, Math.max(0, index + offset))]
        if (next) setCurrentId(next.id)
    }
    const stepRef = useRef(step)
    useEffect(() => {
        stepRef.current = step
    })
    const [loaded, setLoaded] = useState<Loaded | null>(null)
    const [wrap, setWrap] = useState(true)
    const [marking, setMarking] = useState(false)
    const [renaming, setRenaming] = useState(false)
    const markingRef = useRef(marking)
    useEffect(() => {
        markingRef.current = marking
    }, [marking])
    const current = items[index]
    const kind = current ? previewKind(current) : null
    const url = current ? tasksApi.attachmentUrl(taskId, current.id) : ''

    useEffect(() => {
        if (!current || !kind) return
        const controller = new AbortController()
        let source: string | undefined
        void (async () => {
            try {
                const response = await fetch(url, { credentials: 'same-origin', cache: 'no-store', signal: controller.signal })
                if (!response.ok) throw new Error(response.status === 404 ? 'The attachment file is missing.' : `Unable to load the file (${response.status}).`)
                const blob = await response.blob()
                if (kind === 'text') {
                    const truncated = blob.size > TEXT_LIMIT
                    setLoaded({ id: current.id, text: await blob.slice(0, TEXT_LIMIT).text(), truncated })
                } else {
                    source = URL.createObjectURL(new Blob([blob], { type: blobType(kind, current, blob.type) }))
                    setLoaded({ id: current.id, source })
                }
            } catch (cause) {
                if (!controller.signal.aborted) setLoaded({ id: current.id, error: cause instanceof Error ? cause.message : 'Unable to load the file.' })
            }
        })()
        return () => {
            controller.abort()
            if (source) URL.revokeObjectURL(source)
        }
    }, [current, kind, url])

    useEffect(() => {
        const onKey = (event: KeyboardEvent) => {
            // A confirm dialog above the viewer handles its own keys.
            if (document.querySelector('.entropy-modal-backdrop, .entropy-dialog-backdrop')) return
            // The rename field handles its own Enter and Esc.
            if (event.target instanceof HTMLInputElement) return
            // While marking up, Esc leaves the markup and arrows stay on this image.
            if (event.key === 'Escape') {
                if (markingRef.current) setMarking(false)
                else onClose()
            } else if (markingRef.current) return
            else if (event.key === 'ArrowLeft') stepRef.current(-1)
            else if (event.key === 'ArrowRight') stepRef.current(1)
        }
        document.addEventListener('keydown', onKey)
        return () => document.removeEventListener('keydown', onKey)
    }, [onClose])

    if (!current) return null
    const ready = loaded?.id === current.id ? loaded : null
    const canRename = Boolean(onRename) && (canReplace?.(current) ?? true) && !marking
    const startRename = (event: ReactMouseEvent) => {
        if (!canRename) return
        event.preventDefault()
        setRenaming(true)
    }

    return (
        <AppPortal>
            <div className="task-viewer" role="dialog" aria-modal="true" aria-label={`Attachment: ${current.filename}`} onClick={() => !marking && onClose()}>
                <div className="task-viewer-frame" onClick={(event) => event.stopPropagation()}>
                    <header>
                        <span className="task-viewer-title" onContextMenu={startRename}>
                            {renaming && onRename ? (
                                <input
                                    className="task-input task-attachment-rename"
                                    defaultValue={current.filename}
                                    maxLength={255}
                                    autoFocus
                                    aria-label={`Rename ${current.filename}`}
                                    onFocus={(event) => {
                                        const dot = current.filename.lastIndexOf('.')
                                        event.currentTarget.setSelectionRange(0, dot > 0 ? dot : current.filename.length)
                                    }}
                                    onKeyDown={(event) => {
                                        if (event.key === 'Enter') event.currentTarget.blur()
                                        if (event.key === 'Escape') {
                                            event.currentTarget.value = current.filename
                                            event.currentTarget.blur()
                                        }
                                    }}
                                    onBlur={(event) => {
                                        setRenaming(false)
                                        void onRename(current, event.currentTarget.value)
                                    }}
                                />
                            ) : (
                                <strong title={canRename ? `${current.filename} · right-click to rename` : current.filename}>{current.filename}</strong>
                            )}
                            <small>{[formatSize(current.size_bytes), current.uploaded_by].filter(Boolean).join(' · ')}{items.length > 1 ? ` · ${index + 1} of ${items.length}` : ''}</small>
                        </span>
                        {kind === 'image' && onAttach && ready?.source && !marking && (
                            <button type="button" className="entropy-button entropy-button-secondary entropy-button-sm" onClick={() => setMarking(true)} title="Circle, box, draw or point at parts of the image">
                                <Highlighter size={15} /> Mark up
                            </button>
                        )}
                        {kind === 'text' && (
                            <button type="button" className={`entropy-button entropy-button-ghost entropy-button-icon entropy-button-sm${wrap ? ' is-active' : ''}`} onClick={() => setWrap(!wrap)} aria-label="Wrap long lines" title="Wrap long lines">
                                <WrapText size={15} />
                            </button>
                        )}
                        <a className="entropy-button entropy-button-ghost entropy-button-icon entropy-button-sm" href={url} download={current.filename} aria-label={`Download ${current.filename}`} title="Download">
                            <Download size={15} />
                        </a>
                        <button type="button" className="entropy-button entropy-button-ghost entropy-button-icon entropy-button-sm" onClick={onClose} aria-label="Close viewer" title="Close (Esc)">
                            <X size={16} />
                        </button>
                    </header>
                    <div className={`task-viewer-body is-${kind}`}>
                        {!ready ? (
                            <LoaderCircle size={22} className="entropy-spin" aria-label="Loading" />
                        ) : ready.error ? (
                            <p className="task-muted">{ready.error}</p>
                        ) : kind === 'image' && marking && onAttach && ready.source ? (
                            <ImageMarkup source={ready.source} filename={current.filename} onCancel={() => setMarking(false)} onSave={onAttach}
                                onReplace={onReplace && (canReplace?.(current) ?? true) ? (async (file) => {
                                    const replaced = await onReplace(current, file)
                                    if (replaced !== null) setCurrentId(replaced)
                                    return replaced !== null
                                }) : undefined} />
                        ) : kind === 'image' ? (
                            <img src={ready.source} alt={current.filename} onContextMenu={startRename} title={canRename ? 'Right-click to rename' : undefined} />
                        ) : kind === 'pdf' ? (
                            <iframe src={ready.source} title={current.filename} />
                        ) : (
                            <>
                                {ready.truncated && <p className="task-viewer-note">Showing the first {formatSize(TEXT_LIMIT)}. Download the file to see all of it.</p>}
                                <pre className={wrap ? 'is-wrapped' : ''}>{ready.text || '(empty file)'}</pre>
                            </>
                        )}
                    </div>
                    {items.length > 1 && !marking && (
                        <>
                            <button type="button" className="entropy-button entropy-button-secondary entropy-button-icon task-viewer-nav is-previous" onClick={() => step(-1)} disabled={index === 0} aria-label="Previous attachment">
                                <ChevronLeft size={18} />
                            </button>
                            <button type="button" className="entropy-button entropy-button-secondary entropy-button-icon task-viewer-nav is-next" onClick={() => step(1)} disabled={index === items.length - 1} aria-label="Next attachment">
                                <ChevronRight size={18} />
                            </button>
                        </>
                    )}
                </div>
            </div>
        </AppPortal>
    )
}
