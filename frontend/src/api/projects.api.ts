import { apiRequest } from '../services/api'

/** A project: its own workflows, schedules, drafts and runs, and the people who may use them. */
export interface Project {
    id: number
    key: string
    name: string
    description: string | null
    created_by: string | null
    created_at: string | null
    updated_at: string | null
}

/** A project as `GET /api/projects` lists it, with counts and what the signed-in user may do. */
export interface ProjectSummary extends Project {
    /** The signed-in user's project roles here (directly or through groups). */
    my_roles: string[]
    can_manage_members: boolean
    workflows: number
    schedules: number
    members: number
}

export type MemberKind = 'user' | 'group'

export interface ProjectMember {
    id: number
    kind: MemberKind
    name: string
    full_name: string | null
    role: string
    role_title: string
}

/** A member to set: a user or group and one project role. */
export interface ProjectMemberInput {
    kind: MemberKind
    name: string
    role: string
}

/** Which projects may run on a node. */
export interface NodeAccess {
    scope: 'shared' | 'assigned'
    /** Project keys when `scope` is 'assigned'. */
    projects: string[]
}

/** The part of a node the projects pages need. */
export interface ProjectNode {
    id: number
    name: string
    kind: string
    host: string | null
    description: string | null
    enabled: boolean
    access: NodeAccess
}

/** 1–40 lowercase letters, digits and dashes. */
export const PROJECT_KEY_PATTERN = /^[a-z0-9-]{1,40}$/

const JSON_HEADERS = { 'Content-Type': 'application/json' }

const projectPath = (...parts: string[]) =>
    ['/api/projects', ...parts.map((part) => encodeURIComponent(part))].join('/')

function send<T>(method: string, url: string, body?: unknown): Promise<T> {
    return apiRequest<T>(url, {
        method,
        headers: body === undefined ? undefined : JSON_HEADERS,
        body: body === undefined ? undefined : JSON.stringify(body),
    })
}

export const projectsApi = {
    list: () =>
        apiRequest<{ items: ProjectSummary[]; current: string | null; can_create: boolean }>(projectPath()),
    create: (project: { key: string; name: string; description: string }) =>
        send<Project>('POST', projectPath(), project),
    update: (key: string, changes: { name?: string; description?: string }) =>
        send<Project>('PATCH', projectPath(key), changes),
    /** Refused (409) for the default project or one that still has workflows or schedules. */
    remove: (key: string) => send<{ deleted: boolean }>('DELETE', projectPath(key)),

    members: (key: string) =>
        apiRequest<{ project: Project; members: ProjectMember[]; can_manage: boolean }>(projectPath(key, 'members')),
    /** Replaces every member of the project. */
    setMembers: (key: string, members: ProjectMemberInput[]) =>
        send<{ members: ProjectMember[] }>('PUT', projectPath(key, 'members'), { members }),

    /** Users, groups and project roles a member manager may assign (maintainers included). */
    assignable: (key: string) =>
        apiRequest<{
            users: { username: string; full_name: string | null }[]
            groups: { name: string; members: number }[]
            roles: { name: string; title: string; description: string }[]
        }>(projectPath(key, 'assignable')),

    nodes: () => apiRequest<{ items: ProjectNode[] }>('/api/nodes'),
    setNodeAccess: (name: string, access: NodeAccess) =>
        send<unknown>('PUT', `/api/nodes/${encodeURIComponent(name)}/access`, access),
}

/** Whether a node may run this project's work. */
export function nodeServesProject(node: ProjectNode, key: string): boolean {
    return node.access.scope === 'shared' || node.access.projects.includes(key)
}
