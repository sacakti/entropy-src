import { apiRequest } from "../services/api"

export interface ApplicationVersion {
    name: string
    version: string
}

export async function getApplicationVersion(): Promise<ApplicationVersion> {
    return apiRequest<ApplicationVersion>('/api/version', {
        method: 'GET',
        credentials: 'same-origin',
        cache: 'no-store',
    })
}

export interface ReleaseSection {
    title: string
    items: string[]
}

export interface ReleaseNote {
    version: string
    date: string | null
    sections: ReleaseSection[]
    /** Items left out to keep the notes short. */
    more?: number
}

export interface ReleaseNotes {
    version: string
    /** Newest first. */
    releases: ReleaseNote[]
    /** What this person has not been shown yet. */
    unseen: ReleaseNote[]
}

export function getReleaseNotes(): Promise<ReleaseNotes> {
    return apiRequest<ReleaseNotes>('/api/version/notes', { method: 'GET', credentials: 'same-origin', cache: 'no-store' })
}

export function markReleaseNotesSeen(): Promise<unknown> {
    return apiRequest('/api/version/notes/seen', { method: 'POST', credentials: 'same-origin' })
}
