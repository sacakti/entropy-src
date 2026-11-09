import type { NodeFileAccess } from '../../api/runs.api'

export type Mode = NodeFileAccess['mode']

const ABSOLUTE = /^\/(?!.*(^|\/)\.\.(\/|$))/

/** The settings for a mode, keeping what was typed for it. */
export function fileAccessFor(mode: Mode, current: NodeFileAccess, installDir: string): NodeFileAccess {
    if (mode === current.mode) return current
    if (mode === 'fetch') {
        const base = installDir.startsWith('/') ? installDir.replace(/\/+$/, '') : ''
        return { mode, workspace: base ? `${base}/workspace/files` : '', sources: [], max_gb: 5 }
    }
    if (mode === 'shared') return { mode, mappings: [{ main: '', node: '' }] }
    return { mode: 'off' }
}

/** Why the settings cannot be saved yet, or null. */
export function fileAccessProblem(value: NodeFileAccess): string | null {
    if (value.mode === 'fetch') {
        if (!ABSOLUTE.test(value.workspace.trim()) || value.workspace.trim() === '/') {
            return "Enter the node's workspace folder as an absolute path."
        }
        if (value.sources.some((item) => !ABSOLUTE.test(item.trim()))) {
            return 'Folders to send from must be absolute paths.'
        }
        if (!(value.max_gb > 0 && value.max_gb <= 1000)) return 'The size limit must be 1 to 1000 GB.'
    }
    if (value.mode === 'shared') {
        if (!value.mappings.length) return 'Add the shared folder.'
        if (value.mappings.some((pair) => !ABSOLUTE.test(pair.main.trim()) || !ABSOLUTE.test(pair.node.trim()))) {
            return 'Enter both folders of each pair as absolute paths.'
        }
    }
    return null
}

/** Without blank rows, as the server takes them. */
export function cleanFileAccess(value: NodeFileAccess): NodeFileAccess {
    if (value.mode === 'fetch') {
        return { ...value, workspace: value.workspace.trim(), sources: value.sources.map((item) => item.trim()).filter(Boolean) }
    }
    if (value.mode === 'shared') {
        return { mode: 'shared', mappings: value.mappings.map((pair) => ({ main: pair.main.trim(), node: pair.node.trim() })) }
    }
    return value
}
