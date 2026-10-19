import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import Editor, { type OnMount } from '@monaco-editor/react'
import {
    AlertCircle,
    AlertTriangle,
    ArrowLeft,
    Braces,
    CheckCircle2,
    ChevronDown,
    Columns2,
    Eye,
    FileCode2,
    FilePlus2,
    FileText,
    Folder,
    Info,
    LoaderCircle,
    Rows2,
    RotateCcw,
    Save,
    X,
} from 'lucide-react'

import '../../../styles/plugin-editor.css'
import {
    diagnosticsFrom,
    pluginsApi,
    type PluginDiagnostic,
    type PluginItem,
    type PluginSdkCatalog,
} from '../../../api/plugins.api'
import { ApiError } from '../../../services/api'
import { useFeedback } from '../../../components/feedback/FeedbackProvider'
import DiffView from './DiffView'
import { monaco } from './monaco'
import { registerSdkLanguage, toMarkers } from './sdkLanguage'

type FileMap = Record<string, string>
type EditorMode = 'edit' | 'review'

const EDITABLE_SUFFIXES = ['.py', '.json', '.md', '.txt']
const PATH_SEGMENT = /^[A-Za-z0-9_][A-Za-z0-9_.-]*$/
const VALIDATION_DELAY = 600

function languageOf(path: string): string {
    if (path.endsWith('.py')) return 'python'
    if (path.endsWith('.json')) return 'json'
    if (path.endsWith('.md')) return 'markdown'
    return 'plaintext'
}

function FileIcon({ path }: { path: string }) {
    if (path.endsWith('.py')) return <FileCode2 size={15} className="plugin-ide-icon-py" />
    if (path.endsWith('.json')) return <Braces size={15} className="plugin-ide-icon-json" />
    return <FileText size={15} className="plugin-ide-icon-md" />
}

function disposeModels(prefixes: string[]) {
    for (const model of monaco.editor.getModels()) {
        const uri = model.uri.toString()

        if (prefixes.some((prefix) => uri.startsWith(prefix))) model.dispose()
    }
}

function validateNewPath(path: string, files: FileMap): string | null {
    const segments = path.split('/')

    if (!segments.every((segment) => PATH_SEGMENT.test(segment))) {
        return 'Use letters, digits, "_", "-" or "." and "/" between folders.'
    }

    if (segments.includes('__pycache__')) return '__pycache__ is not editable.'

    if (!EDITABLE_SUFFIXES.some((suffix) => path.endsWith(suffix))) {
        return `File must end in ${EDITABLE_SUFFIXES.join(', ')}.`
    }

    if (path in files) return 'A file with this path already exists.'

    return null
}

/** Approximate added/removed line counts for the review list. */
function lineStats(original: string | undefined, modified: string) {
    const before = original === undefined ? [] : original.split('\n')
    const after = modified.split('\n')
    const remaining = new Map<string, number>()

    for (const line of before) remaining.set(line, (remaining.get(line) ?? 0) + 1)

    let added = 0

    for (const line of after) {
        const count = remaining.get(line) ?? 0

        if (count > 0) remaining.set(line, count - 1)
        else added += 1
    }

    let removed = 0

    for (const count of remaining.values()) removed += count

    return { added, removed }
}

interface TreeRow {
    kind: 'folder' | 'file'
    path: string
    label: string
    depth: number
}

function buildTree(paths: string[]): TreeRow[] {
    const rows: TreeRow[] = []
    const folders = new Set<string>()

    const sorted = [...paths].sort((left, right) => {
        const leftParts = left.split('/')
        const rightParts = right.split('/')

        // Folders before files at each level, then alphabetical.
        for (let index = 0; index < Math.min(leftParts.length, rightParts.length); index += 1) {
            const leftIsFolder = index < leftParts.length - 1
            const rightIsFolder = index < rightParts.length - 1

            if (leftParts[index] !== rightParts[index] || leftIsFolder !== rightIsFolder) {
                if (leftIsFolder !== rightIsFolder) return leftIsFolder ? -1 : 1
                return leftParts[index].localeCompare(rightParts[index])
            }
        }

        return leftParts.length - rightParts.length
    })

    for (const path of sorted) {
        const parts = path.split('/')

        for (let depth = 0; depth < parts.length - 1; depth += 1) {
            const folder = parts.slice(0, depth + 1).join('/')

            if (!folders.has(folder)) {
                folders.add(folder)
                rows.push({ kind: 'folder', path: folder, label: parts[depth], depth })
            }
        }

        rows.push({
            kind: 'file',
            path,
            label: parts[parts.length - 1],
            depth: parts.length - 1,
        })
    }

    return rows
}

function SeverityIcon({ severity }: { severity: PluginDiagnostic['severity'] }) {
    if (severity === 'error') return <AlertCircle size={14} className="plugin-ide-error" />
    if (severity === 'warning') return <AlertTriangle size={14} className="plugin-ide-warning" />
    return <Info size={14} className="plugin-ide-info" />
}

function SaveMenu({
    disabled,
    saving,
    onPreview,
    onSave,
}: {
    disabled: boolean
    saving: boolean
    onPreview: () => void
    onSave: () => void
}) {
    const [open, setOpen] = useState(false)
    const closeTimer = useRef<number | undefined>(undefined)
    const containerRef = useRef<HTMLDivElement>(null)

    const show = () => {
        window.clearTimeout(closeTimer.current)
        if (!disabled) setOpen(true)
    }

    const hide = () => {
        closeTimer.current = window.setTimeout(() => setOpen(false), 150)
    }

    useEffect(() => {
        if (!open) return

        function handlePointerDown(event: PointerEvent) {
            if (!containerRef.current?.contains(event.target as Node)) setOpen(false)
        }

        function handleKeyDown(event: KeyboardEvent) {
            if (event.key === 'Escape') setOpen(false)
        }

        document.addEventListener('pointerdown', handlePointerDown)
        document.addEventListener('keydown', handleKeyDown)

        return () => {
            document.removeEventListener('pointerdown', handlePointerDown)
            document.removeEventListener('keydown', handleKeyDown)
        }
    }, [open])

    useEffect(() => () => window.clearTimeout(closeTimer.current), [])

    return (
        <div
            className="plugin-ide-save"
            ref={containerRef}
            onMouseEnter={show}
            onMouseLeave={hide}
        >
            <button
                type="button"
                className="entropy-button entropy-button-primary"
                disabled={disabled}
                aria-haspopup="menu"
                aria-expanded={open}
                onClick={() => setOpen((value) => !value)}
            >
                {saving ? (
                    <LoaderCircle size={16} className="entropy-spin" />
                ) : (
                    <Save size={16} />
                )}
                {saving ? 'Saving…' : 'Save'}
                <ChevronDown size={14} />
            </button>

            {open && (
                <div className="plugin-ide-save-menu" role="menu">
                    <button
                        type="button"
                        role="menuitem"
                        onClick={() => {
                            setOpen(false)
                            onPreview()
                        }}
                    >
                        <Eye size={16} />
                        <span>
                            <strong>Preview &amp; save</strong>
                            <small>Review a diff of every change first</small>
                        </span>
                    </button>
                    <button
                        type="button"
                        role="menuitem"
                        onClick={() => {
                            setOpen(false)
                            onSave()
                        }}
                    >
                        <Save size={16} />
                        <span>
                            <strong>Save without review</strong>
                            <small>Validate and save immediately</small>
                        </span>
                    </button>
                </div>
            )}
        </div>
    )
}

interface PluginEditorProps {
    plugin: PluginItem
    onClose: () => void
    onSaved: (plugin: PluginItem) => void
}

export default function PluginEditor({ plugin, onClose, onSaved }: PluginEditorProps) {
    const { notify, modal } = useFeedback()
    const qualifiedName = plugin.qualified_name
    const uriPrefix = `file:///${qualifiedName}/`

    const [loading, setLoading] = useState(true)
    const [loadError, setLoadError] = useState<string | null>(null)
    const [catalog, setCatalog] = useState<PluginSdkCatalog | null>(null)
    const [originals, setOriginals] = useState<FileMap>({})
    const [drafts, setDrafts] = useState<FileMap>({})
    const [revision, setRevision] = useState('')
    const [openTabs, setOpenTabs] = useState<string[]>([])
    const [activePath, setActivePath] = useState<string | null>(null)
    const [diagnostics, setDiagnostics] = useState<PluginDiagnostic[]>([])
    const [validating, setValidating] = useState(false)
    const [mode, setMode] = useState<EditorMode>('edit')
    const [reviewPath, setReviewPath] = useState<string | null>(null)
    const [sideBySide, setSideBySide] = useState(true)
    const [saving, setSaving] = useState(false)
    const [problemsOpen, setProblemsOpen] = useState(true)
    const [cursor, setCursor] = useState({ line: 1, column: 1 })
    const [newFileOpen, setNewFileOpen] = useState(false)
    const [newFilePath, setNewFilePath] = useState('')

    const editorRef = useRef<Parameters<OnMount>[0] | null>(null)
    const theme = useMemo(
        () =>
            document.querySelector('.entropy-app')?.classList.contains('theme-light')
                ? 'entropy-light'
                : 'entropy-dark',
        [],
    )

    // ------------------------------------------------------------------
    // Loading
    // ------------------------------------------------------------------

    useEffect(() => {
        let active = true

        Promise.all([pluginsApi.files(qualifiedName), pluginsApi.sdk()])
            .then(([result, sdk]) => {
                if (!active) return

                const files = Object.fromEntries(
                    result.files.map((file) => [file.path, file.content]),
                )
                const first =
                    'plugin.py' in files ? 'plugin.py' : Object.keys(files)[0] ?? null

                setOriginals(files)
                setDrafts(files)
                setRevision(result.revision)
                setCatalog(sdk)
                setOpenTabs(first ? [first] : [])
                setActivePath(first)
            })
            .catch((error: unknown) => {
                if (active) {
                    setLoadError(
                        error instanceof Error ? error.message : 'Unable to open plugin.',
                    )
                }
            })
            .finally(() => {
                if (active) setLoading(false)
            })

        return () => {
            active = false
        }
    }, [qualifiedName])

    useEffect(() => {
        if (!catalog) return

        const registration = registerSdkLanguage(monaco, catalog)
        return () => registration.dispose()
    }, [catalog])

    // Dispose this plugin's editor models when the editor closes.
    useEffect(() => () => disposeModels([uriPrefix]), [uriPrefix])

    // ------------------------------------------------------------------
    // Changes
    // ------------------------------------------------------------------

    const changes = useMemo(() => {
        const result: FileMap = {}

        for (const [path, content] of Object.entries(drafts)) {
            if (originals[path] !== content) result[path] = content
        }

        return result
    }, [drafts, originals])

    const changedPaths = useMemo(() => Object.keys(changes).sort(), [changes])
    const dirty = changedPaths.length > 0

    useEffect(() => {
        if (!dirty) return

        function handleBeforeUnload(event: BeforeUnloadEvent) {
            event.preventDefault()
        }

        window.addEventListener('beforeunload', handleBeforeUnload)
        return () => window.removeEventListener('beforeunload', handleBeforeUnload)
    }, [dirty])

    // ------------------------------------------------------------------
    // Validation
    // ------------------------------------------------------------------

    useEffect(() => {
        if (loading || loadError) return

        const controller = new AbortController()
        const timer = window.setTimeout(() => {
            setValidating(true)

            pluginsApi
                .validate(qualifiedName, changes, controller.signal)
                .then((result) => setDiagnostics(result.diagnostics))
                .catch(() => {
                    // Aborted or transient: keep the last known diagnostics.
                })
                .finally(() => {
                    if (!controller.signal.aborted) setValidating(false)
                })
        }, VALIDATION_DELAY)

        return () => {
            window.clearTimeout(timer)
            controller.abort()
        }
    }, [changes, loading, loadError, qualifiedName])

    // Mirror diagnostics onto every open model as editor markers.
    useEffect(() => {
        for (const model of monaco.editor.getModels()) {
            const uri = model.uri.toString()

            if (!uri.startsWith(uriPrefix)) continue

            const path = decodeURIComponent(uri.slice(uriPrefix.length))

            monaco.editor.setModelMarkers(
                model,
                'entropy',
                toMarkers(
                    monaco,
                    diagnostics.filter((item) => item.path === path),
                ),
            )
        }
    }, [diagnostics, activePath, uriPrefix])

    const problemCounts = useMemo(() => {
        const counts: Record<string, { errors: number; warnings: number }> = {}

        for (const item of diagnostics) {
            counts[item.path] ??= { errors: 0, warnings: 0 }
            if (item.severity === 'error') counts[item.path].errors += 1
            else counts[item.path].warnings += 1
        }

        return counts
    }, [diagnostics])

    const errorCount = diagnostics.filter((item) => item.severity === 'error').length

    // ------------------------------------------------------------------
    // Navigation
    // ------------------------------------------------------------------

    const openFile = useCallback((path: string) => {
        setOpenTabs((tabs) => (tabs.includes(path) ? tabs : [...tabs, path]))
        setActivePath(path)
    }, [])

    const closeTab = (path: string) => {
        setOpenTabs((tabs) => {
            const next = tabs.filter((tab) => tab !== path)

            if (activePath === path) {
                const index = tabs.indexOf(path)
                setActivePath(next[Math.min(index, next.length - 1)] ?? null)
            }

            return next
        })
    }

    const revealProblem = (item: PluginDiagnostic) => {
        if (!(item.path in drafts)) return

        openFile(item.path)

        window.setTimeout(() => {
            const editor = editorRef.current
            if (!editor) return

            editor.revealLineInCenter(item.line)
            editor.setPosition({ lineNumber: item.line, column: item.column })
            editor.focus()
        }, 0)
    }

    const createFile = () => {
        const path = newFilePath.trim().replace(/^\/+/, '')
        const problem = validateNewPath(path, drafts)

        if (problem) {
            notify.error(problem, { title: 'Cannot create file' })
            return
        }

        setDrafts((current) => ({ ...current, [path]: '' }))
        setNewFilePath('')
        setNewFileOpen(false)
        openFile(path)
    }

    const revertFile = (path: string) => {
        // Open models keep their own text; reset them along with the draft.
        const model = monaco.editor.getModel(monaco.Uri.parse(`${uriPrefix}${path}`))

        if (model && path in originals) model.setValue(originals[path])
        else model?.dispose()

        setDrafts((current) => {
            const next = { ...current }

            if (path in originals) next[path] = originals[path]
            else delete next[path]

            return next
        })

        if (!(path in originals)) {
            setOpenTabs((tabs) => tabs.filter((tab) => tab !== path))
            if (activePath === path) setActivePath(null)
        }
    }

    // ------------------------------------------------------------------
    // Save
    // ------------------------------------------------------------------

    const save = useCallback(async () => {
        if (!dirty || saving) return

        setSaving(true)

        try {
            const result = await pluginsApi.save(qualifiedName, changes, revision)

            notify.success(
                `${changedPaths.length} file${changedPaths.length === 1 ? '' : 's'} saved and ${result.plugin.qualified_name} reinstalled.`,
                { title: 'Plugin saved' },
            )
            onSaved(result.plugin)
        } catch (error) {
            const found =
                error instanceof ApiError ? diagnosticsFrom(error.detail) : null

            if (found) {
                setDiagnostics(found)
                setProblemsOpen(true)
                setMode('edit')
                notify.error('Fix the reported problems before saving.', {
                    title: 'Validation failed',
                })
            } else {
                notify.error(
                    error instanceof Error ? error.message : 'Unable to save plugin.',
                    { title: 'Save failed' },
                )
            }
        } finally {
            setSaving(false)
        }
    }, [changedPaths.length, changes, dirty, notify, onSaved, qualifiedName, revision, saving])

    const preview = useCallback(() => {
        if (!dirty) return

        setReviewPath((current) =>
            current && current in changes ? current : changedPaths[0] ?? null,
        )
        setMode('review')
    }, [changedPaths, changes, dirty])

    // Keep Ctrl/Cmd+S bound to the latest preview handler.
    const previewRef = useRef(preview)
    useEffect(() => {
        previewRef.current = preview
    }, [preview])

    const cancel = async () => {
        if (
            dirty &&
            !(await modal.confirm({
                title: 'Discard unsaved changes?',
                message: `${changedPaths.length} changed file${changedPaths.length === 1 ? '' : 's'} in ${qualifiedName} will be lost.`,
                confirmText: 'Discard',
                cancelText: 'Keep editing',
                destructive: true,
            }))
        ) {
            return
        }

        onClose()
    }

    const handleMount: OnMount = (editor, instance) => {
        editorRef.current = editor

        editor.addCommand(instance.KeyMod.CtrlCmd | instance.KeyCode.KeyS, () =>
            previewRef.current(),
        )

        editor.onDidChangeCursorPosition((event) =>
            setCursor({
                line: event.position.lineNumber,
                column: event.position.column,
            }),
        )
    }

    // ------------------------------------------------------------------
    // Render
    // ------------------------------------------------------------------

    const tree = useMemo(() => buildTree(Object.keys(drafts)), [drafts])
    const reviewErrors = diagnostics.filter(
        (item) => item.severity === 'error',
    )

    return (
        <div
            className="plugin-ide"
            role="dialog"
            aria-modal="true"
            aria-label={`Edit plugin ${qualifiedName}`}
        >
            <header className="plugin-ide-topbar">
                <button
                    type="button"
                    className="entropy-button entropy-button-secondary"
                    onClick={() => void cancel()}
                    disabled={saving}
                >
                    <X size={16} />
                    Cancel
                </button>

                <div className="plugin-ide-title">
                    <strong>{qualifiedName}</strong>
                    <span className="plugins-version">{plugin.version}</span>
                    {mode === 'review' && (
                        <span className="plugin-ide-chip">Reviewing changes</span>
                    )}
                    {dirty && (
                        <span className="plugin-ide-chip plugin-ide-chip-dirty">
                            {changedPaths.length} unsaved
                        </span>
                    )}
                </div>

                <SaveMenu
                    disabled={!dirty || saving || loading}
                    saving={saving}
                    onPreview={preview}
                    onSave={() => void save()}
                />
            </header>

            {loading ? (
                <div className="plugin-ide-state">
                    <LoaderCircle size={22} className="entropy-spin" />
                    <span>Opening {qualifiedName}…</span>
                </div>
            ) : loadError ? (
                <div className="plugin-ide-state" role="alert">
                    <AlertCircle size={22} />
                    <span>{loadError}</span>
                    <button type="button" className="entropy-button entropy-button-secondary" onClick={onClose}>
                        Close
                    </button>
                </div>
            ) : (
                <>
                    {/* Kept mounted while reviewing so models, cursor and undo survive. */}
                    <div className="plugin-ide-body" hidden={mode !== 'edit'}>
                        <aside className="plugin-ide-explorer" aria-label="Plugin files">
                            <div className="plugin-ide-explorer-heading">
                                <span>Explorer</span>
                                <button
                                    type="button"
                                    aria-label="New file"
                                    title="New file"
                                    onClick={() => setNewFileOpen((value) => !value)}
                                >
                                    <FilePlus2 size={15} />
                                </button>
                            </div>

                            {newFileOpen && (
                                <form
                                    className="plugin-ide-new-file"
                                    onSubmit={(event) => {
                                        event.preventDefault()
                                        createFile()
                                    }}
                                >
                                    <input
                                        autoFocus
                                        value={newFilePath}
                                        placeholder="engine.py"
                                        aria-label="New file path"
                                        onChange={(event) => setNewFilePath(event.target.value)}
                                        onKeyDown={(event) => {
                                            if (event.key === 'Escape') setNewFileOpen(false)
                                        }}
                                    />
                                </form>
                            )}

                            <ul className="plugin-ide-tree">
                                {tree.map((row) =>
                                    row.kind === 'folder' ? (
                                        <li
                                            key={`folder:${row.path}`}
                                            className="plugin-ide-tree-folder"
                                            style={{ paddingLeft: 12 + row.depth * 14 }}
                                        >
                                            <Folder size={15} />
                                            {row.label}
                                        </li>
                                    ) : (
                                        <li key={row.path}>
                                            <button
                                                type="button"
                                                className={`plugin-ide-tree-file${
                                                    row.path === activePath ? ' is-active' : ''
                                                }`}
                                                style={{ paddingLeft: 12 + row.depth * 14 }}
                                                onClick={() => openFile(row.path)}
                                                title={row.path}
                                            >
                                                <FileIcon path={row.path} />
                                                <span className="plugin-ide-tree-label">
                                                    {row.label}
                                                </span>
                                                {problemCounts[row.path]?.errors ? (
                                                    <span className="plugin-ide-badge plugin-ide-badge-error">
                                                        {problemCounts[row.path].errors}
                                                    </span>
                                                ) : null}
                                                {row.path in changes && (
                                                    <span
                                                        className="plugin-ide-dirty"
                                                        title={
                                                            row.path in originals
                                                                ? 'Modified'
                                                                : 'New file'
                                                        }
                                                    >
                                                        {row.path in originals ? 'M' : 'A'}
                                                    </span>
                                                )}
                                            </button>
                                        </li>
                                    ),
                                )}
                            </ul>
                        </aside>

                        <section className="plugin-ide-main">
                            <div className="plugin-ide-tabs" role="tablist">
                                {openTabs.map((path) => (
                                    <div
                                        key={path}
                                        className={`plugin-ide-tab${
                                            path === activePath ? ' is-active' : ''
                                        }`}
                                    >
                                        <button
                                            type="button"
                                            role="tab"
                                            aria-selected={path === activePath}
                                            onClick={() => setActivePath(path)}
                                            title={path}
                                        >
                                            <FileIcon path={path} />
                                            {path.split('/').pop()}
                                            {path in changes && (
                                                <span className="plugin-ide-tab-dot" />
                                            )}
                                        </button>
                                        <button
                                            type="button"
                                            className="plugin-ide-tab-close"
                                            aria-label={`Close ${path}`}
                                            onClick={() => closeTab(path)}
                                        >
                                            <X size={13} />
                                        </button>
                                    </div>
                                ))}
                            </div>

                            <div className="plugin-ide-editor">
                                {activePath ? (
                                    <Editor
                                        path={`${uriPrefix}${activePath}`}
                                        defaultLanguage={languageOf(activePath)}
                                        defaultValue={drafts[activePath] ?? ''}
                                        theme={theme}
                                        onMount={handleMount}
                                        onChange={(value) =>
                                            setDrafts((current) =>
                                                activePath in current
                                                    ? { ...current, [activePath]: value ?? '' }
                                                    : current,
                                            )
                                        }
                                        options={{
                                            automaticLayout: true,
                                            fontSize: 13,
                                            minimap: { enabled: true },
                                            scrollBeyondLastLine: false,
                                            tabSize: 4,
                                            renderWhitespace: 'selection',
                                            quickSuggestions: true,
                                            wordBasedSuggestions: 'currentDocument',
                                        }}
                                    />
                                ) : (
                                    <div className="plugin-ide-state">
                                        <span>Select a file from the explorer.</span>
                                    </div>
                                )}
                            </div>

                            <section
                                className={`plugin-ide-problems${problemsOpen ? '' : ' is-collapsed'}`}
                                aria-label="Problems"
                            >
                                <button
                                    type="button"
                                    className="plugin-ide-problems-heading"
                                    onClick={() => setProblemsOpen((value) => !value)}
                                    aria-expanded={problemsOpen}
                                >
                                    <ChevronDown size={14} />
                                    Problems
                                    <span className="plugin-ide-badge">{diagnostics.length}</span>
                                    {validating && (
                                        <LoaderCircle size={13} className="entropy-spin" />
                                    )}
                                </button>

                                {problemsOpen && (
                                    <ul>
                                        {diagnostics.length === 0 ? (
                                            <li className="plugin-ide-problems-empty">
                                                <CheckCircle2 size={14} />
                                                No problems detected by the Plugin SDK checks.
                                            </li>
                                        ) : (
                                            diagnostics.map((item, index) => (
                                                <li key={`${item.path}:${item.line}:${index}`}>
                                                    <button
                                                        type="button"
                                                        onClick={() => revealProblem(item)}
                                                    >
                                                        <SeverityIcon severity={item.severity} />
                                                        <span>{item.message}</span>
                                                        <small>
                                                            {item.path}:{item.line}:{item.column}
                                                        </small>
                                                    </button>
                                                </li>
                                            ))
                                        )}
                                    </ul>
                                )}
                            </section>
                        </section>
                    </div>

                    {mode === 'review' && (
                        <div className="plugin-ide-body plugin-ide-review">
                            <aside className="plugin-ide-explorer" aria-label="Changed files">
                                <div className="plugin-ide-explorer-heading">
                                    <span>Changes ({changedPaths.length})</span>
                                </div>

                                <ul className="plugin-ide-tree">
                                    {changedPaths.map((path) => {
                                        const stats = lineStats(originals[path], changes[path])

                                        return (
                                            <li key={path} className="plugin-ide-review-row">
                                                <button
                                                    type="button"
                                                    className={`plugin-ide-tree-file${
                                                        path === reviewPath ? ' is-active' : ''
                                                    }`}
                                                    onClick={() => setReviewPath(path)}
                                                    title={path}
                                                >
                                                    <FileIcon path={path} />
                                                    <span className="plugin-ide-tree-label">{path}</span>
                                                    <span className="plugin-ide-added">+{stats.added}</span>
                                                    <span className="plugin-ide-removed">−{stats.removed}</span>
                                                </button>
                                                <button
                                                    type="button"
                                                    className="plugin-ide-revert"
                                                    aria-label={`Revert ${path}`}
                                                    title="Revert this file"
                                                    onClick={() => {
                                                        revertFile(path)
                                                        if (changedPaths.length === 1) setMode('edit')
                                                        else if (path === reviewPath) {
                                                            setReviewPath(
                                                                changedPaths.find((item) => item !== path) ?? null,
                                                            )
                                                        }
                                                    }}
                                                >
                                                    <RotateCcw size={13} />
                                                </button>
                                            </li>
                                        )
                                    })}
                                </ul>
                            </aside>

                            <section className="plugin-ide-main">
                                <div className="plugin-ide-review-heading">
                                    <div>
                                        <strong>{reviewPath}</strong>
                                        <span>
                                            {reviewPath && !(reviewPath in originals)
                                                ? 'New file'
                                                : 'Installed → edited'}
                                        </span>
                                    </div>
                                    <button
                                        type="button"
                                        className="entropy-button entropy-button-secondary"
                                        onClick={() => setSideBySide((value) => !value)}
                                    >
                                        {sideBySide ? <Rows2 size={15} /> : <Columns2 size={15} />}
                                        {sideBySide ? 'Inline' : 'Side by side'}
                                    </button>
                                </div>

                                {reviewErrors.length > 0 && (
                                    <div className="plugin-ide-review-errors" role="alert">
                                        <AlertCircle size={16} />
                                        <span>
                                            {reviewErrors.length} problem
                                            {reviewErrors.length === 1 ? '' : 's'} must be fixed
                                            before saving. Go back to the editor to fix them.
                                        </span>
                                    </div>
                                )}

                                <div className="plugin-ide-editor">
                                    {reviewPath && (
                                        <DiffView
                                            key={reviewPath}
                                            original={originals[reviewPath] ?? ''}
                                            modified={changes[reviewPath] ?? ''}
                                            language={languageOf(reviewPath)}
                                            theme={theme}
                                            sideBySide={sideBySide}
                                        />
                                    )}
                                </div>

                                <footer className="plugin-ide-review-footer">
                                    <button
                                        type="button"
                                        className="entropy-button entropy-button-secondary"
                                        onClick={() => setMode('edit')}
                                        disabled={saving}
                                    >
                                        <ArrowLeft size={15} />
                                        Back to editor
                                    </button>
                                    <button
                                        type="button"
                                        className="entropy-button entropy-button-primary"
                                        onClick={() => void save()}
                                        disabled={saving || !dirty || reviewErrors.length > 0}
                                    >
                                        {saving ? (
                                            <LoaderCircle size={16} className="entropy-spin" />
                                        ) : (
                                            <Save size={16} />
                                        )}
                                        Confirm &amp; save {changedPaths.length} file
                                        {changedPaths.length === 1 ? '' : 's'}
                                    </button>
                                </footer>
                            </section>
                        </div>
                    )}
                </>
            )}

            <footer className="plugin-ide-statusbar">
                <span>
                    {catalog ? (
                        <>
                            <CheckCircle2 size={12} /> Plugin SDK
                        </>
                    ) : (
                        'Plugin SDK loading'
                    )}
                </span>
                <span className={errorCount ? 'plugin-ide-error' : undefined}>
                    {validating
                        ? 'Checking…'
                        : `${errorCount} error${errorCount === 1 ? '' : 's'}, ${
                              diagnostics.length - errorCount
                          } other`}
                </span>
                <span className="plugin-ide-statusbar-spacer" />
                {mode === 'edit' && activePath && (
                    <>
                        <span>
                            Ln {cursor.line}, Col {cursor.column}
                        </span>
                        <span>{languageOf(activePath)}</span>
                    </>
                )}
                <span>Ctrl/⌘+S to preview</span>
            </footer>
        </div>
    )
}
