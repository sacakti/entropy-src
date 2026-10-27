import { apiRequest, downloadFile } from '../services/api'

/** One key/value row (params, headers, form fields). */
export interface EagleRow {
    key: string
    value: string
    enabled: boolean
}

export type BodyMode = 'none' | 'json' | 'form' | 'raw'
export type AuthType = 'none' | 'basic' | 'bearer' | 'oauth2'
export type ClientCertMode = 'none' | 'pem' | 'pfx'
export type PollSource = 'json' | 'header' | 'regex'
export type StopType = 'json' | 'status' | 'none'

/** TLS settings: server verification and client certificate (vault references). */
export interface EagleTls {
    verify: boolean
    client_cert: ClientCertMode
    cert: string
    key: string
    pfx: string
    password: string
    ca_bundle: string
}

export type TlsMode = 'inherit' | 'profile' | 'custom'

export type EagleTlsProfile = EagleTls & { id: string; name: string }

/** The project's EagleAPI settings. */
export interface EagleSettings {
    tls_profiles: EagleTlsProfile[]
    /** Id of the profile requests inherit; empty for the plain defaults. */
    default_tls: string
}

/** A request definition, as stored server-side (every field present). */
export interface EagleRequestData {
    method: string
    url: string
    params: EagleRow[]
    headers: EagleRow[]
    body: {
        mode: BodyMode
        json: string
        form: EagleRow[]
        raw: string
        content_type: string
    }
    auth: {
        type: AuthType
        username: string
        password: string
        token: string
        token_url: string
        client_id: string
        client_secret: string
        scope: string
        client_auth: 'body' | 'basic'
    }
    tls: EagleTls & {
        /** inherit: the project's default profile; profile: a named profile; custom: the fields here. */
        mode: TlsMode
        /** Profile id, for mode "profile". */
        profile: string
    }
    options: {
        timeout: number
        follow_redirects: boolean
    }
    polling: {
        enabled: boolean
        extract: { source: PollSource; expression: string }
        method: string
        reuse_auth: boolean
        interval: number
        max_attempts: number
        stop: {
            type: StopType
            path: string
            values: string
            status: number
            on_error: boolean
        }
    }
}

export type EagleItemKind = 'folder' | 'request'

export interface EagleItem {
    id: number
    parent_id: number | null
    kind: EagleItemKind
    name: string
    position: number
    /** Requests only. */
    method?: string
    created_by: string | null
    updated_at: string
    /** Present when fetched one by one (requests). */
    data?: EagleRequestData
    /** Your access to the item's collection; "manage" also changes who may use it. */
    access: 'read' | 'write' | 'manage'
    /** Top-level items: only some project members may use it. */
    restricted?: boolean
}

export interface EagleAccessEntry {
    kind: 'user' | 'group'
    name: string
    full_name?: string | null
    level: 'read' | 'write'
}

export interface EagleAccessInfo {
    restricted: boolean
    owner: string | null
    entries: EagleAccessEntry[]
    can_manage: boolean
    candidates: { users: { name: string; full_name?: string | null }[]; groups: { name: string }[] }
}

export interface EagleHistorySummary {
    id: number
    item_id: number | null
    item_name: string | null
    environment: string | null
    method: string
    url: string
    status: number | null
    error: string | null
    elapsed_ms: number
    poll: boolean
    created_at: string
}

export interface EagleHistoryEntry extends EagleHistorySummary {
    definition: EagleRequestData | null
    result: EagleResult | null
}

export type ExportFormat = 'eagleapi' | 'postman' | 'soapui'

export interface ImportSummary {
    format: 'eagleapi' | 'postman' | 'soapui' | 'insomnia'
    name: string
    collections: string[]
    folders: number
    requests: number
    warnings: string[]
    tls_profiles: number
    created?: number[]
    added_profiles?: string[]
}

export interface EagleEnvEntry {
    key: string
    type: string
    sensitive: boolean
    updated_at: string | null
    /** Only for values that are not sensitive. */
    value?: string
    file?: { filename: string; content_type: string; size: number }
}

export interface EagleEnvironment {
    namespace: string
    exists: boolean
    access: 'read' | 'write' | 'admin' | null
    entries: EagleEnvEntry[]
    environments: string[]
    /** Why the entries cannot be shown (no access to the namespace). */
    message?: string
}

export interface EagleSentRequest {
    method: string
    url: string
    headers: [string, string][]
}

export interface EagleResult {
    status?: number
    reason?: string
    elapsed_ms: number
    size?: number
    headers?: [string, string][]
    body?: string
    is_base64?: boolean
    truncated?: boolean
    final_url?: string
    /** A network failure (refused, timeout, TLS…); no response then. */
    error?: string
    request: EagleSentRequest
    /** After the main call: the poll URL (or why none was found). After a poll: the stop state. */
    poll?: { url?: string; error?: string; done?: boolean; reason?: string; value?: unknown }
    /** Where the TLS settings came from: "request", "profile <name>", "default <name>" or "none". */
    tls_source?: string
    /** The first TLS handshake was dropped and the request sent again. */
    tls_retry?: string
    /** The history entry of this call, when it was recorded. */
    history_id?: number
}

const BASE = '/api/eagleapi'

function json(method: string, body: unknown): RequestInit {
    return { method, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) }
}

export const eagleApi = {
    listItems: () => apiRequest<{ items: EagleItem[] }>(`${BASE}/items`).then((r) => r.items),

    getItem: (id: number) => apiRequest<{ item: EagleItem }>(`${BASE}/items/${id}`).then((r) => r.item),

    createItem: (payload: {
        kind: EagleItemKind
        name: string
        parent_id: number | null
        data?: EagleRequestData
    }) => apiRequest<{ item: EagleItem }>(`${BASE}/items`, json('POST', payload)).then((r) => r.item),

    updateItem: (id: number, payload: { name?: string; data?: EagleRequestData }) =>
        apiRequest<{ item: EagleItem }>(`${BASE}/items/${id}`, json('PATCH', payload)).then((r) => r.item),

    moveItem: (id: number, parentId: number | null, position?: number) =>
        apiRequest<{ item: EagleItem }>(
            `${BASE}/items/${id}/move`,
            json('POST', { parent_id: parentId, position }),
        ).then((r) => r.item),

    duplicateItem: (id: number) =>
        apiRequest<{ item: EagleItem }>(`${BASE}/items/${id}/duplicate`, { method: 'POST' }).then(
            (r) => r.item,
        ),

    deleteItem: (id: number) =>
        apiRequest<{ deleted: number }>(`${BASE}/items/${id}`, { method: 'DELETE' }),

    settings: () => apiRequest<EagleSettings>(`${BASE}/settings`),

    saveSettings: (settings: EagleSettings) => apiRequest<EagleSettings>(`${BASE}/settings`, json('PUT', settings)),

    environment: () => apiRequest<EagleEnvironment>(`${BASE}/environment`),

    putEntry: (key: string, value: string, sensitive: boolean) =>
        apiRequest<{ entry: EagleEnvEntry }>(
            `${BASE}/environment/entries/${encodeURIComponent(key)}`,
            json('PUT', { value, sensitive }),
        ),

    uploadEntryFile: (key: string, file: File, sensitive: boolean) => {
        const form = new FormData()
        form.append('key', key)
        form.append('file', file)
        form.append('sensitive', String(sensitive))
        return apiRequest<{ entry: EagleEnvEntry }>(`${BASE}/environment/files`, {
            method: 'POST',
            body: form,
        })
    },

    deleteEntry: (key: string) =>
        apiRequest<{ deleted: string }>(`${BASE}/environment/entries/${encodeURIComponent(key)}`, {
            method: 'DELETE',
        }),

    createEnvironment: (name: string, baseUrl: string, sensitive: boolean) =>
        apiRequest<{ environment: string }>(
            `${BASE}/environment/environments`,
            json('POST', { name, base_url: baseUrl, sensitive }),
        ),

    send: (
        request: EagleRequestData,
        environment: string | null,
        options: { pollUrl?: string; itemId?: number | null; record?: boolean; signal?: AbortSignal } = {},
    ) =>
        apiRequest<EagleResult>(`${BASE}/send`, {
            ...json('POST', {
                request,
                environment,
                poll_url: options.pollUrl ?? null,
                item_id: options.itemId ?? null,
                record_history: options.record ?? true,
            }),
            signal: options.signal,
        }),

    access: (id: number) => apiRequest<EagleAccessInfo>(`${BASE}/items/${id}/access`),

    setAccess: (id: number, restricted: boolean, entries: EagleAccessEntry[]) =>
        apiRequest<EagleAccessInfo>(
            `${BASE}/items/${id}/access`,
            json('PUT', { restricted, entries: entries.map(({ kind, name, level }) => ({ kind, name, level })) }),
        ),

    history: (query = '', limit = 200) =>
        apiRequest<{ entries: EagleHistorySummary[]; total: number }>(
            `${BASE}/history?limit=${limit}&q=${encodeURIComponent(query)}`,
        ),

    historyEntry: (id: number) => apiRequest<{ entry: EagleHistoryEntry }>(`${BASE}/history/${id}`).then((r) => r.entry),

    purgeHistory: (ids: number[] | null) =>
        apiRequest<{ deleted: number }>(`${BASE}/history/purge`, json('POST', { ids })),

    exportHistory: (ids: number[] | null, format: 'json' | 'har') =>
        downloadFile(
            `${BASE}/history/export`,
            { ids, format },
            `eagleapi-history-${new Date().toISOString().slice(0, 10)}.${format === 'har' ? 'har' : 'json'}`,
        ),

    exportCollections: (ids: number[], format: ExportFormat, preserve: boolean, filename: string) =>
        downloadFile(`${BASE}/export`, { ids, format, preserve }, filename),

    importCollections: (file: File, options: { parentId: number | null; preserve: boolean; preview: boolean }) => {
        const form = new FormData()
        form.append('file', file)
        if (options.parentId !== null) form.append('parent_id', String(options.parentId))
        form.append('preserve', String(options.preserve))
        form.append('preview', String(options.preview))
        return apiRequest<ImportSummary>(`${BASE}/import`, { method: 'POST', body: form })
    },
}
