export interface TreeRow {
    kind: 'folder' | 'file'
    path: string
    label: string
    depth: number
}

/** Folders (also empty ones made here) and files, folders first at each level. */
export function buildTree(paths: string[], folders: string[] = []): TreeRow[] {
    const all = new Set<string>()
    for (const folder of folders) {
        const parts = folder.split('/')
        for (let depth = 1; depth <= parts.length; depth += 1) all.add(parts.slice(0, depth).join('/'))
    }
    for (const path of paths) {
        const parts = path.split('/')
        for (let depth = 1; depth < parts.length; depth += 1) all.add(parts.slice(0, depth).join('/'))
    }

    const rows: TreeRow[] = []
    const walk = (parent: string, depth: number) => {
        const prefix = parent ? `${parent}/` : ''
        const children = (items: Iterable<string>) =>
            [...items]
                .filter((item) => item.startsWith(prefix) && !item.slice(prefix.length).includes('/'))
                .sort((left, right) => left.localeCompare(right))
        for (const folder of children(all)) {
            rows.push({ kind: 'folder', path: folder, label: folder.slice(prefix.length), depth })
            walk(folder, depth + 1)
        }
        for (const file of children(paths)) {
            rows.push({ kind: 'file', path: file, label: file.slice(prefix.length), depth })
        }
    }
    walk('', 0)
    return rows
}
