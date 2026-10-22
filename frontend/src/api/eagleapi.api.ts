import { apiRequest } from '../services/api'

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
    tls: {
        verify: boolean
        client_cert: ClientCertMode
        cert: string
        key: string
        pfx: string
        password: string
        ca_bundle: string
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

    send: (request: EagleRequestData, environment: string | null, pollUrl?: string, signal?: AbortSignal) =>
        apiRequest<EagleResult>(`${BASE}/send`, {
            ...json('POST', { request, environment, poll_url: pollUrl ?? null }),
            signal,
        }),
}
