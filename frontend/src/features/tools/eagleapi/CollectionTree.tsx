import { useRef, useState, type DragEvent } from 'react'
import {
    ChevronRight,
    Copy,
    Download,
    FilePlus,
    Folder,
    FolderInput,
    FolderOpen,
    FolderPlus,
    Lock,
    MoreHorizontal,
    Pencil,
    Trash2,
    Users,
} from 'lucide-react'

import FloatingMenu from '../../../components/layout/FloatingMenu'
import type { EagleItem } from '../../../api/eagleapi.api'
import { buildTree, itemReadOnlyReason, type TreeNode } from './model'

export type TreeAction =
    | { kind: 'new-folder'; parentId: number | null }
    | { kind: 'new-request'; parentId: number | null }
    | { kind: 'rename'; item: EagleItem }
    | { kind: 'duplicate'; item: EagleItem }
    | { kind: 'move'; item: EagleItem }
    | { kind: 'delete'; item: EagleItem }
    | { kind: 'access'; item: EagleItem }
    | { kind: 'export'; item: EagleItem }


const DRAG_TYPE = 'application/x-entropy-eagle-item'

function ItemMenu({
    item,
    onAction,
    readOnlyReason,
}: {
    item: EagleItem
    onAction: (action: TreeAction) => void
    readOnlyReason: string | null
}) {
    const [open, setOpen] = useState(false)
    const triggerRef = useRef<HTMLButtonElement>(null)
    const pick = (action: TreeAction, always = false) => () => {
        setOpen(false)
        if (always || !readOnlyReason) onAction(action)
    }
    const topLevel = item.parent_id === null
    const disabled = readOnlyReason ? true : undefined

    return (
        <>
            <button
                ref={triggerRef}
                type="button"
                className="eagle-tree-more"
                aria-label={`Actions for ${item.name}`}
                aria-haspopup="menu"
                aria-expanded={open}
                onClick={(event) => {
                    event.stopPropagation()
                    setOpen((value) => !value)
                }}
            >
                <MoreHorizontal size={15} />
            </button>
            <FloatingMenu anchorRef={triggerRef} open={open} onClose={() => setOpen(false)} className="eagle-menu">
                {item.kind === 'folder' && (
                    <>
                        <button
                            type="button"
                            role="menuitem"
                            aria-disabled={disabled}
                            title={readOnlyReason ?? undefined}
                            onClick={pick({ kind: 'new-request', parentId: item.id })}
                        >
                            <FilePlus size={15} /> New request here
                        </button>
                        <button
                            type="button"
                            role="menuitem"
                            aria-disabled={disabled}
                            title={readOnlyReason ?? undefined}
                            onClick={pick({ kind: 'new-folder', parentId: item.id })}
                        >
                            <FolderPlus size={15} /> New folder here
                        </button>
                    </>
                )}
                <button
                    type="button"
                    role="menuitem"
                    aria-disabled={disabled}
                    title={readOnlyReason ?? undefined}
                    onClick={pick({ kind: 'rename', item })}
                >
                    <Pencil size={15} /> Rename
                </button>
                <button
                    type="button"
                    role="menuitem"
                    aria-disabled={disabled}
                    title={readOnlyReason ?? undefined}
                    onClick={pick({ kind: 'duplicate', item })}
                >
                    <Copy size={15} /> Duplicate
                </button>
                <button
                    type="button"
                    role="menuitem"
                    aria-disabled={disabled}
                    title={readOnlyReason ?? undefined}
                    onClick={pick({ kind: 'move', item })}
                >
                    <FolderInput size={15} /> Move to…
                </button>
                <button type="button" role="menuitem" onClick={pick({ kind: 'export', item }, true)}>
                    <Download size={15} /> Export…
                </button>
                {topLevel && (
                    <button type="button" role="menuitem" onClick={pick({ kind: 'access', item }, true)}>
                        <Users size={15} /> Access…
                    </button>
                )}
                <button
                    type="button"
                    role="menuitem"
                    className="eagle-menu-danger"
                    aria-disabled={disabled}
                    title={readOnlyReason ?? undefined}
                    onClick={pick({ kind: 'delete', item })}
                >
                    <Trash2 size={15} /> Delete
                </button>
            </FloatingMenu>
        </>
    )
}

/**
 * The project's collections: folders (any depth) and requests. Requests
 * open in the editor; items can be dragged onto folders (or before a
 * request) to move them.
 */
export default function CollectionTree({
    items,
    selectedId,
    dirtyId,
    expanded,
    onToggle,
    onSelect,
    onAction,
    onMove,
    readOnlyReason,
}: {
    items: EagleItem[]
    selectedId: number | null
    /** The open request, when it has unsaved changes. */
    dirtyId: number | null
    expanded: Set<number>
    onToggle: (id: number) => void
    onSelect: (item: EagleItem) => void
    onAction: (action: TreeAction) => void
    onMove: (id: number, parentId: number | null, position?: number) => void
    readOnlyReason: string | null
}) {
    const [dropTarget, setDropTarget] = useState<string | null>(null)
    const tree = buildTree(items)
    const canDrag = !readOnlyReason
    const byId = new Map(items.map((item) => [item.id, item]))
    const writable = (id: number | null) => id === null || byId.get(id)?.access !== 'read'

    const dragStart = (event: DragEvent, item: EagleItem) => {
        event.dataTransfer.setData(DRAG_TYPE, String(item.id))
        event.dataTransfer.effectAllowed = 'move'
    }

    const allowDrop = (event: DragEvent, target: string) => {
        if (!canDrag || !event.dataTransfer.types.includes(DRAG_TYPE)) return
        event.preventDefault()
        event.dataTransfer.dropEffect = 'move'
        if (dropTarget !== target) setDropTarget(target)
    }

    const drop = (event: DragEvent, parentId: number | null, position?: number) => {
        event.preventDefault()
        event.stopPropagation()
        setDropTarget(null)
        const id = Number(event.dataTransfer.getData(DRAG_TYPE))
        if (id && id !== parentId && writable(id) && writable(parentId)) onMove(id, parentId, position)
    }

    const renderNode = (node: TreeNode, depth: number) => {
        const isFolder = node.kind === 'folder'
        const open = expanded.has(node.id)
        const target = `${node.kind}-${node.id}`

        return (
            <li key={node.id} role="treeitem" aria-expanded={isFolder ? open : undefined} aria-selected={node.id === selectedId}>
                <div
                    className={[
                        'eagle-tree-row',
                        node.id === selectedId ? 'is-selected' : '',
                        dropTarget === target ? 'is-drop-target' : '',
                    ]
                        .filter(Boolean)
                        .join(' ')}
                    style={{ paddingLeft: 6 + depth * 14 }}
                    draggable={canDrag && node.access !== 'read'}
                    onDragStart={(event) => dragStart(event, node)}
                    onDragEnd={() => setDropTarget(null)}
                    onDragOver={(event) => allowDrop(event, target)}
                    onDragLeave={() => setDropTarget((current) => (current === target ? null : current))}
                    onDrop={(event) =>
                        isFolder ? drop(event, node.id) : drop(event, node.parent_id, node.position)
                    }
                >
                    <button
                        type="button"
                        className="eagle-tree-label"
                        onClick={() => (isFolder ? onToggle(node.id) : onSelect(node))}
                        title={node.name}
                    >
                        {isFolder ? (
                            <>
                                <ChevronRight size={14} className={`eagle-tree-chevron${open ? ' is-open' : ''}`} aria-hidden="true" />
                                {open ? <FolderOpen size={15} aria-hidden="true" /> : <Folder size={15} aria-hidden="true" />}
                            </>
                        ) : (
                            <span className={`eagle-method eagle-method-${(node.method ?? 'GET').toLowerCase()}`}>
                                {node.method ?? 'GET'}
                            </span>
                        )}
                        <span className="eagle-tree-name">{node.name}</span>
                        {node.restricted && (
                            <Lock size={12} className="eagle-tree-lock" aria-label="Only some project members can see this" />
                        )}
                        {node.id === dirtyId && <span className="eagle-dirty-dot" aria-label="Unsaved changes" />}
                    </button>
                    <ItemMenu item={node} onAction={onAction} readOnlyReason={itemReadOnlyReason(node, readOnlyReason)} />
                </div>
                {isFolder && open && node.children.length > 0 && (
                    <ul role="group">{node.children.map((child) => renderNode(child, depth + 1))}</ul>
                )}
                {isFolder && open && node.children.length === 0 && (
                    <p className="eagle-tree-empty" style={{ paddingLeft: 30 + depth * 14 }}>
                        Empty folder
                    </p>
                )}
            </li>
        )
    }

    return (
        <div
            className={`eagle-tree${dropTarget === 'root' ? ' is-drop-target' : ''}`}
            onDragOver={(event) => allowDrop(event, 'root')}
            onDragLeave={(event) => {
                if (event.target === event.currentTarget) setDropTarget(null)
            }}
            onDrop={(event) => drop(event, null)}
        >
            {tree.length > 0 ? (
                <ul role="tree" aria-label="Collections">
                    {tree.map((node) => renderNode(node, 0))}
                </ul>
            ) : (
                <div className="eagle-tree-blank">
                    <p>No collections yet.</p>
                    <p className="eagle-muted">Create a folder (e.g. “main”) and add requests to it.</p>
                </div>
            )}
        </div>
    )
}
