
import { apiRequest } from '../services/api'

export type WorkflowJobState =
    | 'queued'
    | 'starting'
    | 'running'
    | 'paused'
    | 'completed'
    | 'failed'
    | 'cancelled'

export interface DashboardSummary {
    total: number
    queued: number
    starting: number
    running: number
    paused: number
    completed: number
    failed: number
    cancelled: number
}

export interface DashboardExecution {
    id: number
    execution_id: string
    workflow: string
    state: WorkflowJobState
    created_at: string | null
    started_at: string | null
    finished_at: string | null
    exit_code: number | null
}

export interface DashboardData {
    summary: DashboardSummary
    active_executions: DashboardExecution[]
    recent_executions: DashboardExecution[]
}

export async function getDashboard(): Promise<DashboardData> {
    return apiRequest<DashboardData>('/api/dashboard')
}
