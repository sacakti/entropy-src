import { useEffect, useRef, useState, type DragEvent, type FormEvent, type ReactNode } from 'react'
import {
    Bell,
    Check,
    Download,
    ExternalLink,
    FileUp,
    Hand,
    History,
    Link2,
    LoaderCircle,
    Maximize2,
    MessageSquare,
    Minimize2,
    Paperclip,
    Plus,
    Send,
    Trash2,
    Upload,
    X,
} from 'lucide-react'

import { useFeedback } from '../../../components/feedback/FeedbackProvider'
import AppPortal from '../../../components/layout/AppPortal'
import AttachmentViewer from './AttachmentViewer'
import Description from './Description'
import MentionInput, { MentionText } from './MentionInput'
import TypeIcon from './TypeIcon'
import { useStatusChange } from './statusChange'
import {
    GROUP_KINDS,
    SEVERITIES,
    STATUSES,
    formatSize,
    previewKind,
    isOverdue,
    localDate,
    nextStatuses,
    statusTitle,
    reminderInput,
    reminderValue,
    reportUrl,
    tasksApi,
    typeLabel,
    type Attachment,
    type Group,
    type GroupKind,
    type ReportScope,
    type Severity,
    type Status,
    type Task,
    type TaskData,
} from './model'

const errorText = (cause: unknown) => (cause instanceof Error ? cause.message : 'Something went wrong.')

const carriesFiles = (event: DragEvent) => event.dataTransfer.types.includes('Files')

// Browsers name pasted screenshots "image.png"; give them a readable, dated name.
const pastedFile = (file: File, index: number) => {
    if (!/^image\.\w+$/i.test(file.name)) return file
    const stamp = new Date().toISOString().slice(0, 19).replace('T', '-').replace(/:/g, '')
    const extension = file.name.split('.').pop()
    return new File([file], `screenshot-${stamp}${index ? `-${index + 1}` : ''}.${extension}`, { type: file.type })
}

function Panel({ title, eyebrow, onClose, children, actions, popup, onDock }: {
    title: ReactNode
    eyebrow?: ReactNode
    onClose: () => void
    children: ReactNode
    actions?: ReactNode
    // Shown over the page instead of beside the tasks; clicking outside docks it again.
    popup?: boolean
    onDock?: () => void
}) {
    const panel = (
        <aside className={`task-panel${popup ? ' is-popup' : ''}`} aria-label={typeof title === 'string' ? title : 'Task'} onClick={popup ? (event) => event.stopPropagation() : undefined}>
            <header className="task-panel-head">
                <div>
                    {eyebrow && <span className="task-eyebrow">{eyebrow}</span>}
                    <h3>{title}</h3>
                </div>
                <div className="task-panel-actions">
                    {actions}
                    <button type="button" className="entropy-button entropy-button-ghost entropy-button-icon entropy-button-sm" onClick={onClose} aria-label="Close panel">
                        <X size={16} />
                    </button>
                </div>
            </header>
            <div className="task-panel-body">{children}</div>
        </aside>
    )
    if (!popup) return panel
    return (
        <AppPortal>
            <div className="task-popup" role="dialog" aria-modal="true" onClick={onDock}>
                {panel}
            </div>
        </AppPortal>
    )
}

function MemberOptions({ data }: { data: TaskData }) {
    const members = data.members.some((member) => member.username === data.username)
        ? data.members
        : [{ username: data.username, full_name: null }, ...data.members]
    return (
        <>
            <option value="">Unassigned</option>
            {members.map((member) => (
                <option key={member.username} value={member.username}>
                    {member.username === data.username ? `Me (${member.username})` : member.full_name ? `${member.full_name} (${member.username})` : member.username}
                </option>
            ))}
        </>
    )
}

function TypeOptions({ types }: { types: string[] }) {
    return (
        <>
            {types.map((type) => (
                <option key={type} value={type}>
                    {typeLabel(type)}
                </option>
            ))}
        </>
    )
}

/** Group chips with remove buttons and a select to add one. */
function GroupPicker({ groups, value, onChange, disabled }: {
    groups: Group[]
    value: number[]
    onChange: (ids: number[]) => void
    disabled?: boolean
}) {
    const chosen = groups.filter((group) => value.includes(group.id))
    const rest = groups.filter((group) => !value.includes(group.id))
    return (
        <div className="task-groups-picker">
            {chosen.map((group) => (
                <span key={group.id} className={`task-group-chip kind-${group.kind}`}>
                    {group.name}
                    {!disabled && (
                        <button type="button" aria-label={`Remove from ${group.name}`} onClick={() => onChange(value.filter((id) => id !== group.id))}>
                            <X size={12} />
                        </button>
                    )}
                </span>
            ))}
            {!disabled && rest.length > 0 && (
                <select
                    value=""
                    aria-label="Add to group"
                    onChange={(event) => event.target.value && onChange([...value, Number(event.target.value)])}
                >
                    <option value="">+ Add to group…</option>
                    {rest.map((group) => (
                        <option key={group.id} value={group.id}>
                            {group.name} ({group.kind})
                        </option>
                    ))}
                </select>
            )}
            {chosen.length === 0 && (disabled || rest.length === 0) && <span className="task-muted">No groups</span>}
        </div>
    )
}

// ----------------------------------------------------------------------
// Create
// ----------------------------------------------------------------------

type Draft = {
    title: string
    type: string
    status: Status
    severity: Severity
    description: string
    remarks: string
    assignee: string
    external_ref: string
    reminder_at: string
    due_date: string
    group_ids: number[]
}

export function CreatePanel({ data, onClose, onCreated, initialGroup }: {
    data: TaskData
    onClose: () => void
    onCreated: (task: Task, another: boolean) => void
    initialGroup?: number | null
}) {
    const { notify } = useFeedback()
    const blank: Draft = {
        title: '', type: 'issue', status: 'todo', severity: 'medium', description: '', remarks: '', assignee: '',
        external_ref: '', reminder_at: '', due_date: '', group_ids: initialGroup ? [initialGroup] : [],
    }
    const [draft, setDraft] = useState<Draft>(blank)
    const [busy, setBusy] = useState(false)
    const another = useRef(false)
    const set = <K extends keyof Draft>(key: K, value: Draft[K]) => setDraft((current) => ({ ...current, [key]: value }))

    const submit = async (event: FormEvent) => {
        event.preventDefault()
        if (!draft.title.trim()) return
        setBusy(true)
        try {
            const created = await tasksApi.create({
                ...draft,
                title: draft.title.trim(),
                assignee: draft.assignee || null,
                external_ref: draft.external_ref.trim() || null,
                reminder_at: reminderValue(draft.reminder_at),
                due_date: draft.due_date || null,
            })
            notify.success(`${created.key} created.`, { title: 'Task created' })
            const keep = another.current
            if (keep) setDraft({ ...blank, type: draft.type, severity: draft.severity, group_ids: draft.group_ids, assignee: draft.assignee })
            onCreated(created, keep)
        } catch (cause) {
            notify.error(errorText(cause), { title: 'Unable to create the task' })
        } finally {
            setBusy(false)
            another.current = false
        }
    }

    return (
        <Panel title="New task" eyebrow={`Will be ${data.settings.next_key}`} onClose={onClose}>
            <form className="task-form" onSubmit={(event) => void submit(event)}>
                <label>
                    Title
                    <input autoFocus maxLength={200} value={draft.title} onChange={(event) => set('title', event.target.value)} required />
                </label>
                <div className="task-form-row is-three">
                    <label>
                        Type
                        <select value={draft.type} onChange={(event) => set('type', event.target.value)}>
                            <TypeOptions types={data.settings.types} />
                        </select>
                    </label>
                    <label>
                        Status
                        <select value={draft.status} onChange={(event) => set('status', event.target.value as Status)}>
                            {STATUSES.filter((status) => status.id !== 'reopened').map((status) => (
                                <option key={status.id} value={status.id}>
                                    {status.title}
                                </option>
                            ))}
                        </select>
                    </label>
                    <label>
                        Severity
                        <select value={draft.severity} onChange={(event) => set('severity', event.target.value as Severity)}>
                            {SEVERITIES.map((severity) => <option key={severity.id} value={severity.id}>{severity.title}</option>)}
                        </select>
                    </label>
                </div>
                <div className="task-form-row">
                    <label>
                        Assignee
                        <select value={draft.assignee} onChange={(event) => set('assignee', event.target.value)}>
                            <MemberOptions data={data} />
                        </select>
                    </label>
                    <label>
                        External reference
                        <input maxLength={120} value={draft.external_ref} placeholder="JIRA-123, INC0042…" onChange={(event) => set('external_ref', event.target.value)} />
                    </label>
                </div>
                <label>
                    Description
                    <MentionInput rows={4} value={draft.description} onChange={(value) => set('description', value)} members={data.members} placeholder="What needs to be done? @mention members to notify them." />
                </label>
                <label>
                    Remarks
                    <textarea rows={2} value={draft.remarks} onChange={(event) => set('remarks', event.target.value)} />
                </label>
                <div className="task-field">
                    <span>Groups</span>
                    <GroupPicker groups={data.groups} value={draft.group_ids} onChange={(ids) => set('group_ids', ids)} />
                </div>
                <div className="task-form-row">
                    <label>
                        Due date
                        <input type="date" value={draft.due_date} onChange={(event) => set('due_date', event.target.value)} />
                    </label>
                    <label className="task-reminder-label">
                        Reminder
                        <input type="datetime-local" value={draft.reminder_at} onChange={(event) => set('reminder_at', event.target.value)} />
                    </label>
                </div>
                {!data.mail_ready && <small className="task-muted">Email reminders need SMTP configuration in Administration → Settings.</small>}
                <footer>
                    <button type="button" className="entropy-button entropy-button-secondary" onClick={onClose}>
                        Cancel
                    </button>
                    <button type="submit" className="entropy-button entropy-button-secondary" disabled={busy || !draft.title.trim()} onClick={() => (another.current = true)}>
                        Create and add another
                    </button>
                    <button type="submit" className="entropy-button entropy-button-primary" disabled={busy || !draft.title.trim()}>
                        {busy ? <LoaderCircle size={15} className="entropy-spin" /> : <Plus size={15} />} Create task
                    </button>
                </footer>
            </form>
        </Panel>
    )
}

// ----------------------------------------------------------------------
// Details
// ----------------------------------------------------------------------

export function DetailPanel({ data, task, onClose, onChanged, onDeleted, popup = false, onPopup }: {
    data: TaskData
    task: Task
    onClose: () => void
    onChanged: () => Promise<void>
    onDeleted: (task: Task) => void
    popup?: boolean
    onPopup?: (popup: boolean) => void
}) {
    const { notify, modal } = useFeedback()
    const [comment, setComment] = useState('')
    const [busy, setBusy] = useState<string | null>(null)
    const [dragging, setDragging] = useState(false)
    const dragDepth = useRef(0)
    const [viewing, setViewing] = useState<number | null>(null)
    const [renaming, setRenaming] = useState<number | null>(null)
    const fileInput = useRef<HTMLInputElement>(null)
    const manage = data.permissions['tasks.manage']
    const canComment = data.permissions['tasks.comment']
    const checkStatus = useStatusChange()

    const run = async (label: string, action: () => Promise<unknown>, failure: string) => {
        setBusy(label)
        try {
            await action()
            await onChanged()
            return true
        } catch (cause) {
            notify.error(errorText(cause), { title: failure })
            return false
        } finally {
            setBusy(null)
        }
    }
    const save = (changes: Record<string, unknown>) => run('save', () => tasksApi.update(task.id, changes), 'Unable to update the task')
    const changeStatus = async (status: Status) => {
        const change = await checkStatus(task, status)
        if (change && (await save(change)) && change.reason) {
            notify.success(`${task.key} reopened.`, { title: 'Task reopened' })
        }
    }

    const remove = async () => {
        const confirmed = await modal.confirm({
            title: `Delete ${task.key}?`,
            message: `“${task.title}” is removed with its comments and attachments. This cannot be undone.`,
            confirmText: 'Delete task',
            cancelText: 'Cancel',
            destructive: true,
        })
        if (!confirmed) return
        try {
            await tasksApi.remove(task.id)
            notify.success(`${task.key} deleted.`, { title: 'Task deleted' })
            onDeleted(task)
        } catch (cause) {
            notify.error(errorText(cause), { title: 'Unable to delete the task' })
        }
    }

    const upload = async (files: File[]) => {
        if (!files.length) return false
        if (!(await run('upload', () => tasksApi.attach(task.id, files), 'Unable to attach the files'))) return false
        notify.success(`${files.length} file${files.length === 1 ? '' : 's'} attached to ${task.key}.`, { title: 'Attached' })
        return true
    }
    // Uploads and resolves to the attachments created (for the description).
    const attachReturning = async (files: File[]): Promise<Attachment[]> => {
        const added: Attachment[] = []
        const done = await run('upload', async () => {
            const before = new Set(task.attachments.map((attachment) => attachment.id))
            const updated = await tasksApi.attach(task.id, files.map(pastedFile))
            added.push(...updated.attachments.filter((attachment) => !before.has(attachment.id)))
        }, 'Unable to attach the files')
        return done ? added : []
    }

    const rename = async (attachment: Attachment, name: string) => {
        const filename = name.trim()
        setRenaming(null)
        if (!filename || filename === attachment.filename) return true
        return run('rename', () => tasksApi.rename(task.id, attachment.id, filename), 'Unable to rename the attachment')
    }

    // The marked-up image is attached first, so a failed removal never loses it.
    const replaceImage = async (original: Attachment, file: File): Promise<number | null> => {
        const confirmed = await modal.confirm({
            title: `Replace ${original.filename}?`,
            message: 'The original image is removed and the marked-up image takes its place. This cannot be undone.',
            confirmText: 'Replace',
            cancelText: 'Cancel',
            destructive: true,
        })
        if (!confirmed) return null
        const added: { id: number | null } = { id: null }
        const done = await run('upload', async () => {
            const before = new Set(task.attachments.map((attachment) => attachment.id))
            const updated = await tasksApi.attach(task.id, [file])
            added.id = updated.attachments.find((attachment) => !before.has(attachment.id))?.id ?? null
            try {
                await tasksApi.detach(task.id, original.id)
            } catch (cause) {
                throw new Error(`The marked-up image was attached, but the original could not be removed: ${errorText(cause)}`, { cause })
            }
        }, 'Unable to replace the image')
        if (done) notify.success(`${original.filename} replaced with the marked-up image.`, { title: 'Image replaced' })
        return added.id
    }
    const canRemove = (attachment: Attachment) => manage || attachment.uploaded_by.toLowerCase() === data.username.toLowerCase()

    const uploadRef = useRef(upload)
    useEffect(() => {
        uploadRef.current = upload
    })

    // Ctrl+V / Cmd+V anywhere while the task is open attaches pasted files
    // (screenshots). Plain text pastes are left to the focused field.
    useEffect(() => {
        if (!canComment) return
        const onPaste = (event: ClipboardEvent) => {
            const files = Array.from(event.clipboardData?.files ?? [])
            // The description editor places pasted files itself.
            if (!files.length || event.defaultPrevented) return
            event.preventDefault()
            void uploadRef.current(files.map(pastedFile))
        }
        document.addEventListener('paste', onPaste)
        return () => document.removeEventListener('paste', onPaste)
    }, [canComment])

    const dropHandlers = canComment ? {
        onDragEnter: (event: DragEvent) => {
            if (!carriesFiles(event)) return
            dragDepth.current += 1
            setDragging(true)
        },
        onDragOver: (event: DragEvent) => {
            if (!carriesFiles(event)) return
            event.preventDefault()
            event.dataTransfer.dropEffect = 'copy'
        },
        onDragLeave: (event: DragEvent) => {
            if (!carriesFiles(event)) return
            dragDepth.current = Math.max(0, dragDepth.current - 1)
            if (!dragDepth.current) setDragging(false)
        },
        onDrop: (event: DragEvent) => {
            if (!carriesFiles(event)) return
            event.preventDefault()
            dragDepth.current = 0
            setDragging(false)
            void upload(Array.from(event.dataTransfer.files))
        },
    } : {}

    const sendComment = async () => {
        if (!comment.trim()) return
        if (await run('comment', () => tasksApi.comment(task.id, comment.trim()), 'Unable to add the comment')) setComment('')
    }

    const following = task.follower_ids.includes(data.user_id)
    const mine = task.assignee?.toLowerCase() === data.username.toLowerCase()

    return (
        <Panel
            title={task.title}
            eyebrow={
                <>
                    <TypeIcon type={task.type} /> {task.key} · {typeLabel(task.type)}
                    {task.external_ref && <> · <Link2 size={12} /> {task.external_ref}</>}
                </>
            }
            onClose={onClose}
            popup={popup}
            onDock={() => onPopup?.(false)}
            actions={
                <>
                    {onPopup && (
                        <button type="button" className="entropy-button entropy-button-ghost entropy-button-icon entropy-button-sm" onClick={() => onPopup(!popup)} aria-label={popup ? 'Dock beside the tasks' : 'Open in a popup'} title={popup ? 'Dock beside the tasks' : 'Open in a popup'}>
                            {popup ? <Minimize2 size={16} /> : <Maximize2 size={16} />}
                        </button>
                    )}
                    {manage && (
                        <button type="button" className="entropy-button entropy-button-ghost entropy-button-icon entropy-button-sm task-delete" onClick={() => void remove()} aria-label={`Delete ${task.key}`} title="Delete task">
                            <Trash2 size={16} />
                        </button>
                    )}
                </>
            }
        >
            <div className="task-form" {...dropHandlers}>
                {manage && (
                    <label>
                        Title
                        <input key={`${task.id}-title`} defaultValue={task.title} maxLength={200} onBlur={(event) => {
                            const value = event.target.value.trim()
                            if (value && value !== task.title) void save({ title: value })
                        }} />
                    </label>
                )}
                <div className="task-form-row is-three">
                    <label>
                        Type
                        <select disabled={!manage} value={task.type} onChange={(event) => void save({ type: event.target.value })}>
                            <TypeOptions types={data.settings.types} />
                        </select>
                    </label>
                    <label>
                        Status
                        <select disabled={!manage} value={task.status} onChange={(event) => void changeStatus(event.target.value as Status)}>
                            {nextStatuses(task.status).map((status) => (
                                <option key={status} value={status}>
                                    {statusTitle(status)}
                                </option>
                            ))}
                        </select>
                    </label>
                    <label>
                        Severity
                        <select disabled={!manage} value={task.severity ?? 'medium'} onChange={(event) => void save({ severity: event.target.value })}>
                            {SEVERITIES.map((severity) => <option key={severity.id} value={severity.id}>{severity.title}</option>)}
                        </select>
                    </label>
                </div>
                <div className="task-form-row">
                    <label>
                        Assignee
                        <span className="task-assignee">
                            <select disabled={!manage} value={task.assignee ?? ''} onChange={(event) => void save({ assignee: event.target.value || null })}>
                                <MemberOptions data={data} />
                            </select>
                            {!mine && canComment && (
                                <button type="button" className="entropy-button entropy-button-secondary entropy-button-sm" onClick={() => void save({ assignee: data.username })} title="Assign this task to yourself">
                                    <Hand size={14} /> Take it
                                </button>
                            )}
                        </span>
                    </label>
                    <label>
                        External reference
                        <input key={`${task.id}-ref`} disabled={!manage} maxLength={120} defaultValue={task.external_ref ?? ''} placeholder="JIRA-123…" onBlur={(event) => {
                            if (event.target.value.trim() !== (task.external_ref ?? '')) void save({ external_ref: event.target.value.trim() || null })
                        }} />
                    </label>
                </div>
                <div className="task-field">
                    <span>Groups</span>
                    <GroupPicker groups={data.groups} value={task.group_ids} disabled={!manage} onChange={(ids) => void save({ group_ids: ids })} />
                </div>
                <div className="task-form-row">
                    <label>
                        Due date {isOverdue(task) && <span className="task-overdue">Overdue</span>}
                        <input type="date" disabled={!manage} value={task.due_date ?? ''} onChange={(event) => void save({ due_date: event.target.value || null })} />
                    </label>
                    <span />
                </div>
                <div className="task-detail-info">
                    <span>Created by <strong>{task.creator}</strong> {localDate(task.created_at)}</span>
                    <span>Updated {localDate(task.updated_at)}</span>
                </div>
                <Description
                    task={task}
                    members={data.members}
                    editable={manage}
                    onSave={(description) => save({ description })}
                    onAttach={attachReturning}
                    onOpen={(attachment) => setViewing(attachment.id)}
                />
                {manage ? (
                    <>
                        <label>
                            Remarks
                            <textarea key={`${task.id}-remarks`} defaultValue={task.remarks} rows={2} onBlur={(event) => {
                                if (event.target.value !== task.remarks) void save({ remarks: event.target.value })
                            }} />
                        </label>
                        <label className="task-reminder-label">
                            Reminder
                            {!data.mail_ready && <small>Email reminders need SMTP configuration in Administration → Settings.</small>}
                            <input type="datetime-local" value={reminderInput(task.reminder_at)} onChange={(event) => void save({ reminder_at: reminderValue(event.target.value) })} />
                        </label>
                    </>
                ) : (
                    <>
                        {task.remarks && <p className="task-remarks">{task.remarks}</p>}
                        {task.reminder_at && <p className="task-detail-info"><Bell size={14} /> Reminder {localDate(task.reminder_at)}</p>}
                    </>
                )}
                {data.permissions['tasks.follow'] && (
                    <button type="button" className="entropy-button entropy-button-secondary entropy-button-sm task-follow" onClick={() => void run('follow', () => tasksApi.follow(task.id, !following), 'Unable to change following')}>
                        {following ? <><Check size={15} /> Following</> : <><Bell size={15} /> Follow task</>}
                    </button>
                )}

                <section className={`task-attachments${dragging ? ' is-dragging' : ''}`}>
                    <h4>
                        <Paperclip size={16} /> Attachments <span>{task.attachments.length}</span>
                        {canComment && (
                            <button type="button" className="entropy-button entropy-button-ghost entropy-button-sm" onClick={() => fileInput.current?.click()} disabled={busy === 'upload'}>
                                {busy === 'upload' ? <LoaderCircle size={14} className="entropy-spin" /> : <Upload size={14} />} Attach files
                            </button>
                        )}
                        <input ref={fileInput} type="file" multiple hidden onChange={(event) => {
                            void upload(Array.from(event.currentTarget.files ?? []))
                            event.currentTarget.value = ''
                        }} />
                    </h4>
                    {task.attachments.length === 0 ? (
                        <p className="task-muted">{canComment ? 'Drop files on this task, paste a screenshot (Ctrl+V / ⌘V) or attach them (up to 50 MiB each).' : 'No attachments.'}</p>
                    ) : (
                        <ul>
                            {task.attachments.map((attachment) => (
                                <li key={attachment.id} onContextMenu={(event) => {
                                    if (!canRemove(attachment)) return
                                    event.preventDefault()
                                    setRenaming(attachment.id)
                                }}>
                                    <FileUp size={15} aria-hidden="true" />
                                    {renaming === attachment.id ? (
                                        <input
                                            className="task-input task-attachment-rename"
                                            defaultValue={attachment.filename}
                                            maxLength={255}
                                            autoFocus
                                            aria-label={`Rename ${attachment.filename}`}
                                            onFocus={(event) => {
                                                const dot = attachment.filename.lastIndexOf('.')
                                                event.currentTarget.setSelectionRange(0, dot > 0 ? dot : attachment.filename.length)
                                            }}
                                            onKeyDown={(event) => {
                                                if (event.key === 'Enter') event.currentTarget.blur()
                                                if (event.key === 'Escape') {
                                                    event.currentTarget.value = attachment.filename
                                                    event.currentTarget.blur()
                                                }
                                            }}
                                            onBlur={(event) => void rename(attachment, event.currentTarget.value)}
                                        />
                                    ) : (() => {
                                        const details = (
                                            <>
                                                <strong title={attachment.filename}>{attachment.filename}</strong>
                                                <small>
                                                    {[formatSize(attachment.size_bytes), attachment.uploaded_by, localDate(attachment.created_at)].filter(Boolean).join(' · ')}
                                                    {attachment.url && !attachment.content_type ? ' · link to Jira' : ''}
                                                </small>
                                            </>
                                        )
                                        return previewKind(attachment) ? (
                                            <button type="button" className="task-attachment-name" onClick={() => setViewing(attachment.id)} title={`View ${attachment.filename}${canRemove(attachment) ? ' · right-click to rename' : ''}`}>{details}</button>
                                        ) : (
                                            <span className="task-attachment-name" title={canRemove(attachment) ? 'Right-click to rename' : undefined}>{details}</span>
                                        )
                                    })()}
                                    {attachment.url ? (
                                        <a className="entropy-button entropy-button-ghost entropy-button-icon entropy-button-sm" href={attachment.url} target="_blank" rel="noopener noreferrer" aria-label={`Open ${attachment.filename}`} title="Open the original">
                                            <ExternalLink size={14} />
                                        </a>
                                    ) : (
                                        <a className="entropy-button entropy-button-ghost entropy-button-icon entropy-button-sm" href={tasksApi.attachmentUrl(task.id, attachment.id)} download={attachment.filename} aria-label={`Download ${attachment.filename}`} title="Download">
                                            <Download size={14} />
                                        </a>
                                    )}
                                    {canRemove(attachment) && (
                                        <button type="button" className="entropy-button entropy-button-ghost entropy-button-icon entropy-button-sm" aria-label={`Remove ${attachment.filename}`} title="Remove" onClick={() => void run('detach', () => tasksApi.detach(task.id, attachment.id), 'Unable to remove the attachment')}>
                                            <X size={14} />
                                        </button>
                                    )}
                                </li>
                            ))}
                        </ul>
                    )}
                    {viewing !== null && (
                        <AttachmentViewer taskId={task.id} attachments={task.attachments} initial={viewing} onClose={() => setViewing(null)}
                            onAttach={canComment ? (file) => upload([file]) : undefined}
                            onReplace={canComment ? replaceImage : undefined}
                            canReplace={canRemove}
                            onRename={rename} />
                    )}
                </section>

                <section className="task-comments">
                    <h4><MessageSquare size={16} /> Comments <span>{task.comments.length}</span></h4>
                    {task.comments.length ? (
                        task.comments.map((item) => (
                            <article key={item.id}>
                                <div><strong>{item.author}</strong><time>{localDate(item.created_at)}</time></div>
                                <p><MentionText text={item.body} members={data.members} /></p>
                            </article>
                        ))
                    ) : (
                        <p className="task-muted">No comments yet.</p>
                    )}
                    {canComment && (
                        <form onSubmit={(event) => {
                            event.preventDefault()
                            void sendComment()
                        }}>
                            <MentionInput value={comment} onChange={setComment} members={data.members} ariaLabel="Comment" placeholder="Write a comment… type @ to mention a member (Ctrl/⌘ + Enter sends)" onSubmitShortcut={() => void sendComment()} />
                            <button className="entropy-button entropy-button-primary entropy-button-sm" disabled={!comment.trim() || busy === 'comment'}>
                                {busy === 'comment' ? <LoaderCircle size={14} className="entropy-spin" /> : <Send size={14} />} Comment
                            </button>
                        </form>
                    )}
                </section>

                {(task.history?.length ?? 0) > 0 && (
                    <section className="task-history">
                        <h4><History size={16} /> Status history <span>{task.history.length}</span></h4>
                        <ol>
                            {task.history.map((item, index) => (
                                <li key={index} className={item.to_status === 'reopened' ? 'is-reopen' : ''}>
                                    <div>
                                        {item.from_status ? <>{statusTitle(item.from_status)} → </> : 'Created as '}
                                        <strong>{statusTitle(item.to_status)}</strong>
                                        <span className="task-muted"> · {item.changed_by} · {localDate(item.changed_at)}</span>
                                    </div>
                                    {item.reason && <p>{item.reason}</p>}
                                </li>
                            ))}
                        </ol>
                    </section>
                )}
            </div>
        </Panel>
    )
}

// ----------------------------------------------------------------------
// Groups
// ----------------------------------------------------------------------

export function GroupsPanel({ data, onClose, onChanged, activeGroup, onFilter }: {
    data: TaskData
    onClose: () => void
    onChanged: () => Promise<void>
    activeGroup: number | null
    onFilter: (id: number | null) => void
}) {
    const { notify, modal } = useFeedback()
    const [draft, setDraft] = useState({ name: '', kind: 'release' as GroupKind, external_ref: '', description: '' })
    const [busy, setBusy] = useState(false)
    const canCreate = data.permissions['tasks.create']
    const manage = data.permissions['tasks.manage']

    const create = async (event: FormEvent) => {
        event.preventDefault()
        if (!draft.name.trim()) return
        setBusy(true)
        try {
            const group = await tasksApi.createGroup({ ...draft, name: draft.name.trim(), external_ref: draft.external_ref.trim() || null })
            notify.success(`Group “${group.name}” created. Add tasks to it from the list (select, then Add to group) or from a task.`, { title: 'Group created' })
            setDraft({ name: '', kind: draft.kind, external_ref: '', description: '' })
            await onChanged()
        } catch (cause) {
            notify.error(errorText(cause), { title: 'Unable to create the group' })
        } finally {
            setBusy(false)
        }
    }

    const remove = async (group: Group) => {
        const confirmed = await modal.confirm({
            title: `Delete the group “${group.name}”?`,
            message: `Its ${group.task_count} task${group.task_count === 1 ? ' is' : 's are'} kept; only the grouping is removed.`,
            confirmText: 'Delete group',
            cancelText: 'Cancel',
            destructive: true,
        })
        if (!confirmed) return
        try {
            await tasksApi.removeGroup(group.id)
            if (activeGroup === group.id) onFilter(null)
            notify.success(`Group “${group.name}” deleted.`)
            await onChanged()
        } catch (cause) {
            notify.error(errorText(cause), { title: 'Unable to delete the group' })
        }
    }

    const rename = async (group: Group, name: string) => {
        if (!name.trim() || name.trim() === group.name) return
        try {
            await tasksApi.updateGroup(group.id, { name: name.trim() })
            await onChanged()
        } catch (cause) {
            notify.error(errorText(cause), { title: 'Unable to rename the group' })
        }
    }

    return (
        <Panel title="Groups" eyebrow="Releases, sprints, epics" onClose={onClose}>
            <div className="task-form">
                <p className="task-muted">
                    Group the issues that belong together, for example all issues of one release. A task may be in several groups.
                </p>
                {canCreate && (
                    <form className="task-group-form" onSubmit={(event) => void create(event)}>
                        <div className="task-form-row">
                            <label>
                                Name
                                <input value={draft.name} maxLength={120} placeholder="Release 2.4" onChange={(event) => setDraft({ ...draft, name: event.target.value })} />
                            </label>
                            <label>
                                Kind
                                <select value={draft.kind} onChange={(event) => setDraft({ ...draft, kind: event.target.value as GroupKind })}>
                                    {GROUP_KINDS.map((kind) => (
                                        <option key={kind.id} value={kind.id}>{kind.title}</option>
                                    ))}
                                </select>
                            </label>
                        </div>
                        <label>
                            External reference
                            <input value={draft.external_ref} maxLength={120} placeholder="REL-2024-04" onChange={(event) => setDraft({ ...draft, external_ref: event.target.value })} />
                        </label>
                        <footer>
                            <button type="submit" className="entropy-button entropy-button-primary entropy-button-sm" disabled={busy || !draft.name.trim()}>
                                <Plus size={14} /> Create group
                            </button>
                        </footer>
                    </form>
                )}
                {data.groups.length === 0 ? (
                    <p className="task-muted">No groups yet.</p>
                ) : (
                    <ul className="task-group-list">
                        {data.groups.map((group) => (
                            <li key={group.id} className={activeGroup === group.id ? 'is-active' : undefined}>
                                <span className={`task-group-chip kind-${group.kind}`}>{group.kind}</span>
                                {manage ? (
                                    <input key={`${group.id}-${group.name}`} defaultValue={group.name} aria-label={`Name of ${group.name}`} onBlur={(event) => void rename(group, event.target.value)} />
                                ) : (
                                    <strong>{group.name}</strong>
                                )}
                                <small>{group.task_count} task{group.task_count === 1 ? '' : 's'}{group.external_ref ? ` · ${group.external_ref}` : ''}</small>
                                <button type="button" className="entropy-button entropy-button-ghost entropy-button-sm" onClick={() => onFilter(activeGroup === group.id ? null : group.id)}>
                                    {activeGroup === group.id ? 'Show all' : 'Show tasks'}
                                </button>
                                {manage && (
                                    <button type="button" className="entropy-button entropy-button-ghost entropy-button-icon entropy-button-sm" aria-label={`Delete group ${group.name}`} onClick={() => void remove(group)}>
                                        <Trash2 size={14} />
                                    </button>
                                )}
                            </li>
                        ))}
                    </ul>
                )}
            </div>
        </Panel>
    )
}

// ----------------------------------------------------------------------
// Settings
// ----------------------------------------------------------------------

export function SettingsPanel({ data, onClose, onChanged }: {
    data: TaskData
    onClose: () => void
    onChanged: () => Promise<void>
}) {
    const { notify } = useFeedback()
    const [prefix, setPrefix] = useState(data.settings.prefix)
    const [type, setType] = useState('')
    const save = async (body: { prefix?: string; types?: string[] }, message: string) => {
        try {
            await tasksApi.settings(body)
            notify.success(message, { title: 'Task settings saved' })
            await onChanged()
        } catch (cause) {
            notify.error(errorText(cause), { title: 'Unable to save the settings' })
        }
    }
    const nextNumber = data.settings.next_key.split('-').pop()
    return (
        <Panel title="Task settings" eyebrow="This project" onClose={onClose}>
            <form className="task-form" onSubmit={(event) => {
                event.preventDefault()
                void save({ prefix: prefix.trim().toUpperCase() }, `New tasks are numbered ${prefix.trim().toUpperCase()}-${nextNumber}, …`)
            }}>
                <label>
                    Key prefix
                    <small>Tasks are numbered PREFIX-01, PREFIX-02, … Keys are unique and never reused; existing tasks keep theirs.</small>
                    <input value={prefix} maxLength={10} onChange={(event) => setPrefix(event.target.value.toUpperCase().replace(/[^A-Z0-9]/g, ''))} />
                </label>
                <p className="task-muted">Next task: <strong>{prefix || '…'}-{nextNumber}</strong></p>
                <footer>
                    <button type="submit" className="entropy-button entropy-button-primary entropy-button-sm" disabled={!/^[A-Z][A-Z0-9]{1,9}$/.test(prefix) || prefix === data.settings.prefix}>
                        Save prefix
                    </button>
                </footer>
            </form>
            <form className="task-form" onSubmit={(event) => {
                event.preventDefault()
                const name = type.trim().toLowerCase().replace(/\s+/g, '_')
                if (!name) return
                void save({ types: [...data.settings.custom_types, name] }, `Type “${typeLabel(name)}” added.`)
                setType('')
            }}>
                <div className="task-field">
                    <span>Types</span>
                    <div className="task-groups-picker">
                        {data.settings.types.map((name) => {
                            const custom = data.settings.custom_types.includes(name)
                            return (
                                <span key={name} className="task-type-chip">
                                    <TypeIcon type={name} /> {typeLabel(name)}
                                    {custom && (
                                        <button type="button" aria-label={`Remove type ${name}`} onClick={() => void save({ types: data.settings.custom_types.filter((item) => item !== name) }, `Type “${typeLabel(name)}” removed.`)}>
                                            <X size={12} />
                                        </button>
                                    )}
                                </span>
                            )
                        })}
                    </div>
                </div>
                <label>
                    Add a type
                    <input value={type} maxLength={30} placeholder="spike, request, …" onChange={(event) => setType(event.target.value)} />
                </label>
                <footer>
                    <button type="submit" className="entropy-button entropy-button-secondary entropy-button-sm" disabled={!type.trim()}>
                        <Plus size={14} /> Add type
                    </button>
                </footer>
            </form>
        </Panel>
    )
}

// ----------------------------------------------------------------------
// Jira import
// ----------------------------------------------------------------------

export function ImportPanel({ onClose, onImported }: { onClose: () => void; onImported: () => Promise<void> }) {
    const { notify } = useFeedback()
    const [file, setFile] = useState<File | null>(null)
    const [group, setGroup] = useState('')
    const [update, setUpdate] = useState(true)
    const [busy, setBusy] = useState(false)

    const submit = async (event: FormEvent) => {
        event.preventDefault()
        if (!file) return
        setBusy(true)
        try {
            const result = await tasksApi.importJira(file, group, update)
            const parts = [
                `${result.created} created`,
                `${result.updated} updated`,
                result.skipped ? `${result.skipped} skipped` : '',
                result.comments ? `${result.comments} comments` : '',
                result.attachments ? `${result.attachments} attachments` : '',
                result.groups.length ? `groups: ${result.groups.join(', ')}` : '',
                result.types_added.length ? `new types: ${result.types_added.join(', ')}` : '',
            ].filter(Boolean)
            notify.success(parts.join(' · '), { title: `Imported ${file.name}` })
            if (result.unassigned.length) {
                notify.warning(`Not members of this project, left unassigned: ${result.unassigned.join(', ')}.`, { title: 'Assignees not found' })
            }
            await onImported()
            onClose()
        } catch (cause) {
            notify.error(errorText(cause), { title: 'Unable to import the Jira file' })
        } finally {
            setBusy(false)
        }
    }

    return (
        <Panel title="Import from Jira" eyebrow="XML, CSV or JSON export" onClose={onClose}>
            <form className="task-form" onSubmit={(event) => void submit(event)}>
                <p className="task-muted">
                    Use Jira's <strong>Export → XML</strong> or <strong>CSV (all fields)</strong>, or a REST search result (JSON).
                    Types, statuses, assignees, comments, attachments (as links), fix versions, sprints and epics are kept;
                    the Jira key becomes the external reference and each task gets its own key.
                </p>
                <label className="task-import-file">
                    <Upload size={18} />
                    <span>{file ? file.name : 'Choose a Jira export'}</span>
                    <input type="file" accept=".xml,.csv,.json,text/xml,text/csv,application/json" onChange={(event) => setFile(event.currentTarget.files?.[0] ?? null)} />
                </label>
                <label>
                    Put all imported tasks in a group (optional)
                    <input value={group} maxLength={120} placeholder="Release 2.4 intake" onChange={(event) => setGroup(event.target.value)} />
                </label>
                <label className="task-check">
                    <input type="checkbox" checked={update} onChange={(event) => setUpdate(event.target.checked)} />
                    Update tasks already imported (same Jira key); otherwise skip them
                </label>
                <footer>
                    <button type="button" className="entropy-button entropy-button-secondary" onClick={onClose}>Cancel</button>
                    <button type="submit" className="entropy-button entropy-button-primary" disabled={!file || busy}>
                        {busy ? <LoaderCircle size={15} className="entropy-spin" /> : <Upload size={15} />} Import
                    </button>
                </footer>
            </form>
        </Panel>
    )
}

// ----------------------------------------------------------------------
// Report
// ----------------------------------------------------------------------

export function ReportPanel({ data, selection, groupFilter, onClose, onPickTasks }: {
    data: TaskData
    selection: number[]
    groupFilter: number | null
    onClose: () => void
    onPickTasks: () => void
}) {
    const [scope, setScope] = useState<ReportScope>(selection.length ? 'selected' : groupFilter ? 'group' : 'all')
    const [groupId, setGroupId] = useState<number | null>(groupFilter ?? data.groups[0]?.id ?? null)
    const [format, setFormat] = useState<'html' | 'pdf'>('html')
    const count =
        scope === 'all' ? data.items.length
            : scope === 'selected' ? selection.length
                : data.items.filter((task) => groupId !== null && task.group_ids.includes(groupId)).length
    const ready = count > 0 && (scope !== 'group' || groupId !== null)

    const generate = () => {
        const url = reportUrl(scope, format, selection, groupId)
        if (format === 'pdf') {
            // The report opens in a tab and asks the browser to print it: choose "Save as PDF".
            window.open(url, '_blank', 'noopener')
            return
        }
        const link = document.createElement('a')
        link.href = url
        link.click()
    }

    return (
        <Panel title="Task report" eyebrow="For sharing" onClose={onClose}>
            <div className="task-form task-report">
                <p className="task-muted">
                    A readable report for people outside Entropy: a summary, then each group's tasks with their
                    fields, comments, status history and attachments (images, text files and videos are included).
                </p>
                <fieldset>
                    <legend>Tasks</legend>
                    <label className="task-choice">
                        <input type="radio" checked={scope === 'all'} onChange={() => setScope('all')} />
                        All tasks <span className="task-muted">{data.items.length}</span>
                    </label>
                    <label className="task-choice">
                        <input type="radio" checked={scope === 'group'} disabled={!data.groups.length} onChange={() => setScope('group')} />
                        One group
                        <select value={groupId ?? ''} disabled={scope !== 'group'} onChange={(event) => setGroupId(Number(event.target.value) || null)} aria-label="Report group">
                            {data.groups.map((group) => <option key={group.id} value={group.id}>{group.name} ({group.task_count})</option>)}
                        </select>
                    </label>
                    <label className="task-choice">
                        <input type="radio" checked={scope === 'selected'} disabled={!selection.length} onChange={() => setScope('selected')} />
                        Selected tasks <span className="task-muted">{selection.length}</span>
                    </label>
                    {!selection.length && (
                        <button type="button" className="entropy-button entropy-button-ghost entropy-button-sm" onClick={onPickTasks}>
                            Select tasks in the list view
                        </button>
                    )}
                </fieldset>
                <fieldset>
                    <legend>Format</legend>
                    <label className="task-choice">
                        <input type="radio" checked={format === 'html'} onChange={() => setFormat('html')} />
                        HTML file <span className="task-muted">one file, opens in any browser; videos play</span>
                    </label>
                    <label className="task-choice">
                        <input type="radio" checked={format === 'pdf'} onChange={() => setFormat('pdf')} />
                        PDF <span className="task-muted">opens the print dialog: choose “Save as PDF”</span>
                    </label>
                </fieldset>
                <footer>
                    <button type="button" className="entropy-button entropy-button-secondary" onClick={onClose}>Cancel</button>
                    <button type="button" className="entropy-button entropy-button-primary" disabled={!ready} onClick={generate}>
                        <Download size={15} /> {format === 'pdf' ? 'Open PDF' : 'Download'} ({count} task{count === 1 ? '' : 's'})
                    </button>
                </footer>
            </div>
        </Panel>
    )
}
