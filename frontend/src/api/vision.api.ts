import { apiRequest } from '../services/api'

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

export interface VisionStatus {
    enabled: boolean
    broadcasts: VisionBroadcast[]
    /** The current project shows its members each other's runs, not only their own. */
    project_activity: boolean
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
