import { apiRequest } from '../services/api'

/** An installed extension version (a library and what came with it). */
export interface ExtensionVersion {
    id: number
    name: string
    canonical: string
    version: string
    source: 'index' | 'upload' | 'server'
    origin: string | null
    summary: string
    /** Everything installed with it: the library and its dependencies. */
    packages: string[]
    /** Dependencies left out because Entropy has the same version. */
    shared: string[]
    size: number
    installed_by: string | null
    installed_at: string
    /** Installed plugins that get this version. */
    used_by: string[]
}

export interface BuiltinLibrary {
    name: string
    version: string
    summary: string
}

export interface RequirementStatus {
    name: string
    requirement: string
    spec: string
    status: 'entropy' | 'extension' | 'missing'
    version: string | null
    available: string[]
    entropy_version: string | null
}

const BASE = '/api/extensions'

function json(method: string, body: unknown): RequestInit {
    return { method, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) }
}

export const extensionsApi = {
    list: () => apiRequest<{ installed: ExtensionVersion[]; builtin: BuiltinLibrary[] }>(BASE),

    install: (payload: { name: string; version?: string; dependencies: boolean; index_url?: string }) =>
        apiRequest<{ extension: ExtensionVersion }>(`${BASE}/install`, json('POST', payload)).then((r) => r.extension),

    upload: (
        file: File,
        options: { name?: string; version?: string; summary?: string; dependencies: boolean; index_url?: string },
    ) => {
        const form = new FormData()
        form.append('file', file)
        for (const [key, value] of Object.entries(options)) {
            if (value !== undefined && value !== '') form.append(key, String(value))
        }
        return apiRequest<{ extension: ExtensionVersion }>(`${BASE}/upload`, { method: 'POST', body: form }).then(
            (r) => r.extension,
        )
    },

    remove: (name: string, version: string) =>
        apiRequest<{ removed: string }>(`${BASE}/${encodeURIComponent(name)}/${encodeURIComponent(version)}`, {
            method: 'DELETE',
        }),

    verify: (name: string, version: string) =>
        apiRequest<{ problems: string[] }>(
            `${BASE}/${encodeURIComponent(name)}/${encodeURIComponent(version)}/verify`,
            { method: 'POST' },
        ),

    repair: (name: string, version: string) =>
        apiRequest<{ extension: ExtensionVersion }>(
            `${BASE}/${encodeURIComponent(name)}/${encodeURIComponent(version)}/repair`,
            { method: 'POST' },
        ),

    /** A plugin's (installed or draft) library requirements and whether they are met. */
    forPlugin: (qualifiedName: string) =>
        apiRequest<{ plugin: string; requirements: RequirementStatus[] }>(
            `${BASE}/plugin/${encodeURIComponent(qualifiedName)}`,
        ).then((r) => r.requirements),

    installMissing: (requirements: { name: string; version?: string | null }[], indexUrl?: string) =>
        apiRequest<{ installed: ExtensionVersion[]; failed: { requirement: string; error: string }[] }>(
            `${BASE}/install-missing`,
            json('POST', { requirements, index_url: indexUrl || null }),
        ),
}
