import { useCallback, useEffect, useMemo, useRef, useState, type CSSProperties, type PointerEvent as ReactPointerEvent } from 'react'
import Editor, { type OnMount } from '@monaco-editor/react'
import {
    AlertCircle,
    AlertTriangle,
    ArrowLeft,
    Bug,
    CheckCircle2,
    ChevronDown,
    Columns2,
    Eye,
    FilePlus2,
    Files,
    FileSignature,
    FolderPlus,
    History,
    Info,
    Keyboard,
    ListOrdered,
    LoaderCircle,
    PanelLeftClose,
    Pilcrow,
    Play,
    Replace,
    Rows2,
    RotateCcw,
    Save,
    Search,
    WrapText,
    X,
} from 'lucide-react'

import '../../../styles/plugin-editor.css'
import {
    diagnosticsFrom,
    pluginsApi,
    type PluginDiagnostic,
    type PluginFile,
    type PluginItem,
    type PluginSdkCatalog,
} from '../../../api/plugins.api'
import type { Run } from '../../../api/runs.api'
import { ApiError } from '../../../services/api'
import { useFeedback } from '../../../components/feedback/FeedbackProvider'
import Dialog from '../../../components/layout/Dialog'
import { keyMatches } from '../../../components/layout/useShortcuts'
import WallpaperLayer from '../../preferences/WallpaperLayer'
import HistoryDialog from '../../history/HistoryDialog'
import StartRunDialog from '../../runs/StartRunDialog'
import DiffView from './DiffView'
import FileTree, { FileIcon } from './FileTree'
import { buildTree, type TreeRow } from './tree'
import { monaco } from './monaco'
import SearchPanel from './SearchPanel'
import type { SearchMatch } from './search'
import { registerSdkLanguage, toMarkers } from './sdkLanguage'
import VisualBuilder from './visual/VisualBuilder'
import { forSave, withIds, type BuilderModel } from './visual/model'

type FileMap = Record<string, string>
type EditorMode = 'edit' | 'review'
type SidebarView = 'explorer' | 'search'
type FileMeta = Record<string, { size?: number; modified?: string }>

const EDITABLE_SUFFIXES = ['.py', '.json', '.md', '.txt']
const PATH_SEGMENT = /^[A-Za-z0-9_][A-Za-z0-9_.-]*$/
const VALIDATION_DELAY = 600
const PREFS_KEY = 'entropy.pluginEditor'
const SIDEBAR = { min: 180, max: 640, initial: 260 }
// Line-end markers are skipped past this size to keep typing smooth.
const EOL_MARK_LIMIT = 20000

interface Prefs {
    wrap: boolean
    showAll: boolean
    sidebarWidth: number
}

function loadPrefs(): Prefs {
    const fallback = { wrap: false, showAll: false, sidebarWidth: SIDEBAR.initial }
    try {
        return { ...fallback, ...(JSON.parse(localStorage.getItem(PREFS_KEY) ?? '{}') as Partial<Prefs>) }
    } catch {
        return fallback
    }
}

function savePrefs(prefs: Prefs) {
    try {
        localStorage.setItem(PREFS_KEY, JSON.stringify(prefs))
    } catch {
        // Preferences are a convenience only.
    }
}

const SHORTCUTS: Array<[string, string]> = [
    ['Ctrl/⌘ + S', 'Save (review the changes first)'],
    ['Ctrl/⌘ + F', 'Find in this file'],
    ['Ctrl/⌘ + H', 'Replace in this file (⌘ + ⌥ + F on macOS)'],
    ['Ctrl/⌘ + Shift + F', 'Search in all files'],
    ['Ctrl/⌘ + Shift + H', 'Replace in all files'],
    ['Ctrl/⌘ + G', 'Go to line'],
    ['Ctrl/⌘ + Shift + E', 'Show the explorer'],
    ['Ctrl/⌘ + B', 'Show or hide the sidebar'],
    ['Ctrl/⌘ + Alt + N', 'New file (Ctrl + N belongs to the browser)'],
    ['Alt + Z', 'Wrap long lines'],
    ['Alt + Shift + W', 'Show all characters (spaces, tabs, CR/LF)'],
    ['F5', 'Debug run'],
    ['Ctrl/⌘ + F5', 'Run'],
    ['Ctrl/⌘ + /', 'Comment or uncomment lines'],
    ['Alt + ↑ / ↓', 'Move lines up or down'],
    ['F1', 'All editor commands'],
    ['Double-click the tab bar', 'New file'],
]

function languageOf(path: string): string {
    if (path.endsWith('.py')) return 'python'
    if (path.endsWith('.json')) return 'json'
    if (path.endsWith('.md')) return 'markdown'
    return 'plaintext'
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

/** How the text ends its lines: counts of CRLF, LF and lone CR. */
function lineEndings(text: string) {
    let crlf = 0
    let lf = 0
    let cr = 0
    for (let index = 0; index < text.length; index += 1) {
        const char = text.charCodeAt(index)
        if (char === 13) {
            if (text.charCodeAt(index + 1) === 10) {
                crlf += 1
                index += 1
            } else cr += 1
        } else if (char === 10) lf += 1
    }
    return { crlf, lf, cr, mixed: [crlf, lf, cr].filter(Boolean).length > 1 }
}

function formatBytes(size: number): string {
    if (size < 1024) return `${size} B`
    if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`
    return `${(size / 1024 / 1024).toFixed(1)} MB`
}

const parentOf = (path: string) => (path.includes('/') ? path.slice(0, path.lastIndexOf('/')) : '')
const join = (folder: string, name: string) => (folder ? `${folder}/${name}` : name)

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

interface KeyActions {
    save: () => void
    search: (replace: boolean) => void
    explorer: () => void
    sidebar: () => void
    wrap: () => void
    showAll: () => void
    newFile: () => void
    run: (debug: boolean) => void
}

interface PluginEditorProps {
    plugin: PluginItem
    onClose: () => void
    /** The plugin was saved; the editor stays open unless the author closes it. */
    onSaved: (plugin: PluginItem) => void
    /** View the source without changing it (read access only). */
    readOnly?: boolean
    /** Why earlier versions may not be restored, or null when they may. */
    restoreReason?: string | null
    /** An earlier version was restored; the editor should reopen. */
    onRestored?: (version: string) => void
    /** Why the plugin may not be run, or null when it may. */
    runReason?: string | null
    /** A new draft made for the visual builder: start it there. */
    startVisual?: boolean
}

export default function PluginEditor({
    plugin,
    onClose,
    onSaved,
    readOnly = false,
    restoreReason = null,
    onRestored,
    runReason = null,
    startVisual = false,
}: PluginEditorProps) {
    const { notify, modal } = useFeedback()
    const qualifiedName = plugin.qualified_name
    const uriPrefix = `file:///${qualifiedName}/`

    const [current, setCurrent] = useState<PluginItem>(plugin)
    const [loading, setLoading] = useState(true)
    const [loadError, setLoadError] = useState<string | null>(null)
    const [catalog, setCatalog] = useState<PluginSdkCatalog | null>(null)
    const [originals, setOriginals] = useState<FileMap>({})
    const [drafts, setDrafts] = useState<FileMap>({})
    const [meta, setMeta] = useState<FileMeta>({})
    const [folders, setFolders] = useState<string[]>([])
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
    const [historyOpen, setHistoryOpen] = useState(false)
    const [renaming, setRenaming] = useState<string | null>(null)
    const [sidebar, setSidebar] = useState<SidebarView>('explorer')
    const [sidebarOpen, setSidebarOpen] = useState(true)
    const [replaceFocus, setReplaceFocus] = useState(0)
    const [prefs, setPrefs] = useState<Prefs>(loadPrefs)
    const [eol, setEol] = useState<'LF' | 'CRLF'>('LF')
    const [runDialog, setRunDialog] = useState<{ debug: boolean } | null>(null)
    const [lastRun, setLastRun] = useState<Run | null>(null)
    const [shortcutsOpen, setShortcutsOpen] = useState(false)
    const [infoFor, setInfoFor] = useState<TreeRow | null>(null)
    const [contractBusy, setContractBusy] = useState(false)
    // Plugins with builder.json are made in the visual builder.
    const [builderModel, setBuilderModel] = useState<BuilderModel | null>(null)
    const [view, setView] = useState<'visual' | 'source'>('source')
    const [builderProblems, setBuilderProblems] = useState<string[]>([])
    const [generating, setGenerating] = useState(false)
    const regenerate = useRef(false)

    const rootRef = useRef<HTMLDivElement>(null)
    const editorRef = useRef<Parameters<OnMount>[0] | null>(null)
    const decorationsRef = useRef<ReturnType<Parameters<OnMount>[0]['createDecorationsCollection']> | null>(null)
    const draftsRef = useRef(drafts)
    const showAllRef = useRef(prefs.showAll)
    const theme = useMemo(
        () =>
            document.querySelector('.entropy-app')?.classList.contains('theme-light')
                ? 'entropy-light'
                : 'entropy-dark',
        [],
    )

    useEffect(() => {
        draftsRef.current = drafts
    }, [drafts])

    useEffect(() => savePrefs(prefs), [prefs])

    // ------------------------------------------------------------------
    // Loading
    // ------------------------------------------------------------------

    const metaOf = (files: PluginFile[]): FileMeta =>
        Object.fromEntries(files.map((file) => [file.path, { size: file.size, modified: file.modified }]))

    useEffect(() => {
        let active = true

        // SDK help is optional: the editor still opens without it.
        Promise.all([
            pluginsApi.files(qualifiedName),
            pluginsApi.sdk().catch(() => null),
        ])
            .then(([result, sdk]) => {
                if (!active) return

                const files = Object.fromEntries(
                    result.files.map((file) => [file.path, file.content]),
                )
                const first =
                    'plugin.py' in files ? 'plugin.py' : Object.keys(files)[0] ?? null

                setOriginals(files)
                setDrafts(files)
                setMeta(metaOf(result.files))
                setRevision(result.revision)
                setCatalog(sdk)
                setOpenTabs(first ? [first] : [])
                setActivePath(first)

                if ('builder.json' in files) {
                    try {
                        setBuilderModel(withIds(JSON.parse(files['builder.json']) as BuilderModel))
                        setView('visual')
                    } catch {
                        // An unreadable builder.json: the source stays editable.
                    }
                } else if (startVisual && result.plugin.draft) {
                    pluginsApi
                        .builder(qualifiedName, null)
                        .then((built) => {
                            if (!active) return
                            setDrafts((existing) => ({ ...existing, ...built.files }))
                            setBuilderModel(withIds(built.model as BuilderModel))
                            setView('visual')
                        })
                        .catch(() => undefined)
                }
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
    }, [qualifiedName, startVisual])

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

    // Deleted files, and the old paths of moved ones.
    const removed = useMemo(
        () => Object.keys(originals).filter((path) => !(path in drafts)).sort(),
        [drafts, originals],
    )
    const changedPaths = useMemo(() => Object.keys(changes).sort(), [changes])
    const pending = changedPaths.length + removed.length
    const dirty = pending > 0

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
                .validate(qualifiedName, changes, controller.signal, removed)
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
    }, [changes, removed, loading, loadError, qualifiedName])

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
    // Models
    // ------------------------------------------------------------------

    const modelOf = useCallback(
        (path: string) => monaco.editor.getModel(monaco.Uri.parse(`${uriPrefix}${path}`)),
        [uriPrefix],
    )

    /** Set a file's text, in its open model too (undoable there). */
    const setContent = useCallback(
        (path: string, text: string) => {
            setDrafts((existing) => ({ ...existing, [path]: text }))
            const model = modelOf(path)
            if (model && model.getValue() !== text) {
                model.pushEditOperations([], [{ range: model.getFullModelRange(), text }], () => null)
            }
        },
        [modelOf],
    )

    // The builder writes plugin.py, plugin.json and builder.json from its model.
    useEffect(() => {
        if (!builderModel || !regenerate.current) return
        regenerate.current = false
        const timer = window.setTimeout(() => {
            setGenerating(true)
            pluginsApi
                .builder(qualifiedName, forSave(builderModel), draftsRef.current['plugin.json'])
                .then((built) => {
                    for (const [path, text] of Object.entries(built.files)) {
                        if (draftsRef.current[path] !== text) setContent(path, text)
                    }
                    setBuilderProblems([])
                })
                .catch((error: unknown) => {
                    const detail = error instanceof ApiError ? (error.detail as { problems?: string[] } | null) : null
                    setBuilderProblems(
                        detail?.problems ?? [error instanceof Error ? error.message : 'The plugin could not be written.'],
                    )
                })
                .finally(() => setGenerating(false))
        }, 450)
        return () => window.clearTimeout(timer)
    }, [builderModel, qualifiedName, setContent])

    const changeModel = (model: BuilderModel) => {
        regenerate.current = true
        setBuilderModel(model)
    }

    /** Line-end markers (and the line-ending label) for the file on screen. */
    const paintLineEnds = useCallback(() => {
        const editor = editorRef.current
        const model = editor?.getModel()
        if (!editor || !model) return

        setEol(model.getEOL() === '\r\n' ? 'CRLF' : 'LF')
        decorationsRef.current?.clear()
        if (!showAllRef.current || model.getLineCount() > EOL_MARK_LIMIT) return

        // The real ending of each line, from the text (a model reports one for all).
        const path = decodeURIComponent(model.uri.toString().slice(uriPrefix.length))
        const text = draftsRef.current[path] ?? model.getValue()
        const ends = text.match(/\r\n|\r|\n/g) ?? []
        // Drawn by CSS (::after) so the marks are never part of the text.
        const marks = { '\r\n': 'plugin-ide-eol is-crlf', '\n': 'plugin-ide-eol is-lf', '\r': 'plugin-ide-eol is-cr' } as const
        const lines = model.getLineCount()
        const items = []
        for (let line = 1; line < lines; line += 1) {
            const column = model.getLineMaxColumn(line)
            const end = (ends[line - 1] ?? model.getEOL()) as keyof typeof marks
            items.push({
                range: new monaco.Range(line, column, line, column),
                options: { afterContentClassName: marks[end] ?? marks['\n'] },
            })
        }
        decorationsRef.current = editor.createDecorationsCollection(items)
    }, [uriPrefix])

    useEffect(() => {
        showAllRef.current = prefs.showAll
        paintLineEnds()
    }, [prefs.showAll, paintLineEnds])

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

    const reveal = useCallback(
        (path: string, line: number, column: number, endColumn?: number) => {
            openFile(path)

            window.setTimeout(() => {
                const editor = editorRef.current
                if (!editor) return

                editor.revealLineInCenter(line)
                if (endColumn) editor.setSelection(new monaco.Range(line, column, line, endColumn))
                else editor.setPosition({ lineNumber: line, column })
                editor.focus()
            }, 30)
        },
        [openFile],
    )

    const revealProblem = (item: PluginDiagnostic) => {
        if (item.path in drafts) reveal(item.path, item.line, item.column)
    }

    const editorAction = useCallback((id: string) => {
        const editor = editorRef.current
        if (!editor) return
        editor.focus()
        void editor.getAction(id)?.run()
    }, [])

    // ------------------------------------------------------------------
    // Files and folders
    // ------------------------------------------------------------------

    const uniquePath = (folder: string, stem: string, suffix: string) => {
        for (let index = 0; ; index += 1) {
            const path = join(folder, `${stem}${index ? `-${index}` : ''}${suffix}`)
            if (!(path in drafts) && !folders.includes(path)) return path
        }
    }

    const newFile = (folder: string) => {
        if (readOnly) return
        const path = uniquePath(folder, 'untitled', '.py')
        setDrafts((existing) => ({ ...existing, [path]: '' }))
        setSidebar('explorer')
        setSidebarOpen(true)
        openFile(path)
        setRenaming(path)
    }

    const newFolder = (folder: string) => {
        if (readOnly) return
        const path = uniquePath(folder, 'new_folder', '')
        setFolders((existing) => [...existing, path])
        setSidebar('explorer')
        setSidebarOpen(true)
        setRenaming(path)
    }

    /** Move files (and folders) to new paths, keeping their open tabs. */
    const relocate = (mapping: Array<[string, string]>, folderMapping: Array<[string, string]> = []) => {
        const next = { ...drafts }
        for (const [from] of mapping) delete next[from]
        for (const [from, to] of mapping) {
            const problem = validateNewPath(to, next)
            if (problem) {
                notify.error(`${to}: ${problem}`, { title: 'Cannot move' })
                return
            }
            next[to] = drafts[from]
        }
        for (const [from] of mapping) modelOf(from)?.dispose()
        setDrafts(next)
        const moved = new Map(mapping)
        setOpenTabs((tabs) => tabs.map((tab) => moved.get(tab) ?? tab))
        setActivePath((path) => (path ? moved.get(path) ?? path : path))
        if (folderMapping.length) {
            const renamed = new Map(folderMapping)
            setFolders((existing) => existing.map((folder) => renamed.get(folder) ?? folder))
        }
    }

    /** Files and folders under a folder, mapped to a new folder path. */
    const folderMoves = (from: string, to: string) => {
        const files = Object.keys(drafts)
            .filter((path) => path.startsWith(`${from}/`))
            .map((path): [string, string] => [path, `${to}${path.slice(from.length)}`])
        const subfolders = [from, ...folders.filter((folder) => folder.startsWith(`${from}/`))].map(
            (folder): [string, string] => [folder, `${to}${folder.slice(from.length)}`],
        )
        return { files, subfolders }
    }

    const renameRow = (row: TreeRow, name: string) => {
        if (!name) {
            setRenaming(row.path)
            return
        }
        if (!PATH_SEGMENT.test(name)) {
            notify.error('Use letters, digits, "_", "-" or ".".', { title: 'Cannot rename' })
            return
        }
        const target = join(parentOf(row.path), name)
        if (row.kind === 'file') {
            relocate([[row.path, target]])
            return
        }
        if (target in drafts || folders.includes(target) || Object.keys(drafts).some((path) => path.startsWith(`${target}/`))) {
            notify.error(`${target} already exists.`, { title: 'Cannot rename' })
            return
        }
        const { files, subfolders } = folderMoves(row.path, target)
        relocate(files, subfolders)
        if (!files.length) setFolders((existing) => existing.map((folder) => (folder === row.path ? target : folder)))
    }

    const moveRow = (row: TreeRow, folder: string) => {
        const target = join(folder, row.path.split('/').pop() as string)
        if (row.kind === 'file') relocate([[row.path, target]])
        else {
            const { files, subfolders } = folderMoves(row.path, target)
            relocate(files, subfolders)
        }
    }

    const removeRow = async (row: TreeRow) => {
        const files =
            row.kind === 'file' ? [row.path] : Object.keys(drafts).filter((path) => path.startsWith(`${row.path}/`))
        if (
            files.length &&
            !(await modal.confirm({
                title: `Delete ${row.label}?`,
                message:
                    row.kind === 'file'
                        ? `${row.path} is deleted when you save.`
                        : `${files.length} file${files.length === 1 ? '' : 's'} in ${row.path} ${
                              files.length === 1 ? 'is' : 'are'
                          } deleted when you save.`,
                confirmText: 'Delete',
                destructive: true,
            }))
        ) {
            return
        }
        setDrafts((existing) => {
            const next = { ...existing }
            for (const path of files) delete next[path]
            return next
        })
        for (const path of files) modelOf(path)?.dispose()
        setOpenTabs((tabs) => tabs.filter((tab) => !files.includes(tab)))
        setActivePath((path) => (path && files.includes(path) ? null : path))
        if (row.kind === 'folder') {
            setFolders((existing) => existing.filter((folder) => folder !== row.path && !folder.startsWith(`${row.path}/`)))
        }
    }

    const revertFile = (path: string) => {
        // Open models keep their own text; reset them along with the draft.
        const model = modelOf(path)

        if (model && path in originals) model.setValue(originals[path])
        else model?.dispose()

        setDrafts((existing) => {
            const next = { ...existing }

            if (path in originals) next[path] = originals[path]
            else delete next[path]

            return next
        })

        if (!(path in originals)) {
            setOpenTabs((tabs) => tabs.filter((tab) => tab !== path))
            if (activePath === path) setActivePath(null)
        }
    }

    const generateContract = async () => {
        setContractBusy(true)
        try {
            const result = await pluginsApi.generateContract(qualifiedName, changes, removed)
            const added = [...result.added.arguments, ...result.added.outputs]
            if (result.content !== drafts['plugin.json']) setContent('plugin.json', result.content)
            openFile('plugin.json')
            if (added.length) {
                notify.success(
                    `Added ${result.added.arguments.length} argument${result.added.arguments.length === 1 ? '' : 's'} and ${
                        result.added.outputs.length
                    } output${result.added.outputs.length === 1 ? '' : 's'} to plugin.json. Fill in their types, required flags and descriptions.`,
                    { title: 'Contract generated' },
                )
            } else if (result.content !== drafts['plugin.json']) {
                notify.success('plugin.json now declares its contract: the source reads no arguments and publishes no outputs.', {
                    title: 'Contract generated',
                })
            } else {
                notify.success('plugin.json already declares every argument and output the source uses.', {
                    title: 'Contract up to date',
                })
            }
        } catch (error) {
            notify.error(error instanceof Error ? error.message : 'Unable to generate the contract.', {
                title: 'Contract not generated',
            })
        } finally {
            setContractBusy(false)
        }
    }

    // ------------------------------------------------------------------
    // Save
    // ------------------------------------------------------------------

    const save = useCallback(async () => {
        if (!dirty || saving) return

        // A draft is only saved unless the author chooses to install it now.
        const install =
            Boolean(current.draft) &&
            (await modal.confirm({
                title: `Install ${qualifiedName}?`,
                message:
                    'This plugin is a draft: workflows cannot use it until it is installed. ' +
                    'Install it now (it must pass validation), or keep saving it as a draft.',
                confirmText: 'Save and install',
                cancelText: 'Save as draft',
            }))

        setSaving(true)

        try {
            const result = await pluginsApi.save(qualifiedName, changes, revision, install, removed)
            const files = Object.fromEntries(result.files.map((file) => [file.path, file.content]))

            // The server may change files too (plugin.json's version).
            for (const [path, content] of Object.entries(files)) {
                const model = modelOf(path)
                if (model && draftsRef.current[path] !== content) model.setValue(content)
            }
            setOriginals(files)
            setDrafts(files)
            setMeta(metaOf(result.files))
            setRevision(result.revision)
            setCurrent(result.plugin)
            setFolders((existing) => existing.filter((folder) => !Object.keys(files).some((path) => path.startsWith(`${folder}/`))))
            setMode('edit')
            onSaved(result.plugin)

            notify.success(
                result.plugin.draft
                    ? `${pending} change${pending === 1 ? '' : 's'} saved to the draft.`
                    : install
                      ? `${result.plugin.qualified_name} saved and installed as version ${result.plugin.version}.`
                      : `${pending} change${pending === 1 ? '' : 's'} saved; ${result.plugin.qualified_name} reinstalled as version ${result.plugin.version}.`,
                { title: result.plugin.draft ? 'Draft saved' : 'Plugin saved' },
            )

            setSaving(false)
            const close = await modal.confirm({
                title: 'Saved. Close the editor?',
                message: `${result.plugin.qualified_name} ${result.plugin.version} is saved. Keep editing, or close the editor.`,
                confirmText: 'Close editor',
                cancelText: 'Keep editing',
            })
            if (close) onClose()
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
    }, [changes, current.draft, dirty, modal, modelOf, notify, onClose, onSaved, pending, qualifiedName, removed, revision, saving])

    const preview = useCallback(() => {
        if (!dirty) return

        // Only deletions: nothing to diff, save straight away.
        if (!changedPaths.length) {
            void save()
            return
        }

        setReviewPath((path) =>
            path && path in changes ? path : changedPaths[0] ?? null,
        )
        setMode('review')
    }, [changedPaths, changes, dirty, save])

    const cancel = async () => {
        if (
            dirty &&
            !(await modal.confirm({
                title: 'Discard unsaved changes?',
                message: `${pending} unsaved change${pending === 1 ? '' : 's'} in ${qualifiedName} will be lost.`,
                confirmText: 'Discard',
                cancelText: 'Keep editing',
                destructive: true,
            }))
        ) {
            return
        }

        onClose()
    }

    // ------------------------------------------------------------------
    // Run
    // ------------------------------------------------------------------

    const runBlocker = current.draft
        ? 'Install the plugin to run it: save it and choose "Save and install".'
        : dirty
          ? 'Save your changes first: runs use the installed plugin.'
          : runReason

    const startRun = (debug: boolean) => {
        if (runBlocker) {
            notify.error(runBlocker, { title: debug ? 'Cannot debug yet' : 'Cannot run yet' })
            return
        }
        setRunDialog({ debug })
    }

    // ------------------------------------------------------------------
    // Keyboard
    // ------------------------------------------------------------------

    // Bound in the capture phase so the browser (Save page, Find, Reload)
    // never sees them, wherever the focus is in the editor; keys are matched
    // by their physical position too, for Windows and non-US layouts.
    const keyActions = useRef<KeyActions | null>(null)

    useEffect(() => {
        keyActions.current = {
            save: preview,
            search: (replace) => {
                setSidebar('search')
                setSidebarOpen(true)
                setReplaceFocus((value) => (replace ? value + 1 : 0))
            },
            explorer: () => {
                setSidebar('explorer')
                setSidebarOpen(true)
            },
            sidebar: () => setSidebarOpen((value) => !value),
            wrap: () => setPrefs((value) => ({ ...value, wrap: !value.wrap })),
            showAll: () => setPrefs((value) => ({ ...value, showAll: !value.showAll })),
            newFile: () => newFile(''),
            run: startRun,
        }
    })

    useEffect(() => {
        function handleKeyDown(event: KeyboardEvent) {
            const root = rootRef.current
            const target = event.target as HTMLElement | null
            // Dialogs over the editor (run, history, confirmations) keep their keys.
            if (!root || !target || !(root.contains(target) || target === document.body)) return

            const mod = event.ctrlKey || event.metaKey
            const inMonaco = Boolean(target.closest('.monaco-editor'))
            const actions = keyActions.current
            if (!actions) return
            let handled = true

            if (mod && !event.shiftKey && !event.altKey && keyMatches(event, 's')) {
                if (!readOnly) actions.save()
            } else if (mod && event.shiftKey && keyMatches(event, 'f')) actions.search(false)
            else if (mod && event.shiftKey && keyMatches(event, 'h')) actions.search(!readOnly)
            else if (mod && event.shiftKey && keyMatches(event, 'e')) actions.explorer()
            else if (mod && !event.shiftKey && !event.altKey && keyMatches(event, 'b')) actions.sidebar()
            else if (mod && event.altKey && keyMatches(event, 'n')) actions.newFile()
            else if (event.altKey && !mod && !event.shiftKey && keyMatches(event, 'z')) actions.wrap()
            else if (event.altKey && event.shiftKey && !mod && keyMatches(event, 'w')) actions.showAll()
            else if (event.key === 'F5' && !event.shiftKey) actions.run(!mod)
            else if (!inMonaco && mod && !event.shiftKey && keyMatches(event, 'f')) editorAction('actions.find')
            else if (!inMonaco && mod && !event.shiftKey && keyMatches(event, 'h')) {
                editorAction('editor.action.startFindReplaceAction')
            } else if (!inMonaco && mod && !event.shiftKey && keyMatches(event, 'g')) {
                editorAction('editor.action.gotoLine')
            } else handled = false

            if (handled) {
                event.preventDefault()
                event.stopPropagation()
            }
        }

        window.addEventListener('keydown', handleKeyDown, true)
        return () => window.removeEventListener('keydown', handleKeyDown, true)
    }, [editorAction, readOnly])

    const handleMount: OnMount = (editor) => {
        editorRef.current = editor

        editor.onDidChangeCursorPosition((event) =>
            setCursor({
                line: event.position.lineNumber,
                column: event.position.column,
            }),
        )

        let frame = 0
        const repaint = () => {
            window.cancelAnimationFrame(frame)
            frame = window.requestAnimationFrame(paintLineEnds)
        }
        editor.onDidChangeModel(repaint)
        editor.onDidChangeModelContent(repaint)
        repaint()
    }

    // ------------------------------------------------------------------
    // Sidebar resize
    // ------------------------------------------------------------------

    const startResize = (event: ReactPointerEvent<HTMLDivElement>) => {
        event.preventDefault()
        const handle = event.currentTarget
        const startX = event.clientX
        const startWidth = prefs.sidebarWidth
        handle.setPointerCapture(event.pointerId)
        const move = (moveEvent: PointerEvent) => {
            const width = Math.min(SIDEBAR.max, Math.max(SIDEBAR.min, startWidth + moveEvent.clientX - startX))
            setPrefs((value) => ({ ...value, sidebarWidth: width }))
        }
        const up = () => {
            handle.removeEventListener('pointermove', move)
            handle.removeEventListener('pointerup', up)
        }
        handle.addEventListener('pointermove', move)
        handle.addEventListener('pointerup', up)
    }

    const resizeBy = (delta: number) =>
        setPrefs((value) => ({
            ...value,
            sidebarWidth: Math.min(SIDEBAR.max, Math.max(SIDEBAR.min, value.sidebarWidth + delta)),
        }))

    // ------------------------------------------------------------------
    // Render
    // ------------------------------------------------------------------

    const tree = useMemo(() => buildTree(Object.keys(drafts), folders), [drafts, folders])
    const reviewErrors = diagnostics.filter(
        (item) => item.severity === 'error',
    )
    const activeEndings = activePath ? lineEndings(drafts[activePath] ?? '') : null

    const infoRows = (row: TreeRow): Array<[string, string]> => {
        if (row.kind === 'folder') {
            const files = Object.keys(drafts).filter((path) => path.startsWith(`${row.path}/`))
            const size = files.reduce((total, path) => total + new Blob([drafts[path]]).size, 0)
            return [
                ['Folder', row.path],
                ['Files', String(files.length)],
                ['Size', formatBytes(size)],
                ['Status', files.length ? (files.some((path) => path in changes) ? 'Has unsaved changes' : 'Saved') : 'Empty: saved once it holds a file'],
            ]
        }
        const text = drafts[row.path] ?? ''
        const endings = lineEndings(text)
        const saved = meta[row.path]
        return [
            ['File', row.path],
            ['Type', languageOf(row.path)],
            ['Size', formatBytes(new Blob([text]).size) + (saved?.size !== undefined && row.path in changes ? ` (saved: ${formatBytes(saved.size)})` : '')],
            ['Lines', String(text ? text.split(/\r\n|\r|\n/).length : 0)],
            [
                'Line endings',
                endings.mixed
                    ? `Mixed: ${endings.crlf} CRLF, ${endings.lf} LF${endings.cr ? `, ${endings.cr} CR` : ''}`
                    : endings.crlf
                      ? 'CRLF (Windows)'
                      : endings.cr
                        ? 'CR'
                        : 'LF (Unix)',
            ],
            ['Encoding', 'UTF-8'],
            ['Modified', saved?.modified ? new Date(saved.modified).toLocaleString() : 'Not saved yet'],
            ['Status', !(row.path in originals) ? 'New, not saved yet' : row.path in changes ? 'Unsaved changes' : 'Saved'],
        ]
    }

    return (
        <div
            ref={rootRef}
            className="plugin-ide"
            role="dialog"
            aria-modal="true"
            aria-label={`${readOnly ? 'View' : 'Edit'} plugin ${qualifiedName}`}
        >
            <WallpaperLayer veil="var(--ide-bg-base)" />
            <header className="plugin-ide-topbar">
                <button
                    type="button"
                    className="entropy-button entropy-button-secondary"
                    onClick={() => void cancel()}
                    disabled={saving}
                >
                    <X size={16} />
                    {readOnly || !dirty ? 'Close' : 'Cancel'}
                </button>

                <div className="plugin-ide-title">
                    <strong>{qualifiedName}</strong>
                    <span className="plugins-version">{current.version}</span>
                    {current.draft && <span className="plugin-ide-chip">Draft</span>}
                    {readOnly && <span className="plugin-ide-chip">Read only</span>}
                    {mode === 'review' && (
                        <span className="plugin-ide-chip">Reviewing changes</span>
                    )}
                    {dirty && (
                        <span className="plugin-ide-chip plugin-ide-chip-dirty">
                            {pending} unsaved
                        </span>
                    )}
                    {builderModel && mode === 'edit' && (
                        <div className="seg-control plugin-ide-view" role="tablist" aria-label="Editor view">
                            <button
                                type="button"
                                role="tab"
                                aria-selected={view === 'visual'}
                                className={view === 'visual' ? 'is-active' : ''}
                                onClick={() => setView('visual')}
                            >
                                Visual
                            </button>
                            <button
                                type="button"
                                role="tab"
                                aria-selected={view === 'source'}
                                className={view === 'source' ? 'is-active' : ''}
                                onClick={() => setView('source')}
                            >
                                Source
                            </button>
                        </div>
                    )}
                </div>

                <div className="plugin-ide-actions">
                    <button
                        type="button"
                        className="entropy-button entropy-button-secondary"
                        onClick={() => startRun(false)}
                        aria-disabled={runBlocker ? true : undefined}
                        disabled={loading || saving}
                        title={runBlocker ?? 'Run the installed plugin once (Ctrl/⌘ + F5)'}
                    >
                        <Play size={15} />
                        Run
                    </button>
                    <button
                        type="button"
                        className="entropy-button entropy-button-secondary"
                        onClick={() => startRun(true)}
                        aria-disabled={runBlocker ? true : undefined}
                        disabled={loading || saving}
                        title={runBlocker ?? 'Run with debug messages and the debug log shown (F5)'}
                    >
                        <Bug size={15} />
                        Debug
                    </button>
                    <button
                        type="button"
                        className="entropy-button entropy-button-secondary"
                        onClick={() => setHistoryOpen(true)}
                        disabled={loading || saving}
                        title="Earlier versions of this plugin: compare and restore"
                    >
                        <History size={15} />
                        History
                    </button>
                    {!readOnly && (
                        <SaveMenu
                            disabled={!dirty || saving || loading}
                            saving={saving}
                            onPreview={preview}
                            onSave={() => void save()}
                        />
                    )}
                </div>
            </header>

            {historyOpen && (
                <HistoryDialog
                    kind="plugin"
                    name={qualifiedName}
                    restoreReason={
                        restoreReason ?? (dirty ? 'Save or discard your unsaved changes before restoring.' : null)
                    }
                    onRestored={(version) => onRestored?.(version)}
                    onClose={() => setHistoryOpen(false)}
                />
            )}

            {runDialog && (
                <StartRunDialog
                    kind="plugin"
                    target={qualifiedName}
                    debug={runDialog.debug}
                    onStarted={(run) => {
                        setLastRun(run)
                        notify.success(`Run #${run.id} started on ${run.node}. Open it from the status bar.`, {
                            title: runDialog.debug ? 'Debug run started' : 'Run started',
                        })
                    }}
                    onClose={() => setRunDialog(null)}
                />
            )}

            {shortcutsOpen && (
                <Dialog
                    title="Editor shortcuts"
                    subtitle="Ctrl on Windows and Linux, ⌘ on macOS."
                    icon={<Keyboard size={18} />}
                    onClose={() => setShortcutsOpen(false)}
                    className="plugin-ide-shortcuts"
                >
                    <dl className="plugin-ide-shortcut-list">
                        {SHORTCUTS.map(([keys, label]) => (
                            <div key={keys}>
                                <dt>
                                    <kbd>{keys}</kbd>
                                </dt>
                                <dd>{label}</dd>
                            </div>
                        ))}
                    </dl>
                </Dialog>
            )}

            {infoFor && (
                <Dialog
                    title={infoFor.label}
                    subtitle={infoFor.kind === 'folder' ? 'Folder' : 'File'}
                    icon={<Info size={18} />}
                    onClose={() => setInfoFor(null)}
                    className="plugin-ide-info-dialog"
                >
                    <dl className="plugin-ide-info-list">
                        {infoRows(infoFor).map(([label, value]) => (
                            <div key={label}>
                                <dt>{label}</dt>
                                <dd>{value}</dd>
                            </div>
                        ))}
                    </dl>
                </Dialog>
            )}

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
                    {builderModel && view === 'visual' && mode === 'edit' && (
                        <div className="plugin-ide-body plugin-ide-visual">
                            <VisualBuilder
                                model={builderModel}
                                onChange={changeModel}
                                problems={builderProblems}
                                source={drafts['plugin.py'] ?? ''}
                                generating={generating}
                                readOnly={readOnly}
                            />
                        </div>
                    )}

                    {/* Kept mounted while reviewing so models, cursor and undo survive. */}
                    <div
                        className={`plugin-ide-body plugin-ide-workbench${sidebarOpen ? '' : ' is-sidebar-hidden'}`}
                        hidden={mode !== 'edit' || (builderModel !== null && view === 'visual')}
                        style={{ '--ide-sidebar': `${prefs.sidebarWidth}px` } as CSSProperties}
                    >
                        {sidebarOpen && (
                            <>
                                <aside className="plugin-ide-explorer" aria-label="Plugin files">
                                    <div className="plugin-ide-sidebar-tabs" role="tablist">
                                        <button
                                            type="button"
                                            role="tab"
                                            aria-selected={sidebar === 'explorer'}
                                            className={sidebar === 'explorer' ? 'is-active' : ''}
                                            onClick={() => setSidebar('explorer')}
                                            title="Explorer (Ctrl/⌘ + Shift + E)"
                                        >
                                            <Files size={14} /> Explorer
                                        </button>
                                        <button
                                            type="button"
                                            role="tab"
                                            aria-selected={sidebar === 'search'}
                                            className={sidebar === 'search' ? 'is-active' : ''}
                                            onClick={() => {
                                                setSidebar('search')
                                                setReplaceFocus(0)
                                            }}
                                            title="Search and replace in all files (Ctrl/⌘ + Shift + F)"
                                        >
                                            <Search size={14} /> Search
                                        </button>
                                        <button
                                            type="button"
                                            className="plugin-ide-sidebar-hide"
                                            aria-label="Hide the sidebar"
                                            title="Hide the sidebar (Ctrl/⌘ + B)"
                                            onClick={() => setSidebarOpen(false)}
                                        >
                                            <PanelLeftClose size={14} />
                                        </button>
                                    </div>

                                    {sidebar === 'explorer' ? (
                                        <>
                                            <div className="plugin-ide-explorer-heading">
                                                <span>{qualifiedName}</span>
                                                {!readOnly && (
                                                    <span className="plugin-ide-explorer-actions">
                                                        <button
                                                            type="button"
                                                            aria-label="New file"
                                                            title="New file (Ctrl/⌘ + Alt + N)"
                                                            onClick={() => newFile('')}
                                                        >
                                                            <FilePlus2 size={15} />
                                                        </button>
                                                        <button
                                                            type="button"
                                                            aria-label="New folder"
                                                            title="New folder"
                                                            onClick={() => newFolder('')}
                                                        >
                                                            <FolderPlus size={15} />
                                                        </button>
                                                    </span>
                                                )}
                                            </div>
                                            <FileTree
                                                rows={tree}
                                                activePath={activePath}
                                                readOnly={readOnly}
                                                renaming={renaming}
                                                onRenamingDone={() => setRenaming(null)}
                                                badges={(path) => (
                                                    <>
                                                        {problemCounts[path]?.errors ? (
                                                            <span className="plugin-ide-badge plugin-ide-badge-error">
                                                                {problemCounts[path].errors}
                                                            </span>
                                                        ) : null}
                                                        {path in changes && (
                                                            <span
                                                                className="plugin-ide-dirty"
                                                                title={path in originals ? 'Modified' : 'New file'}
                                                            >
                                                                {path in originals ? 'M' : 'A'}
                                                            </span>
                                                        )}
                                                    </>
                                                )}
                                                actions={{
                                                    open: openFile,
                                                    newFile,
                                                    newFolder,
                                                    rename: renameRow,
                                                    move: moveRow,
                                                    remove: (row) => void removeRow(row),
                                                    info: setInfoFor,
                                                }}
                                            />
                                            {removed.length > 0 && (
                                                <div className="plugin-ide-removed">
                                                    <span>Deleted when saved</span>
                                                    <ul>
                                                        {removed.map((path) => (
                                                            <li key={path}>
                                                                <span className="plugin-ide-tree-label">{path}</span>
                                                                <button
                                                                    type="button"
                                                                    aria-label={`Restore ${path}`}
                                                                    title="Restore"
                                                                    onClick={() =>
                                                                        setDrafts((existing) => ({
                                                                            ...existing,
                                                                            [path]: originals[path],
                                                                        }))
                                                                    }
                                                                >
                                                                    <RotateCcw size={12} />
                                                                </button>
                                                            </li>
                                                        ))}
                                                    </ul>
                                                </div>
                                            )}
                                        </>
                                    ) : (
                                        <SearchPanel
                                            files={drafts}
                                            readOnly={readOnly}
                                            focusReplace={replaceFocus}
                                            onOpen={(match: SearchMatch) =>
                                                reveal(match.path, match.line, match.column, match.endColumn)
                                            }
                                            onReplace={(replaced) => {
                                                for (const [path, text] of Object.entries(replaced)) setContent(path, text)
                                                notify.success(
                                                    `Replaced in ${Object.keys(replaced).length} file${
                                                        Object.keys(replaced).length === 1 ? '' : 's'
                                                    }. Undo with Ctrl/⌘ + Z in each file.`,
                                                    { title: 'Replaced' },
                                                )
                                            }}
                                        />
                                    )}
                                </aside>

                                <div
                                    className="plugin-ide-resizer"
                                    role="separator"
                                    aria-orientation="vertical"
                                    aria-label="Resize the sidebar"
                                    aria-valuemin={SIDEBAR.min}
                                    aria-valuemax={SIDEBAR.max}
                                    aria-valuenow={prefs.sidebarWidth}
                                    tabIndex={0}
                                    title="Drag to resize; double-click to reset"
                                    onPointerDown={startResize}
                                    onDoubleClick={() => setPrefs((value) => ({ ...value, sidebarWidth: SIDEBAR.initial }))}
                                    onKeyDown={(event) => {
                                        if (event.key === 'ArrowLeft') resizeBy(-16)
                                        if (event.key === 'ArrowRight') resizeBy(16)
                                    }}
                                />
                            </>
                        )}

                        <section className="plugin-ide-main">
                            {builderModel && (
                                <div className="plugin-ide-banner" role="note">
                                    <Info size={14} aria-hidden="true" />
                                    This plugin is made in the visual builder: plugin.py and plugin.json are rewritten
                                    from it whenever the model changes. Delete builder.json to edit the source by hand
                                    for good.
                                </div>
                            )}
                            <div className="plugin-ide-tabbar">
                                {!sidebarOpen && (
                                    <button
                                        type="button"
                                        className="plugin-ide-tool"
                                        aria-label="Show the sidebar"
                                        title="Show the sidebar (Ctrl/⌘ + B)"
                                        onClick={() => setSidebarOpen(true)}
                                    >
                                        <Files size={15} />
                                    </button>
                                )}
                                <div
                                    className="plugin-ide-tabs"
                                    role="tablist"
                                    title={readOnly ? undefined : 'Double-click for a new file'}
                                    onDoubleClick={(event) => {
                                        if (event.target === event.currentTarget) newFile('')
                                    }}
                                >
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
                                                onAuxClick={(event) => {
                                                    if (event.button === 1) closeTab(path)
                                                }}
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

                                <div className="plugin-ide-toolbar" role="toolbar" aria-label="Editor tools">
                                    <button
                                        type="button"
                                        className="plugin-ide-tool"
                                        aria-label="Find in this file"
                                        title="Find in this file (Ctrl/⌘ + F)"
                                        disabled={!activePath}
                                        onClick={() => editorAction('actions.find')}
                                    >
                                        <Search size={15} />
                                    </button>
                                    {!readOnly && (
                                        <button
                                            type="button"
                                            className="plugin-ide-tool"
                                            aria-label="Replace in this file"
                                            title="Replace in this file (Ctrl/⌘ + H)"
                                            disabled={!activePath}
                                            onClick={() => editorAction('editor.action.startFindReplaceAction')}
                                        >
                                            <Replace size={15} />
                                        </button>
                                    )}
                                    <button
                                        type="button"
                                        className="plugin-ide-tool"
                                        aria-label="Go to line"
                                        title="Go to line (Ctrl/⌘ + G)"
                                        disabled={!activePath}
                                        onClick={() => editorAction('editor.action.gotoLine')}
                                    >
                                        <ListOrdered size={15} />
                                    </button>
                                    <button
                                        type="button"
                                        className={`plugin-ide-tool${prefs.wrap ? ' is-active' : ''}`}
                                        aria-pressed={prefs.wrap}
                                        aria-label="Wrap long lines"
                                        title="Wrap long lines (Alt + Z)"
                                        onClick={() => setPrefs((value) => ({ ...value, wrap: !value.wrap }))}
                                    >
                                        <WrapText size={15} />
                                    </button>
                                    <button
                                        type="button"
                                        className={`plugin-ide-tool${prefs.showAll ? ' is-active' : ''}`}
                                        aria-pressed={prefs.showAll}
                                        aria-label="Show all characters"
                                        title="Show all characters: spaces, tabs, control characters and line ends (␍␊ CRLF, ␊ LF) (Alt + Shift + W)"
                                        onClick={() => setPrefs((value) => ({ ...value, showAll: !value.showAll }))}
                                    >
                                        <Pilcrow size={15} />
                                    </button>
                                    {!readOnly && (
                                        <button
                                            type="button"
                                            className="plugin-ide-tool"
                                            aria-label="Generate contract"
                                            title="Generate contract: add the arguments and outputs the source uses to plugin.json"
                                            disabled={contractBusy || !('plugin.json' in drafts)}
                                            onClick={() => void generateContract()}
                                        >
                                            {contractBusy ? (
                                                <LoaderCircle size={15} className="entropy-spin" />
                                            ) : (
                                                <FileSignature size={15} />
                                            )}
                                        </button>
                                    )}
                                    <button
                                        type="button"
                                        className="plugin-ide-tool"
                                        aria-label="Keyboard shortcuts"
                                        title="Keyboard shortcuts"
                                        onClick={() => setShortcutsOpen(true)}
                                    >
                                        <Keyboard size={15} />
                                    </button>
                                </div>
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
                                            setDrafts((existing) =>
                                                activePath in existing
                                                    ? { ...existing, [activePath]: value ?? '' }
                                                    : existing,
                                            )
                                        }
                                        options={{
                                            automaticLayout: true,
                                            fontSize: 13,
                                            minimap: { enabled: true },
                                            scrollBeyondLastLine: false,
                                            tabSize: 4,
                                            renderWhitespace: prefs.showAll ? 'all' : 'selection',
                                            renderControlCharacters: prefs.showAll,
                                            unicodeHighlight: { invisibleCharacters: prefs.showAll },
                                            wordWrap: prefs.wrap ? 'on' : 'off',
                                            quickSuggestions: true,
                                            wordBasedSuggestions: 'currentDocument',
                                            readOnly,
                                        }}
                                    />
                                ) : (
                                    <div
                                        className="plugin-ide-state"
                                        onDoubleClick={() => newFile('')}
                                    >
                                        <span>Select a file from the explorer{readOnly ? '' : ', or double-click here for a new one'}.</span>
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
                                    <span>Changes ({pending})</span>
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
                                                        if (changedPaths.length === 1 && !removed.length) setMode('edit')
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
                                    {removed.map((path) => (
                                        <li key={`removed:${path}`} className="plugin-ide-review-row">
                                            <span className="plugin-ide-tree-file plugin-ide-tree-removed" title={path}>
                                                <FileIcon path={path} />
                                                <span className="plugin-ide-tree-label">{path}</span>
                                                <span className="plugin-ide-removed">deleted</span>
                                            </span>
                                        </li>
                                    ))}
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
                                        Confirm &amp; save {pending} change
                                        {pending === 1 ? '' : 's'}
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
                    ) : loading ? (
                        'Plugin SDK loading'
                    ) : (
                        'Plugin SDK help unavailable'
                    )}
                </span>
                <span className={errorCount ? 'plugin-ide-error' : undefined}>
                    {validating
                        ? 'Checking…'
                        : `${errorCount} error${errorCount === 1 ? '' : 's'}, ${
                              diagnostics.length - errorCount
                          } other`}
                </span>
                {lastRun && (
                    <a
                        href={`#/runs/${lastRun.id}`}
                        target="_blank"
                        rel="noopener noreferrer"
                        title="Open the run's live screen in a new tab"
                    >
                        {lastRun.debug ? <Bug size={12} /> : <Play size={12} />} Run #{lastRun.id}
                    </a>
                )}
                <span className="plugin-ide-statusbar-spacer" />
                {mode === 'edit' && activePath && (
                    <>
                        <button
                            type="button"
                            className="plugin-ide-status-button"
                            title="Go to line (Ctrl/⌘ + G)"
                            onClick={() => editorAction('editor.action.gotoLine')}
                        >
                            Ln {cursor.line}, Col {cursor.column}
                        </button>
                        <span>Spaces: 4</span>
                        <span>UTF-8</span>
                        {activeEndings?.mixed && (
                            <span
                                className="plugin-ide-warning"
                                title={`${activeEndings.crlf} CRLF, ${activeEndings.lf} LF${
                                    activeEndings.cr ? `, ${activeEndings.cr} CR` : ''
                                } line ends. Choose one to convert the whole file.`}
                            >
                                <AlertTriangle size={12} /> Mixed line ends
                            </span>
                        )}
                        <button
                            type="button"
                            className="plugin-ide-status-button"
                            disabled={readOnly}
                            title={
                                readOnly
                                    ? `Line ends: ${eol}`
                                    : `Line ends: ${eol}. Click to convert the file to ${eol === 'CRLF' ? 'LF (Unix)' : 'CRLF (Windows)'}.`
                            }
                            onClick={() => {
                                const model = editorRef.current?.getModel()
                                if (!model) return
                                model.pushEOL(
                                    eol === 'CRLF'
                                        ? monaco.editor.EndOfLineSequence.LF
                                        : monaco.editor.EndOfLineSequence.CRLF,
                                )
                                // A conversion touches no text, so report it as a change.
                                if (activePath) setDrafts((existing) => ({ ...existing, [activePath]: model.getValue() }))
                                paintLineEnds()
                            }}
                        >
                            {eol}
                        </button>
                        <span>{languageOf(activePath)}</span>
                    </>
                )}
                <button
                    type="button"
                    className="plugin-ide-status-button"
                    onClick={() => setShortcutsOpen(true)}
                >
                    <Keyboard size={12} /> Shortcuts
                </button>
            </footer>
        </div>
    )
}
