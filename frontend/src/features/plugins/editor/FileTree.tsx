import { useEffect, useRef, useState, type DragEvent as ReactDragEvent, type MouseEvent as ReactMouseEvent, type ReactNode } from 'react'
import {
    Braces,
    ChevronDown,
    ChevronRight,
    FileCode2,
    FilePlus2,
    FileText,
    Folder,
    FolderInput,
    FolderOpen,
    FolderPlus,
    Info,
    Pencil,
    Trash2,
} from 'lucide-react'

import type { TreeRow } from './tree'

export function FileIcon({ path }: { path: string }) {
    if (path.endsWith('.py')) return <FileCode2 size={15} className="plugin-ide-icon-py" />
    if (path.endsWith('.json')) return <Braces size={15} className="plugin-ide-icon-json" />
    return <FileText size={15} className="plugin-ide-icon-md" />
}

export interface FileTreeActions {
    open: (path: string) => void
    newFile: (folder: string) => void
    newFolder: (folder: string) => void
    rename: (row: TreeRow, name: string) => void
    move: (row: TreeRow, folder: string) => void
    remove: (row: TreeRow) => void
    info: (row: TreeRow) => void
}

interface Menu {
    row: TreeRow | null
    x: number
    y: number
    moving?: boolean
}

/**
 * The plugin's files: folders open and close; files and folders are moved
 * by dragging them onto a folder (or the empty space, for the top level),
 * and a right click offers new, rename, move, delete and info.
 */
export default function FileTree({
    rows,
    activePath,
    readOnly,
    renaming,
    onRenamingDone,
    badges,
    actions,
}: {
    rows: TreeRow[]
    activePath: string | null
    readOnly: boolean
    /** Row whose name is being edited in place. */
    renaming: string | null
    onRenamingDone: () => void
    badges: (path: string) => ReactNode
    actions: FileTreeActions
}) {
    const [closed, setClosed] = useState<Record<string, boolean>>({})
    const [menu, setMenu] = useState<Menu | null>(null)
    const [dropTarget, setDropTarget] = useState<string | null>(null)
    const menuRef = useRef<HTMLDivElement>(null)
    const folders = rows.filter((row) => row.kind === 'folder').map((row) => row.path)

    useEffect(() => {
        if (!menu) return
        const close = (event: Event) => {
            if (!menuRef.current?.contains(event.target as Node)) setMenu(null)
        }
        const escape = (event: KeyboardEvent) => {
            if (event.key === 'Escape') setMenu(null)
        }
        document.addEventListener('pointerdown', close)
        document.addEventListener('keydown', escape)
        return () => {
            document.removeEventListener('pointerdown', close)
            document.removeEventListener('keydown', escape)
        }
    }, [menu])

    const visible = rows.filter((row) => {
        const parts = row.path.split('/')
        for (let depth = 1; depth < parts.length; depth += 1) {
            if (closed[parts.slice(0, depth).join('/')]) return false
        }
        return true
    })

    const parentOf = (path: string) => (path.includes('/') ? path.slice(0, path.lastIndexOf('/')) : '')

    const drop = (event: ReactDragEvent, folder: string) => {
        event.preventDefault()
        event.stopPropagation()
        setDropTarget(null)
        if (readOnly) return
        const raw = event.dataTransfer.getData('application/x-entropy-tree')
        if (!raw) return
        const row = JSON.parse(raw) as TreeRow
        if (parentOf(row.path) === folder) return
        if (row.kind === 'folder' && (folder === row.path || folder.startsWith(`${row.path}/`))) return
        actions.move(row, folder)
    }

    const openMenu = (event: ReactMouseEvent, row: TreeRow | null) => {
        event.preventDefault()
        event.stopPropagation()
        setMenu({ row, x: event.clientX, y: event.clientY })
    }

    const item = (label: string, icon: ReactNode, run: () => void, destructive = false) => (
        <button
            type="button"
            role="menuitem"
            className={destructive ? 'is-destructive' : undefined}
            onClick={() => {
                setMenu(null)
                run()
            }}
        >
            {icon}
            {label}
        </button>
    )

    const menuFolder = menu?.row ? (menu.row.kind === 'folder' ? menu.row.path : parentOf(menu.row.path)) : ''

    return (
        <div
            className={`plugin-ide-tree-area${dropTarget === '' ? ' is-drop-target' : ''}`}
            onContextMenu={(event) => openMenu(event, null)}
            onDragOver={(event) => {
                if (readOnly) return
                event.preventDefault()
                setDropTarget('')
            }}
            onDragLeave={() => setDropTarget(null)}
            onDrop={(event) => drop(event, '')}
        >
            <ul className="plugin-ide-tree" role="tree">
                {visible.map((row) => {
                    const indent = { paddingLeft: 10 + row.depth * 14 }
                    const editing = renaming === row.path
                    const common = {
                        draggable: !readOnly && !editing,
                        onDragStart: (event: ReactDragEvent) => {
                            event.dataTransfer.setData('application/x-entropy-tree', JSON.stringify(row))
                            event.dataTransfer.effectAllowed = 'move'
                        },
                        onContextMenu: (event: ReactMouseEvent) => openMenu(event, row),
                        title: row.path,
                    }

                    if (editing) {
                        return (
                            <li key={`${row.kind}:${row.path}`} style={indent} className="plugin-ide-tree-rename">
                                {row.kind === 'folder' ? <Folder size={15} /> : <FileIcon path={row.path} />}
                                <RenameInput
                                    initial={row.label}
                                    onDone={(name) => {
                                        onRenamingDone()
                                        if (name && name !== row.label) actions.rename(row, name)
                                    }}
                                />
                            </li>
                        )
                    }

                    return row.kind === 'folder' ? (
                        <li key={`folder:${row.path}`} role="treeitem" aria-expanded={!closed[row.path]}>
                            <button
                                type="button"
                                className={`plugin-ide-tree-file plugin-ide-tree-folder${
                                    dropTarget === row.path ? ' is-drop-target' : ''
                                }`}
                                style={indent}
                                onClick={() => setClosed((current) => ({ ...current, [row.path]: !current[row.path] }))}
                                onDragOver={(event) => {
                                    if (readOnly) return
                                    event.preventDefault()
                                    event.stopPropagation()
                                    setDropTarget(row.path)
                                }}
                                onDrop={(event) => drop(event, row.path)}
                                {...common}
                            >
                                {closed[row.path] ? <ChevronRight size={13} /> : <ChevronDown size={13} />}
                                {closed[row.path] ? <Folder size={15} /> : <FolderOpen size={15} />}
                                <span className="plugin-ide-tree-label">{row.label}</span>
                            </button>
                        </li>
                    ) : (
                        <li key={row.path} role="treeitem" aria-selected={row.path === activePath}>
                            <button
                                type="button"
                                className={`plugin-ide-tree-file${row.path === activePath ? ' is-active' : ''}`}
                                style={{ ...indent, paddingLeft: indent.paddingLeft + 17 }}
                                onClick={() => actions.open(row.path)}
                                {...common}
                            >
                                <FileIcon path={row.path} />
                                <span className="plugin-ide-tree-label">{row.label}</span>
                                {badges(row.path)}
                            </button>
                        </li>
                    )
                })}
            </ul>

            {menu && (
                <div
                    ref={menuRef}
                    className="plugin-ide-context-menu"
                    role="menu"
                    style={{ left: Math.min(menu.x, window.innerWidth - 230), top: Math.min(menu.y, window.innerHeight - 280) }}
                    onContextMenu={(event) => event.preventDefault()}
                >
                    {menu.moving && menu.row ? (
                        <>
                            <p className="plugin-ide-context-title">Move {menu.row.label} to…</p>
                            {['', ...folders]
                                .filter(
                                    (folder) =>
                                        folder !== parentOf(menu.row!.path) &&
                                        !(menu.row!.kind === 'folder' &&
                                            (folder === menu.row!.path || folder.startsWith(`${menu.row!.path}/`))),
                                )
                                .map((folder) =>
                                    item(folder || '(top level)', <Folder size={14} />, () => actions.move(menu.row!, folder)),
                                )}
                        </>
                    ) : (
                        <>
                            {menu.row?.kind === 'file' && item('Open', <FileText size={14} />, () => actions.open(menu.row!.path))}
                            {!readOnly && item('New file', <FilePlus2 size={14} />, () => actions.newFile(menuFolder))}
                            {!readOnly && item('New folder', <FolderPlus size={14} />, () => actions.newFolder(menuFolder))}
                            {menu.row && !readOnly && (
                                <>
                                    <hr />
                                    {item('Rename', <Pencil size={14} />, () => actions.rename(menu.row!, ''))}
                                    <button
                                        type="button"
                                        role="menuitem"
                                        onClick={() => setMenu({ ...menu, moving: true })}
                                    >
                                        <FolderInput size={14} />
                                        Move to…
                                    </button>
                                    {item('Delete', <Trash2 size={14} />, () => actions.remove(menu.row!), true)}
                                </>
                            )}
                            {menu.row && (
                                <>
                                    <hr />
                                    {item('Info', <Info size={14} />, () => actions.info(menu.row!))}
                                </>
                            )}
                        </>
                    )}
                </div>
            )}
        </div>
    )
}

function RenameInput({ initial, onDone }: { initial: string; onDone: (name: string | null) => void }) {
    const [value, setValue] = useState(initial)
    const ref = useRef<HTMLInputElement>(null)
    const done = useRef(false)

    useEffect(() => {
        const input = ref.current
        if (!input) return
        input.focus()
        // Select the name without its extension, as editors do.
        const dot = initial.lastIndexOf('.')
        input.setSelectionRange(0, dot > 0 ? dot : initial.length)
    }, [initial])

    const finish = (name: string | null) => {
        if (done.current) return
        done.current = true
        onDone(name)
    }

    return (
        <input
            ref={ref}
            value={value}
            aria-label="New name"
            spellCheck={false}
            onChange={(event) => setValue(event.target.value)}
            onBlur={() => finish(value.trim())}
            onKeyDown={(event) => {
                if (event.key === 'Enter') finish(value.trim())
                if (event.key === 'Escape') finish(null)
            }}
        />
    )
}
