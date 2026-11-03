import { apiRequest } from '../services/api'

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
    }): Promise<ClashDatabaseResult> {
        return post('compare', payload)
    },

    rows(payload: {
        left: ClashDatabaseSide
        right: ClashDatabaseSide
        table: string
    }): Promise<ClashRowsResult> {
        return post('rows', payload)
    },
}
