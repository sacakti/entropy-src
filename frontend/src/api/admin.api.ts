import { apiRequest } from '../services/api'

export interface AdminSummary {
    charts: {
        groups: { name: string; members: number }[]
        roles: { name: string; users: number; groups: number; permissions: number }[]
        modules: { name: string; read: number; write: number; execute: number }[]
    }
    users: number
    active_users: number
    groups: number
    roles: number
    permissions: number
    modules: number
}

export interface AdminUser {
    id: number
    username: string
    full_name: string | null
    email: string | null
    is_active: boolean
    /** The built-in administrator account; it cannot be disabled or deleted. */
    is_system: boolean
    created_at: string | null
    updated_at: string | null
    roles: string[]
    groups: string[]
}

export interface AdminGroup {
    id: number
    name: string
    description: string | null
    created_at: string | null
    updated_at: string | null
    users: string[]
    roles: string[]
}

export interface AdminRole {
    id: number
    name: string
    description: string | null
    /** The built-in admin role; it cannot be changed. */
    is_builtin: boolean
    created_at: string | null
    updated_at: string | null
    permissions: string[]
    users: string[]
    groups: string[]
}

export interface AdminPermission {
    id: number
    name: string
    description: string | null
    type: 'read' | 'write' | 'execute'
    roles: string[]
}

export interface AdminModule {
    name: string
    description: string | null
    permissions: AdminPermission[]
}

const BASE = '/api/admin'
const JSON_HEADERS = { 'Content-Type': 'application/json' }

const path = (...parts: string[]) =>
    [BASE, ...parts.map((part) => encodeURIComponent(part))].join('/')

function send<T>(method: string, url: string, body?: unknown): Promise<T> {
    return apiRequest<T>(url, {
        method,
        headers: body === undefined ? undefined : JSON_HEADERS,
        body: body === undefined ? undefined : JSON.stringify(body),
    })
}

export const adminApi = {
    summary: () => apiRequest<AdminSummary>(path('summary')),

    users: () => apiRequest<{ items: AdminUser[] }>(path('users')),
    createUser: (user: {
        username: string
        password: string
        full_name: string | null
        email: string | null
        roles: string[]
        groups: string[]
    }) => send<AdminUser>('POST', path('users'), user),
    updateUser: (username: string, changes: { full_name: string | null; email: string | null }) =>
        send<AdminUser>('PATCH', path('users', username), changes),
    setUserActive: (username: string, active: boolean) =>
        send<AdminUser>('POST', path('users', username, active ? 'enable' : 'disable')),
    /** Without a password the server generates a temporary one and returns it. */
    setUserPassword: (username: string, password: string | null) =>
        send<{ message: string; password: string | null }>(
            'PUT',
            path('users', username, 'password'),
            password ? { password } : {},
        ),
    deleteUser: (username: string) => send<{ message: string }>('DELETE', path('users', username)),
    setUserRoles: (username: string, names: string[]) =>
        send<AdminUser>('PUT', path('users', username, 'roles'), { names }),
    setUserGroups: (username: string, names: string[]) =>
        send<AdminUser>('PUT', path('users', username, 'groups'), { names }),

    groups: () => apiRequest<{ items: AdminGroup[] }>(path('groups')),
    createGroup: (group: { name: string; description: string | null }) =>
        send<AdminGroup>('POST', path('groups'), group),
    updateGroup: (name: string, changes: { name?: string; description?: string }) =>
        send<AdminGroup>('PATCH', path('groups', name), changes),
    deleteGroup: (name: string) => send<{ message: string }>('DELETE', path('groups', name)),
    setGroupUsers: (name: string, names: string[]) =>
        send<AdminGroup>('PUT', path('groups', name, 'users'), { names }),
    setGroupRoles: (name: string, names: string[]) =>
        send<AdminGroup>('PUT', path('groups', name, 'roles'), { names }),

    roles: () => apiRequest<{ items: AdminRole[] }>(path('roles')),
    createRole: (role: { name: string; description: string | null }) =>
        send<AdminRole>('POST', path('roles'), role),
    updateRole: (name: string, changes: { name?: string; description?: string }) =>
        send<AdminRole>('PATCH', path('roles', name), changes),
    deleteRole: (name: string) => send<{ message: string }>('DELETE', path('roles', name)),
    setRolePermissions: (name: string, names: string[]) =>
        send<AdminRole>('PUT', path('roles', name, 'permissions'), { names }),

    permissions: () => apiRequest<{ modules: AdminModule[] }>(path('permissions')),
    setPermissionRoles: (name: string, names: string[]) =>
        send<{ name: string; roles: string[] }>('PUT', path('permissions', name, 'roles'), { names }),
}
