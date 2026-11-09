import { useCallback, useEffect, useMemo, useState, useRef } from 'react'
import {
    Bell,
    CalendarClock,
    Columns3,
    FileText,
    Download,
    Layers,
    Link2,
    List,
    ListTodo,
    MessageSquare,
    Paperclip,
    Plus,
    RefreshCw,
    Search,
    Settings2,
    Trash2,
    Upload,
    UserRound, Repeat } from 'lucide-react'

import EntropyLoader from '../../../components/feedback/EntropyLoader'
import Pagination from '../../../components/layout/Pagination'
import SelectionBar from '../../../components/layout/SelectionBar'
import { usePagination } from '../../../components/layout/usePagination'
import { currentProject, setCurrentProject } from '../../../services/project'
import { taskIdFromHash } from './navigation'
import { useFeedback } from '../../../components/feedback/FeedbackProvider'
import { plainText } from './markup'
import { CreatePanel, DetailPanel, GroupsPanel, ImportPanel, ReportPanel, SettingsPanel } from './TaskPanels'
import { useStatusChange } from './statusChange'
import TypeIcon from './TypeIcon'
import {
    STATUSES,
    exportJiraCsv,
    isOverdue,
    localDate,
    SEVERITIES,
    severityTitle,
    statusTitle,
    tasksApi,
    typeLabel,
    type Status,
    type Task,
    type TaskData,
    memberName,
} from './model'
import './tasks.css'
import { inChunks } from '../../../services/chunks'

type PanelState =
    | { kind: 'create' }
    | { kind: 'task'; id: number }
    | { kind: 'groups' }
    | { kind: 'settings' }
    | { kind: 'import' }
    | { kind: 'report' }
    | null

const VIEW_KEY = 'entropy.tasks.view'

function storedView(): 'board' | 'list' {
    try {
        return window.localStorage.getItem(VIEW_KEY) === 'list' ? 'list' : 'board'
    } catch {
        return 'board'
    }
}

const LIVE_POLL_MS = 5_000
const LIVE_POLL_MAX_MS = 60_000

/** The group filter's value for tasks in no group; real group ids are positive. */
const NO_GROUP = -1

export default function Tasks() {
    const { notify, modal } = useFeedback()
    const [data, setData] = useState<TaskData | null>(null)
    const [panel, setPanel] = useState<PanelState>(null)
    // The version `data` was loaded at, for the live check below.
    const shownVersion = useRef<number | null>(null)
    // A task named by the address (from an alert), until it is opened.
    const [wantedTask, setWantedTask] = useState<number | null>(() => taskIdFromHash(window.location.hash))
    const [popup, setPopup] = useState(false)
    const [view, setViewState] = useState<'board' | 'list'>(storedView)
    const [query, setQuery] = useState('')
    const [typeFilter, setTypeFilter] = useState('')
    const [severityFilter, setSeverityFilter] = useState('')
    const [groupFilter, setGroupFilter] = useState<number | null>(null)
    const [assigneeFilter, setAssigneeFilter] = useState('')
    const [selection, setSelection] = useState<number[]>([])
    const checkStatus = useStatusChange()

    const setView = (next: 'board' | 'list') => {
        setViewState(next)
        try {
            window.localStorage.setItem(VIEW_KEY, next)
        } catch {
            // Only a convenience.
        }
    }

    const refresh = useCallback(async () => {
        try {
            const response = await tasksApi.load()
            setData(response)
            setSelection((current) => current.filter((id) => response.items.some((item) => item.id === id)))
        } catch (cause) {
            notify.error(cause instanceof Error ? cause.message : 'Unable to load the tasks.', { title: 'Tasks' })
        }
    }, [notify])

    useEffect(() => {
        let active = true
        tasksApi
            .load()
            .then((response) => active && setData(response))
            .catch((cause: unknown) =>
                notify.error(cause instanceof Error ? cause.message : 'Unable to load the tasks.', { title: 'Tasks' }),
            )
        return () => {
            active = false
        }
    }, [notify])

    useEffect(() => {
        const follow = () => {
            const id = taskIdFromHash(window.location.hash)
            if (id !== null) setWantedTask(id)
        }
        window.addEventListener('popstate', follow)
        return () => window.removeEventListener('popstate', follow)
    }, [])

    // Live: ask often whether anything changed (one small request), and reload only when it did.
    useEffect(() => {
        let alive = true
        let timer: number | undefined
        let busy = false
        let delay = LIVE_POLL_MS

        const check = async () => {
            window.clearTimeout(timer)
            if (busy) return
            if (!document.hidden) {
                busy = true
                try {
                    const { version } = await tasksApi.version()
                    if (shownVersion.current !== null && version !== shownVersion.current) {
                        const response = await tasksApi.load()
                        if (alive) {
                            setData(response)
                            setSelection((current) =>
                                current.filter((id) => response.items.some((item) => item.id === id)),
                            )
                        }
                    }
                    delay = LIVE_POLL_MS
                } catch {
                    // The server may be restarting: try less often, and say nothing.
                    delay = Math.min(delay * 2, LIVE_POLL_MAX_MS)
                } finally {
                    busy = false
                }
            }
            if (alive) timer = window.setTimeout(() => void check(), delay)
        }

        const now = () => void check()
        timer = window.setTimeout(now, LIVE_POLL_MS)
        window.addEventListener('focus', now)
        document.addEventListener('visibilitychange', now)
        return () => {
            alive = false
            window.clearTimeout(timer)
            window.removeEventListener('focus', now)
            document.removeEventListener('visibilitychange', now)
        }
    }, [])

    if (wantedTask !== null && data?.items.some((item) => item.id === wantedTask)) {
        setPanel({ kind: 'task', id: wantedTask })
        setWantedTask(null)
    }

    useEffect(() => {
        shownVersion.current = data?.version ?? null
    }, [data])

    // Opened or gone: clear the address, so the same alert can open it again.
    useEffect(() => {
        if (wantedTask === null && taskIdFromHash(window.location.hash) !== null) {
            window.history.replaceState(null, '', '#/tools/tasks')
        }
    }, [wantedTask])

    // Not in this project: the alert may be from another. Switching project reloads this page.
    useEffect(() => {
        if (wantedTask === null || !data || data.items.some((item) => item.id === wantedTask)) return
        let active = true
        tasksApi
            .project(wantedTask)
            .then(({ project }) => {
                if (!active) return
                if (project !== currentProject()) {
                    setCurrentProject(project)
                } else {
                    // Listed as another project's, or just deleted.
                    setWantedTask(null)
                }
            })
            .catch((cause: unknown) => {
                if (!active) return
                setWantedTask(null)
                notify.warning(cause instanceof Error ? cause.message : 'That task cannot be opened.', {
                    title: 'Task not opened',
                })
            })
        return () => {
            active = false
        }
    }, [wantedTask, data, notify])

    // A task deleted elsewhere closes its panel.
    const selected = panel?.kind === 'task' ? data?.items.find((item) => item.id === panel.id) ?? null : null

    const groupsById = useMemo(() => new Map((data?.groups ?? []).map((group) => [group.id, group])), [data])

    const visible = useMemo(() => {
        if (!data) return []
        const needle = query.trim().toLowerCase()
        return data.items.filter((task) => {
            if (typeFilter && task.type !== typeFilter) return false
            if (severityFilter && (task.severity ?? 'medium') !== severityFilter) return false
            if (groupFilter === NO_GROUP ? task.group_ids.length > 0 : groupFilter && !task.group_ids.includes(groupFilter)) return false
            if (assigneeFilter === '__me' && task.assignee?.toLowerCase() !== data.username.toLowerCase()) return false
            if (assigneeFilter === '__none' && task.assignee) return false
            if (assigneeFilter && !assigneeFilter.startsWith('__') && task.assignee !== assigneeFilter) return false
            if (!needle) return true
            const assignee = task.assignee ? [task.assignee, memberName(data.members, task.assignee)] : []
            return [task.key, task.title, task.external_ref ?? '', task.description, ...assignee]
                .some((value) => value.toLowerCase().includes(needle))
        })
    }, [data, query, typeFilter, severityFilter, groupFilter, assigneeFilter])
    const paging = usePagination(visible, 'tasks')
    const shown = paging.pageItems

    const move = async (task: Task, status: Status) => {
        const change = await checkStatus(task, status)
        if (!change) return
        try {
            await tasksApi.update(task.id, change)
            await refresh()
        } catch (cause) {
            notify.error((cause as Error).message, { title: `Unable to move ${task.key}` })
        }
    }

    const addSelectionToGroup = async (groupId: number) => {
        const group = groupsById.get(groupId)
        if (!group) return
        try {
            // The endpoint takes 1000 per request.
            for (const part of inChunks(selection, 1000)) await tasksApi.updateGroup(groupId, { add_task_ids: part })
            notify.success(`${selection.length} task${selection.length === 1 ? '' : 's'} added to “${group.name}”.`, { title: 'Grouped' })
            setSelection([])
            await refresh()
        } catch (cause) {
            notify.error((cause as Error).message, { title: 'Unable to group the tasks' })
        }
    }

    const deleteSelection = async () => {
        const confirmed = await modal.confirm({
            title: `Delete ${selection.length} task${selection.length === 1 ? '' : 's'}?`,
            message: 'They are removed with their comments and attachments. This cannot be undone.',
            confirmText: 'Delete',
            cancelText: 'Cancel',
            destructive: true,
        })
        if (!confirmed) return
        const failed: string[] = []
        for (const id of selection) {
            try {
                await tasksApi.remove(id)
            } catch {
                failed.push(data?.items.find((item) => item.id === id)?.key ?? String(id))
            }
        }
        if (failed.length) notify.error(`Not deleted: ${failed.join(', ')}.`, { title: 'Some tasks were not deleted' })
        else notify.success(`${selection.length} task${selection.length === 1 ? '' : 's'} deleted.`, { title: 'Tasks deleted' })
        setSelection([])
        await refresh()
    }

    if (!data) {
        return (
            <div className="tasks-tool">
                <EntropyLoader label="Loading project tasks…" />
            </div>
        )
    }

    const permissions = data.permissions
    const filtering = Boolean(query || typeFilter || severityFilter || groupFilter || assigneeFilter)
    const activeGroup = groupFilter ? groupsById.get(groupFilter) : null
    const allSelected = shown.length > 0 && shown.every((task) => selection.includes(task.id))

    const meta = (task: Task) => (
        <span className="task-card-meta">
            <span className={`task-severity severity-${task.severity ?? 'medium'}`} title="Severity">{severityTitle(task.severity)}</span>
            {task.assignee && <span title={task.assignee}><UserRound size={13} /> {memberName(data.members, task.assignee)}</span>}
            {task.comments.length > 0 && <span><MessageSquare size={13} /> {task.comments.length}</span>}
            {task.attachments.length > 0 && <span><Paperclip size={13} /> {task.attachments.length}</span>}
            {task.reminder_at && <span title={`Reminder ${localDate(task.reminder_at)}`}><Bell size={13} /></span>}
            {task.due_date && (
                <span className={isOverdue(task) ? 'task-overdue' : ''} title={isOverdue(task) ? 'Overdue' : 'Due date'}>
                    <CalendarClock size={13} /> {task.due_date}{task.due_time ? ` ${task.due_time}` : ''}
                    {task.due_repeat && <Repeat size={12} aria-label={`Repeats ${task.due_repeat}`} />}
                </span>
            )}
        </span>
    )

    const keyLabel = (task: Task) => {
        return (
            <span className={`task-key type-${task.type}`} title={typeLabel(task.type)}>
                <TypeIcon type={task.type} /> {task.key}
                {task.external_ref && <span className="task-ext"><Link2 size={11} /> {task.external_ref}</span>}
            </span>
        )
    }

    const groupChips = (task: Task, limit = 2) => {
        const groups = task.group_ids.map((id) => groupsById.get(id)).filter(Boolean)
        if (!groups.length) return null
        return (
            <span className="task-card-groups">
                {groups.slice(0, limit).map((group) => (
                    <span key={group!.id} className={`task-group-chip kind-${group!.kind}`}>{group!.name}</span>
                ))}
                {groups.length > limit && <span className="task-group-chip">+{groups.length - limit}</span>}
            </span>
        )
    }

    return (
        <div className={`tasks-tool${panel && !(panel.kind === 'task' && popup) ? ' has-panel' : ''}`}>
            <div className="tasks-toolbar">
                <div className="tasks-actions">
                    <div className="tasks-view-switch" aria-label="Task view">
                        <button className={view === 'board' ? 'active' : ''} onClick={() => setView('board')} title="Board view"><Columns3 size={16} /> Board</button>
                        <button className={view === 'list' ? 'active' : ''} onClick={() => setView('list')} title="List view"><List size={16} /> List</button>
                    </div>
                    <label className="tasks-search">
                        <Search size={15} />
                        <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search key, title, reference…" aria-label="Search tasks" />
                    </label>
                    <select value={typeFilter} onChange={(event) => setTypeFilter(event.target.value)} aria-label="Filter by type">
                        <option value="">All types</option>
                        {data.settings.types.map((type) => <option key={type} value={type}>{typeLabel(type)}</option>)}
                    </select>
                    <select value={severityFilter} onChange={(event) => setSeverityFilter(event.target.value)} aria-label="Filter by severity">
                        <option value="">All severities</option>
                        {SEVERITIES.map((severity) => <option key={severity.id} value={severity.id}>{severity.title}</option>)}
                    </select>
                    <select value={groupFilter ?? ''} onChange={(event) => setGroupFilter(event.target.value ? Number(event.target.value) : null)} aria-label="Filter by group">
                        <option value="">All groups</option>
                        <option value={NO_GROUP}>No group</option>
                        {data.groups.map((group) => <option key={group.id} value={group.id}>{group.name}</option>)}
                    </select>
                    <select value={assigneeFilter} onChange={(event) => setAssigneeFilter(event.target.value)} aria-label="Filter by assignee">
                        <option value="">Everyone</option>
                        <option value="__me">Assigned to me</option>
                        <option value="__none">Unassigned</option>
                        {data.members.map((member) => <option key={member.username} value={member.username}>{member.full_name?.trim() || member.username}</option>)}
                    </select>
                </div>
                <div className="tasks-actions">
                    <button className="entropy-button entropy-button-secondary entropy-button-sm" onClick={() => void refresh()} title="Refresh tasks" aria-label="Refresh tasks"><RefreshCw size={15} /></button>
                    <button className={`entropy-button entropy-button-secondary entropy-button-sm${panel?.kind === 'groups' ? ' is-active' : ''}`} onClick={() => setPanel(panel?.kind === 'groups' ? null : { kind: 'groups' })}><Layers size={15} /> Groups</button>
                    <button className={`entropy-button entropy-button-secondary entropy-button-sm${panel?.kind === 'report' ? ' is-active' : ''}`} onClick={() => setPanel(panel?.kind === 'report' ? null : { kind: 'report' })} disabled={!data.items.length} title="HTML or PDF report for sharing"><FileText size={15} /> Report</button>
                    <button className="entropy-button entropy-button-secondary entropy-button-sm" onClick={() => exportJiraCsv(data)} disabled={!data.items.length} title="Export a CSV Jira can import"><Download size={15} /> Export</button>
                    {permissions['tasks.create'] && <button className="entropy-button entropy-button-secondary entropy-button-sm" onClick={() => setPanel({ kind: 'import' })} title="Import a Jira XML, CSV or JSON export"><Upload size={15} /> Import Jira</button>}
                    {permissions['tasks.manage'] && <button className="entropy-button entropy-button-secondary entropy-button-sm" onClick={() => setPanel({ kind: 'settings' })} title="Key prefix and task types" aria-label="Task settings"><Settings2 size={15} /></button>}
                    {permissions['tasks.create'] && <button className="entropy-button entropy-button-primary entropy-button-sm" onClick={() => setPanel({ kind: 'create' })}><Plus size={16} /> New task</button>}
                </div>
            </div>

            {activeGroup && (
                <div className="tasks-group-banner">
                    <span className={`task-group-chip kind-${activeGroup.kind}`}>{activeGroup.kind}</span>
                    <strong>{activeGroup.name}</strong>
                    {activeGroup.external_ref && <span className="task-muted">{activeGroup.external_ref}</span>}
                    <span className="task-muted">{visible.length} task{visible.length === 1 ? '' : 's'}</span>
                    <button className="entropy-button entropy-button-ghost entropy-button-sm" onClick={() => setGroupFilter(null)}>Show all tasks</button>
                </div>
            )}

            <div className="tasks-layout">
                <div className="tasks-main">
                    {data.items.length === 0 ? (
                        <div className="tasks-empty">
                            <ListTodo size={26} />
                            <strong>No tasks yet</strong>
                            <span>Create a task, or import issues from Jira.</span>
                        </div>
                    ) : visible.length === 0 ? (
                        <div className="tasks-empty">
                            <Search size={24} />
                            <strong>No task matches</strong>
                            {filtering && <button className="entropy-button entropy-button-secondary entropy-button-sm" onClick={() => { setQuery(''); setTypeFilter(''); setSeverityFilter(''); setGroupFilter(null); setAssigneeFilter('') }}>Clear filters</button>}
                        </div>
                    ) : view === 'board' ? (
                        <div className="tasks-board">
                            {STATUSES.map((column) => {
                                const items = shown.filter((task) => task.status === column.id)
                                const columnTotal = visible.filter((task) => task.status === column.id).length
                                return (
                                    <section className="tasks-column" key={column.id} onDragOver={(event) => event.preventDefault()} onDrop={(event) => {
                                        event.preventDefault()
                                        const task = data.items.find((item) => item.id === Number(event.dataTransfer.getData('text/task-id')))
                                        if (task && permissions['tasks.manage']) void move(task, column.id)
                                    }}>
                                        <header><strong>{column.title}</strong><span title={columnTotal > items.length ? `${items.length} on this page of ${columnTotal}` : undefined}>{columnTotal > items.length ? `${items.length}/${columnTotal}` : items.length}</span></header>
                                        <div className="tasks-column-body">
                                            {items.map((task) => (
                                                <button key={task.id} className={`task-card${selected?.id === task.id ? ' selected' : ''}`} draggable={permissions['tasks.manage']} onDragStart={(event) => event.dataTransfer.setData('text/task-id', String(task.id))} onClick={() => setPanel({ kind: 'task', id: task.id })}>
                                                    {keyLabel(task)}
                                                    <strong>{task.title}</strong>
                                                    {task.description && <span className="task-card-description">{plainText(task.description)}</span>}
                                                    {groupChips(task)}
                                                    {meta(task)}
                                                </button>
                                            ))}
                                        </div>
                                    </section>
                                )
                            })}
                        </div>
                    ) : (
                        <>
                            {selection.length > 0 && (
                                <div className="tasks-bulk" role="toolbar" aria-label="Selected tasks">
                                    <strong>{selection.length} selected</strong>
                                    {permissions['tasks.manage'] && data.groups.length > 0 && (
                                        <select value="" aria-label="Add selected tasks to a group" onChange={(event) => event.target.value && void addSelectionToGroup(Number(event.target.value))}>
                                            <option value="">Add to group…</option>
                                            {data.groups.map((group) => <option key={group.id} value={group.id}>{group.name}</option>)}
                                        </select>
                                    )}
                                    {permissions['tasks.manage'] && data.groups.length === 0 && (
                                        <button className="entropy-button entropy-button-secondary entropy-button-sm" onClick={() => setPanel({ kind: 'groups' })}><Layers size={14} /> Create a group first</button>
                                    )}
                                    {permissions['tasks.manage'] && (
                                        <button className="entropy-button entropy-button-ghost entropy-button-sm task-delete" onClick={() => void deleteSelection()}><Trash2 size={14} /> Delete</button>
                                    )}
                                    <button className="entropy-button entropy-button-ghost entropy-button-sm" onClick={() => setSelection([])}>Clear</button>
                                </div>
                            )}
                            <SelectionBar
                                noun="tasks"
                                pageCount={shown.length}
                                total={visible.length}
                                pageSelected={shown.filter((task) => selection.includes(task.id)).length}
                                selectedCount={selection.length}
                                onSelectPage={() => setSelection(shown.map((task) => task.id))}
                                onSelectAll={() => setSelection(visible.map((task) => task.id))}
                                onClear={() => setSelection([])}
                            />
                            <div className="tasks-list" role="table" aria-label="Project tasks">
                                <div className="tasks-list-row tasks-list-head" role="row">
                                    <input type="checkbox" aria-label="Select all tasks on this page" checked={allSelected} onChange={() => setSelection((current) => allSelected ? current.filter((id) => !shown.some((task) => task.id === id)) : [...new Set([...current, ...shown.map((task) => task.id)])])} />
                                    <span>Key</span><span>Task</span><span>Status</span><span>Assignee</span><span>Groups</span><span>Updated</span>
                                </div>
                                {shown.map((task) => (
                                    <div className={`tasks-list-row${selected?.id === task.id ? ' selected' : ''}`} key={task.id} role="row">
                                        <input type="checkbox" aria-label={`Select ${task.key}`} checked={selection.includes(task.id)} onChange={() => setSelection((current) => current.includes(task.id) ? current.filter((id) => id !== task.id) : [...current, task.id])} />
                                        <button className="tasks-list-open" onClick={() => setPanel({ kind: 'task', id: task.id })}>{keyLabel(task)}</button>
                                        <button className="tasks-list-open tasks-list-title" onClick={() => setPanel({ kind: 'task', id: task.id })}>
                                            <strong>{task.title}</strong>
                                            {meta(task)}
                                        </button>
                                        <span className={`task-status status-${task.status}`}>{statusTitle(task.status)}</span>
                                        <span title={task.assignee ?? undefined}>{task.assignee ? memberName(data.members, task.assignee) : <span className="task-muted">Unassigned</span>}</span>
                                        <span>{groupChips(task, 1) ?? <span className="task-muted">—</span>}</span>
                                        <span className="task-muted">{localDate(task.updated_at)}</span>
                                    </div>
                                ))}
                            </div>
                        </>
                    )}
                    <Pagination state={paging} noun="tasks" />
                </div>

                {panel?.kind === 'create' && (
                    <CreatePanel
                        data={data}
                        initialGroup={groupFilter === NO_GROUP ? null : groupFilter}
                        onClose={() => setPanel(null)}
                        onCreated={(task, another) => {
                            void refresh()
                            if (!another) setPanel({ kind: 'task', id: task.id })
                        }}
                    />
                )}
                {panel?.kind === 'task' && selected && (
                    <DetailPanel
                        key={selected.id}
                        data={data}
                        task={selected}
                        onClose={() => {
                            setPanel(null)
                            setPopup(false)
                        }}
                        onChanged={refresh}
                        onDeleted={() => {
                            setPanel(null)
                            setPopup(false)
                            void refresh()
                        }}
                        popup={popup}
                        onPopup={setPopup}
                    />
                )}
                {panel?.kind === 'groups' && (
                    <GroupsPanel data={data} onClose={() => setPanel(null)} onChanged={refresh} activeGroup={groupFilter} onFilter={setGroupFilter} />
                )}
                {panel?.kind === 'settings' && <SettingsPanel data={data} onClose={() => setPanel(null)} onChanged={refresh} />}
                {panel?.kind === 'import' && <ImportPanel onClose={() => setPanel(null)} onImported={refresh} />}
                {panel?.kind === 'report' && (
                    <ReportPanel data={data} selection={selection} groupFilter={groupFilter === NO_GROUP ? null : groupFilter} onClose={() => setPanel(null)} onPickTasks={() => setView('list')} />
                )}
            </div>
        </div>
    )
}
