import type { NodeCredentials } from '../../api/runs.api'

export function credentialsReady(value: NodeCredentials): boolean {
    if (value.auth === 'password') return Boolean(value.password)
    if (value.auth === 'key') return Boolean(value.private_key?.trim())
    return true
}
