import type { EagleItem, EagleRequestData, EagleRow } from '../../../api/eagleapi.api'

export const METHODS = ['GET', 'POST', 'PUT', 'PATCH', 'DELETE', 'HEAD', 'OPTIONS'] as const

export const ENV_STORAGE_KEY = 'entropy.eagleapi.environment'

export function emptyRow(): EagleRow {
    return { key: '', value: '', enabled: true }
}

export function defaultRequest(): EagleRequestData {
    return {
        method: 'GET',
        url: '',
        params: [],
        headers: [],
        body: { mode: 'none', json: '', form: [], raw: '', content_type: 'text/plain' },
        auth: {
            type: 'none',
            username: '',
            password: '',
            token: '',
            token_url: '',
            client_id: '',
            client_secret: '',
            scope: '',
            client_auth: 'body',
        },
        tls: {
            mode: 'inherit',
            profile: '',
            verify: true,
            client_cert: 'none',
            cert: '',
            key: '',
            pfx: '',
            password: '',
            ca_bundle: '',
        },
        options: { timeout: 30, follow_redirects: true },
        polling: {
            enabled: false,
            extract: { source: 'json', expression: '' },
            method: 'GET',
            reuse_auth: true,
            interval: 2,
            max_attempts: 30,
            stop: { type: 'json', path: 'status', values: 'COMPLETED,FAILED', status: 202, on_error: true },
        },
    }
}

export function sameRequest(a: EagleRequestData | null, b: EagleRequestData | null): boolean {
    return JSON.stringify(a) === JSON.stringify(b)
}

export type TreeNode = EagleItem & { children: TreeNode[] }

/** The flat item list as a tree, siblings ordered by position then name. */
export function buildTree(items: EagleItem[]): TreeNode[] {
    const nodes = new Map<number, TreeNode>()
    for (const item of items) nodes.set(item.id, { ...item, children: [] })

    const roots: TreeNode[] = []
    for (const node of nodes.values()) {
        const parent = node.parent_id === null ? null : nodes.get(node.parent_id)
        if (parent) parent.children.push(node)
        else roots.push(node)
    }

    const order = (list: TreeNode[]) => {
        list.sort((a, b) => a.position - b.position || a.name.localeCompare(b.name) || a.id - b.id)
        list.forEach((node) => order(node.children))
    }
    order(roots)
    return roots
}

/** Ids of an item and everything below it. */
export function subtreeIds(items: EagleItem[], id: number): Set<number> {
    const found = new Set<number>([id])
    let grew = true
    while (grew) {
        grew = false
        for (const item of items) {
            if (item.parent_id !== null && found.has(item.parent_id) && !found.has(item.id)) {
                found.add(item.id)
                grew = true
            }
        }
    }
    return found
}

/** "main / app1 / REQ1" */
export function itemPath(items: EagleItem[], id: number | null): string {
    const byId = new Map(items.map((item) => [item.id, item]))
    const parts: string[] = []
    let current = id === null ? undefined : byId.get(id)
    while (current) {
        parts.unshift(current.name)
        current = current.parent_id === null ? undefined : byId.get(current.parent_id)
    }
    return parts.join(' / ')
}

export function formatBytes(size: number): string {
    if (size < 1024) return `${size} B`
    if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`
    return `${(size / (1024 * 1024)).toFixed(1)} MB`
}

/** Pretty JSON when the text is JSON, else null. */
export function prettyJson(text: string): string | null {
    const trimmed = text.trim()
    if (!trimmed || !'{["'.includes(trimmed[0])) return null
    try {
        return JSON.stringify(JSON.parse(trimmed), null, 2)
    } catch {
        return null
    }
}

export function vaultRef(namespace: string, key: string, file = false): string {
    return `\${${file ? 'entvfile' : 'entv'}:${namespace}/${key}}`
}
