import { apiRequest } from '../services/api'

export type RunState =
    | 'queued'
    | 'starting'
    | 'running'
    | 'paused'
    | 'completed'
    | 'failed'
    | 'cancelled'

export type RunTab = 'active' | 'completed' | 'failed' | 'cancelled' | 'all'

export const ACTIVE_STATES: readonly RunState[] = ['queued', 'starting', 'running', 'paused']

export interface Run {
    id: number
    execution_id: string
    workflow: string
    state: RunState
    pid: number | null
    user_id: number | null
    username: string | null
    full_name: string | null
    created_at: string | null
    started_at: string | null
    finished_at: string | null
    exit_code: number | null
    node: string
    kind: 'workflow' | 'plugin'
    target: string
    trigger: 'manual' | 'schedule' | 'retry' | 'cli'
    schedule_id: number | null
    /** The run's plan when it started (newer runs only). */
    options?: RunOptionsSnapshot | null
    /** Set on a segment of a multi-node run. */
    parent_job_id?: number | null
    /** Runs steps on several nodes, one segment after another. */
    coordinated?: boolean
}

export interface StepDependency {
    step: string
    output: string
}

export interface RunSegment {
    node: string
    steps: string[]
}

/** What a run recorded about its plan (variable names only, no values). */
export interface RunOptionsSnapshot {
    default_node: string
    tags: string[]
    selected: string[]
    skipped: string[]
    nodes: string[]
    segments: RunSegment[]
    variables: string[]
    steps: PlannedStep[]
}

export interface RunOptions {
    steps?: string[]
    tags?: string[]
    step_nodes?: Record<string, string>
}

export interface RunStep {
    id: string | null
    name: string
    status: 'started' | 'completed' | 'failed' | 'skipped' | string
    started_at: string | null
    finished_at: string | null
    duration_ms: number | null
}

export interface PlannedStep {
    name: string
    plugin: string
    enabled: boolean
    // Present on runs that recorded their plan.
    tags?: string[]
    selected?: boolean
    skip_reason?: 'disabled' | 'tag filter' | 'not selected' | null
    node?: string
    depends_on?: StepDependency[]
}

export interface RunEvent {
    id: number
    type: string
    source: string | null
    level: string | null
    message: string | null
    node_type: string | null
    node_id: string | null
    node_name: string | null
    payload: Record<string, unknown> | null
    created_at: string | null
}

export interface RunListResponse {
    items: Run[]
    total: number
    counts: Record<RunTab, number>
}

export interface RunListQuery {
    tab?: RunTab
    search?: string
    node?: string
    user?: string
    limit?: number
    offset?: number
}

export interface RunEventsResponse {
    run: Run
    steps: RunStep[]
    events: RunEvent[]
    cursor: number | null
}

export interface RunLog {
    offset: number
    size: number
    text: string
}

export interface Housekeeping {
    archive_after_days: number
    purge_archive_after_days: number
    archived: { jobs: number; events: number }
}

function json(method: string, body?: unknown): RequestInit {
    return {
        method,
        headers: { 'Content-Type': 'application/json' },
        body: body === undefined ? undefined : JSON.stringify(body),
    }
}

export const runsApi = {
    list(query: RunListQuery = {}): Promise<RunListResponse> {
        const params = new URLSearchParams()
        Object.entries(query).forEach(([key, value]) => {
            if (value !== undefined && value !== '') params.set(key, String(value))
        })
        return apiRequest(`/api/runs?${params.toString()}`)
    },

    get(id: number): Promise<{ run: Run; plan: PlannedStep[]; steps: RunStep[] }> {
        return apiRequest(`/api/runs/${id}`)
    },

    events(id: number, after: number | null): Promise<RunEventsResponse> {
        const params = new URLSearchParams({ limit: '1000' })
        if (after !== null) params.set('after', String(after))
        return apiRequest(`/api/runs/${id}/events?${params.toString()}`)
    },

    log(id: number, offset: number): Promise<RunLog> {
        return apiRequest(`/api/runs/${id}/log?offset=${offset}`)
    },

    stop(id: number): Promise<{ run: Run }> {
        return apiRequest(`/api/runs/${id}/stop`, json('POST'))
    },

    startWorkflow(
        name: string,
        node: string,
        variables: Record<string, unknown> = {},
        options: RunOptions = {},
    ): Promise<{ run: Run }> {
        return apiRequest(
            `/api/workflows/${encodeURIComponent(name)}/run`,
            json('POST', { node, variables, ...options }),
        )
    },

    /** The steps, nodes and segments a run with these options would follow. */
    planWorkflow(
        name: string,
        node: string,
        options: RunOptions = {},
    ): Promise<{ valid: true; plan: RunOptionsSnapshot } | { valid: false; error: string }> {
        return apiRequest(
            `/api/workflows/${encodeURIComponent(name)}/plan`,
            json('POST', { node, ...options }),
        )
    },

    startPlugin(
        qualifiedName: string,
        node: string,
        argumentsMap: Record<string, unknown> = {},
    ): Promise<{ run: Run }> {
        return apiRequest(
            `/api/plugins/${encodeURIComponent(qualifiedName)}/run`,
            json('POST', { node, arguments: argumentsMap }),
        )
    },

    housekeeping(): Promise<Housekeeping> {
        return apiRequest('/api/runs-housekeeping')
    },

    updateHousekeeping(
        values: Partial<Pick<Housekeeping, 'archive_after_days' | 'purge_archive_after_days'>> & {
            run_now?: boolean
        },
    ): Promise<Housekeeping & { result: Record<string, number> | null }> {
        return apiRequest('/api/runs-housekeeping', json('PUT', values))
    },
}

// ----------------------------------------------------------------------
// Nodes
// ----------------------------------------------------------------------

export interface NodeMetrics {
    cpu: { percent: number | null; count: number | null }
    memory: { total: number | null; used: number | null; percent: number | null }
    disk: {
        total: number | null
        used: number | null
        free?: number | null
        percent: number | null
        path: string
    }
    load: (number | null)[]
    uptime_seconds: number | null
    agent_up: boolean
    running_jobs: number
}

export interface EntropyNode {
    id: number
    name: string
    kind: 'local' | 'remote'
    host: string
    description: string
    enabled: boolean
    info: Record<string, string>
    created_at: string
    updated_at: string
    last_seen_at: string | null
    agent_up: boolean
    running_jobs: number
    metrics: NodeMetrics | null
    port: number
    ssh_user: string
    install_dir: string
    host_key: string | null
    server_url: string | null
    agent_version: string | null
    max_jobs: number
}

export type SshAuth = 'password' | 'key' | 'server'

export interface NodeCredentials {
    auth: SshAuth
    password?: string
    private_key?: string
    passphrase?: string
    forget_host_key?: boolean
}

export interface NodeSetupInput extends NodeCredentials {
    name: string
    host: string
    port: number
    ssh_user: string
    server_url: string
    verify_tls: boolean
    ca_cert?: string
    python: 'auto' | 'system' | 'bundled'
    install_dir: string
    max_jobs: number
    description: string
    /** Also install the `ent` command line, preset to this server. */
    install_cli: boolean
}

export interface ProvisioningRecord {
    id: number
    node: string
    action: 'install' | 'uninstall'
    status: 'running' | 'succeeded' | 'failed'
    log: { at: string; level: 'info' | 'success' | 'warning' | 'error'; message: string }[]
    error: string | null
    username: string | null
    created_at: string
    finished_at: string | null
}

export interface MetricSample {
    sampled_at: string
    cpu_percent: number | null
    memory_percent: number | null
    disk_percent: number | null
    load1: number | null
    running_jobs: number
    agent_up: number
}

/** Where this server listens and how nodes can reach it. */
export interface ServerAddress {
    bind_host: string
    port: number
    /** Listens on loopback only: no other machine can connect. */
    local_only: boolean
    suggestions: string[]
    advice?: string
}

export const nodesApi = {
    list(): Promise<{ items: EntropyNode[] }> {
        return apiRequest('/api/nodes')
    },

    serverAddress(): Promise<ServerAddress> {
        return apiRequest('/api/nodes/server-address')
    },

    get(name: string, hours = 1): Promise<{ node: EntropyNode; history: MetricSample[] }> {
        return apiRequest(`/api/nodes/${encodeURIComponent(name)}?hours=${hours}`)
    },

    update(
        name: string,
        values: { description?: string; enabled?: boolean; max_jobs?: number },
    ): Promise<{ node: EntropyNode }> {
        return apiRequest(`/api/nodes/${encodeURIComponent(name)}`, json('PATCH', values))
    },

    add(values: NodeSetupInput): Promise<{ provisioning_id: number; node: string }> {
        return apiRequest('/api/nodes', json('POST', values))
    },

    setup(values: NodeSetupInput): Promise<{ provisioning_id: number; node: string }> {
        return apiRequest(`/api/nodes/${encodeURIComponent(values.name)}/setup`, json('POST', values))
    },

    remove(
        name: string,
        values: NodeCredentials & { uninstall: boolean },
    ): Promise<{ removed: boolean; provisioning_id?: number }> {
        return apiRequest(`/api/nodes/${encodeURIComponent(name)}/remove`, json('POST', values))
    },

    provisioning(id: number): Promise<ProvisioningRecord> {
        return apiRequest(`/api/nodes/provisioning/${id}`)
    },

    latestProvisioning(name: string): Promise<{ provisioning: ProvisioningRecord | null }> {
        return apiRequest(`/api/nodes/${encodeURIComponent(name)}/provisioning`)
    },

    metricsUrl(name?: string): string {
        return name ? `/api/nodes/${encodeURIComponent(name)}/metrics` : '/api/nodes/metrics'
    },
}

// ----------------------------------------------------------------------
// Schedules
// ----------------------------------------------------------------------

export interface ScheduleRun {
    id: number
    schedule_id: number
    schedule: string | null
    job_id: number | null
    trigger: 'schedule' | 'manual' | 'retry'
    state: 'running' | 'completed' | 'failed' | 'cancelled' | 'error' | 'retried'
    error: string | null
    retry_of: number | null
    created_at: string
    finished_at: string | null
}

export interface Schedule {
    id: number
    name: string
    description: string
    kind: 'workflow' | 'plugin'
    target: string
    cron: string
    timezone: string
    node: string
    parameters: Record<string, unknown>
    enabled: boolean
    user_id: number
    username: string
    created_at: string
    updated_at: string
    next_run_at: string | null
    last_run_at: string | null
    last_run?: ScheduleRun | null
    failed_runs?: number
}

export type ScheduleInput = Pick<
    Schedule,
    'name' | 'description' | 'kind' | 'target' | 'cron' | 'timezone' | 'node' | 'parameters' | 'enabled'
>

export const schedulesApi = {
    list(): Promise<{ items: Schedule[]; failed: ScheduleRun[] }> {
        return apiRequest('/api/schedules')
    },

    get(id: number): Promise<{ schedule: Schedule; runs: ScheduleRun[] }> {
        return apiRequest(`/api/schedules/${id}`)
    },

    preview(
        cron: string,
        timezone: string,
    ): Promise<{ valid: boolean; error: string | null; next: string[] }> {
        const params = new URLSearchParams({ cron, timezone })
        return apiRequest(`/api/schedules/preview?${params.toString()}`)
    },

    create(values: ScheduleInput): Promise<{ schedule: Schedule }> {
        return apiRequest('/api/schedules', json('POST', values))
    },

    update(id: number, values: Partial<ScheduleInput>): Promise<{ schedule: Schedule }> {
        return apiRequest(`/api/schedules/${id}`, json('PATCH', values))
    },

    remove(ids: number[]): Promise<{ deleted: number }> {
        return apiRequest('/api/schedules/delete', json('POST', { ids }))
    },

    trigger(id: number): Promise<{ run: ScheduleRun }> {
        return apiRequest(`/api/schedules/${id}/trigger`, json('POST'))
    },

    retry(ids: number[]): Promise<{ runs: ScheduleRun[] }> {
        return apiRequest('/api/schedules/runs/retry', json('POST', { ids }))
    },

    dismiss(ids: number[]): Promise<{ dismissed: number }> {
        return apiRequest('/api/schedules/runs/dismiss', json('POST', { ids }))
    },
}
