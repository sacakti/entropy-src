import { apiRequest } from '../services/api'
import type { PluginFilesResponse } from './plugins.api'

/** A kept earlier version of a workflow or plugin. */
export interface HistoryEntry {
    id: number
    version: string
    /** 'edit': kept before an edit; 'restore': kept before a restore. */
    reason: 'edit' | 'restore' | string
    created_by: string | null
    created_at: string
}

export interface HistoryList {
    current_version: string
    items: HistoryEntry[]
}

export interface WorkflowHistoryEntry extends HistoryEntry {
    format: 'json' | 'yaml'
    definition: string
}

export interface PluginHistoryEntry extends HistoryEntry {
    files: Record<string, string>
}

const post: RequestInit = { method: 'POST' }

export const workflowHistoryApi = {
    list: (name: string) => apiRequest<HistoryList>(`/api/workflows/${encodeURIComponent(name)}/history`),
    get: (name: string, id: number) =>
        apiRequest<WorkflowHistoryEntry>(`/api/workflows/${encodeURIComponent(name)}/history/${id}?format=yaml`),
    restore: (name: string, id: number) =>
        apiRequest<{ version: string; restored_from: string }>(
            `/api/workflows/${encodeURIComponent(name)}/history/${id}/restore`,
            post,
        ),
}

export const pluginHistoryApi = {
    list: (name: string) => apiRequest<HistoryList>(`/api/plugins/${encodeURIComponent(name)}/history`),
    get: (name: string, id: number) =>
        apiRequest<PluginHistoryEntry>(`/api/plugins/${encodeURIComponent(name)}/history/${id}`),
    restore: (name: string, id: number) =>
        apiRequest<PluginFilesResponse & { restored_from: string }>(
            `/api/plugins/${encodeURIComponent(name)}/history/${id}/restore`,
            post,
        ),
}
