import { apiRequest } from '../services/api'

export type AuditOutcome = 'success' | 'failure' | 'denied'
export type AuditSortField = 'time' | 'user' | 'category' | 'action' | 'outcome' | 'project'

/** One audited activity: who did what, when, from where, and whether it was allowed. */
export interface AuditEntry {
    id: number
    created_at: string
    user_id: number | null
    username: string | null
    address: string | null
    user_agent: string | null
    /** web (browser) or cli (`ent`). */
    source: string
    category: string
    action: string
    target: string | null
    method: string | null
    path: string | null
    status: number | null
    outcome: AuditOutcome
    project: string | null
    duration_ms: number | null
    details: Record<string, unknown>
}

export interface AuditFilters {
    search?: string
    user?: string
    category?: string
    outcome?: string
    project?: string
    since?: string
    until?: string
}

export interface AuditListResponse {
    items: AuditEntry[]
    total: number
    facets: { users: string[]; categories: string[]; projects: string[] }
    retention_days: number
    /** May change the retention (system.settings). */
    can_manage: boolean
}

const query = (filters: AuditFilters, extra: Record<string, string | number> = {}) => {
    const params = new URLSearchParams()
    Object.entries({ ...filters, ...extra }).forEach(([key, value]) => {
        if (value !== undefined && value !== '') params.set(key, String(value))
    })
    return params
}

export const auditApi = {
    list(filters: AuditFilters, page: { limit: number; offset: number; sort: AuditSortField; order: 'asc' | 'desc' }): Promise<AuditListResponse> {
        return apiRequest(`/api/audit?${query(filters, page).toString()}`)
    },

    /** The matching entries as CSV (the audit log is global: no project needed). */
    exportUrl(filters: AuditFilters): string {
        return `/api/audit/export.csv?${query(filters).toString()}`
    },

    setRetention(days: number): Promise<{ retention_days: number; removed: number }> {
        return apiRequest('/api/audit/retention', {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ retention_days: days }),
        })
    },
}
