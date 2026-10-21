import { apiRequest, downloadFile } from '../services/api'

export type WorkflowFormat = 'json' | 'yaml' | 'yml'

export interface WorkflowSummary {
    name: string
    version: string
    description: string
    created_at: string
    updated_at: string
}

// The detail endpoint returns no timestamps; use the list entry for those.
export interface WorkflowDetail
    extends Omit<WorkflowSummary, 'created_at' | 'updated_at'> {
    step_count: number
    format: WorkflowFormat
    definition: string
}

export interface WorkflowListResponse {
    items: WorkflowSummary[]
}

export interface WorkflowValidationResponse {
    valid: boolean
    workflow: WorkflowDetail
}

export interface WorkflowDefinitionRequest {
    definition: string
    format: WorkflowFormat
}

export interface WorkflowDeleteResponse {
    deleted: boolean
    name: string
}

export const workflowsApi = {
    list(): Promise<WorkflowListResponse> {
        return apiRequest<WorkflowListResponse>('/api/workflows')
    },

    get(
        name: string,
        format: WorkflowFormat = 'json',
    ): Promise<WorkflowDetail> {
        const params = new URLSearchParams({ format })

        return apiRequest<WorkflowDetail>(
            `/api/workflows/${encodeURIComponent(name)}?${params.toString()}`,
        )
    },

    validate(
        payload: WorkflowDefinitionRequest,
    ): Promise<WorkflowValidationResponse> {
        return apiRequest<WorkflowValidationResponse>(
            '/api/workflows/validate',
            {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload),
            },
        )
    },

    create(
        payload: WorkflowDefinitionRequest,
    ): Promise<WorkflowDetail> {
        return apiRequest<WorkflowDetail>('/api/workflows', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload),
        })
    },

    update(
        name: string,
        payload: WorkflowDefinitionRequest,
    ): Promise<WorkflowDetail> {
        return apiRequest<WorkflowDetail>(
            `/api/workflows/${encodeURIComponent(name)}`,
            {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload),
            },
        )
    },

    delete(name: string): Promise<WorkflowDeleteResponse> {
        return apiRequest<WorkflowDeleteResponse>(
            `/api/workflows/${encodeURIComponent(name)}`,
            { method: 'DELETE' },
        )
    },

    exportZip(names: string[], format: WorkflowFormat = 'json'): Promise<void> {
        return downloadFile(
            '/api/workflows/export',
            { names, format },
            names.length === 1 ? `${names[0]}.zip` : 'entropy-workflows.zip',
        )
    },
}

/** A definition saved with errors ("Save with errors"); it cannot run. */
export interface WorkflowDraftSummary {
    id: number
    /** The registered workflow it edits, or null for a new workflow. */
    workflow: string | null
    title: string
    format: 'json' | 'yaml'
    errors: string[]
    created_by: string | null
    updated_by: string | null
    created_at: string
    updated_at: string
}

export interface WorkflowDraft extends WorkflowDraftSummary {
    definition: string
}

export const workflowDraftsApi = {
    list(): Promise<{ items: WorkflowDraftSummary[] }> {
        return apiRequest<{ items: WorkflowDraftSummary[] }>('/api/workflow-drafts')
    },

    get(id: number): Promise<WorkflowDraft> {
        return apiRequest<WorkflowDraft>(`/api/workflow-drafts/${id}`)
    },

    save(draft: {
        id?: number | null
        workflow?: string | null
        definition: string
        format: 'json' | 'yaml'
        errors: string[]
    }): Promise<WorkflowDraft> {
        return apiRequest<WorkflowDraft>('/api/workflow-drafts', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(draft),
        })
    },

    delete(id: number): Promise<{ deleted: boolean }> {
        return apiRequest<{ deleted: boolean }>(`/api/workflow-drafts/${id}`, { method: 'DELETE' })
    },
}
