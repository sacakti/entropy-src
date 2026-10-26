import { apiRequest } from '../services/api'

export interface ServerFileEntry {
    name: string
    path: string
    kind: 'file' | 'directory'
    size: number | null
    modified: string
    readable: boolean
}

export interface ServerFolder {
    path: string
    parent: string | null
    /** Where browsing starts: the workspace, else the server user's home. */
    home: string
    roots: string[]
    separator: string
    /** The file asked for, when a file path was given. */
    selected: string | null
    entries: ServerFileEntry[]
    truncated: boolean
}

/** Files on the Entropy server, for path arguments of plugins and workflows. */
export const serverFilesApi = {
    browse(path = '', hidden = false): Promise<ServerFolder> {
        const query = new URLSearchParams({ path, hidden: String(hidden) })
        return apiRequest<ServerFolder>(`/api/server-files?${query.toString()}`)
    },
}
