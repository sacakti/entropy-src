import { apiRequest, downloadFile } from '../services/api'

const today = () => new Date().toISOString().slice(0, 10)

const projectPath = (key: string, action: string) => `/api/projects/${encodeURIComponent(key)}/${action}`

export interface TransferResult {
    workflows: { name: string; as: string }[]
    schedules: { name: string; as: string }[]
    errors: string[]
    source: string
    target: string
    mode: 'move' | 'copy'
}

export interface VaultRestoreSummary {
    namespaces: { name: string; created: boolean; added: number; updated: number; skipped: number; error: string | null }[]
    added: number
    updated: number
    skipped: number
}

export interface DumpManifest {
    format: string
    version: number
    entropy_version: string
    project: { key: string; name: string; description: string }
    created_at: string
    created_by: string
    workflows: string[]
    schedules: number
    plugins: string[]
    plugins_used: string[]
    vault: boolean
}

export interface RestoreResult {
    workflows: { name: string; as: string; replaced: boolean }[]
    skipped: string[]
    skipped_schedules: string[]
    schedules: { name: string; as: string }[]
    plugins: string[]
    errors: string[]
    vault: VaultRestoreSummary | null
    manifest: DumpManifest
}

export interface DumpOptions {
    workflows?: string[] | null
    schedules: boolean
    plugins: boolean
    vault: string[]
    passphrase: string
}

export interface RestoreOptions {
    conflict: 'skip' | 'overwrite' | 'rename'
    schedules: boolean
    plugins: boolean
    vault: boolean
    vault_overwrite: boolean
    passphrase: string
}

function form(file: File, fields: Record<string, string | boolean>): FormData {
    const body = new FormData()
    body.append('file', file)
    for (const [key, value] of Object.entries(fields)) body.append(key, String(value))
    return body
}

export const transferApi = {
    /** Move or copy workflows and schedules from project `source` to `target`. */
    transfer(
        source: string,
        body: { target: string; mode: 'move' | 'copy'; workflows?: string[]; schedules?: number[]; with_schedules?: boolean },
    ): Promise<TransferResult> {
        return apiRequest(projectPath(source, 'transfer'), {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body),
        })
    },

    dump(key: string, options: DumpOptions): Promise<void> {
        return downloadFile(projectPath(key, 'dump'), options, `entropy-${key}-${today()}.zip`)
    },

    preview(key: string, file: File): Promise<{ manifest: DumpManifest }> {
        return apiRequest(projectPath(key, 'restore'), { method: 'POST', body: form(file, { preview: true }) })
    },

    restore(key: string, file: File, options: RestoreOptions): Promise<RestoreResult> {
        return apiRequest(projectPath(key, 'restore'), { method: 'POST', body: form(file, { ...options }) })
    },

    exportVault(namespaces: string[], passphrase: string): Promise<void> {
        const name = namespaces.length === 1 ? namespaces[0] : 'entropy-vault'
        return downloadFile('/api/vault/export', { namespaces, passphrase }, `${name}-${today()}.entvault`)
    },

    importVault(
        file: File,
        passphrase: string,
        overwrite: boolean,
    ): Promise<VaultRestoreSummary & { exported_by: string | null; exported_at: string | null }> {
        return apiRequest('/api/vault/import', { method: 'POST', body: form(file, { passphrase, overwrite }) })
    },
}
