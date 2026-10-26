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
    /** Bytes on disk. */
    size?: number
    /** ISO time the file last changed on the server. */
    modified?: string
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
    description?: string
    /** Typed in a masked field; never echoed back. */
    secret?: boolean
    choices?: unknown[]
    /** For type 'path': what the path names. */
    path?: 'file' | 'directory' | 'any'
    label?: string
    example?: unknown
    /** Asked for at run time when an interactive run does not give it. */
    prompt?: boolean
}

export interface PluginOutputSpec {
    name: string
    type: PluginArgumentType
    description: string
}

/**
 * Arguments a plugin takes and outputs it publishes: declared in its
 * plugin.json, or (plugins installed before contracts) recovered from its source.
 */
export interface PluginContract extends PluginItem {
    description: string | null
    contract?: 'declared' | 'inferred'
    arguments: PluginArgumentSpec[]
    outputs: string[]
    output_details?: PluginOutputSpec[]
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
        removed: string[] = [],
    ): Promise<PluginValidationResponse> {
        return apiRequest<PluginValidationResponse>(
            pluginPath(qualifiedName, '/validate'),
            {
                method: 'POST',
                headers: jsonHeaders,
                body: JSON.stringify({ files, removed }),
                signal,
            },
        )
    },

    save(
        qualifiedName: string,
        files: Record<string, string>,
        revision: string,
        install = false,
        /** Files to delete; a moved file is its new path plus the old one here. */
        removed: string[] = [],
    ): Promise<PluginFilesResponse> {
        return apiRequest<PluginFilesResponse>(
            pluginPath(qualifiedName, '/files'),
            {
                method: 'PUT',
                headers: jsonHeaders,
                body: JSON.stringify({ files, revision, install, removed }),
            },
        )
    },

    /**
     * plugin.json with "arguments" and "outputs" filled in from the source
     * (unsaved edits included); what is declared already is kept.
     */
    generateContract(
        qualifiedName: string,
        files: Record<string, string>,
        removed: string[] = [],
    ): Promise<{ content: string; added: { arguments: string[]; outputs: string[] } }> {
        return apiRequest(pluginPath(qualifiedName, '/contract'), {
            method: 'POST',
            headers: jsonHeaders,
            body: JSON.stringify({ files, removed }),
        })
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

    /** Plugins shipped with this Entropy release that are new or newer than installed. */
    updates(): Promise<BundledUpdates> {
        return apiRequest<BundledUpdates>('/api/plugins/updates')
    },

    installUpdates(names: string[]): Promise<{ installed: PluginItem[]; failed: { qualified_name: string; error: string }[] }> {
        return apiRequest('/api/plugins/updates/install', {
            method: 'POST',
            headers: jsonHeaders,
            body: JSON.stringify({ names }),
        })
    },
}

export interface BundledUpdate {
    qualified_name: string
    kind: 'new' | 'upgrade'
    installed_version: string | null
    available_version: string
    display_name: string
    description: string
}

export interface BundledUpdates {
    items: BundledUpdate[]
    /** Set when the bundled plugin folder could not be read. */
    error: string | null
    can_install: boolean
}

/** A plugin's help page (GET /api/plugins/{name}/docs). */
export interface PluginDocs extends PluginItem {
    description: string | null
    author: string | null
    license: string | null
    tags: string[]
    dependencies: string[]
    /** Entropy versions the plugin supports, e.g. ">=1.0.0". */
    entropy: string | null
    arguments: PluginArgumentSpec[]
    outputs: string[]
    /** A workflow step using the plugin. */
    usage: Record<string, unknown>
    /** The step comes from the plugin's own example workflow. */
    usage_from_example: boolean
    /** MAN.md or README.md rendered as safe HTML (no raw HTML, safe links only). */
    manual: { file: string; html: string } | null
    /** Workflows with steps using it; empty without workflow read access. */
    used_by: { name: string; version: string; steps: string[] }[]
}

export function getPluginDocs(qualifiedName: string): Promise<PluginDocs> {
    return apiRequest<PluginDocs>(`/api/plugins/${encodeURIComponent(qualifiedName)}/docs`)
}
