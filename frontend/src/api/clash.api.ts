import { apiRequest, downloadUrl } from '../services/api'

/** One database and schema; credentials are read from the project's Vault on the server. */
export interface ClashDatabaseSide {
    host: string
    port: number
    sid: string
    schema_name: string
    namespace: string
    key: string
}

export type ClashStatus =
    | 'same'
    | 'different'
    | 'only_left'
    | 'only_right'
    | 'error'
    | 'not_compared'

export interface ClashDdlItem {
    type: string
    name: string
    status: ClashStatus
    left?: string
    right?: string
    error?: string
}

export interface ClashDataItem {
    table: string
    status: ClashStatus
    key?: string[]
    left_rows?: number | null
    right_rows?: number | null
    columns_only_left?: string[]
    columns_only_right?: string[]
    columns_not_compared?: string[]
    error?: string
}

export interface ClashDatabaseResult {
    left: string
    right: string
    ddl: ClashDdlItem[] | null
    data: ClashDataItem[] | null
}

export interface ClashChangedRow {
    key: string[]
    left: string[]
    right: string[]
    columns: string[]
}

export interface ClashRowsResult {
    table: string
    columns: string[]
    key: string[]
    same: number
    only_left_count: number
    only_right_count: number
    changed_count: number
    only_left: string[][]
    only_right: string[][]
    changed: ClashChangedRow[]
    truncated: boolean
    limit: number
}

export type ClashCompareState = 'analyzing' | 'waiting' | 'running' | 'done' | 'failed' | 'stopped'

/** What Vision shows of a comparison under way. */
export interface ClashCompareBrief {
    id: string
    state: ClashCompareState
    phase: 'analyze' | 'ddl' | 'data'
    left: string
    right: string
    current: string | null
    done: number
    total: number
    stopping: boolean
}

/** How much hashing a comparison would mean, from Oracle's statistics. */
export interface ClashEstimate {
    tables: number
    rows: number
    largest: { table: string; rows: number }[]
    unknown: string[]
    unknown_count: number
    large_count: number
    needs_consent: boolean
}

export interface ClashCompareJob extends ClashCompareBrief {
    rows_done: number
    rows_total: number
    elapsed_seconds: number
    /** Since the last step finished: how to tell a long table from a stuck one. */
    quiet_seconds: number
    error: string | null
    estimate: ClashEstimate | null
    sides: { left: ClashDatabaseSide; right: ClashDatabaseSide }
    ddl: boolean
    data: boolean
    name_filter: string | null
    object_types: string[] | null
    skipped: number
}

export function isCompareActive(job: { state: ClashCompareState }): boolean {
    return job.state === 'analyzing' || job.state === 'waiting' || job.state === 'running'
}

/** One line for what a comparison is doing. */
export function compareLabel(job: ClashCompareBrief): string {
    if (job.state === 'waiting') return 'Database compare is waiting for you'
    if (job.stopping) return 'Stopping the database compare'
    if (job.phase === 'analyze') return 'Database compare: reading table sizes'
    const noun = job.phase === 'ddl' ? 'objects' : 'tables'
    return `Database compare: ${job.done.toLocaleString()} of ${job.total.toLocaleString()} ${noun}`
}

function post<T>(path: string, body: unknown): Promise<T> {
    return apiRequest<T>(`/api/clash/database/${path}`, {
        method: 'POST',
        credentials: 'same-origin',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
    })
}

export const clashApi = {
    compare(payload: {
        left: ClashDatabaseSide
        right: ClashDatabaseSide
        ddl: boolean
        data: boolean
        name_filter: string | null
        object_types: string[] | null
    }): Promise<ClashCompareJob> {
        return post('compare', payload)
    },

    current(): Promise<{ job: ClashCompareJob | null }> {
        return apiRequest('/api/clash/database/compare/current')
    },

    job(id: string): Promise<ClashCompareJob> {
        return apiRequest(`/api/clash/database/compare/${id}`)
    },

    confirm(id: string, skipLarge: boolean): Promise<ClashCompareJob> {
        return post(`compare/${id}/confirm`, { skip_large: skipLarge })
    },

    stop(id: string): Promise<ClashCompareJob> {
        return post(`compare/${id}/stop`, {})
    },

    result(id: string): Promise<ClashDatabaseResult> {
        return apiRequest(`/api/clash/database/compare/${id}/result`)
    },

    downloadReport(job: ClashCompareJob): Promise<void> {
        const name = `database-compare-${job.left}-${job.right}`.replace(/[^A-Za-z0-9._-]+/g, '_')
        return downloadUrl(`/api/clash/database/compare/${job.id}/report`, `${name}.html`)
    },

    rows(payload: {
        left: ClashDatabaseSide
        right: ClashDatabaseSide
        table: string
    }): Promise<ClashRowsResult> {
        return post('rows', payload)
    },
}
