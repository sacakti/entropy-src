import { useCallback, useEffect, useMemo, useState, type FormEvent, type ReactNode } from 'react'
import { createPortal } from 'react-dom'
import { Bell, Check, Columns3, Download, List, ListTodo, MessageSquare, Plus, RefreshCw, Send, Upload, UserRound, X } from 'lucide-react'
import { apiRequest } from '../../../services/api'
import './tasks.css'

type Status = 'todo' | 'in_progress' | 'done'
type Comment = { id: number; author: string; body: string; created_at: string }
type Task = {
    id: number; title: string; description: string; remarks: string; status: Status
    assignee: string | null; creator: string; reminder_at: string | null; created_at: string
    updated_at: string; comments: Comment[]; follower_ids: number[]
}
type Member = { username: string; full_name: string | null }
type TaskData = {
    items: Task[]; members: Member[]; user_id: number; mail_ready: boolean
    permissions: { 'tasks.create': boolean; 'tasks.manage': boolean; 'tasks.comment': boolean; 'tasks.follow': boolean }
}
type Draft = { title: string; description: string; remarks: string; assignee: string; reminder_at: string }

const columns: { id: Status; title: string }[] = [
    { id: 'todo', title: 'To do' }, { id: 'in_progress', title: 'In progress' }, { id: 'done', title: 'Done' },
]
const blank: Draft = { title: '', description: '', remarks: '', assignee: '', reminder_at: '' }
const localDate = (value: string | null) => value ? new Date(value).toLocaleString() : ''
const reminderValue = (value: string) => value ? new Date(value).toISOString() : null
const csvCell = (value: string) => `"${value.replaceAll('"', '""')}"`

function parseCsv(text: string): string[][] {
    const rows: string[][] = []
    let row: string[] = [], cell = '', quoted = false
    for (let index = 0; index < text.length; index += 1) {
        const char = text[index]
        if (quoted && char === '"' && text[index + 1] === '"') { cell += '"'; index += 1 }
        else if (char === '"') quoted = !quoted
        else if (char === ',' && !quoted) { row.push(cell); cell = '' }
        else if ((char === '\n' || char === '\r') && !quoted) {
            if (char === '\r' && text[index + 1] === '\n') index += 1
            row.push(cell); if (row.some((value) => value.trim())) rows.push(row); row = []; cell = ''
        } else cell += char
    }
    row.push(cell); if (row.some((value) => value.trim())) rows.push(row)
    return rows
}

function jiraField(record: Record<string, string>, ...names: string[]) {
    const key = Object.keys(record).find((candidate) => names.includes(candidate.trim().toLowerCase()))
    return key ? record[key].trim() : ''
}

function jiraDescription(value: unknown): string {
    if (typeof value === 'string') return value
    if (!value || typeof value !== 'object') return ''
    const node = value as { text?: unknown; content?: unknown[]; type?: unknown }
    const own = typeof node.text === 'string' ? node.text : ''
    const children = Array.isArray(node.content) ? node.content.map(jiraDescription).filter(Boolean).join('') : ''
    return own + children + (node.type === 'paragraph' ? '\n' : '')
}

function TaskModalLayer({ children, onClose }: { children: ReactNode; onClose: () => void }) {
    const host = document.querySelector('.entropy-app') ?? document.body
    return createPortal(
        <div className="task-modal-backdrop" role="presentation" onMouseDown={(event) => {
            if (event.target === event.currentTarget) onClose()
        }}>{children}</div>,
        host,
    )
}

export default function Tasks() {
    const [data, setData] = useState<TaskData | null>(null)
    const [selectedId, setSelectedId] = useState<number | null>(null)
    const [view, setView] = useState<'board' | 'list'>('board')
    const [creating, setCreating] = useState(false)
    const [draft, setDraft] = useState<Draft>(blank)
    const [comment, setComment] = useState('')
    const [error, setError] = useState('')
    const [busy, setBusy] = useState(false)
    const [importing, setImporting] = useState(false)
    const selected = data?.items.find((item) => item.id === selectedId) ?? null

    const refresh = useCallback(async () => {
        const response = await apiRequest<TaskData>('/api/tasks')
        setData(response)
        setSelectedId((current) => current && response.items.some((item) => item.id === current) ? current : null)
    }, [])

    useEffect(() => { void refresh().catch((reason: Error) => setError(reason.message)) }, [refresh])

    const updateDraft = (key: keyof Draft, value: string) => setDraft((current) => ({ ...current, [key]: value }))
    const submit = async (event: FormEvent) => {
        event.preventDefault()
        if (!draft.title.trim()) return
        setBusy(true); setError('')
        try {
            const created = await apiRequest<Task>('/api/tasks', {
                method: 'POST', headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ ...draft, title: draft.title.trim(), assignee: draft.assignee || null, reminder_at: reminderValue(draft.reminder_at) }),
            })
            setCreating(false); setDraft(blank); await refresh(); setSelectedId(created.id)
        } catch (reason) { setError((reason as Error).message) } finally { setBusy(false) }
    }

    const save = async (changes: Partial<Task>) => {
        if (!selected) return
        setError('')
        try {
            await apiRequest<Task>(`/api/tasks/${selected.id}`, {
                method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(changes),
            })
            await refresh()
        } catch (reason) { setError((reason as Error).message) }
    }

    const ordered = useMemo(() => data?.items ?? [], [data])
    const addComment = async (event: FormEvent) => {
        event.preventDefault()
        if (!selected || !comment.trim()) return
        try {
            await apiRequest(`/api/tasks/${selected.id}/comments`, {
                method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ body: comment.trim() }),
            })
            setComment(''); await refresh()
        } catch (reason) { setError((reason as Error).message) }
    }
    const toggleFollow = async () => {
        if (!selected) return
        try {
            await apiRequest(`/api/tasks/${selected.id}/follow`, {
                method: 'PUT', headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ following: !selected.follower_ids.includes(data?.user_id ?? -1) }),
            })
            await refresh()
        } catch (reason) { setError((reason as Error).message) }
    }
    const move = async (taskId: number, status: Status) => {
        try {
            await apiRequest(`/api/tasks/${taskId}`, { method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ status }) })
            await refresh()
        } catch (reason) { setError((reason as Error).message) }
    }

    const exportJiraCsv = () => {
        const rows = [
            ['Issue Type', 'Summary', 'Description', 'Status', 'Assignee', 'Labels'],
            ...(data?.items ?? []).map((task) => [
                'Task', task.title, task.description,
                task.status === 'todo' ? 'To Do' : task.status === 'in_progress' ? 'In Progress' : 'Done',
                task.assignee ?? '', 'entropy-task',
            ]),
        ]
        const blob = new Blob([`\uFEFF${rows.map((row) => row.map(csvCell).join(',')).join('\r\n')}`], { type: 'text/csv;charset=utf-8' })
        const url = URL.createObjectURL(blob)
        const link = document.createElement('a'); link.href = url; link.download = 'entropy-tasks-jira.csv'; link.click()
        URL.revokeObjectURL(url)
    }

    const importJiraDump = async (file?: File) => {
        if (!file) return
        setImporting(true); setError('')
        try {
            const text = await file.text()
            let drafts: { title: string; description: string; status: Status; assignee: string }[]
            if (file.name.toLowerCase().endsWith('.json')) {
                const parsed: unknown = JSON.parse(text)
                const issues = Array.isArray(parsed) ? parsed : (parsed as { issues?: unknown[] } | null)?.issues
                if (!Array.isArray(issues)) throw new Error('Jira JSON must contain an issues array.')
                drafts = issues.map((entry) => {
                    const issue = entry as { fields?: Record<string, unknown> }
                    const fields = issue.fields ?? entry as Record<string, unknown>
                    const summary = String(fields.summary ?? fields.title ?? '').trim()
                    const description = jiraDescription(fields.description).trim()
                    const statusValue = String((fields.status as { name?: string } | string | undefined) && typeof fields.status === 'object' ? (fields.status as { name?: string }).name ?? '' : fields.status ?? '').toLowerCase()
                    const assigneeValue = fields.assignee as { name?: string; displayName?: string } | string | undefined
                    return { title: summary, description, status: statusValue.includes('progress') ? 'in_progress' : statusValue === 'done' || statusValue === 'closed' ? 'done' : 'todo', assignee: typeof assigneeValue === 'string' ? assigneeValue : assigneeValue?.name ?? assigneeValue?.displayName ?? '' }
                })
            } else {
                const rows = parseCsv(text)
                if (rows.length < 2) throw new Error('The Jira CSV has no task rows.')
                const headers = rows[0].map((value) => value.trim().replace(/^\uFEFF/, '').toLowerCase())
                if (!headers.some((header) => ['summary', 'title'].includes(header))) throw new Error('The Jira CSV must include a Summary column.')
                drafts = rows.slice(1).map((values) => {
                    const record = Object.fromEntries(headers.map((header, index) => [header, values[index] ?? '']))
                    const statusValue = jiraField(record, 'status').toLowerCase()
                    return { title: jiraField(record, 'summary', 'title'), description: jiraField(record, 'description'), status: statusValue.includes('progress') ? 'in_progress' : ['done', 'closed', 'resolved'].includes(statusValue) ? 'done' : 'todo', assignee: jiraField(record, 'assignee') }
                })
            }
            drafts = drafts.filter((item) => item.title.trim())
            if (!drafts.length) throw new Error('No tasks with a Summary were found in the Jira dump.')
            for (const task of drafts) {
                const assignee = data?.members.find((member) => member.username.toLowerCase() === task.assignee.toLowerCase())?.username ?? null
                const created = await apiRequest<Task>('/api/tasks', {
                method: 'POST', headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ title: task.title.slice(0, 200), description: task.description.slice(0, 10000), remarks: '', assignee, reminder_at: null }),
                })
                if (task.status !== 'todo') await apiRequest(`/api/tasks/${created.id}`, {
                    method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ status: task.status }),
                })
            }
            await refresh()
        } catch (reason) { setError((reason as Error).message) } finally { setImporting(false) }
    }

    return (
        <div className="tasks-tool">
            <div className="tasks-toolbar">
                <div><h3>Project tasks</h3><p>Assign and track work with your project members.</p></div>
                <div className="tasks-actions">
                    <div className="tasks-view-switch" aria-label="Task view">
                        <button className={view === 'board' ? 'active' : ''} onClick={() => setView('board')} title="Board view"><Columns3 size={16} /> Board</button>
                        <button className={view === 'list' ? 'active' : ''} onClick={() => setView('list')} title="List view"><List size={16} /> List</button>
                    </div>
                    <button className="entropy-button entropy-button-secondary entropy-button-sm" onClick={() => void refresh()} title="Refresh tasks"><RefreshCw size={15} /></button>
                    <button className="entropy-button entropy-button-secondary entropy-button-sm" onClick={exportJiraCsv} disabled={!ordered.length} title="Export Jira-compatible CSV"><Download size={15} /> Export Jira CSV</button>
                    {data?.permissions['tasks.create'] && <label className="entropy-button entropy-button-secondary entropy-button-sm tasks-import-button" title="Import Jira CSV or JSON dump"><Upload size={15} /> {importing ? 'Importing…' : 'Import Jira'}<input type="file" accept=".csv,.json,text/csv,application/json" disabled={importing} onChange={(event) => { void importJiraDump(event.currentTarget.files?.[0]); event.currentTarget.value = '' }} /></label>}
                    {data?.permissions['tasks.create'] && <button className="entropy-button entropy-button-primary entropy-button-sm" onClick={() => { setCreating(true); setDraft(blank) }}><Plus size={16} /> New task</button>}
                </div>
            </div>

            {error && <div className="entropy-alert entropy-alert-error" role="alert">{error}</div>}
            {!data ? <div className="tasks-loading">Loading project tasks…</div> : ordered.length === 0 ? (
                <div className="tasks-empty"><ListTodo size={26} /><strong>No tasks yet</strong><span>Create a task to organize work for this project.</span></div>
            ) : view === 'board' ? (
                <div className="tasks-board">
                    {columns.map((column) => <section className="tasks-column" key={column.id} onDragOver={(event) => event.preventDefault()} onDrop={(event) => { event.preventDefault(); const id = Number(event.dataTransfer.getData('text/task-id')); if (id && data.permissions['tasks.manage']) void move(id, column.id) }}>
                        <header><strong>{column.title}</strong><span>{ordered.filter((task) => task.status === column.id).length}</span></header>
                        <div className="tasks-column-body">{ordered.filter((task) => task.status === column.id).map((task) => <button key={task.id} className={`task-card${selectedId === task.id ? ' selected' : ''}`} draggable={data.permissions['tasks.manage']} onDragStart={(event) => event.dataTransfer.setData('text/task-id', String(task.id))} onClick={() => setSelectedId(task.id)}>
                            <strong>{task.title}</strong>{task.description && <span className="task-card-description">{task.description}</span>}
                            <span className="task-card-meta">{task.assignee && <span><UserRound size={13} /> {task.assignee}</span>}<span><MessageSquare size={13} /> {task.comments.length}</span>{task.reminder_at && <span title={`Reminder ${localDate(task.reminder_at)}`}><Bell size={13} /></span>}</span>
                        </button>)}</div>
                    </section>)}
                </div>
            ) : (
                <div className="tasks-list" role="table" aria-label="Project tasks">
                    <div className="tasks-list-row tasks-list-head" role="row"><span>Task</span><span>Status</span><span>Assignee</span><span>Reminder</span><span>Comments</span></div>
                    {ordered.map((task) => <button className={`tasks-list-row${selectedId === task.id ? ' selected' : ''}`} key={task.id} onClick={() => setSelectedId(task.id)} role="row"><strong>{task.title}</strong><span>{columns.find((item) => item.id === task.status)?.title}</span><span>{task.assignee || 'Unassigned'}</span><span>{localDate(task.reminder_at) || '—'}</span><span>{task.comments.length}</span></button>)}
                </div>
            )}

            {creating && <TaskModalLayer onClose={() => setCreating(false)}><form className="task-dialog" onSubmit={(event) => void submit(event)}>
                <header><div><h3>Create task</h3><p>Task will be added to the active project.</p></div><button type="button" className="entropy-button entropy-button-ghost entropy-button-sm" onClick={() => setCreating(false)} aria-label="Close"><X size={18} /></button></header>
                <label>Title<input autoFocus maxLength={200} value={draft.title} onChange={(event) => updateDraft('title', event.target.value)} required /></label>
                <label>Description<textarea rows={3} value={draft.description} onChange={(event) => updateDraft('description', event.target.value)} /></label>
                <label>Remarks<textarea rows={2} value={draft.remarks} onChange={(event) => updateDraft('remarks', event.target.value)} /></label>
                <label>Assign to<select value={draft.assignee} onChange={(event) => updateDraft('assignee', event.target.value)}><option value="">Unassigned</option>{data?.members.map((member) => <option key={member.username} value={member.username}>{member.full_name ? `${member.full_name} (${member.username})` : member.username}</option>)}</select></label>
                <label className="task-reminder-label">Reminder{!data?.mail_ready && <small>Email reminders need SMTP configuration in Administration → Settings.</small>}<input type="datetime-local" value={draft.reminder_at} onChange={(event) => updateDraft('reminder_at', event.target.value)} /></label>
                <footer><button type="button" className="entropy-button entropy-button-secondary" onClick={() => setCreating(false)}>Cancel</button><button type="submit" className="entropy-button entropy-button-primary" disabled={busy || !draft.title.trim()}>{busy ? 'Creating…' : 'Create task'}</button></footer>
            </form></TaskModalLayer>}

            {selected && <TaskModalLayer onClose={() => setSelectedId(null)}><section className="task-dialog task-detail">
                <header><div><span className="task-eyebrow">TASK #{selected.id}</span><h3>{selected.title}</h3></div><button className="entropy-button entropy-button-ghost entropy-button-sm" onClick={() => setSelectedId(null)} aria-label="Close"><X size={18} /></button></header>
                <div className="task-detail-scroll">
                    <label>Status<select disabled={!data?.permissions['tasks.manage']} value={selected.status} onChange={(event) => void save({ status: event.target.value as Status })}>{columns.map((column) => <option key={column.id} value={column.id}>{column.title}</option>)}</select></label>
                    <label>Assignee<select disabled={!data?.permissions['tasks.manage']} value={selected.assignee ?? ''} onChange={(event) => void save({ assignee: event.target.value || null })}><option value="">Unassigned</option>{data?.members.map((member) => <option key={member.username} value={member.username}>{member.full_name ? `${member.full_name} (${member.username})` : member.username}</option>)}</select></label>
                    <div className="task-detail-info"><span>Created by <strong>{selected.creator}</strong></span><span>Updated {localDate(selected.updated_at)}</span></div>
                    {data?.permissions['tasks.manage'] ? <>
                        <label>Description<textarea key={`${selected.id}-description`} defaultValue={selected.description} rows={3} onBlur={(event) => { if (event.target.value !== selected.description) void save({ description: event.target.value }) }} /></label>
                        <label>Remarks<textarea key={`${selected.id}-remarks`} defaultValue={selected.remarks} rows={2} onBlur={(event) => { if (event.target.value !== selected.remarks) void save({ remarks: event.target.value }) }} /></label>
                        <label className="task-reminder-label">Reminder{!data.mail_ready && <small>Email reminders need SMTP configuration in Administration → Settings.</small>}<input type="datetime-local" value={selected.reminder_at ? new Date(new Date(selected.reminder_at).getTime() - new Date(selected.reminder_at).getTimezoneOffset() * 60000).toISOString().slice(0,16) : ''} onChange={(event) => void save({ reminder_at: reminderValue(event.target.value) })} /></label>
                    </> : <><p className="task-description">{selected.description || 'No description.'}</p>{selected.remarks && <p className="task-remarks">{selected.remarks}</p>}{selected.reminder_at && <p className="task-detail-info"><Bell size={14} /> Reminder {localDate(selected.reminder_at)}</p>}</>}
                    {data?.permissions['tasks.follow'] && <button type="button" className="entropy-button entropy-button-secondary entropy-button-sm" onClick={() => void toggleFollow()}>{selected.follower_ids.includes(data.user_id) ? <><Check size={15} /> Following</> : 'Follow task'}</button>}
                    <section className="task-comments"><h4><MessageSquare size={16} /> Comments <span>{selected.comments.length}</span></h4>
                        {selected.comments.length ? selected.comments.map((item) => <article key={item.id}><div><strong>{item.author}</strong><time>{localDate(item.created_at)}</time></div><p>{item.body}</p></article>) : <p className="task-no-comments">No comments yet.</p>}
                        {data?.permissions['tasks.comment'] && <form onSubmit={(event) => void addComment(event)}><textarea rows={2} placeholder="Write a comment…" value={comment} onChange={(event) => setComment(event.target.value)} /><button className="entropy-button entropy-button-primary entropy-button-sm" disabled={!comment.trim()}><Send size={14} /> Comment</button></form>}
                    </section>
                </div>
            </section></TaskModalLayer>}
        </div>
    )
}
