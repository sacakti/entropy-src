import { apiRequest } from '../services/api'
import type { ClashCompareBrief } from './clash.api'

export type BroadcastLevel = 'info' | 'warning' | 'error'

/** A message an administrator sent to everyone. */
export interface VisionBroadcast {
    id: number
    message: string
    level: BroadcastLevel
    created_by: string
    created_at: string
    /** Null: until someone ends it. */
    expires_at: string | null
}

/** A database switch under way; nothing can be saved until it finishes. */
export interface DatabaseSwitch {
    state: 'idle' | 'copying' | 'restarting' | 'restart_required' | 'failed'
    engine: string | null
    table: string | null
    tables_done: number
    tables_total: number
    rows_done: number
    rows_total: number
    error?: string | null
}

const ENGINE_NAMES: Record<string, string> = { postgresql: 'PostgreSQL', sqlite: 'SQLite' }

/** One line for what a switch is doing. */
export function databaseSwitchLabel(progress: DatabaseSwitch): string {
    const engine = ENGINE_NAMES[progress.engine ?? ''] ?? 'another database'
    if (progress.state === 'restarting') return `Restarting Entropy on ${engine}`
    if (progress.state === 'restart_required') return `Restart Entropy to finish moving to ${engine}`
    if (progress.tables_total === 0) return `Preparing to switch to ${engine}`
    return `Switching to ${engine}: ${progress.tables_done} of ${progress.tables_total} tables`
}

/** Which table, and what it means for people working now. */
export function databaseSwitchDetail(progress: DatabaseSwitch): string {
    if (progress.state === 'restarting') return 'Everyone reconnects in a moment.'
    if (progress.state === 'restart_required') return 'The data is copied. Changes are not saved until the restart.'
    const where = progress.table ? `Copying ${progress.table}. ` : ''
    return `${where}Changes cannot be saved until this finishes.`
}

export interface VisionStatus {
    enabled: boolean
    broadcasts: VisionBroadcast[]
    /** The current project shows its members each other's runs, not only their own. */
    project_activity: boolean
    database_switch?: DatabaseSwitch | null
    /** This person's database comparison under way in this project. */
    clash_compare?: ClashCompareBrief | null
}

const BASE = '/api/vision'

export const visionApi = {
    status: () => apiRequest<VisionStatus>(BASE),
    send: (broadcast: { message: string; level: BroadcastLevel; duration_minutes: number }) =>
        apiRequest<VisionBroadcast>(`${BASE}/broadcasts`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(broadcast),
        }),
    end: (id: number) => apiRequest<unknown>(`${BASE}/broadcasts/${id}`, { method: 'DELETE' }),
}
