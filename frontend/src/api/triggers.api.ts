import { apiRequest } from '../services/api'

export type TriggerSource = 'webhook' | 'queue'

/** Runs a workflow or plugin when its webhook is called or a queue message arrives. */
export interface Trigger {
    id: number
    project_id: number
    name: string
    description: string
    source: TriggerSource
    kind: 'workflow' | 'plugin'
    target: string
    node: string
    parameters: Record<string, unknown>
    /** A JSON object payload overrides the parameters key by key. */
    use_payload: boolean
    /** Queue triggers: the STOMP destination, e.g. /queue/deploy.orders. */
    destination: string | null
    /** Webhooks: where to POST (the public address when one is set). */
    hook_url: string | null
    /** The last 4 characters of the secret token, to tell tokens apart. */
    token_hint: string | null
    has_token: boolean
    enabled: boolean
    username: string
    created_at: string
    updated_at: string
    last_fired_at: string | null
    fired: number
    failed_to_start: number
}

export type TriggerInput = Pick<
    Trigger,
    'name' | 'description' | 'source' | 'kind' | 'target' | 'node' | 'parameters' | 'use_payload' | 'destination' | 'enabled'
>

/** One firing: the run it started, or why it could not start. */
export interface TriggerRun {
    id: number
    trigger_id: number
    job_id: number | null
    source: TriggerSource | 'manual'
    error: string | null
    payload: string | null
    caller: string | null
    created_at: string
    /** The run's state while the run is kept; "error" when it never started. */
    state: string | null
}

/** The queue listener on the main node: listening, off (and why) or an error. */
export interface ListenerStatus {
    state: 'listening' | 'off' | 'error'
    detail: string
    at: string | null
}

const json = (method: string, body?: unknown): RequestInit => ({
    method,
    headers: { 'Content-Type': 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body),
})

export const triggersApi = {
    list(): Promise<{ items: Trigger[]; listener: ListenerStatus }> {
        return apiRequest('/api/triggers')
    },

    get(id: number): Promise<{ trigger: Trigger; runs: TriggerRun[] }> {
        return apiRequest(`/api/triggers/${id}`)
    },

    /** A new webhook's secret token is in `token`, this once. */
    create(values: TriggerInput): Promise<{ trigger: Trigger; token: string | null }> {
        return apiRequest('/api/triggers', json('POST', values))
    },

    update(id: number, values: Partial<TriggerInput>): Promise<{ trigger: Trigger; token: string | null }> {
        return apiRequest(`/api/triggers/${id}`, json('PATCH', values))
    },

    newToken(id: number): Promise<{ trigger: Trigger; token: string }> {
        return apiRequest(`/api/triggers/${id}/token`, json('POST'))
    },

    fire(id: number, payload: string): Promise<{ run: TriggerRun }> {
        return apiRequest(`/api/triggers/${id}/fire`, json('POST', { payload }))
    },

    remove(ids: number[]): Promise<{ deleted: number }> {
        return apiRequest('/api/triggers/delete', json('POST', { ids }))
    },
}
