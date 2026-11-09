import { useCallback, useEffect, useMemo, useRef, useState, type KeyboardEvent, type ReactNode } from 'react'
import {
    BookOpen,
    CalendarDays,
    FileDown,
    FileUp,
    GitCommitVertical,
    Check,
    History,
    ImagePlus,
    LoaderCircle,
    MapPin,
    Paperclip,
    Pencil,
    Plus,
    RefreshCw,
    RotateCcw,
    Search,
    Tag,
    Trash2,
    UsersRound,
    X,
} from 'lucide-react'

import {
    knowledgeApi,
    type KnowledgeAttachment,
    type KnowledgeEntry,
    type KnowledgeExportFormat,
    type KnowledgeFilters,
    type KnowledgeList,
    type KnowledgeRevision,
    type KnowledgeValues,
} from '../../../api/knowledge.api'
import { useFeedback } from '../../../components/feedback/FeedbackProvider'
import { PROJECT_CHANGED_EVENT } from '../../../services/project'
import MarkupView from '../tasks/MarkupView'
import RichEditor, { type RichEditorHandle } from '../tasks/RichEditor'
import { formatSize, memberName, type Member } from '../tasks/model'
import type { PlacedAttachment } from '../tasks/richText'
import { entryIdFromHash, openKnowledgeEntry } from './navigation'
import './knowledge.css'

const SEARCH_DELAY_MS = 300
const IMAGE = /\.(png|jpe?g|gif|webp|bmp)$/i

type Mode = { kind: 'view' } | { kind: 'edit' } | { kind: 'new' } | { kind: 'revision'; revision: KnowledgeRevision }

type Draft = Required<Omit<KnowledgeValues, 'happened_time'>> & { happened_time: string }

function today(): string {
    const now = new Date()
    const offset = now.getTimezoneOffset() * 60_000
    return new Date(now.getTime() - offset).toISOString().slice(0, 10)
}

function blankDraft(): Draft {
    return { title: '', body: '', location: '', happened_on: today(), happened_time: '', people: [], tags: [], reference: '' }
}

function draftOf(entry: KnowledgeEntry): Draft {
    return {
        title: entry.title,
        body: entry.body,
        location: entry.location,
        happened_on: entry.happened_on,
        happened_time: entry.happened_time ?? '',
        people: [...entry.people],
        tags: [...entry.tags],
        reference: entry.reference,
    }
}

function isImage(attachment: KnowledgeAttachment): boolean {
    return (attachment.content_type ?? '').startsWith('image/') || IMAGE.test(attachment.filename)
}

function longDate(day: string, time: string | null): string {
    const parsed = new Date(`${day}T${time || '00:00'}`)
    if (Number.isNaN(parsed.getTime())) return day
    const date = parsed.toLocaleDateString(undefined, { weekday: 'short', day: 'numeric', month: 'short', year: 'numeric' })
    return time ? `${date}, ${time}` : date
}

const EXPORTS: { format: KnowledgeExportFormat; label: string }[] = [
    { format: 'pdf', label: 'PDF' },
    { format: 'html', label: 'HTML' },
    { format: 'docx', label: 'Word (.docx)' },
]

/** The server's file name for an export, so the download is named alike. */
function exportName(title: string, version: number | string, format: KnowledgeExportFormat): string {
    const stem =
        title
            .replace(/[^A-Za-z0-9_-]+/g, '-')
            .split('-')
            .filter(Boolean)
            .join('-')
            .slice(0, 80) || 'entry'
    return `${stem}-v${version}.${format}`
}

/** Download as PDF, HTML or Word: a menu that acts when a format is picked. */
function ExportMenu({ onExport, busy }: { onExport: (format: KnowledgeExportFormat) => void; busy: boolean }) {
    return (
        <label className="kb-export" title="Download this version as a file">
            {busy ? <LoaderCircle size={14} className="entropy-spin" /> : <FileDown size={14} />}
            <select
                className="entropy-select"
                value=""
                disabled={busy}
                onChange={(event) => {
                    if (event.target.value) onExport(event.target.value as KnowledgeExportFormat)
                }}
                aria-label="Export"
            >
                <option value="">Export…</option>
                {EXPORTS.map((item) => (
                    <option key={item.format} value={item.format}>
                        {item.label}
                    </option>
                ))}
            </select>
        </label>
    )
}

function messageOf(cause: unknown, fallback: string): string {
    return cause instanceof Error ? cause.message : fallback
}

/** Words typed one by one, each kept as a chip (Enter, comma or Tab adds one). */
function ChipInput({ label, icon, values, onChange, suggestions, display, placeholder, listId }: {
    label: string
    icon: ReactNode
    values: string[]
    onChange: (values: string[]) => void
    suggestions: { value: string; label: string }[]
    display?: (value: string) => string
    placeholder: string
    listId: string
}) {
    const [text, setText] = useState('')
    const add = (raw: string) => {
        const value = raw.trim()
        if (!value) return
        const match = suggestions.find((item) => item.value.toLowerCase() === value.toLowerCase() || item.label.toLowerCase() === value.toLowerCase())
        const chosen = match?.value ?? value
        if (!values.some((item) => item.toLowerCase() === chosen.toLowerCase())) onChange([...values, chosen])
        setText('')
    }
    const onKeyDown = (event: KeyboardEvent<HTMLInputElement>) => {
        if (event.key === 'Enter' || event.key === ',' || (event.key === 'Tab' && text.trim())) {
            event.preventDefault()
            add(text)
        } else if (event.key === 'Backspace' && !text && values.length) {
            onChange(values.slice(0, -1))
        }
    }
    return (
        <div className="kb-field">
            <span className="kb-field-label">{icon} {label}</span>
            <div className="kb-chips-input">
                {values.map((value) => (
                    <span key={value} className="kb-chip">
                        {display ? display(value) : value}
                        <button type="button" aria-label={`Remove ${value}`} onClick={() => onChange(values.filter((item) => item !== value))}>
                            <X size={12} />
                        </button>
                    </span>
                ))}
                <input
                    value={text}
                    list={listId}
                    placeholder={values.length ? '' : placeholder}
                    onChange={(event) => {
                        // Picking from the list fills the whole value: add it at once.
                        const next = event.target.value
                        if (suggestions.some((item) => item.value === next)) add(next)
                        else setText(next)
                    }}
                    onKeyDown={onKeyDown}
                    onBlur={() => add(text)}
                    aria-label={label}
                />
                <datalist id={listId}>
                    {suggestions
                        .filter((item) => !values.includes(item.value))
                        .map((item) => (
                            <option key={item.value} value={item.value}>
                                {item.label}
                            </option>
                        ))}
                </datalist>
            </div>
        </div>
    )
}

/**
 * The project's knowledge base: what was done, where, when, how and by whom, written
 * like a note (the task description editor), with screenshots and files in place, every
 * earlier version kept, and found again by words, tags, place, people and dates.
 */
export default function KnowledgeBase() {
    const { notify } = useFeedback()
    const [data, setData] = useState<KnowledgeList | null>(null)
    const [loading, setLoading] = useState(true)
    const [filters, setFilters] = useState<KnowledgeFilters>({})
    const [query, setQuery] = useState('')
    const [selectedId, setSelectedId] = useState<number | null>(() => entryIdFromHash(window.location.hash))
    const [entry, setEntry] = useState<KnowledgeEntry | null>(null)
    const [mode, setMode] = useState<Mode>({ kind: 'view' })
    const [draft, setDraft] = useState<Draft>(blankDraft)
    const latestBody = useRef('')
    const [editorKey, setEditorKey] = useState(0)
    const [busy, setBusy] = useState<'save' | 'upload' | 'delete' | 'export' | 'import' | 'restore' | null>(null)
    const editor = useRef<RichEditorHandle>(null)
    const importInput = useRef<HTMLInputElement>(null)

    const members: Member[] = useMemo(() => data?.members ?? [], [data])
    const canWrite = Boolean(data?.permissions['knowledge.write'])
    const canDelete = Boolean(data?.permissions['knowledge.delete'])
    const personName = useCallback((name: string) => memberName(members, name), [members])

    const load = useCallback(
        async (next: KnowledgeFilters) => {
            setLoading(true)
            try {
                setData(await knowledgeApi.list(next))
            } catch (cause) {
                notify.error(messageOf(cause, 'Unable to load the knowledge base.'), { title: 'Knowledge base' })
            } finally {
                setLoading(false)
            }
        },
        [notify],
    )

    // Typing searches after a pause; the other filters at once.
    useEffect(() => {
        const timer = window.setTimeout(() => void load({ ...filters, q: query.trim() || undefined }), query ? SEARCH_DELAY_MS : 0)
        return () => window.clearTimeout(timer)
    }, [filters, query, load])

    useEffect(() => {
        const reload = () => {
            setSelectedId(null)
            setEntry(null)
            setMode({ kind: 'view' })
            void load({})
        }
        const follow = () => {
            const id = entryIdFromHash(window.location.hash)
            if (id !== null) {
                setSelectedId(id)
                setMode({ kind: 'view' })
            }
        }
        window.addEventListener(PROJECT_CHANGED_EVENT, reload)
        window.addEventListener('popstate', follow)
        return () => {
            window.removeEventListener(PROJECT_CHANGED_EVENT, reload)
            window.removeEventListener('popstate', follow)
        }
    }, [load])

    useEffect(() => {
        if (selectedId === null) return
        let active = true
        knowledgeApi
            .get(selectedId)
            .then((found) => {
                if (active) setEntry(found)
            })
            .catch((cause: unknown) => {
                if (!active) return
                setEntry(null)
                notify.error(messageOf(cause, 'Unable to open the entry.'), { title: 'Knowledge base' })
            })
        return () => {
            active = false
        }
    }, [selectedId, notify])

    const open = (id: number) => {
        if (mode.kind === 'edit' || mode.kind === 'new') {
            if (!window.confirm('Leave without saving your changes?')) return
        }
        setMode({ kind: 'view' })
        openKnowledgeEntry(id)
    }

    const startNew = () => {
        setEntry(null)
        setSelectedId(null)
        const fresh = blankDraft()
        latestBody.current = ''
        setDraft(fresh)
        setEditorKey((key) => key + 1)
        setMode({ kind: 'new' })
    }

    const startEdit = () => {
        if (!entry) return
        latestBody.current = entry.body
        setDraft(draftOf(entry))
        setEditorKey((key) => key + 1)
        setMode({ kind: 'edit' })
    }

    const values = (): KnowledgeValues => ({
        ...draft,
        body: latestBody.current,
        happened_time: draft.happened_time || null,
    })

    /** Save; a new entry is created (so files can be attached to it). */
    const persist = async (): Promise<KnowledgeEntry | null> => {
        if (!draft.title.trim()) {
            notify.error('Say what was done: give the entry a title.', { title: 'Knowledge base' })
            return null
        }
        const saved = mode.kind === 'new' || !entry ? await knowledgeApi.create(values()) : await knowledgeApi.update(entry.id, values())
        setEntry(saved)
        setSelectedId(saved.id)
        if (mode.kind === 'new') {
            window.history.replaceState(null, '', `#/tools/knowledge?entry=${saved.id}`)
            setMode({ kind: 'edit' })
        }
        return saved
    }

    const save = async () => {
        setBusy('save')
        try {
            const saved = await persist()
            if (!saved) return
            setMode({ kind: 'view' })
            notify.success(`"${saved.title}" saved.`)
            void load({ ...filters, q: query.trim() || undefined })
        } catch (cause) {
            notify.error(messageOf(cause, 'Unable to save the entry.'), { title: 'Knowledge base' })
        } finally {
            setBusy(null)
        }
    }

    const remove = async () => {
        if (!entry || !window.confirm(`Delete "${entry.title}" and its attachments? Its history goes too.`)) return
        setBusy('delete')
        try {
            await knowledgeApi.remove(entry.id)
            notify.success(`"${entry.title}" deleted.`)
            setEntry(null)
            setSelectedId(null)
            setMode({ kind: 'view' })
            window.history.replaceState(null, '', '#/tools/knowledge')
            void load({ ...filters, q: query.trim() || undefined })
        } catch (cause) {
            notify.error(messageOf(cause, 'Unable to delete the entry.'), { title: 'Knowledge base' })
        } finally {
            setBusy(null)
        }
    }

    /** Pasted or chosen files: kept with the entry (saved first if it is new). */
    const attach = async (files: File[]) => {
        setBusy('upload')
        try {
            const target = mode.kind === 'new' || !entry ? await persist() : entry
            if (!target) return []
            const { entry: updated, added } = await knowledgeApi.attach(target.id, files)
            setEntry(updated)
            return added.map((item) => ({
                id: item.id,
                caption: item.filename,
                placed: { src: isImage(item) ? knowledgeApi.attachmentUrl(target.id, item.id) : null, label: item.filename },
            }))
        } catch (cause) {
            notify.error(messageOf(cause, 'Unable to attach the files.'), { title: 'Knowledge base' })
            return []
        } finally {
            setBusy(null)
        }
    }

    const detach = async (attachment: KnowledgeAttachment) => {
        if (!entry || !window.confirm(`Remove ${attachment.filename}?`)) return
        try {
            await knowledgeApi.detach(entry.id, attachment.id)
            setEntry(await knowledgeApi.get(entry.id))
        } catch (cause) {
            notify.error(messageOf(cause, 'Unable to remove the file.'), { title: 'Knowledge base' })
        }
    }

    const exportEntry = async (format: KnowledgeExportFormat, revision?: KnowledgeRevision) => {
        if (!entry) return
        setBusy('export')
        try {
            const version = revision ? revision.version ?? 'earlier' : entry.version
            await knowledgeApi.export(entry.id, format, exportName(revision?.title ?? entry.title, version, format), revision?.id)
        } catch (cause) {
            notify.error(messageOf(cause, 'Unable to export the entry.'), { title: 'Knowledge base' })
        } finally {
            setBusy(null)
        }
    }

    const restore = async (revision: KnowledgeRevision) => {
        if (!entry) return
        const label = revision.version ? `version ${revision.version}` : 'this version'
        if (!window.confirm(`Restore ${label}? It is saved as version ${entry.version + 1}; the current version stays in the history.`)) return
        setBusy('restore')
        try {
            const restored = await knowledgeApi.restore(entry.id, revision.id)
            setEntry(restored)
            setMode({ kind: 'view' })
            notify.success(`Restored as version ${restored.version}.`)
            void load({ ...filters, q: query.trim() || undefined })
        } catch (cause) {
            notify.error(messageOf(cause, 'Unable to restore that version.'), { title: 'Knowledge base' })
        } finally {
            setBusy(null)
        }
    }

    const importFile = async (file: File) => {
        setBusy('import')
        try {
            const created = await knowledgeApi.importFile(file)
            notify.success(`Imported "${created.title}". Review it, then edit what needs changing.`)
            void load({ ...filters, q: query.trim() || undefined })
            setMode({ kind: 'view' })
            openKnowledgeEntry(created.id)
        } catch (cause) {
            notify.error(messageOf(cause, 'Unable to import the file.'), { title: 'Knowledge base' })
        } finally {
            setBusy(null)
            if (importInput.current) importInput.current.value = ''
        }
    }

    const showRevision = async (revisionId: number) => {
        if (!entry) return
        try {
            setMode({ kind: 'revision', revision: await knowledgeApi.revision(entry.id, revisionId) })
        } catch (cause) {
            notify.error(messageOf(cause, 'Unable to open that version.'), { title: 'Knowledge base' })
        }
    }

    // How an attachment looks in the text: the image itself, or the file's name.
    const placed = (target: KnowledgeEntry | null) => (id: number, caption: string): PlacedAttachment => {
        const attachment = target?.attachments.find((item) => item.id === id)
        const label = caption || attachment?.filename || 'attachment'
        if (!attachment || !target) return { src: null, label: `${label} (removed)` }
        return { src: isImage(attachment) ? knowledgeApi.attachmentUrl(target.id, id) : null, label }
    }

    const renderAttachment = (target: KnowledgeEntry) => (id: number, caption: string) => {
        const attachment = target.attachments.find((item) => item.id === id)
        const label = caption || attachment?.filename || 'attachment'
        if (!attachment) return <p key={`${id}-${caption}`} className="task-md-p task-muted">[{label} — removed]</p>
        const url = knowledgeApi.attachmentUrl(target.id, id)
        return isImage(attachment) ? (
            <figure key={`${id}-${caption}`} className="task-description-image">
                <a href={url} target="_blank" rel="noreferrer" title={`Open ${attachment.filename}`}>
                    <img src={url} alt={label} loading="lazy" />
                </a>
                <figcaption>{label}</figcaption>
            </figure>
        ) : (
            <a key={`${id}-${caption}`} className="task-description-file" href={url} target="_blank" rel="noreferrer">
                <Paperclip size={13} /> {label}
            </a>
        )
    }

    const set = <K extends keyof Draft>(key: K, value: Draft[K]) => setDraft((current) => ({ ...current, [key]: value }))
    const editing = mode.kind === 'edit' || mode.kind === 'new'
    const facets = data?.facets ?? { tags: [], locations: [], people: [] }
    const peopleChoices = useMemo(() => {
        const choices = members.map((member) => ({ value: member.username, label: member.full_name || member.username }))
        facets.people
            .filter((name) => !members.some((member) => member.username.toLowerCase() === name.toLowerCase()))
            .forEach((name) => choices.push({ value: name, label: name }))
        return choices
    }, [members, facets.people])
    const filtering = Boolean(query || Object.values(filters).some(Boolean))
    const images = entry?.attachments.filter(isImage) ?? []

    // ------------------------------------------------------------------
    // Parts
    // ------------------------------------------------------------------

    const meta = (
        source: Pick<KnowledgeEntry, 'location' | 'happened_on' | 'happened_time' | 'people' | 'tags' | 'reference'>,
        version: number | null,
    ) => (
        <dl className="kb-meta">
            <div>
                <dt><GitCommitVertical size={13} /> Version</dt>
                <dd>{version ?? 'Earlier'}</dd>
            </div>
            <div>
                <dt><MapPin size={13} /> Where</dt>
                <dd>{source.location || <span className="task-muted">—</span>}</dd>
            </div>
            <div>
                <dt><CalendarDays size={13} /> When</dt>
                <dd>{longDate(source.happened_on, source.happened_time)}</dd>
            </div>
            <div>
                <dt><UsersRound size={13} /> Who</dt>
                <dd>{source.people.length ? source.people.map(personName).join(', ') : <span className="task-muted">—</span>}</dd>
            </div>
            {source.reference && (
                <div>
                    <dt><BookOpen size={13} /> Reference</dt>
                    <dd>{source.reference}</dd>
                </div>
            )}
            {source.tags.length > 0 && (
                <div>
                    <dt><Tag size={13} /> Tags</dt>
                    <dd className="kb-tags">
                        {source.tags.map((tag) => (
                            <button key={tag} type="button" className="kb-tag" onClick={() => setFilters((current) => ({ ...current, tag }))} title="Show entries with this tag">
                                {tag}
                            </button>
                        ))}
                    </dd>
                </div>
            )}
        </dl>
    )

    const editorForm = (
        <div className="kb-form">
            <label className="kb-field kb-field-wide">
                <span className="kb-field-label">What was done</span>
                <input
                    className="kb-title-input"
                    value={draft.title}
                    maxLength={200}
                    placeholder="Rotated the Oracle password of APP1 in SIT"
                    onChange={(event) => set('title', event.target.value)}
                    autoFocus={mode.kind === 'new'}
                />
            </label>
            <label className="kb-field">
                <span className="kb-field-label"><MapPin size={13} /> Where</span>
                <input value={draft.location} list="kb-locations" maxLength={120} placeholder="SIT, db-sit-01, Payments…" onChange={(event) => set('location', event.target.value)} />
                <datalist id="kb-locations">
                    {facets.locations.map((location) => <option key={location} value={location} />)}
                </datalist>
            </label>
            <div className="kb-field">
                <span className="kb-field-label"><CalendarDays size={13} /> When</span>
                <span className="kb-when">
                    <input type="date" value={draft.happened_on} onChange={(event) => set('happened_on', event.target.value)} aria-label="Date" />
                    <input type="time" value={draft.happened_time} onChange={(event) => set('happened_time', event.target.value)} aria-label="Time (optional)" />
                </span>
            </div>
            <ChipInput
                label="Who"
                icon={<UsersRound size={13} />}
                values={draft.people}
                onChange={(people) => set('people', people)}
                suggestions={peopleChoices}
                display={personName}
                placeholder="Members, or anyone else by name"
                listId="kb-people"
            />
            <ChipInput
                label="Tags"
                icon={<Tag size={13} />}
                values={draft.tags}
                onChange={(tags) => set('tags', tags.map((tag) => tag.toLowerCase()))}
                suggestions={facets.tags.map((tag) => ({ value: tag, label: tag }))}
                placeholder="oracle, password, outage…"
                listId="kb-tags"
            />
            <label className="kb-field">
                <span className="kb-field-label"><BookOpen size={13} /> Reference</span>
                <input value={draft.reference} maxLength={200} placeholder="CHG-1042, INC0042, a task key…" onChange={(event) => set('reference', event.target.value)} />
            </label>
            <div className="kb-field kb-field-wide">
                <span className="kb-field-label">How</span>
                <RichEditor
                    key={editorKey}
                    // Where it starts; the editor keeps what is typed (latestBody) from there.
                    value={draft.body}
                    onChange={(body) => {
                        latestBody.current = body
                    }}
                    members={members}
                    attachment={placed(entry)}
                    ariaLabel="How it was done"
                    placeholder="Steps, commands, what was checked, what to watch for next time…"
                    minHeight={260}
                    handleRef={editor}
                    onFiles={attach}
                    onSubmitShortcut={() => void save()}
                    tools={
                        <select
                            className="entropy-select task-editor-style"
                            value=""
                            disabled={!images.length}
                            aria-label="Insert an attached image"
                            onChange={(event) => {
                                const attachment = images.find((item) => item.id === Number(event.target.value))
                                if (attachment) editor.current?.insertAttachments([{ id: attachment.id, caption: attachment.filename }])
                            }}
                        >
                            <option value="">{images.length ? 'Insert image…' : 'No images attached'}</option>
                            {images.map((attachment) => <option key={attachment.id} value={attachment.id}>{attachment.filename}</option>)}
                        </select>
                    }
                />
                <small className="task-muted task-description-hint">
                    {busy === 'upload' ? (
                        <><LoaderCircle size={12} className="entropy-spin" /> Attaching…</>
                    ) : (
                        <><ImagePlus size={12} /> Paste a screenshot to place it here · type @ to mention · {mode.kind === 'new' ? 'pasting a file saves the entry first' : '⌘/Ctrl+Enter saves'}</>
                    )}
                </small>
            </div>
            <div className="kb-actions">
                <button type="button" className="entropy-button entropy-button-secondary entropy-button-sm" disabled={busy !== null} onClick={() => setMode({ kind: 'view' })}>
                    <X size={14} /> Cancel
                </button>
                <button type="button" className="entropy-button entropy-button-primary entropy-button-sm" disabled={busy !== null} onClick={() => void save()}>
                    {busy === 'save' ? <LoaderCircle size={14} className="entropy-spin" /> : <Check size={14} />} Save
                </button>
            </div>
        </div>
    )

    const attachmentsList = (target: KnowledgeEntry) =>
        target.attachments.length > 0 && (
            <section className="kb-section">
                <h4><Paperclip size={14} /> Attachments ({target.attachments.length})</h4>
                <ul className="kb-files">
                    {target.attachments.map((attachment) => (
                        <li key={attachment.id}>
                            <a href={knowledgeApi.attachmentUrl(target.id, attachment.id)} target="_blank" rel="noreferrer">{attachment.filename}</a>
                            <small>{formatSize(attachment.size_bytes)} · {personName(attachment.uploaded_by)}</small>
                            {canWrite && (attachment.uploaded_by.toLowerCase() === data?.username.toLowerCase() || canDelete) && (
                                <button type="button" className="entropy-button entropy-button-ghost entropy-button-icon entropy-button-sm" aria-label={`Remove ${attachment.filename}`} onClick={() => void detach(attachment)}>
                                    <Trash2 size={13} />
                                </button>
                            )}
                        </li>
                    ))}
                </ul>
            </section>
        )

    const detail = () => {
        if (editing) return editorForm
        if (mode.kind === 'revision' && entry) {
            const revision = mode.revision
            return (
                <article className="kb-article">
                    <p className="kb-revision-note">
                        <History size={14} /> {revision.version ? `Version ${revision.version}, ` : 'An earlier version, '}saved by{' '}
                        {personName(revision.edited_by)} on {revision.edited_at} UTC.
                        <span className="kb-revision-actions">
                            <ExportMenu busy={busy === 'export'} onExport={(format) => void exportEntry(format, revision)} />
                            {canWrite && (
                                <button type="button" className="entropy-button entropy-button-secondary entropy-button-sm" disabled={busy !== null} onClick={() => void restore(revision)}>
                                    {busy === 'restore' ? <LoaderCircle size={14} className="entropy-spin" /> : <RotateCcw size={14} />} Restore
                                </button>
                            )}
                            <button type="button" className="entropy-button entropy-button-secondary entropy-button-sm" onClick={() => setMode({ kind: 'view' })}>
                                Back to version {entry.version}
                            </button>
                        </span>
                    </p>
                    <h3 className="kb-article-title">{revision.title}</h3>
                    {meta(revision, revision.version)}
                    {revision.body.trim() ? (
                        <MarkupView text={revision.body} members={members} attachment={renderAttachment(entry)} />
                    ) : (
                        <p className="task-muted">No description.</p>
                    )}
                </article>
            )
        }
        if (!entry) {
            return (
                <div className="kb-empty">
                    <BookOpen size={28} />
                    <strong>Keep what was done, so it can be done again</strong>
                    <span>Write down what you did, where and when, who took part and how — steps, commands, screenshots.</span>
                    {canWrite && (
                        <button type="button" className="entropy-button entropy-button-primary" onClick={startNew}>
                            <Plus size={15} /> New entry
                        </button>
                    )}
                </div>
            )
        }
        return (
            <article className="kb-article">
                <header className="kb-article-head">
                    <h3 className="kb-article-title">{entry.title}</h3>
                    <span className="kb-article-tools">
                        <ExportMenu busy={busy === 'export'} onExport={(format) => void exportEntry(format)} />
                        {canWrite && (
                            <button type="button" className="entropy-button entropy-button-secondary entropy-button-sm" onClick={startEdit}>
                                <Pencil size={14} /> Edit
                            </button>
                        )}
                        {canDelete && (
                            <button type="button" className="entropy-button entropy-button-ghost entropy-button-icon entropy-button-sm" aria-label="Delete this entry" title="Delete this entry" disabled={busy !== null} onClick={() => void remove()}>
                                <Trash2 size={14} />
                            </button>
                        )}
                    </span>
                </header>
                {meta(entry, entry.version)}
                <section className="kb-body">
                    {entry.body.trim() ? (
                        <MarkupView text={entry.body} members={members} attachment={renderAttachment(entry)} />
                    ) : (
                        <p className="task-muted">Nothing written on how yet.{canWrite ? ' Choose Edit to add the steps.' : ''}</p>
                    )}
                </section>
                {attachmentsList(entry)}
                <section className="kb-section">
                    <h4><History size={14} /> History</h4>
                    <ul className="kb-history">
                        <li>
                            <strong>Version {entry.version}</strong> (current) · {personName(entry.updated_by)} · {entry.updated_at} UTC
                        </li>
                        {entry.revisions.map((revision) => (
                            <li key={revision.id}>
                                <button type="button" className="tools-db-link" onClick={() => void showRevision(revision.id)}>
                                    {revision.version ? `Version ${revision.version}` : 'Earlier version'}
                                </button>{' '}
                                · {personName(revision.edited_by)} · {revision.edited_at} UTC
                            </li>
                        ))}
                        <li className="task-muted">Written by {personName(entry.created_by)} on {entry.created_at} UTC</li>
                    </ul>
                </section>
            </article>
        )
    }

    return (
        <div className="kb">
            <div className="kb-toolbar">
                <label className="list-search kb-search">
                    <Search size={15} aria-hidden="true" />
                    <input type="search" value={query} placeholder="Search what, where, how, who, tags…" onChange={(event) => setQuery(event.target.value)} aria-label="Search the knowledge base" />
                    {query && (
                        <button type="button" aria-label="Clear search" onClick={() => setQuery('')}>
                            <X size={14} />
                        </button>
                    )}
                </label>
                <select className="entropy-select" value={filters.tag ?? ''} onChange={(event) => setFilters((current) => ({ ...current, tag: event.target.value || undefined }))} aria-label="Filter by tag">
                    <option value="">All tags</option>
                    {facets.tags.map((tag) => <option key={tag} value={tag}>{tag}</option>)}
                </select>
                <select className="entropy-select" value={filters.location ?? ''} onChange={(event) => setFilters((current) => ({ ...current, location: event.target.value || undefined }))} aria-label="Filter by place">
                    <option value="">Everywhere</option>
                    {facets.locations.map((location) => <option key={location} value={location}>{location}</option>)}
                </select>
                <select className="entropy-select" value={filters.person ?? ''} onChange={(event) => setFilters((current) => ({ ...current, person: event.target.value || undefined }))} aria-label="Filter by person">
                    <option value="">Everyone</option>
                    {facets.people.map((person) => <option key={person} value={person}>{personName(person)}</option>)}
                </select>
                <span className="kb-dates">
                    <input type="date" value={filters.start ?? ''} onChange={(event) => setFilters((current) => ({ ...current, start: event.target.value || undefined }))} aria-label="From date" title="From" />
                    <span aria-hidden="true">–</span>
                    <input type="date" value={filters.end ?? ''} onChange={(event) => setFilters((current) => ({ ...current, end: event.target.value || undefined }))} aria-label="To date" title="To" />
                </span>
                {filtering && (
                    <button type="button" className="tools-db-link" onClick={() => { setFilters({}); setQuery('') }}>
                        Clear
                    </button>
                )}
                <span className="kb-toolbar-end">
                    <button type="button" className="entropy-button entropy-button-secondary entropy-button-sm" onClick={() => void load({ ...filters, q: query.trim() || undefined })} aria-label="Refresh" title="Refresh">
                        <RefreshCw size={15} />
                    </button>
                    {canWrite && (
                        <>
                            <input
                                ref={importInput}
                                type="file"
                                accept=".docx,.md,.markdown,application/vnd.openxmlformats-officedocument.wordprocessingml.document,text/markdown"
                                hidden
                                onChange={(event) => {
                                    const file = event.target.files?.[0]
                                    if (file) void importFile(file)
                                }}
                            />
                            <button
                                type="button"
                                className="entropy-button entropy-button-secondary entropy-button-sm"
                                disabled={busy === 'import'}
                                onClick={() => importInput.current?.click()}
                                title="A new entry from a Word (.docx) or Markdown (.md) file"
                            >
                                {busy === 'import' ? <LoaderCircle size={15} className="entropy-spin" /> : <FileUp size={15} />} Import
                            </button>
                            <button type="button" className="entropy-button entropy-button-primary entropy-button-sm" onClick={startNew}>
                                <Plus size={15} /> New entry
                            </button>
                        </>
                    )}
                </span>
            </div>

            <div className="kb-layout">
                <nav className="kb-list" aria-label="Entries">
                    {loading && !data ? (
                        <p className="kb-list-note"><LoaderCircle size={14} className="entropy-spin" /> Loading…</p>
                    ) : !data?.items.length ? (
                        <p className="kb-list-note">{filtering ? 'Nothing matches.' : 'No entries yet.'}</p>
                    ) : (
                        <>
                            <small className="kb-list-note">{data.items.length} {data.items.length === 1 ? 'entry' : 'entries'}</small>
                            <ul>
                                {data.items.map((item) => (
                                    <li key={item.id}>
                                        <button type="button" className={`kb-card${item.id === selectedId && !editing ? ' is-active' : ''}`} onClick={() => open(item.id)}>
                                            <span className="kb-card-when">{longDate(item.happened_on, item.happened_time)}</span>
                                            <strong>{item.title}</strong>
                                            <span className="kb-card-meta">
                                                {item.location && <span><MapPin size={12} /> {item.location}</span>}
                                                {item.people.length > 0 && <span><UsersRound size={12} /> {item.people.map(personName).join(', ')}</span>}
                                                {item.attachment_count > 0 && <span><Paperclip size={12} /> {item.attachment_count}</span>}
                                            </span>
                                            {item.excerpt && <span className="kb-card-excerpt">{item.excerpt}</span>}
                                            {item.tags.length > 0 && (
                                                <span className="kb-tags">
                                                    {item.tags.map((tag) => <span key={tag} className="kb-tag">{tag}</span>)}
                                                </span>
                                            )}
                                        </button>
                                    </li>
                                ))}
                            </ul>
                        </>
                    )}
                </nav>
                <section className="kb-detail">{detail()}</section>
            </div>
        </div>
    )
}
