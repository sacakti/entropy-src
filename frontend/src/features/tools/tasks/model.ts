import {
    AlertTriangle,
    BookOpen,
    Bug,
    CheckSquare,
    CircleDot,
    Repeat,
    Tag,
    TrendingUp,
    Zap,
    type LucideIcon,
} from 'lucide-react'

import { apiRequest } from '../../../services/api'
import { currentProject } from '../../../services/project'

export type Status = 'todo' | 'in_progress' | 'done' | 'reopened'
export type Severity = 'critical' | 'high' | 'medium' | 'low'
export type StatusChange = { from_status: Status | null; to_status: Status; reason: string; changed_by: string; changed_at: string }
export type Comment = { id: number; author: string; body: string; created_at: string }
export type Attachment = {
    id: number
    filename: string
    content_type: string | null
    size_bytes: number
    url: string | null
    uploaded_by: string
    created_at: string
}
export type Task = {
    id: number
    key: string
    type: string
    external_ref: string | null
    title: string
    description: string
    remarks: string
    status: Status
    severity: Severity
    assignee: string | null
    creator: string
    reminder_at: string | null
    due_date: string | null
    created_at: string
    updated_at: string
    comments: Comment[]
    follower_ids: number[]
    group_ids: number[]
    attachments: Attachment[]
    history: StatusChange[]
}
export type GroupKind = 'release' | 'sprint' | 'epic' | 'other'
export type Group = {
    id: number
    name: string
    kind: GroupKind
    description: string
    external_ref: string | null
    created_by: string
    created_at: string
    task_count: number
}
export type Member = { username: string; full_name: string | null }
export type TaskSettings = { prefix: string; next_key: string; types: string[]; custom_types: string[] }
export type TaskData = {
    items: Task[]
    groups: Group[]
    settings: TaskSettings
    members: Member[]
    user_id: number
    username: string
    mail_ready: boolean
    permissions: { 'tasks.create': boolean; 'tasks.manage': boolean; 'tasks.comment': boolean; 'tasks.follow': boolean }
}
export type ImportSummary = {
    created: number
    updated: number
    skipped: number
    comments: number
    attachments: number
    groups: string[]
    types_added: string[]
    unassigned: string[]
}

export const STATUSES: { id: Status; title: string }[] = [
    { id: 'todo', title: 'Open' },
    { id: 'in_progress', title: 'In progress' },
    { id: 'done', title: 'Closed' },
    { id: 'reopened', title: 'Reopened' },
]

// Most severe first, as the server lists them.
export const SEVERITIES: { id: Severity; title: string }[] = [
    { id: 'critical', title: 'Critical' },
    { id: 'high', title: 'High' },
    { id: 'medium', title: 'Medium' },
    { id: 'low', title: 'Low' },
]
export const severityTitle = (severity: Severity | undefined) =>
    SEVERITIES.find((item) => item.id === severity)?.title ?? 'Medium'

/** Where a task may go next: a closed task is only reopened (with a reason). */
export function nextStatuses(current: Status | null): Status[] {
    if (current === 'done') return ['done', 'reopened']
    const open: Status[] = ['todo', 'in_progress', 'done']
    return current === 'reopened' ? ['reopened', ...open] : open
}

export const isOverdue = (task: Task) =>
    Boolean(task.due_date) && task.status !== 'done' && task.due_date! < new Date().toLocaleDateString('en-CA')

export type ReportScope = 'all' | 'selected' | 'group'

export function reportUrl(scope: ReportScope, format: 'html' | 'pdf', ids: number[] = [], groupId?: number | null): string {
    const params = new URLSearchParams({ scope, format })
    if (scope === 'selected') params.set('ids', ids.join(','))
    if (scope === 'group' && groupId) params.set('group_id', String(groupId))
    const project = currentProject()
    if (project) params.set('project', project)
    return `/api/tasks/report?${params.toString()}`
}

export const GROUP_KINDS: { id: GroupKind; title: string }[] = [
    { id: 'release', title: 'Release' },
    { id: 'sprint', title: 'Sprint' },
    { id: 'epic', title: 'Epic' },
    { id: 'other', title: 'Other' },
]

const TYPE_ICONS: Record<string, LucideIcon> = {
    issue: CircleDot,
    bug: Bug,
    task: CheckSquare,
    story: BookOpen,
    improvement: TrendingUp,
    epic: Zap,
    incident: AlertTriangle,
    change: Repeat,
}

export function typeIcon(type: string): LucideIcon {
    return TYPE_ICONS[type] ?? Tag
}

export function typeLabel(type: string): string {
    const text = type.replace(/[_-]+/g, ' ')
    return text.charAt(0).toUpperCase() + text.slice(1)
}

export const statusTitle = (status: Status) => STATUSES.find((item) => item.id === status)?.title ?? status

export const localDate = (value: string | null) => {
    if (!value) return ''
    // SQLite times are UTC without a zone.
    const date = new Date(/[zZ]|[+-]\d\d:?\d\d$/.test(value) ? value : `${value.replace(' ', 'T')}Z`)
    return Number.isNaN(date.getTime()) ? value : date.toLocaleString()
}

export const reminderValue = (value: string) => (value ? new Date(value).toISOString() : null)

export const reminderInput = (value: string | null) => {
    if (!value) return ''
    const date = new Date(value)
    return new Date(date.getTime() - date.getTimezoneOffset() * 60000).toISOString().slice(0, 16)
}

export function formatSize(bytes: number): string {
    if (!bytes) return ''
    if (bytes < 1024) return `${bytes} B`
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
    return `${(bytes / 1024 / 1024).toFixed(1)} MB`
}

const json = (method: string, body: unknown) => ({
    method,
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
})

export const tasksApi = {
    load: () => apiRequest<TaskData>('/api/tasks'),
    create: (body: Record<string, unknown>) => apiRequest<Task>('/api/tasks', json('POST', body)),
    update: (id: number, body: Record<string, unknown>) => apiRequest<Task>(`/api/tasks/${id}`, json('PATCH', body)),
    remove: (id: number) => apiRequest<void>(`/api/tasks/${id}`, { method: 'DELETE' }),
    comment: (id: number, body: string) => apiRequest<Task>(`/api/tasks/${id}/comments`, json('POST', { body })),
    follow: (id: number, following: boolean) => apiRequest(`/api/tasks/${id}/follow`, json('PUT', { following })),
    attach: (id: number, files: File[]) => {
        const form = new FormData()
        files.forEach((file) => form.append('files', file))
        return apiRequest<Task>(`/api/tasks/${id}/attachments`, { method: 'POST', body: form })
    },
    rename: (id: number, attachmentId: number, filename: string) =>
        apiRequest<Task>(`/api/tasks/${id}/attachments/${attachmentId}`, json('PATCH', { filename })),
    detach: (id: number, attachmentId: number) =>
        apiRequest<void>(`/api/tasks/${id}/attachments/${attachmentId}`, { method: 'DELETE' }),
    attachmentUrl: (id: number, attachmentId: number) => {
        // A plain link sends no project header: name the project in the URL.
        const project = currentProject()
        return `/api/tasks/${id}/attachments/${attachmentId}${project ? `?project=${encodeURIComponent(project)}` : ''}`
    },
    settings: (body: { prefix?: string; types?: string[] }) => apiRequest<TaskSettings>('/api/tasks/settings', json('PUT', body)),
    createGroup: (body: Record<string, unknown>) => apiRequest<Group>('/api/tasks/groups', json('POST', body)),
    updateGroup: (id: number, body: Record<string, unknown>) => apiRequest<Group>(`/api/tasks/groups/${id}`, json('PATCH', body)),
    removeGroup: (id: number) => apiRequest<void>(`/api/tasks/groups/${id}`, { method: 'DELETE' }),
    importJira: (file: File, group: string, updateExisting: boolean) => {
        const form = new FormData()
        form.append('file', file)
        form.append('group', group)
        form.append('update_existing', String(updateExisting))
        return apiRequest<ImportSummary>('/api/tasks/import', { method: 'POST', body: form })
    },
}

const csvCell = (value: string) => `"${value.replaceAll('"', '""')}"`

/** A CSV Jira imports (Issue key, type, groups as fix versions and sprints). */
export function exportJiraCsv(data: TaskData): void {
    const groups = new Map(data.groups.map((group) => [group.id, group]))
    const releases = (task: Task) => task.group_ids.map((id) => groups.get(id)).filter((group) => group?.kind === 'release')
    const sprints = (task: Task) => task.group_ids.map((id) => groups.get(id)).filter((group) => group?.kind === 'sprint')
    const width = (pick: (task: Task) => unknown[]) => Math.max(1, ...data.items.map((task) => pick(task).length))
    const releaseColumns = width(releases)
    const sprintColumns = width(sprints)
    const rows = [
        [
            'Issue key', 'Issue Type', 'Summary', 'Description', 'Status', 'Assignee', 'External reference', 'Due Date',
            ...Array<string>(releaseColumns).fill('Fix Version/s'), ...Array<string>(sprintColumns).fill('Sprint'), 'Labels',
        ],
        ...data.items.map((task) => {
            const release = releases(task).map((group) => group?.name ?? '')
            const sprint = sprints(task).map((group) => group?.name ?? '')
            return [
                task.key, typeLabel(task.type), task.title, task.description,
                task.status === 'in_progress' ? 'In Progress' : task.status === 'done' ? 'Done' : task.status === 'reopened' ? 'Reopened' : 'To Do',
                task.assignee ?? '', task.external_ref ?? '', task.due_date ?? '',
                ...release, ...Array<string>(releaseColumns - release.length).fill(''),
                ...sprint, ...Array<string>(sprintColumns - sprint.length).fill(''),
                'entropy-task',
            ]
        }),
    ]
    const blob = new Blob([`\uFEFF${rows.map((row) => row.map(csvCell).join(',')).join('\r\n')}`], {
        type: 'text/csv;charset=utf-8',
    })
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = 'entropy-tasks-jira.csv'
    link.click()
    URL.revokeObjectURL(url)
}

// Attachments the task viewer can show; null means download only.
export type PreviewKind = 'image' | 'pdf' | 'text'

const IMAGE = /\.(png|jpe?g|gif|webp|bmp|svg)$/i
const TEXT = /\.(txt|log|out|csv|json|ya?ml|xml|md|ini|conf|cfg|properties|sh|sql|py|env)$/i
export function previewKind(attachment: Attachment): PreviewKind | null {
    if (attachment.url) return null // a link to Jira; there is no file here
    const name = attachment.filename
    const type = attachment.content_type ?? ''
    if (IMAGE.test(name) || type.startsWith('image/')) return 'image'
    if (/\.pdf$/i.test(name) || type === 'application/pdf') return 'pdf'
    if (TEXT.test(name) || type.startsWith('text/')) return 'text'
    return null
}

// An attachment shown inside a description: ![caption](attachment:42).
// The report places it at the same spot instead of listing it at the end.
export const attachmentReferencePattern = () => /!\[([^\]\n]*)\]\(attachment:(\d+)\)/g
export const attachmentReference = (attachment: Attachment) =>
    `![${attachment.filename.replace(/[[\]\n]/g, '')}](attachment:${attachment.id})`
