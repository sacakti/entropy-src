/**
 * Folder compare model: merge two file lists by relative path, then build a
 * tree whose folders summarise the status of everything below them.
 */
import type { FolderEntry } from './files'

export type EntryStatus = 'identical' | 'different' | 'left-only' | 'right-only' | 'pending'

export type CompareEntry = {
    path: string
    left?: File
    right?: File
}

export type FileNode = {
    kind: 'file'
    name: string
    path: string
    depth: number
    entry: CompareEntry
    status: EntryStatus
}

export type DirNode = {
    kind: 'dir'
    name: string
    path: string
    depth: number
    children: TreeNode[]
    status: EntryStatus
}

export type TreeNode = FileNode | DirNode

export type StatusCounts = Record<EntryStatus, number>

export const STATUS_LABELS: Record<EntryStatus, string> = {
    identical: 'Identical',
    different: 'Different',
    'left-only': 'Only in original',
    'right-only': 'Only in changed',
    pending: 'Comparing…',
}

const collator = new Intl.Collator(undefined, { numeric: true, sensitivity: 'base' })

/** Entries of both folders keyed by relative path, sorted by path. */
export function mergeFolders(left: FolderEntry[], right: FolderEntry[]): CompareEntry[] {
    const byPath = new Map<string, CompareEntry>()

    for (const { path, file } of left) byPath.set(path, { path, left: file })
    for (const { path, file } of right) {
        const entry = byPath.get(path)
        if (entry) entry.right = file
        else byPath.set(path, { path, right: file })
    }

    return [...byPath.values()].sort((a, b) => collator.compare(a.path, b.path))
}

/** Status known without reading content; `pending` needs a content check. */
export function initialStatus(entry: CompareEntry): EntryStatus {
    if (!entry.right) return 'left-only'
    if (!entry.left) return 'right-only'
    if (entry.left.size !== entry.right.size) return 'different'
    return 'pending'
}

export function countStatuses(statuses: Iterable<EntryStatus>): StatusCounts {
    const counts: StatusCounts = { identical: 0, different: 0, 'left-only': 0, 'right-only': 0, pending: 0 }
    for (const status of statuses) counts[status] += 1
    return counts
}

function folderStatus(children: TreeNode[]): EntryStatus {
    const statuses = new Set(children.map((child) => child.status))

    if (statuses.size === 1) return children[0].status
    if (statuses.has('pending')) return 'pending'
    return 'different'
}

function sortChildren(children: TreeNode[]) {
    children.sort((a, b) =>
        a.kind === b.kind ? collator.compare(a.name, b.name) : a.kind === 'dir' ? -1 : 1,
    )
}

/** Build the folder tree; a folder's status is its children's when they all agree. */
export function buildTree(entries: CompareEntry[], statuses: Map<string, EntryStatus>): TreeNode[] {
    const root: DirNode = { kind: 'dir', name: '', path: '', depth: -1, children: [], status: 'identical' }
    const dirs = new Map<string, DirNode>([['', root]])

    const dirFor = (path: string): DirNode => {
        const existing = dirs.get(path)
        if (existing) return existing

        const slash = path.lastIndexOf('/')
        const parent = dirFor(slash >= 0 ? path.slice(0, slash) : '')
        const node: DirNode = {
            kind: 'dir',
            name: path.slice(slash + 1),
            path,
            depth: parent.depth + 1,
            children: [],
            status: 'identical',
        }

        parent.children.push(node)
        dirs.set(path, node)
        return node
    }

    for (const entry of entries) {
        const slash = entry.path.lastIndexOf('/')
        const parent = dirFor(slash >= 0 ? entry.path.slice(0, slash) : '')

        parent.children.push({
            kind: 'file',
            name: entry.path.slice(slash + 1),
            path: entry.path,
            depth: parent.depth + 1,
            entry,
            status: statuses.get(entry.path) ?? initialStatus(entry),
        })
    }

    // Children before parents: deepest folders first.
    const ordered = [...dirs.values()].sort((a, b) => b.depth - a.depth)
    for (const dir of ordered) {
        sortChildren(dir.children)
        if (dir.children.length > 0) dir.status = folderStatus(dir.children)
    }

    return root.children
}

export type VisibleRow = { node: TreeNode; open: boolean }

/**
 * Rows to render, depth first. With `differencesOnly`, identical files and
 * folders are left out. A folder is open unless toggled; by default
 * identical folders start closed.
 */
export function visibleRows(
    nodes: TreeNode[],
    differencesOnly: boolean,
    toggled: Map<string, boolean>,
): VisibleRow[] {
    const rows: VisibleRow[] = []

    const walk = (list: TreeNode[]) => {
        for (const node of list) {
            if (differencesOnly && node.status === 'identical') continue

            if (node.kind === 'dir') {
                const open = toggled.get(node.path) ?? node.status !== 'identical'
                rows.push({ node, open })
                if (open) walk(node.children)
            } else {
                rows.push({ node, open: false })
            }
        }
    }

    walk(nodes)
    return rows
}
