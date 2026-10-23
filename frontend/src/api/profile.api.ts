import { apiRequest } from '../services/api'

export interface Profile {
    id: number
    username: string
    full_name: string | null
    email: string | null
    /** Linked sign-in provider; null for a password managed by Entropy. */
    auth_provider: 'ldap' | 'oidc' | null
    /** Versioned URL of the profile picture, or null when none is set. */
    avatar_url: string | null
}

export function getProfile(): Promise<Profile> {
    return apiRequest<Profile>('/api/profile')
}

export function updateProfile(changes: {
    full_name: string | null
    email: string | null
}): Promise<Profile> {
    return apiRequest<Profile>('/api/profile', {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(changes),
    })
}

export function uploadAvatar(file: File): Promise<Profile> {
    const body = new FormData()
    body.append('file', file)

    return apiRequest<Profile>('/api/profile/avatar', { method: 'PUT', body })
}

export function removeAvatar(): Promise<Profile> {
    return apiRequest<Profile>('/api/profile/avatar', { method: 'DELETE' })
}
