import { apiRequest } from '../services/api'

/** The remote `ent` command line this server hands out (GET /api/cli). */
export interface CliInfo {
    version: string
    server: string
    requires: string
    downloads: { pyz: string; install_sh: string; install_ps1: string }
    install: { posix: string; windows: string }
    login: string
}

export interface CliToken {
    token: string
    expires_at: string
}

export function getCliInfo(): Promise<CliInfo> {
    return apiRequest<CliInfo>('/api/cli')
}

/** A token for `ent login --token`, issued to the signed-in user. */
export function issueCliToken(): Promise<CliToken> {
    return apiRequest<CliToken>('/api/auth/cli-token', { method: 'POST' })
}
