import { apiRequest, downloadFile } from '../services/api'

export interface PluginItem {
    id: number
    namespace: string
    name: string
    qualified_name: string
    version: string
    enabled: boolean
    installed_at: string | null
    /** Saved but not installed; workflows cannot use it until installed. */
    draft?: boolean
}

export interface PluginListResponse {
    items: PluginItem[]
    /** Unfiltered counts; absent on servers older than the plugin studio API. */
    summary?: {
        total: number
        enabled: number
        drafts?: number
        /** Every installed namespace, ignoring filters. */
        namespaces?: string[]
    }
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
    draft?: boolean | null
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
    if (params.namespace) query.set('namespace', params.namespace)
    if (params.enabled !== undefined && params.enabled !== null) {
        query.set('enabled', String(params.enabled))
    }
    if (params.draft !== undefined && params.draft !== null) {
        query.set('draft', String(params.draft))
    }

    query.set('sort_by', params.sort_by ?? 'name')
    query.set('order', params.order ?? 'asc')
    query.set('page', String(params.page ?? 1))
    query.set('page_size', String(Math.min(params.page_size ?? 10, 10)))

    return apiRequest<PluginListResponse>(
        `/api/plugins?${query.toString()}`,
    )
}

// ----------------------------------------------------------------------
// Plugin development
// ----------------------------------------------------------------------

export interface PluginFile {
    path: string
    content: string
}

export interface PluginFilesResponse {
    plugin: PluginItem
    files: PluginFile[]
    revision: string
}

export type DiagnosticSeverity = 'error' | 'warning' | 'info'

export interface PluginDiagnostic {
    path: string
    severity: DiagnosticSeverity
    message: string
    line: number
    column: number
    end_line: number | null
    end_column: number | null
    source: string
}

export interface PluginValidationResponse {
    valid: boolean
    diagnostics: PluginDiagnostic[]
}

export interface PluginAvailability {
    available: boolean
    reason: string | null
}

export interface SdkMember {
    name: string
    kind: 'property' | 'method'
    type: string | null
    signature?: string
    annotation?: string | null
    doc: string
}

export interface SdkType {
    name: string
    module: string
    doc: string
    members: SdkMember[]
}

export interface SdkSymbol {
    name: string
    module: string
    kind: 'class' | 'function'
    signature: string
    doc: string
}

export interface PluginSdkCatalog {
    root: string
    types: Record<string, SdkType>
    symbols: SdkSymbol[]
}

export type PluginArgumentType =
    | 'string'
    | 'boolean'
    | 'integer'
    | 'number'
    | 'path'
    | 'list'
    | 'dictionary'
    | 'any'

export interface PluginArgumentSpec {
    name: string
    type: PluginArgumentType
    required: boolean
    default: unknown
    minimum?: number
    maximum?: number
}

/** Arguments a plugin reads and outputs it publishes, recovered from its source. */
export interface PluginContract extends PluginItem {
    description: string | null
    arguments: PluginArgumentSpec[]
    outputs: string[]
}

/** Diagnostics carried by a 422 save response, if any. */
export function diagnosticsFrom(detail: unknown): PluginDiagnostic[] | null {
    const diagnostics = (detail as { diagnostics?: unknown } | null)?.diagnostics

    return Array.isArray(diagnostics)
        ? (diagnostics as PluginDiagnostic[])
        : null
}

function pluginPath(qualifiedName: string, suffix = ''): string {
    return `/api/plugins/${encodeURIComponent(qualifiedName)}${suffix}`
}

const jsonHeaders = { 'Content-Type': 'application/json' }

export const pluginsApi = {
    availability(
        namespace: string,
        name: string,
    ): Promise<PluginAvailability> {
        const query = new URLSearchParams({ namespace, name })

        return apiRequest<PluginAvailability>(
            `/api/plugins/availability?${query.toString()}`,
        )
    },

    create(payload: {
        namespace: string
        name: string
        description?: string
        /** Install right away instead of keeping a draft. */
        install?: boolean
    }): Promise<PluginItem> {
        return apiRequest<PluginItem>('/api/plugins', {
            method: 'POST',
            headers: jsonHeaders,
            body: JSON.stringify(payload),
        })
    },

    files(qualifiedName: string): Promise<PluginFilesResponse> {
        return apiRequest<PluginFilesResponse>(
            pluginPath(qualifiedName, '/files'),
        )
    },

    validate(
        qualifiedName: string,
        files: Record<string, string>,
        signal?: AbortSignal,
    ): Promise<PluginValidationResponse> {
        return apiRequest<PluginValidationResponse>(
            pluginPath(qualifiedName, '/validate'),
            {
                method: 'POST',
                headers: jsonHeaders,
                body: JSON.stringify({ files }),
                signal,
            },
        )
    },

    save(
        qualifiedName: string,
        files: Record<string, string>,
        revision: string,
        install = false,
    ): Promise<PluginFilesResponse> {
        return apiRequest<PluginFilesResponse>(
            pluginPath(qualifiedName, '/files'),
            {
                method: 'PUT',
                headers: jsonHeaders,
                body: JSON.stringify({ files, revision, install }),
            },
        )
    },

    delete(
        qualifiedName: string,
    ): Promise<{ deleted: boolean; qualified_name: string }> {
        return apiRequest(pluginPath(qualifiedName), { method: 'DELETE' })
    },

    install(qualifiedName: string): Promise<PluginItem> {
        return apiRequest<PluginItem>(pluginPath(qualifiedName, '/install'), { method: 'POST' })
    },

    exportZip(names: string[]): Promise<void> {
        return downloadFile(
            '/api/plugins/export',
            { names },
            names.length === 1 ? `${names[0]}.zip` : 'entropy-plugins.zip',
        )
    },

    importZip(file: File, install: boolean): Promise<{ items: PluginItem[] }> {
        const body = new FormData()
        body.append('file', file)
        body.append('install', String(install))
        return apiRequest<{ items: PluginItem[] }>('/api/plugins/import', { method: 'POST', body })
    },

    contracts(): Promise<{ items: PluginContract[] }> {
        return apiRequest<{ items: PluginContract[] }>('/api/plugins/contracts')
    },

    sdk(): Promise<PluginSdkCatalog> {
        return apiRequest<PluginSdkCatalog>('/api/plugins/sdk')
    },
}
