import { useState, type FormEvent } from 'react'
import { Check, Copy, Download, LoaderCircle, Plus } from 'lucide-react'

import { eagleApi, type EagleHistorySummary } from '../../../api/eagleapi.api'
import { schedulesApi, type Schedule } from '../../../api/runs.api'
import { useFeedback } from '../../../components/feedback/FeedbackProvider'
import { apiRequest } from '../../../services/api'
import { TOOLS } from '../../tools/registry'
import { formatBytes, formatWhen, limitOf, openTool, useWidgetData, type WidgetProps } from './core'
import { WidgetBody, WidgetEmpty } from './WidgetBody'

// Tool data changes slowly: automatic refreshes reload it at most twice a minute.
const TOOL_REFRESH_MS = 30_000

// ----------------------------------------------------------------------
// Tasks
// ----------------------------------------------------------------------

type TaskStatus = 'todo' | 'in_progress' | 'done'
type Task = {
    id: number
    key?: string
    title: string
    status: TaskStatus
    assignee: string | null
    creator: string
    reminder_at: string | null
    updated_at: string
}
type TaskData = {
    items: Task[]
    members: { username: string }[]
    username?: string
    permissions: { 'tasks.create': boolean; 'tasks.manage': boolean }
}

const TASK_LABELS: Record<TaskStatus, string> = { todo: 'To do', in_progress: 'In progress', done: 'Done' }

export function TasksWidget(props: WidgetProps) {
    const { notify } = useFeedback()
    const state = useWidgetData(() => apiRequest<TaskData>('/api/tasks'), props, TOOL_REFRESH_MS)
    const [title, setTitle] = useState('')
    const [busy, setBusy] = useState<number | 'new' | null>(null)
    const filter = String(props.settings.filter ?? 'open')
    const limit = limitOf(props.settings, 8)
    const quickAdd = props.settings.quick_add !== false

    const add = async (event: FormEvent, data: TaskData) => {
        event.preventDefault()
        const text = title.trim()
        if (!text) return
        setBusy('new')
        // In "my tasks", a new task is the user's own (tasks go to project members only).
        const member = data.members.some((item) => item.username === data.username)
        const assignee = filter === 'mine' && member ? data.username ?? null : null
        try {
            await apiRequest('/api/tasks', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ title: text, assignee }),
            })
            setTitle('')
            if (filter === 'mine' && !assignee) {
                notify.info('It is not assigned to you: you are not a member of this project.', { title: 'Task added' })
            }
            state.reload()
        } catch (cause) {
            notify.error((cause as Error).message, { title: 'Unable to add the task' })
        } finally {
            setBusy(null)
        }
    }

    const toggle = async (task: Task) => {
        setBusy(task.id)
        try {
            await apiRequest(`/api/tasks/${task.id}`, {
                method: 'PATCH',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ status: task.status === 'done' ? 'todo' : 'done' }),
            })
            state.reload()
        } catch (cause) {
            notify.error((cause as Error).message, { title: 'Unable to update the task' })
        } finally {
            setBusy(null)
        }
    }

    return (
        <WidgetBody state={state} tool="Tasks">
            {(data) => {
                const counts = { todo: 0, in_progress: 0, done: 0 }
                data.items.forEach((task) => (counts[task.status] += 1))
                const items = data.items
                    .filter((task) =>
                        filter === 'mine'
                            ? task.assignee === data.username && task.status !== 'done'
                            : filter === 'open'
                              ? task.status !== 'done'
                              : filter === 'done'
                                ? task.status === 'done'
                                : true,
                    )
                    .slice(0, limit)
                return (
                    <div className="dw-tasks">
                        <div className="dw-counts">
                            {(Object.keys(TASK_LABELS) as TaskStatus[]).map((status) => (
                                <span key={status} className={`dw-count dw-task-${status}`}>
                                    <strong>{counts[status]}</strong> {TASK_LABELS[status]}
                                </span>
                            ))}
                        </div>
                        {quickAdd && data.permissions['tasks.create'] && (
                            <form className="dw-add" onSubmit={(event) => void add(event, data)}>
                                <input
                                    value={title}
                                    onChange={(event) => setTitle(event.target.value)}
                                    placeholder={filter === 'mine' ? 'Add a task for me…' : 'Add a task…'}
                                    aria-label="New task title"
                                    maxLength={200}
                                />
                                <button
                                    type="submit"
                                    className="entropy-button entropy-button-primary entropy-button-sm"
                                    disabled={!title.trim() || busy === 'new'}
                                    aria-label="Add task"
                                >
                                    {busy === 'new' ? <LoaderCircle size={14} className="entropy-spin" /> : <Plus size={14} />}
                                </button>
                            </form>
                        )}
                        {items.length === 0 ? (
                            <WidgetEmpty>{filter === 'mine' ? 'Nothing assigned to you.' : 'No tasks here.'}</WidgetEmpty>
                        ) : (
                            <ul className="dw-list">
                                {items.map((task) => (
                                    <li key={task.id} className={`dw-row${task.status === 'done' ? ' is-done' : ''}`}>
                                        <button
                                            type="button"
                                            className="dw-check"
                                            role="checkbox"
                                            aria-checked={task.status === 'done'}
                                            aria-label={`${task.status === 'done' ? 'Reopen' : 'Complete'} ${task.title}`}
                                            disabled={!data.permissions['tasks.manage'] || busy === task.id}
                                            title={data.permissions['tasks.manage'] ? undefined : 'You may not change tasks'}
                                            onClick={() => void toggle(task)}
                                        >
                                            {busy === task.id ? (
                                                <LoaderCircle size={12} className="entropy-spin" />
                                            ) : (
                                                task.status === 'done' && <Check size={12} />
                                            )}
                                        </button>
                                        <button type="button" className="dw-row-main" onClick={() => openTool('tasks')}>
                                            <strong>{task.title}</strong>
                                            <small>
                                                {task.key ? `${task.key} · ` : ''}
                                                {task.assignee ? `@${task.assignee}` : 'Unassigned'}
                                                {task.reminder_at ? ` · reminder ${formatWhen(task.reminder_at)}` : ''}
                                            </small>
                                        </button>
                                        <span className={`dw-pill dw-task-${task.status}`}>{TASK_LABELS[task.status]}</span>
                                    </li>
                                ))}
                            </ul>
                        )}
                    </div>
                )
            }}
        </WidgetBody>
    )
}

// ----------------------------------------------------------------------
// Releases
// ----------------------------------------------------------------------

type ReleaseStage = 'workflow_queue' | 'workflow_done' | 'task_queue' | 'completed'
type Release = {
    id: number
    name: string
    version: string
    environment: string
    stage: ReleaseStage
    updated_at: string
    tasks: { status: string }[]
}
type ReleaseData = { items: Release[]; promotions: { id: number; status: string }[] }

const STAGES: Record<ReleaseStage, string> = {
    workflow_queue: 'Workflow queue',
    workflow_done: 'Workflow done',
    task_queue: 'Task queue',
    completed: 'Completed',
}

export function ReleasesWidget(props: WidgetProps) {
    const state = useWidgetData(() => apiRequest<ReleaseData>('/api/releases'), props, TOOL_REFRESH_MS)
    const environment = String(props.settings.environment ?? '').trim().toLowerCase()
    const limit = limitOf(props.settings, 6)
    return (
        <WidgetBody state={state} tool="Release Manager">
            {(data) => {
                const releases = data.items.filter(
                    (release) => !environment || release.environment.toLowerCase() === environment,
                )
                const counts = Object.fromEntries(
                    (Object.keys(STAGES) as ReleaseStage[]).map((stage) => [
                        stage,
                        releases.filter((release) => release.stage === stage).length,
                    ]),
                )
                const latest = [...releases].sort((a, b) => b.updated_at.localeCompare(a.updated_at)).slice(0, limit)
                return (
                    <div>
                        <div className="dw-counts">
                            {(Object.keys(STAGES) as ReleaseStage[]).map((stage) => (
                                <span key={stage} className={`dw-count dw-stage-${stage}`}>
                                    <strong>{counts[stage]}</strong> {STAGES[stage]}
                                </span>
                            ))}
                        </div>
                        {latest.length === 0 ? (
                            <WidgetEmpty>No releases{environment ? ` for ${props.settings.environment}` : ''}.</WidgetEmpty>
                        ) : (
                            <ul className="dw-list">
                                {latest.map((release) => {
                                    const open = release.tasks.filter((task) => task.status !== 'done').length
                                    return (
                                        <li key={release.id} className="dw-row">
                                            <button type="button" className="dw-row-main" onClick={() => openTool('release-manager')}>
                                                <strong>
                                                    {release.name} <span className="dw-muted">{release.version}</span>
                                                </strong>
                                                <small>
                                                    {release.environment}
                                                    {open ? ` · ${open} open task${open === 1 ? '' : 's'}` : ''} · updated{' '}
                                                    {formatWhen(release.updated_at)}
                                                </small>
                                            </button>
                                            <span className={`dw-pill dw-stage-${release.stage}`}>{STAGES[release.stage]}</span>
                                        </li>
                                    )
                                })}
                            </ul>
                        )}
                    </div>
                )
            }}
        </WidgetBody>
    )
}

// ----------------------------------------------------------------------
// Artifacts
// ----------------------------------------------------------------------

type Artifact = {
    id: number
    name: string
    classification: 'added' | 'generated'
    origin: string | null
    size_bytes: number
    created_by: string
    created_at: string
    download_url: string | null
}

export function ArtifactsWidget(props: WidgetProps) {
    const state = useWidgetData(() => apiRequest<{ items: Artifact[] }>('/api/artifacts'), props, TOOL_REFRESH_MS)
    const kind = String(props.settings.classification ?? 'all')
    const limit = limitOf(props.settings, 6)
    return (
        <WidgetBody state={state} tool="Artifacts">
            {(data) => {
                const items = data.items
                    .filter((item) => kind === 'all' || item.classification === kind)
                    .sort((a, b) => b.created_at.localeCompare(a.created_at))
                    .slice(0, limit)
                return items.length === 0 ? (
                    <WidgetEmpty>No artifacts yet.</WidgetEmpty>
                ) : (
                    <ul className="dw-list">
                        {items.map((item) => (
                            <li key={item.id} className="dw-row">
                                <button type="button" className="dw-row-main" onClick={() => openTool('artifacts')}>
                                    <strong title={item.name}>{item.name}</strong>
                                    <small>
                                        {formatBytes(item.size_bytes)} · {item.classification === 'generated' ? `generated${item.origin ? ` by ${item.origin}` : ''}` : `added by ${item.created_by}`} ·{' '}
                                        {formatWhen(item.created_at)}
                                    </small>
                                </button>
                                {item.download_url && (
                                    <a
                                        className="entropy-button entropy-button-ghost entropy-button-icon entropy-button-sm"
                                        href={item.download_url}
                                        aria-label={`Download ${item.name}`}
                                        title="Download"
                                    >
                                        <Download size={14} />
                                    </a>
                                )}
                            </li>
                        ))}
                    </ul>
                )
            }}
        </WidgetBody>
    )
}

// ----------------------------------------------------------------------
// Git repositories
// ----------------------------------------------------------------------

type Repository = {
    id: number
    name: string
    scope: 'user' | 'project'
    clone_path: string
    source_display: string
    assignments: unknown[]
}

export function GitRepositoriesWidget(props: WidgetProps) {
    const { notify } = useFeedback()
    const state = useWidgetData(() => apiRequest<{ items: Repository[] }>('/api/git-repositories'), props, TOOL_REFRESH_MS)
    const limit = limitOf(props.settings, 6)
    const copy = (text: string) =>
        void navigator.clipboard
            ?.writeText(text)
            .then(() => notify.success('Clone path copied.'))
            .catch(() => notify.error('The clipboard is not available.'))
    return (
        <WidgetBody state={state} tool="Git repositories">
            {(data) =>
                data.items.length === 0 ? (
                    <WidgetEmpty>No repositories in this project.</WidgetEmpty>
                ) : (
                    <ul className="dw-list">
                        {data.items.slice(0, limit).map((repo) => (
                            <li key={repo.id} className="dw-row">
                                <button type="button" className="dw-row-main" onClick={() => openTool('git-repositories')}>
                                    <strong>{repo.name}</strong>
                                    <small title={repo.clone_path}>
                                        {repo.source_display || repo.clone_path} · used by {repo.assignments.length}
                                    </small>
                                </button>
                                <span className="dw-pill">{repo.scope === 'project' ? 'Project' : 'Mine'}</span>
                                <button
                                    type="button"
                                    className="entropy-button entropy-button-ghost entropy-button-icon entropy-button-sm"
                                    aria-label={`Copy the clone path of ${repo.name}`}
                                    title="Copy clone path"
                                    onClick={() => copy(repo.clone_path)}
                                >
                                    <Copy size={14} />
                                </button>
                            </li>
                        ))}
                    </ul>
                )
            }
        </WidgetBody>
    )
}

// ----------------------------------------------------------------------
// EagleAPI
// ----------------------------------------------------------------------

function statusClass(entry: EagleHistorySummary): string {
    if (entry.error || entry.status === null) return 'dw-http-error'
    if (entry.status >= 500) return 'dw-http-error'
    if (entry.status >= 400) return 'dw-http-warn'
    return 'dw-http-ok'
}

export function EagleHistoryWidget(props: WidgetProps) {
    const limit = limitOf(props.settings, 6)
    const state = useWidgetData(() => eagleApi.history('', limit), props, TOOL_REFRESH_MS, [limit])
    return (
        <WidgetBody state={state} tool="EagleAPI">
            {(data) =>
                data.entries.length === 0 ? (
                    <WidgetEmpty>No requests sent yet.</WidgetEmpty>
                ) : (
                    <ul className="dw-list">
                        {data.entries.slice(0, limit).map((entry) => (
                            <li key={entry.id} className="dw-row">
                                <span className="dw-method">{entry.method}</span>
                                <button type="button" className="dw-row-main" onClick={() => openTool('eagleapi')}>
                                    <strong title={entry.url}>{entry.item_name || entry.url}</strong>
                                    <small>
                                        {entry.environment ? `${entry.environment} · ` : ''}
                                        {entry.elapsed_ms} ms · {formatWhen(entry.created_at)}
                                    </small>
                                </button>
                                <span className={`dw-pill ${statusClass(entry)}`} title={entry.error ?? undefined}>
                                    {entry.status ?? 'Error'}
                                </span>
                            </li>
                        ))}
                    </ul>
                )
            }
        </WidgetBody>
    )
}

// ----------------------------------------------------------------------
// Schedules
// ----------------------------------------------------------------------

function openSchedules(): void {
    window.history.pushState(null, '', '#/schedulers')
    window.dispatchEvent(new PopStateEvent('popstate'))
}

export function SchedulesWidget(props: WidgetProps) {
    const state = useWidgetData(() => schedulesApi.list(), props, TOOL_REFRESH_MS)
    const limit = limitOf(props.settings, 6)
    return (
        <WidgetBody state={state} tool="schedules">
            {(data) => {
                const upcoming: Schedule[] = data.items
                    .filter((schedule) => schedule.enabled && schedule.next_run_at)
                    .sort((a, b) => (a.next_run_at ?? '').localeCompare(b.next_run_at ?? ''))
                    .slice(0, limit)
                const failed = data.failed.length
                return (
                    <div>
                        {failed > 0 && (
                            <button type="button" className="dw-alert" onClick={openSchedules}>
                                {failed} failed scheduled run{failed === 1 ? '' : 's'} to look at
                            </button>
                        )}
                        {upcoming.length === 0 ? (
                            <WidgetEmpty>No enabled schedules.</WidgetEmpty>
                        ) : (
                            <ul className="dw-list">
                                {upcoming.map((schedule) => (
                                    <li key={schedule.id} className="dw-row">
                                        <button type="button" className="dw-row-main" onClick={openSchedules}>
                                            <strong>{schedule.name}</strong>
                                            <small>
                                                {schedule.kind} {schedule.target} · {schedule.cron}
                                            </small>
                                        </button>
                                        <span className="dw-pill" title={schedule.next_run_at ?? undefined}>
                                            {formatWhen(schedule.next_run_at)}
                                        </span>
                                    </li>
                                ))}
                            </ul>
                        )}
                    </div>
                )
            }}
        </WidgetBody>
    )
}

// ----------------------------------------------------------------------
// Tool shortcuts
// ----------------------------------------------------------------------

export function ToolLauncherWidget() {
    return (
        <div className="dw-launcher">
            {TOOLS.map((tool) => {
                const Icon = tool.icon
                return (
                    <button key={tool.id} type="button" className="dw-launch" onClick={() => openTool(tool.id)} title={tool.description}>
                        <Icon size={20} />
                        <span>{tool.name}</span>
                    </button>
                )
            })}
        </div>
    )
}
