import { apiRequest } from '../services/api'

export interface PluginItem {
    id: number
    namespace: string
    name: string
    qualified_name: string
    version: string
    enabled: boolean
    installed_at: string | null
}

export interface PluginListResponse {
    items: PluginItem[]
    pagination: {
        page: number
        page_size: number
        total: number
        total_pages: number
    }
}

export interface PluginListParams {
    q?: string
    enabled?: boolean | null
    namespace?: string
    installed_from?: string
    installed_to?: string
    sort_by?:
        | 'name'
        | 'namespace'
        | 'version'
        | 'enabled'
        | 'installed_at'
    order?: 'asc' | 'desc'
    page?: number
    page_size?: number
}

export async function listPlugins(
    params: PluginListParams = {},
): Promise<PluginListResponse> {
    const query = new URLSearchParams()

    if (params.q) query.set('q', params.q)
    if (params.enabled !== undefined && params.enabled !== null) {
        query.set('enabled', String(params.enabled))
    }

    query.set('sort_by', params.sort_by ?? 'name')
    query.set('order', params.order ?? 'asc')
    query.set('page', String(params.page ?? 1))
    query.set('page_size', String(Math.min(params.page_size ?? 10, 10)))

    return apiRequest<PluginListResponse>(
        `/api/plugins?${query.toString()}`,
    )
}
