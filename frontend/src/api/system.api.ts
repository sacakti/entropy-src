import { ApiError, apiRequest } from '../services/api'

export interface UpgradeHistoryEntry {
    from: string
    to: string
    at: string
    by: string
    rollback?: boolean
    database_backup: string | null
}

export interface UpgradeLogLine {
    at: string
    message: string
}

export interface UpgradeJob {
    id?: string
    action?: 'upgrade' | 'rollback'
    state: 'idle' | 'running' | 'restarting' | 'succeeded' | 'failed'
    target?: string | null
    by?: string
    started_at?: string
    finished_at?: string
    error?: string | null
    log: UpgradeLogLine[]
    version?: string
}

export interface SystemInfo {
    version: string
    python: string
    python_executable: string
    deps: 'bundled' | 'index' | 'manual'
    index_url: string | null
    platform: string | null
    installed_at: string | null
    application: string
    home: string
    installed: boolean
    web: {
        running: boolean
        healthy: boolean
        pid: number | null
        supervisor: string
        url: string
        log: string
        service: string
    }
    upgrades: UpgradeHistoryEntry[]
    can_rollback: boolean
    job: UpgradeJob
}

export interface PackageInfo {
    id: string
    filename: string
    version: string
    current: string
    platform: string | null
    python: string | null
    built_at: string | null
    newer: boolean
    same: boolean
    problems: string[]
    size: number
}

async function csrfToken(): Promise<string> {
    const response = await fetch('/api/auth/csrf', { credentials: 'same-origin', cache: 'no-store' })
    if (!response.ok) throw new Error('Unable to obtain a CSRF token.')
    return ((await response.json()) as { csrf_token: string }).csrf_token
}

/** Upload with progress (fetch cannot report it); resolves to the package description. */
async function uploadPackage(file: File, onProgress: (fraction: number) => void): Promise<PackageInfo> {
    const token = await csrfToken()
    const body = new FormData()
    body.append('file', file)

    return new Promise((resolve, reject) => {
        const request = new XMLHttpRequest()
        request.open('POST', '/api/system/upgrade/package')
        request.withCredentials = true
        request.setRequestHeader('X-CSRF-Token', token)
        request.upload.onprogress = (event) => {
            if (event.lengthComputable) onProgress(event.loaded / event.total)
        }
        request.onerror = () => reject(new Error('The upload failed.'))
        request.onload = () => {
            let data: unknown = null
            try {
                data = JSON.parse(request.responseText)
            } catch {
                // Non-JSON error page.
            }
            if (request.status >= 200 && request.status < 300) {
                resolve(data as PackageInfo)
            } else {
                const detail = (data as { detail?: unknown } | null)?.detail
                reject(
                    new ApiError(
                        typeof detail === 'string' ? detail : `Upload failed (${request.status}).`,
                        request.status,
                        detail,
                    ),
                )
            }
        }
        request.send(body)
    })
}

export const systemApi = {
    info: () => apiRequest<SystemInfo>('/api/system'),
    upload: uploadPackage,
    discard: (id: string) => apiRequest<{ ok: boolean }>(`/api/system/upgrade/package/${id}`, { method: 'DELETE' }),
    apply: (id: string, allowDowngrade: boolean) =>
        apiRequest<UpgradeJob>('/api/system/upgrade', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ id, allow_downgrade: allowDowngrade }),
        }),
    rollback: () => apiRequest<UpgradeJob>('/api/system/rollback', { method: 'POST' }),
    status: () => apiRequest<UpgradeJob>('/api/system/upgrade'),
}
