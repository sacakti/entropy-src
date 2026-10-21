/**
 * The project the UI works in. Every API request carries its key in the
 * X-Entropy-Project header; the server checks project roles against it.
 */

const STORAGE_KEY = 'entropy.project'

/** Dispatched on `window` after the current project changes. */
export const PROJECT_CHANGED_EVENT = 'entropy:project-changed'

let current: string | null = null

try {
    current = window.localStorage.getItem(STORAGE_KEY)
} catch {
    current = null
}

export function currentProject(): string | null {
    return current
}

export function setCurrentProject(key: string | null): void {
    if (key === current) return
    current = key
    try {
        if (key) window.localStorage.setItem(STORAGE_KEY, key)
        else window.localStorage.removeItem(STORAGE_KEY)
    } catch {
        // Storage may be refused (private windows); the choice lasts this visit.
    }
    window.dispatchEvent(new Event(PROJECT_CHANGED_EVENT))
}

/** Dispatched on `window` after projects are created, renamed or removed. */
export const PROJECTS_UPDATED_EVENT = 'entropy:projects-updated'

export function notifyProjectsUpdated(): void {
    window.dispatchEvent(new Event(PROJECTS_UPDATED_EVENT))
}
