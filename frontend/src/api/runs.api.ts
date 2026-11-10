import { apiRequest, downloadFile, downloadUrl } from '../services/api'
import { currentProject } from '../services/project'
import { displayTimeZone } from '../services/timezone'

export type RunState =
    | 'queued'
    | 'starting'
    | 'running'
    | 'paused'
    | 'completed'
    | 'failed'
    | 'cancelled'

export type RunTab = 'active' | 'completed' | 'failed' | 'cancelled' | 'all' | 'archived'

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
    /** A plugin run started with "Debug": its debug messages are shown. */
    debug?: boolean
    /** "interactive": the run's plugins may ask for input on the run screen. */
    mode?: RunMode
    /** Active-runs list only: questions waiting for an answer (input or a paused step). */
    waiting_for_input?: number
    /** Set on a segment of a multi-node run. */
    parent_job_id?: number | null
    /** Runs steps on several nodes, one segment after another. */
    coordinated?: boolean
    archived?: boolean
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
    mode?: RunMode
    steps?: string[]
    tags?: string[]
    step_nodes?: Record<string, string>
}

export interface RunRerunConfig {
    definition: string
    variables: Record<string, unknown>
    node: string
    steps: string[] | null
    tags: string[]
    step_nodes: Record<string, string>
}

/** What a plugin run was started with; a plugin always runs its installed version. */
export interface PluginRerunConfig {
    arguments: Record<string, unknown>
    node: string
    debug?: boolean
    mode?: RunMode
}

/** A file a step of the run generated (registered in Artifacts). */
export interface RunArtifact {
    id: number
    name: string
    size_bytes: number
    step_name: string | null
    origin: string | null
    created_at: string | null
    download_url: string
    available: boolean
}

/** A plain link sends no project header: name the project in the URL. */
export function artifactDownloadUrl(artifact: RunArtifact): string {
    const project = currentProject()
    return `${artifact.download_url}${project ? `?project=${encodeURIComponent(project)}` : ''}`
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
    sort?: RunSortField
    order?: 'asc' | 'desc'
}

export type RunSortField = 'id' | 'run' | 'status' | 'user' | 'node' | 'started' | 'duration'

export type RunMode = 'automated' | 'interactive'

/** A question a plugin of an interactive run waits on. */
/** An input of an app plugin's live page (plugin.json "app.inputs"). */
export interface RunAppInput {
    name: string
    type: 'text' | 'number' | 'select' | 'toggle' | 'button' | 'datetime'
    label: string
    description?: string
    placeholder?: string
    default?: unknown
    choices?: string[]
    /** Buttons: the selectable table whose selected rows are sent. */
    target?: string
}

/** A view the plugin keeps up to date (plugin.json "app.views"). */
export interface RunAppView {
    name: string
    type: 'table' | 'stats' | 'log' | 'keyvalue' | 'text' | 'chart' | 'files'
    label: string
    title?: string
    description?: string
    columns?: { key: string; label: string }[]
    row_key?: string
    selectable?: boolean
    filter?: boolean
    max_lines?: number
    /** Chart: what it can plot, what one line is called, and how many samples it keeps. */
    metrics?: { key: string; label: string }[]
    series_label?: string
    max_points?: number
    /** Shown as a tab of that view (a table's graph) instead of a panel of its own. */
    tab_of?: string
    /** Files: the button pressed with a node's id when it is clicked. */
    open?: string
    /** Files: buttons shown above the tree, pressed with the ticked nodes (the other buttons act on the open file). */
    tree_actions?: string[]
    /** Files: a search box above the tree; its text goes to `input`, then `button` is pressed with the ticked nodes. */
    search?: { input: string; button: string } | null
}

/** One entry of a files view's tree; `parent` is another node's id, or null at the top. */
export interface RunAppFileNode {
    id: string
    name: string
    kind: 'group' | 'folder' | 'file' | 'archive'
    parent: string | null
    size?: number | null
    modified?: string | null
    /** Its children are known (folders and archives are read when first opened). */
    loaded?: boolean
    note?: string | null
}

export interface RunAppDefinition {
    title?: string
    description?: string
    refresh_seconds: number
    inputs: RunAppInput[]
    views: RunAppView[]
}

/** The data the plugin published for one view. */
export interface RunAppViewData {
    columns?: { key: string; label: string }[]
    rows?: Record<string, unknown>[]
    total?: number
    items?: { label?: string; key?: string; value: unknown }[]
    lines?: string[]
    text?: string
    /** Chart samples: one value per metric for each series, in `metrics` order. */
    metrics?: { key: string; label: string }[]
    series_label?: string
    samples?: { at: string; values: Record<string, (number | null)[]> }[]
    /** Files: the tree, and the file open in the viewer. */
    nodes?: RunAppFileNode[]
    opened?: {
        id: string
        title: string
        text: string
        notice?: string | null
        download_name?: string
        /** Text the viewer marks when the file opens (e.g. what was searched for). */
        highlight?: string | null
    } | null
    /** Files: files the plugin offered for download, newest first. */
    downloads?: { id: number; name: string; size: number; url: string }[]
    /** Files: work under way (a download being made), until it is null. */
    progress?: { label: string; done?: number; total?: number; detail?: string } | null
}

/** The live page of an app plugin step. */
export interface RunApp {
    id: number
    job_id: number
    step: string
    plugin: string
    definition: RunAppDefinition
    inputs: Record<string, unknown>
    views: Record<string, RunAppViewData>
    state: 'running' | 'stopping' | 'finished'
    created_at: string
    updated_at: string
}

export interface RunPrompt {
    id: number
    step: string | null
    name: string
    label: string
    description: string
    secret: boolean
    default: string | null
    choices: string[] | null
    state: 'waiting' | 'answered' | 'consumed' | 'expired'
}

export interface RunEventsResponse {
    run: Run
    steps: RunStep[]
    events: RunEvent[]
    cursor: number | null
    /** Questions waiting for an answer (interactive runs). */
    prompts?: RunPrompt[]
}

export interface RunLog {
    offset: number
    size: number
    text: string
}

export interface Housekeeping {
    archive_after_days: number
    purge_archive_after_days: number
    archive_rules: ArchiveRules
    archived: { jobs: number; events: number }
}

export interface ArchiveRules {
    schedule: boolean
    plugin: boolean
    completed: boolean
    failed: boolean
    cancelled: boolean
    workflows: { mode: 'exact' | 'startswith'; pattern: string }[]
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

    artifacts(id: number): Promise<{ items: RunArtifact[] }> {
        return apiRequest(`/api/runs/${id}/artifacts`)
    },

    rerunConfig(id: number): Promise<{ config: RunRerunConfig }> {
        return apiRequest(`/api/runs/${id}/rerun-config`)
    },

    pluginRerunConfig(id: number): Promise<{ config: PluginRerunConfig }> {
        return apiRequest(`/api/runs/${id}/rerun-config`)
    },

    downloadReport(id: number, target: string, format: 'html' | 'pdf'): Promise<void> {
        // Times in the report read as on the run page.
        const zone = encodeURIComponent(displayTimeZone())
        return downloadUrl(`/api/runs/${id}/report?format=${format}&tz=${zone}`, `run-${id}-${target}.${format}`)
    },

    rerunWorkflow(id: number, node: string, variables: Record<string, unknown>, options: RunOptions = {}): Promise<{ run: Run }> {
        return apiRequest(`/api/runs/${id}/rerun`, json('POST', { node, variables, ...options }))
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
        definition?: string,
    ): Promise<{ valid: true; plan: RunOptionsSnapshot } | { valid: false; error: string }> {
        return apiRequest(
            `/api/workflows/${encodeURIComponent(name)}/plan`,
            json('POST', { node, ...options, ...(definition ? { definition } : {}) }),
        )
    },

    startPlugin(
        qualifiedName: string,
        node: string,
        argumentsMap: Record<string, unknown> = {},
        debug = false,
        mode: RunMode = 'automated',
    ): Promise<{ run: Run }> {
        return apiRequest(
            `/api/plugins/${encodeURIComponent(qualifiedName)}/run`,
            json('POST', { node, arguments: argumentsMap, debug, mode }),
        )
    },

    apps(runId: number): Promise<{ items: RunApp[] }> {
        return apiRequest(`/api/runs/${runId}/apps`)
    },

    setAppInputs(runId: number, appId: number, values: Record<string, unknown>): Promise<{ inputs: Record<string, unknown> }> {
        return apiRequest(`/api/runs/${runId}/apps/${appId}/inputs`, json('PUT', { values }))
    },

    pressAppButton(runId: number, appId: number, name: string, selection: unknown[]): Promise<{ ok: boolean }> {
        return apiRequest(`/api/runs/${runId}/apps/${appId}/events`, json('POST', { name, selection }))
    },

    stopApp(runId: number, appId: number): Promise<{ ok: boolean }> {
        return apiRequest(`/api/runs/${runId}/apps/${appId}/stop`, json('POST', {}))
    },

    answerPrompt(runId: number, promptId: number, value: string): Promise<{ prompt: RunPrompt }> {
        return apiRequest(`/api/runs/${runId}/prompts/${promptId}`, json('POST', { value }))
    },

    housekeeping(): Promise<Housekeeping> {
        return apiRequest('/api/runs-housekeeping')
    },

    updateHousekeeping(
        values: Partial<Pick<Housekeeping, 'archive_after_days' | 'purge_archive_after_days' | 'archive_rules'>> & {
            run_now?: boolean
        },
    ): Promise<Housekeeping & { result: Record<string, number> | null }> {
        return apiRequest('/api/runs-housekeeping', json('PUT', values))
    },

    purgeArchive(values: { older_than_days?: number; purge_all?: boolean }): Promise<{ purged_jobs: number; archived: { jobs: number; events: number } }> {
        return apiRequest('/api/runs-housekeeping/purge', json('POST', values))
    },

    exportArchive(values: { older_than_days?: number; purge_all?: boolean }): Promise<void> {
        const date = new Date().toISOString().slice(0, 10)
        return downloadFile('/api/runs-housekeeping/export', values, `entropy-runs-${date}.tar.gz`)
    },

    archiveSelected(jobIds: number[]): Promise<{ result: { jobs: number; events: number } }> {
        return apiRequest('/api/runs-housekeeping/archive-selected', json('POST', { job_ids: jobIds }))
    },

    purgeSelected(jobIds: number[]): Promise<{ purged_jobs: number }> {
        return apiRequest('/api/runs-housekeeping/purge-selected', json('POST', { job_ids: jobIds }))
    },

    exportSelected(jobIds: number[]): Promise<void> {
        const date = new Date().toISOString().slice(0, 10)
        return downloadFile(
            '/api/runs-housekeeping/export-selected',
            { job_ids: jobIds },
            `entropy-selected-runs-${date}.tar.gz`,
        )
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
    file_access: NodeFileAccess
}

/**
 * How runs on a remote node reach files picked on the main node:
 * - off: paths are sent as they are;
 * - fetch: files under `sources` (default: uploaded artifacts and the workspace) are
 *   copied to the node's `workspace` folder before the run, once per content;
 * - shared: both mount the same storage; `main` folders are read as `node` folders.
 */
export type NodeFileAccess =
    | { mode: 'off' }
    | { mode: 'fetch'; workspace: string; sources: string[]; max_gb: number }
    | { mode: 'shared'; mappings: { main: string; node: string }[] }

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
    /** Saved before the setup, which then prepares or checks the folders on the node. */
    file_access?: NodeFileAccess
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

    setFileAccess(name: string, value: NodeFileAccess): Promise<{ node: EntropyNode }> {
        return apiRequest(`/api/nodes/${encodeURIComponent(name)}/file-access`, json('PUT', value))
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
