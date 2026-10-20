import type { Run, RunState } from '../../api/runs.api'

export function errorMessage(error: unknown, fallback: string): string {
    return error instanceof Error ? error.message : fallback
}

export function formatDateTime(value: string | null | undefined): string {
    if (!value) return '—'
    const date = new Date(value)
    return Number.isNaN(date.getTime())
        ? '—'
        : new Intl.DateTimeFormat(undefined, { dateStyle: 'medium', timeStyle: 'medium' }).format(date)
}

export function formatTime(value: string | null | undefined): string {
    if (!value) return ''
    const date = new Date(value)
    return Number.isNaN(date.getTime())
        ? ''
        : new Intl.DateTimeFormat(undefined, { timeStyle: 'medium' }).format(date)
}

export function formatDuration(milliseconds: number | null | undefined): string {
    if (milliseconds === null || milliseconds === undefined || milliseconds < 0) return '—'
    const seconds = Math.floor(milliseconds / 1000)
    if (seconds < 1) return `${Math.max(0, Math.round(milliseconds))} ms`
    if (seconds < 60) return `${seconds}s`
    const minutes = Math.floor(seconds / 60)
    if (minutes < 60) return `${minutes}m ${seconds % 60}s`
    const hours = Math.floor(minutes / 60)
    return `${hours}h ${minutes % 60}m`
}

/** Elapsed time of a run, ticking while it is active. */
export function runDuration(run: Run, now: number): number | null {
    const start = run.started_at ?? run.created_at
    if (!start) return null
    const end = run.finished_at ? new Date(run.finished_at).getTime() : now
    return end - new Date(start).getTime()
}

export function formatBytes(value: number | null | undefined): string {
    if (value === null || value === undefined) return '—'
    const units = ['B', 'KB', 'MB', 'GB', 'TB']
    let size = value
    let unit = 0
    while (size >= 1024 && unit < units.length - 1) {
        size /= 1024
        unit += 1
    }
    return `${size >= 10 || unit === 0 ? Math.round(size) : size.toFixed(1)} ${units[unit]}`
}

export const STATE_LABELS: Record<RunState, string> = {
    queued: 'Queued',
    starting: 'Starting',
    running: 'Running',
    paused: 'Paused',
    completed: 'Completed',
    failed: 'Failed',
    cancelled: 'Cancelled',
}

export function isActive(state: RunState): boolean {
    return state === 'queued' || state === 'starting' || state === 'running' || state === 'paused'
}

/** Message levels arrive as logging numbers (20, 25, 40) or names. */
export function levelName(level: string | null): 'debug' | 'info' | 'success' | 'warning' | 'error' {
    if (!level) return 'info'
    const number = Number(level)
    if (!Number.isNaN(number)) {
        if (number >= 40) return 'error'
        if (number >= 30) return 'warning'
        if (number >= 25) return 'success'
        if (number >= 20) return 'info'
        return 'debug'
    }
    const name = level.toLowerCase()
    if (name.startsWith('err') || name === 'critical') return 'error'
    if (name.startsWith('warn')) return 'warning'
    if (name === 'success') return 'success'
    if (name === 'debug') return 'debug'
    return 'info'
}

export function runnerName(run: Run): string {
    return run.full_name || run.username || 'Unknown'
}

export const TRIGGER_LABELS: Record<Run['trigger'], string> = {
    manual: 'Manual',
    schedule: 'Schedule',
    retry: 'Retry',
    cli: 'CLI',
}
