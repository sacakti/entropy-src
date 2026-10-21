import { memo, useCallback, useEffect, useMemo, useRef, useState, type DragEvent } from 'react'
import {
    AlertCircle,
    ChevronDown,
    ChevronRight,
    CircleCheck,
    File as FileIcon,
    Folder,
    FolderOpen,
    LoaderCircle,
    X,
} from 'lucide-react'

import DiffPanel from './DiffPanel'
import DropZone from './DropZone'
import {
    MAX_TEXT_BYTES,
    TextFileError,
    droppedDirectory,
    folderFromEntry,
    folderFromInput,
    formatSize,
    languageFromName,
    readTextFile,
    sameContent,
    type LanguageId,
    type PickedFolder,
} from './files'
import {
    STATUS_LABELS,
    buildTree,
    countStatuses,
    initialStatus,
    mergeFolders,
    visibleRows,
    type CompareEntry,
    type EntryStatus,
    type TreeNode,
} from './folderTree'

type Side = 'left' | 'right'
type Filter = 'all' | 'differences'

/** Content checks running at once; reads are I/O bound. */
const CONCURRENCY = 8
/** Minimum work time between progress renders while checking content. */
const FLUSH_MS = 400
/** Rows rendered before "Show more", to keep huge trees responsive. */
const ROW_PAGE = 1000

type SelectedFile = {
    path: string
    loading: boolean
    error: string | null
    left: string
    right: string
}

const SIDE_LABELS: Record<Side, string> = { left: 'Original folder', right: 'Changed folder' }

const yieldToBrowser = () => new Promise<void>((resolve) => setTimeout(resolve, 0))

/**
 * Check same-size files by content, a few at a time, writing results into
 * `statuses`. Calls `onFlush` at most every FLUSH_MS and then yields, so
 * thousands of files never freeze the page. Stops once `active` is false.
 */
async function checkContents(
    pending: CompareEntry[],
    statuses: Map<string, EntryStatus>,
    active: () => boolean,
    onFlush: (done: number) => void,
) {
    let next = 0
    let done = 0
    let flushed = performance.now()

    const worker = async () => {
        while (next < pending.length && active()) {
            const entry = pending[next]
            next += 1

            let same: boolean
            try {
                same = await sameContent(entry.left as File, entry.right as File)
            } catch {
                // Unreadable (moved or permission lost): report it as different.
                same = false
            }

            if (!active()) return

            statuses.set(entry.path, same ? 'identical' : 'different')
            done += 1

            if (performance.now() - flushed > FLUSH_MS) {
                flushed = Number.POSITIVE_INFINITY
                onFlush(done)
                await yieldToBrowser()
                // Measured after the yield, so the render it triggered does
                // not count as work time.
                flushed = performance.now()
            }
        }
    }

    await Promise.all(Array.from({ length: CONCURRENCY }, worker))
}

// Static on purpose: hundreds of animated spinners in pending rows repaint
// the page every frame and starve the content checks.
function StatusBadge({ status }: { status: EntryStatus }) {
    return <span className={`tools-status is-${status}`}>{STATUS_LABELS[status]}</span>
}

function sizeOf(node: TreeNode, side: Side): string {
    if (node.kind === 'dir') return ''

    const file = node.entry[side]
    return file ? formatSize(file.size) : '—'
}

/**
 * One tree row. Props are primitives so memo skips the rows whose status
 * did not change while thousands of files are being checked.
 */
const TreeRow = memo(function TreeRow({
    kind,
    name,
    path,
    depth,
    status,
    leftSize,
    rightSize,
    canOpen,
    open,
    selected,
    onToggle,
    onOpenFile,
}: {
    kind: TreeNode['kind']
    name: string
    path: string
    depth: number
    status: EntryStatus
    leftSize: string
    rightSize: string
    canOpen: boolean
    open: boolean
    selected: boolean
    onToggle: (path: string, open: boolean) => void
    onOpenFile: (path: string) => void
}) {
    const indent = { paddingInlineStart: `${10 + depth * 18}px` }

    const label =
        kind === 'dir' ? (
            <>
                {open ? <ChevronDown size={14} aria-hidden="true" /> : <ChevronRight size={14} aria-hidden="true" />}
                {open ? <FolderOpen size={15} aria-hidden="true" /> : <Folder size={15} aria-hidden="true" />}
                <span className="tools-tree-name">{name}</span>
            </>
        ) : (
            <>
                <span className="tools-tree-spacer" aria-hidden="true" />
                <FileIcon size={15} aria-hidden="true" />
                <span className="tools-tree-name">{name}</span>
            </>
        )

    return (
        <li className={`tools-tree-row is-${status}${selected ? ' is-selected' : ''}`}>
            {kind === 'dir' ? (
                <button
                    type="button"
                    className="tools-tree-cell tools-tree-label"
                    style={indent}
                    aria-expanded={open}
                    onClick={() => onToggle(path, !open)}
                >
                    {label}
                </button>
            ) : canOpen ? (
                <button
                    type="button"
                    className="tools-tree-cell tools-tree-label"
                    style={indent}
                    title={`Show the differences in ${path}`}
                    onClick={() => onOpenFile(path)}
                >
                    {label}
                </button>
            ) : (
                <span className="tools-tree-cell tools-tree-label" style={indent} title={path}>
                    {label}
                </span>
            )}
            <span className="tools-tree-cell">
                <StatusBadge status={status} />
            </span>
            <span className="tools-tree-cell tools-tree-size">{leftSize}</span>
            <span className="tools-tree-cell tools-tree-size">{rightSize}</span>
        </li>
    )
})

/** Folder compare: two folders, merged by relative path, checked file by file. */
export default function FolderCompare() {
    const [folders, setFolders] = useState<Record<Side, PickedFolder | null>>({ left: null, right: null })
    const [scanning, setScanning] = useState<Record<Side, number | null>>({ left: null, right: null })
    const [errors, setErrors] = useState<Record<Side, string | null>>({ left: null, right: null })
    const [entries, setEntries] = useState<CompareEntry[]>([])
    const [statuses, setStatuses] = useState<Map<string, EntryStatus>>(new Map())
    const [progress, setProgress] = useState<{ done: number; total: number } | null>(null)
    const [filter, setFilter] = useState<Filter>('all')
    const [toggled, setToggled] = useState<Map<string, boolean>>(new Map())
    const [rowLimit, setRowLimit] = useState(ROW_PAGE)
    const [selected, setSelected] = useState<SelectedFile | null>(null)
    const [language, setLanguage] = useState<LanguageId>('plaintext')

    const foldersRef = useRef(folders)
    const runRef = useRef(0)
    const selectedRef = useRef<string | null>(null)
    const diffRef = useRef<HTMLDivElement>(null)
    const inputs = useRef<Record<Side, HTMLInputElement | null>>({ left: null, right: null })

    // Stop background checks when the tool closes.
    useEffect(() => {
        const runs = runRef
        return () => {
            runs.current += 1
        }
    }, [])

    useEffect(() => {
        if (selected?.path) diffRef.current?.scrollIntoView({ block: 'nearest', behavior: 'smooth' })
    }, [selected?.path])

    const entriesByPath = useMemo(() => new Map(entries.map((entry) => [entry.path, entry])), [entries])
    const tree = useMemo(() => buildTree(entries, statuses), [entries, statuses])
    const counts = useMemo(() => countStatuses(statuses.values()), [statuses])
    const rows = useMemo(() => visibleRows(tree, filter === 'differences', toggled), [tree, filter, toggled])

    const compare = async (left: PickedFolder, right: PickedFolder) => {
        const run = ++runRef.current
        const merged = mergeFolders(left.files, right.files)
        const current = new Map(merged.map((entry) => [entry.path, initialStatus(entry)]))
        const pending = merged.filter((entry) => current.get(entry.path) === 'pending')

        setEntries(merged)
        setStatuses(new Map(current))
        setToggled(new Map())
        setRowLimit(ROW_PAGE)
        setSelected(null)
        selectedRef.current = null
        setProgress(pending.length > 0 ? { done: 0, total: pending.length } : null)

        if (pending.length === 0) return

        await checkContents(
            pending,
            current,
            () => run === runRef.current,
            (done) => {
                setStatuses(new Map(current))
                setProgress({ done, total: pending.length })
            },
        )

        if (run !== runRef.current) return

        setStatuses(new Map(current))
        setProgress(null)
    }

    const setFolder = (side: Side, folder: PickedFolder | null) => {
        const next = { ...foldersRef.current, [side]: folder }

        foldersRef.current = next
        setFolders(next)
        setErrors((current) => ({ ...current, [side]: null }))

        if (next.left && next.right) {
            void compare(next.left, next.right)
        } else {
            runRef.current += 1
            setEntries([])
            setStatuses(new Map())
            setProgress(null)
            setSelected(null)
            selectedRef.current = null
        }
    }

    const fail = (side: Side, message: string) => setErrors((current) => ({ ...current, [side]: message }))

    const dropFolder = (side: Side, event: DragEvent<HTMLDivElement>) => {
        const directory = droppedDirectory(event.dataTransfer)

        if (directory === undefined) {
            fail(side, 'This browser cannot read dropped folders. Use Choose folder instead.')
            return
        }
        if (directory === null) {
            fail(side, 'Drop a folder here. To compare two files, use File compare.')
            return
        }

        setScanning((current) => ({ ...current, [side]: 0 }))
        folderFromEntry(directory, (count) => setScanning((current) => ({ ...current, [side]: count })))
            .then((folder) => setFolder(side, folder))
            .catch(() => fail(side, `${directory.name} could not be read.`))
            .finally(() => setScanning((current) => ({ ...current, [side]: null })))
    }

    const pickFolder = (side: Side, list: FileList | null) => {
        const folder = list ? folderFromInput(list) : null

        if (folder) setFolder(side, folder)
        else if (list) fail(side, 'That folder has no files to compare.')
    }

    const openFile = useCallback(
        (path: string) => {
            const entry = entriesByPath.get(path)
            if (!entry?.left || !entry.right) return

            selectedRef.current = path
            setLanguage(languageFromName(path))
            setSelected({ path, loading: true, error: null, left: '', right: '' })

            Promise.all([readTextFile(entry.left, MAX_TEXT_BYTES), readTextFile(entry.right, MAX_TEXT_BYTES)])
                .then(([leftText, rightText]) => {
                    if (selectedRef.current !== path) return
                    setSelected({ path, loading: false, error: null, left: leftText, right: rightText })
                })
                .catch((error: unknown) => {
                    if (selectedRef.current !== path) return
                    setSelected({
                        path,
                        loading: false,
                        error:
                            error instanceof TextFileError
                                ? `${error.message} The files differ in content.`
                                : `${path} could not be read.`,
                        left: '',
                        right: '',
                    })
                })
        },
        [entriesByPath],
    )

    const closeFile = () => {
        selectedRef.current = null
        setSelected(null)
    }

    const toggle = useCallback(
        (path: string, open: boolean) => setToggled((current) => new Map(current).set(path, open)),
        [],
    )

    const differences = counts.different + counts['left-only'] + counts['right-only']
    const ready = Boolean(folders.left && folders.right)
    const shown = rows.slice(0, rowLimit)

    return (
        <div className="tools-folder-compare">
            <div className="tools-drop-pair">
                {(['left', 'right'] as const).map((side) => {
                    const folder = folders[side]
                    const scanned = scanning[side]

                    return (
                        <div key={side} className="tools-drop-slot">
                            <DropZone
                                label={SIDE_LABELS[side]}
                                icon={<Folder size={22} />}
                                prompt="Drop a folder here"
                                pickLabel="Choose folder…"
                                picked={
                                    folder
                                        ? {
                                              name: folder.name,
                                              detail: `${folder.files.length.toLocaleString()} file${
                                                  folder.files.length === 1 ? '' : 's'
                                              }`,
                                          }
                                        : null
                                }
                                busy={
                                    scanned !== null ? (
                                        <>
                                            <LoaderCircle size={16} className="entropy-spin" />
                                            <span>Reading folder… {scanned.toLocaleString()} files</span>
                                        </>
                                    ) : null
                                }
                                error={errors[side]}
                                onPick={() => inputs.current[side]?.click()}
                                onDrop={(event) => dropFolder(side, event)}
                                onClear={() => {
                                    setFolder(side, null)
                                    const input = inputs.current[side]
                                    if (input) input.value = ''
                                }}
                            />
                            <input
                                ref={(element) => {
                                    inputs.current[side] = element
                                    // Not in React's typings; selects a whole folder.
                                    element?.setAttribute('webkitdirectory', '')
                                }}
                                type="file"
                                multiple
                                hidden
                                onChange={(event) => pickFolder(side, event.target.files)}
                            />
                        </div>
                    )
                })}
            </div>

            {!ready ? (
                <div className="tools-empty">
                    <Folder size={22} aria-hidden="true" />
                    <strong>Choose two folders to compare</strong>
                    <p>
                        Files are matched by their path inside each folder, compared by size and then by SHA-256
                        checksum. Nothing is uploaded.
                    </p>
                </div>
            ) : entries.length === 0 ? (
                <div className="tools-empty">
                    <Folder size={22} aria-hidden="true" />
                    <strong>Both folders are empty</strong>
                    <p>There are no files to compare.</p>
                </div>
            ) : (
                <>
                    <div className="tools-folder-summary">
                        <div className="tools-folder-counts" aria-live="polite">
                            <span className="tools-count-chip">
                                <strong>{entries.length.toLocaleString()}</strong> files
                            </span>
                            <span className="tools-count-chip is-identical">
                                <strong>{counts.identical.toLocaleString()}</strong> identical
                            </span>
                            <span className="tools-count-chip is-different">
                                <strong>{counts.different.toLocaleString()}</strong> different
                            </span>
                            <span className="tools-count-chip is-left-only">
                                <strong>{counts['left-only'].toLocaleString()}</strong> only in original
                            </span>
                            <span className="tools-count-chip is-right-only">
                                <strong>{counts['right-only'].toLocaleString()}</strong> only in changed
                            </span>
                        </div>

                        <div className="tools-segmented" role="group" aria-label="Show">
                            <button
                                type="button"
                                aria-pressed={filter === 'all'}
                                onClick={() => {
                                    setFilter('all')
                                    setRowLimit(ROW_PAGE)
                                }}
                            >
                                All files
                            </button>
                            <button
                                type="button"
                                aria-pressed={filter === 'differences'}
                                onClick={() => {
                                    setFilter('differences')
                                    setRowLimit(ROW_PAGE)
                                }}
                            >
                                Differences only
                            </button>
                        </div>
                    </div>

                    {progress && (
                        <div className="tools-progress" role="status">
                            <div className="tools-progress-label">
                                <LoaderCircle size={14} className="entropy-spin" aria-hidden="true" />
                                Checking contents… {progress.done.toLocaleString()} of{' '}
                                {progress.total.toLocaleString()} same-size files
                            </div>
                            <div
                                className="tools-progress-track"
                                role="progressbar"
                                aria-valuemin={0}
                                aria-valuemax={progress.total}
                                aria-valuenow={progress.done}
                                aria-label="Content check progress"
                            >
                                <span style={{ width: `${(progress.done / progress.total) * 100}%` }} />
                            </div>
                        </div>
                    )}

                    {!progress && differences === 0 && filter === 'all' && (
                        <div className="entropy-alert entropy-alert-success" role="status">
                            <CircleCheck size={16} />
                            <span>
                                The folders are identical: {entries.length.toLocaleString()} file
                                {entries.length === 1 ? '' : 's'} with the same content.
                            </span>
                        </div>
                    )}

                    {selected && (
                        <div className="tools-folder-diff" ref={diffRef}>
                            <div className="tools-folder-diff-heading">
                                <strong title={selected.path}>{selected.path}</strong>
                                <button
                                    type="button"
                                    className="entropy-button entropy-button-ghost entropy-button-icon entropy-button-sm"
                                    aria-label="Close file differences"
                                    title="Close"
                                    onClick={closeFile}
                                >
                                    <X size={14} />
                                </button>
                            </div>
                            {selected.loading ? (
                                <div className="tools-empty" role="status">
                                    <LoaderCircle size={20} className="entropy-spin" aria-hidden="true" />
                                    <strong>Reading files…</strong>
                                </div>
                            ) : selected.error ? (
                                <div className="entropy-alert entropy-alert-warning" role="alert">
                                    <AlertCircle size={16} />
                                    <span>{selected.error}</span>
                                </div>
                            ) : (
                                <DiffPanel
                                    original={selected.left}
                                    modified={selected.right}
                                    originalLabel={`${folders.left?.name ?? 'Original'}/${selected.path}`}
                                    modifiedLabel={`${folders.right?.name ?? 'Changed'}/${selected.path}`}
                                    language={language}
                                    onLanguageChange={setLanguage}
                                />
                            )}
                        </div>
                    )}

                    <div className="tools-tree-wrap">
                        <div className="tools-tree-head" aria-hidden="true">
                            <span>Name</span>
                            <span>Status</span>
                            <span>{folders.left?.name ?? 'Original'}</span>
                            <span>{folders.right?.name ?? 'Changed'}</span>
                        </div>
                        {rows.length === 0 ? (
                            <div className="tools-empty">
                                <CircleCheck size={22} aria-hidden="true" />
                                <strong>No differences</strong>
                                <p>Every file has the same content in both folders.</p>
                            </div>
                        ) : (
                            <ul className="tools-tree" aria-label="Compared files">
                                {shown.map(({ node, open }) => (
                                    <TreeRow
                                        key={node.path}
                                        kind={node.kind}
                                        name={node.name}
                                        path={node.path}
                                        depth={node.depth}
                                        status={node.status}
                                        leftSize={sizeOf(node, 'left')}
                                        rightSize={sizeOf(node, 'right')}
                                        canOpen={
                                            node.kind === 'file' &&
                                            node.status === 'different' &&
                                            Boolean(node.entry.left && node.entry.right)
                                        }
                                        open={open}
                                        selected={selected?.path === node.path}
                                        onToggle={toggle}
                                        onOpenFile={openFile}
                                    />
                                ))}
                            </ul>
                        )}
                        {rows.length > shown.length && (
                            <div className="tools-tree-more">
                                <span>
                                    Showing {shown.length.toLocaleString()} of {rows.length.toLocaleString()} rows
                                </span>
                                <button
                                    type="button"
                                    className="entropy-button entropy-button-secondary entropy-button-sm"
                                    onClick={() => setRowLimit((limit) => limit + ROW_PAGE)}
                                >
                                    Show more
                                </button>
                            </div>
                        )}
                    </div>
                </>
            )}
        </div>
    )
}
