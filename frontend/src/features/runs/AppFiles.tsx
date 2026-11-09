import { useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import {
    Box,
    ChevronDown,
    ChevronRight,
    ChevronUp,
    Download,
    FileArchive,
    FileText,
    Folder,
    FolderOpen,
    LoaderCircle,
    Palette,
    Search,
    X,
} from 'lucide-react'

import type { RunAppFileNode, RunAppInput, RunAppView, RunAppViewData } from '../../api/runs.api'
import { useFeedback } from '../../components/feedback/FeedbackProvider'
import { downloadUrl } from '../../services/api'

const EXPANDABLE = new Set(['group', 'folder', 'archive'])

function formatSize(size: number | null | undefined): string {
    if (size === null || size === undefined) return ''
    if (size < 1024) return `${size} B`
    if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`
    return `${(size / (1024 * 1024)).toFixed(1)} MB`
}

function escapeRegExp(text: string): string {
    return text.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
}

/** Log words coloured like a terminal: the first rule to claim a character wins. */
const SYNTAX: { tone: string; pattern: RegExp }[] = [
    { tone: 'time', pattern: /^\[?\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(?:[.,]\d+)?(?:Z|[+-]\d{2}:?\d{2})?\]?/g },
    { tone: 'frame', pattern: /^\s+(?:at |\.\.\. \d+ more).*$/g },
    { tone: 'danger', pattern: /\b(?:ERROR|ERR|FATAL|SEVERE|CRITICAL|PANIC|FAIL(?:ED|URE|S)?|Traceback|Caused by)\b/gi },
    { tone: 'danger', pattern: /\b[\w.$]*(?:Exception|Error)\b/g },
    { tone: 'warning', pattern: /\b(?:WARN(?:ING)?|DEPRECATED)\b/gi },
    { tone: 'success', pattern: /\b(?:OK|SUCCESS(?:FUL(?:LY)?)?|SUCCEEDED|PASS(?:ED)?|DONE|COMPLETED|HEALTHY|READY)\b/gi },
    { tone: 'info', pattern: /\b(?:INFO|NOTICE)\b/g },
    { tone: 'debug', pattern: /\b(?:DEBUG|TRACE)\b/g },
]

type Range = { start: number; end: number }

function syntaxRanges(line: string): (Range & { tone: string })[] {
    const taken: (Range & { tone: string })[] = []
    for (const rule of SYNTAX) {
        for (const match of line.matchAll(rule.pattern)) {
            const start = match.index ?? 0
            const end = start + match[0].length
            if (end > start && !taken.some((range) => start < range.end && end > range.start)) {
                taken.push({ start, end, tone: rule.tone })
            }
        }
    }
    return taken
}

const COLOURS_KEY = 'entropy.appFiles.colours'

/**
 * A files view: a tree on the left and a read-only viewer on the right. Clicking a
 * node presses the view's `open` button with the node's id; other buttons aimed at
 * the view act on the open file.
 */
export default function AppFiles({ view, data, buttons, live, onPress }: {
    view: RunAppView
    data: RunAppViewData
    /** Buttons aimed at this view, besides `open`: they act on the open file. */
    buttons: RunAppInput[]
    live: boolean
    onPress: (name: string, selection: unknown[]) => Promise<void>
}) {
    const { notify } = useFeedback()
    const nodes = useMemo(() => data.nodes ?? [], [data.nodes])
    const treeActions = buttons.filter((input) => view.tree_actions?.includes(input.name))
    const fileActions = buttons.filter((input) => !view.tree_actions?.includes(input.name))
    const downloads = data.downloads ?? []
    const opened = data.opened ?? null
    const [expanded, setExpanded] = useState<Set<string>>(new Set())
    const [waiting, setWaiting] = useState<string | null>(null)
    const [busy, setBusy] = useState<string | null>(null)

    const children = useMemo(() => {
        const map = new Map<string | null, RunAppFileNode[]>()
        nodes.forEach((node) => {
            const list = map.get(node.parent) ?? []
            list.push(node)
            map.set(node.parent, list)
        })
        return map
    }, [nodes])

    // The spinner shows until what was asked for arrives: the file, or a folder's contents.
    const waitingNode = waiting ? nodes.find((item) => item.id === waiting) : undefined
    const pending =
        waitingNode &&
        opened?.id !== waiting &&
        !(EXPANDABLE.has(waitingNode.kind) && (waitingNode.loaded || children.has(waitingNode.id)))
            ? waitingNode.id
            : null

    const click = (node: RunAppFileNode) => {
        if (EXPANDABLE.has(node.kind)) {
            const open = expanded.has(node.id)
            const next = new Set(expanded)
            if (open) next.delete(node.id)
            else next.add(node.id)
            setExpanded(next)
            // Folders are read again each time they are opened; logs keep changing.
            if (open || !live || (node.kind !== 'folder' && node.loaded)) return
        } else if (!live) {
            return
        }
        setWaiting(node.id)
        void onPress(view.open ?? 'open', [node.id]).catch(() => setWaiting(null))
    }

    const run = async (input: RunAppInput, needsFile = true) => {
        if (needsFile && !opened) return
        setBusy(input.name)
        try {
            await onPress(input.name, opened ? [opened.id] : [])
        } finally {
            setBusy(null)
        }
    }

    const fetchFile = async (item: { url: string; name: string }) => {
        try {
            await downloadUrl(item.url, item.name)
        } catch (cause) {
            notify.error(cause instanceof Error ? cause.message : 'Unable to download.', { title: 'Download' })
        }
    }

    const renderNodes = (parent: string | null, depth: number) =>
        (children.get(parent) ?? []).map((node) => {
            const expandable = EXPANDABLE.has(node.kind)
            const isOpen = expanded.has(node.id)
            const Icon =
                node.kind === 'group' ? Box : node.kind === 'archive' ? FileArchive : node.kind === 'folder' ? (isOpen ? FolderOpen : Folder) : FileText
            const kids = children.get(node.id)
            return (
                <li key={node.id} role="treeitem" aria-expanded={expandable ? isOpen : undefined} aria-selected={opened?.id === node.id}>
                    <button
                        type="button"
                        className={`run-app-file${opened?.id === node.id ? ' is-open' : ''}`}
                        style={{ paddingLeft: 8 + depth * 14 }}
                        onClick={() => click(node)}
                        title={[node.name, node.note, node.modified, formatSize(node.size)].filter(Boolean).join(' · ')}
                    >
                        {expandable ? (isOpen ? <ChevronDown size={13} /> : <ChevronRight size={13} />) : <span className="run-app-file-gap" />}
                        <Icon size={14} aria-hidden="true" />
                        <span className="run-app-file-name">{node.name}</span>
                        {pending === node.id ? (
                            <LoaderCircle size={13} className="entropy-spin" />
                        ) : (
                            (node.note || node.size !== undefined) && (
                                <small>{node.note ?? formatSize(node.size)}</small>
                            )
                        )}
                    </button>
                    {expandable && isOpen && (
                        <ul role="group">
                            {kids?.length ? (
                                renderNodes(node.id, depth + 1)
                            ) : (
                                <li className="run-app-file-empty" style={{ paddingLeft: 30 + depth * 14 }}>
                                    {node.loaded ? 'Empty' : live ? 'Loading…' : 'Not read'}
                                </li>
                            )}
                        </ul>
                    )}
                </li>
            )
        })

    return (
        <div className="run-app-files-wrap">
            {(treeActions.length > 0 || downloads.length > 0) && (
                <div className="run-app-files-bar">
                    {treeActions.map((input) => (
                        <button
                            key={input.name}
                            type="button"
                            className="entropy-button entropy-button-secondary entropy-button-sm"
                            disabled={!live || busy !== null || nodes.length === 0}
                            title={input.description}
                            onClick={() => void run(input, false)}
                        >
                            {busy === input.name ? <LoaderCircle size={14} className="entropy-spin" /> : <Download size={14} />}
                            {input.label}
                        </button>
                    ))}
                    {downloads.length > 0 && (
                        <div className="run-app-downloads" aria-label="Ready to download">
                            <small>Ready:</small>
                            {downloads.map((item) => (
                                <button key={item.id} type="button" className="run-app-download" title={`Download ${item.name}`} onClick={() => void fetchFile(item)}>
                                    <FileArchive size={13} aria-hidden="true" />
                                    {item.name}
                                    <small>{formatSize(item.size)}</small>
                                </button>
                            ))}
                        </div>
                    )}
                </div>
            )}
            <div className="run-app-files">
                <nav className="run-app-files-tree" aria-label={`${view.title || view.label} tree`}>
                    {nodes.length === 0 ? (
                        <p className="run-app-muted">Nothing to browse.</p>
                    ) : (
                        <ul role="tree">{renderNodes(null, 0)}</ul>
                    )}
                    {(data.total ?? 0) > nodes.length && <small className="run-app-muted">Showing {nodes.length} of {data.total}.</small>}
                </nav>
                <FileViewer
                    opened={opened}
                    buttons={fileActions}
                    live={live}
                    busy={busy}
                    onRun={(input) => void run(input)}
                />
            </div>
        </div>
    )
}

function FileViewer({ opened, buttons, live, busy, onRun }: {
    opened: RunAppViewData['opened']
    buttons: RunAppInput[]
    live: boolean
    busy: string | null
    onRun: (input: RunAppInput) => void
}) {
    const [query, setQuery] = useState('')
    const [current, setCurrent] = useState(0)
    const [colours, setColours] = useState(() => localStorage.getItem(COLOURS_KEY) !== 'off')
    const body = useRef<HTMLDivElement>(null)
    const text = opened?.text ?? ''
    const lines = useMemo(() => (text ? text.split('\n') : []), [text])
    const pattern = useMemo(() => (query.trim() ? new RegExp(escapeRegExp(query.trim()), 'gi') : null), [query])

    // Every match as (line, nth match on that line), in order.
    const matches = useMemo(() => {
        if (!pattern) return [] as [number, number][]
        const found: [number, number][] = []
        lines.forEach((line, index) => {
            const count = line.match(pattern)?.length ?? 0
            for (let nth = 0; nth < count; nth += 1) found.push([index, nth])
        })
        return found
    }, [lines, pattern])

    const position = matches.length ? Math.min(current, matches.length - 1) : 0

    useEffect(() => {
        if (!matches.length) return
        body.current?.querySelector('mark.is-current')?.scrollIntoView({ block: 'center' })
    }, [position, matches])

    const move = (step: number) => {
        if (!matches.length) return
        setCurrent((position + step + matches.length) % matches.length)
    }

    const download = () => {
        if (!opened) return
        const url = URL.createObjectURL(new Blob([text], { type: 'text/plain;charset=utf-8' }))
        const link = document.createElement('a')
        link.href = url
        link.download = opened.download_name || 'log.txt'
        link.click()
        URL.revokeObjectURL(url)
    }

    /** One line as segments: keyword colours underneath, search matches on top. */
    const highlight = (line: string, index: number) => {
        if (!line) return ' '
        const tones = colours ? syntaxRanges(line) : []
        const marks: (Range & { nth: number })[] = []
        if (pattern) {
            let nth = 0
            for (const match of line.matchAll(pattern)) {
                const start = match.index ?? 0
                marks.push({ start, end: start + match[0].length, nth })
                nth += 1
            }
        }
        if (!tones.length && !marks.length) return line
        const cuts = new Set([0, line.length])
        ;[...tones, ...marks].forEach((range) => {
            cuts.add(range.start)
            cuts.add(range.end)
        })
        const points = [...cuts].sort((a, b) => a - b)
        const parts: ReactNode[] = []
        for (let i = 0; i < points.length - 1; i += 1) {
            const start = points[i]
            const end = points[i + 1]
            const text = line.slice(start, end)
            const tone = tones.find((range) => start >= range.start && end <= range.end)?.tone
            const mark = marks.find((range) => start >= range.start && end <= range.end)
            const coloured = tone ? <span className={`log-${tone}`}>{text}</span> : text
            if (mark) {
                const isCurrent = matches[position]?.[0] === index && matches[position]?.[1] === mark.nth
                parts.push(
                    <mark key={start} className={isCurrent ? 'is-current' : undefined}>
                        {coloured}
                    </mark>,
                )
            } else {
                parts.push(tone ? <span key={start} className={`log-${tone}`}>{text}</span> : text)
            }
        }
        return parts
    }

    if (!opened) {
        return (
            <section className="run-app-viewer is-empty">
                <FileText size={20} aria-hidden="true" />
                <p>Pick a file in the tree to read it here.</p>
            </section>
        )
    }

    return (
        <section className="run-app-viewer" aria-label={opened.title}>
            <header className="run-app-viewer-head">
                <strong title={opened.title}>{opened.title}</strong>
                <div className="run-app-viewer-tools">
                    <label className="list-search">
                        <Search size={14} aria-hidden="true" />
                        <input
                            type="search"
                            value={query}
                            onChange={(event) => {
                                setQuery(event.target.value)
                                setCurrent(0)
                            }}
                            onKeyDown={(event) => {
                                if (event.key === 'Enter') {
                                    event.preventDefault()
                                    move(event.shiftKey ? -1 : 1)
                                }
                            }}
                            placeholder="Highlight…"
                            aria-label="Highlight words in the file"
                        />
                        {query && (
                            <button type="button" aria-label="Clear" onClick={() => setQuery('')}>
                                <X size={13} />
                            </button>
                        )}
                    </label>
                    {pattern && (
                        <small aria-live="polite">{matches.length ? `${position + 1} / ${matches.length}` : 'No matches'}</small>
                    )}
                    <button type="button" className="entropy-button entropy-button-ghost entropy-button-icon entropy-button-sm" aria-label="Previous match" disabled={!matches.length} onClick={() => move(-1)}>
                        <ChevronUp size={14} />
                    </button>
                    <button type="button" className="entropy-button entropy-button-ghost entropy-button-icon entropy-button-sm" aria-label="Next match" disabled={!matches.length} onClick={() => move(1)}>
                        <ChevronDown size={14} />
                    </button>
                    <button
                        type="button"
                        className={`entropy-button entropy-button-ghost entropy-button-icon entropy-button-sm${colours ? ' is-active' : ''}`}
                        aria-pressed={colours}
                        aria-label="Colour log words"
                        title="Colour log words: errors red, warnings yellow, OK green"
                        onClick={() => {
                            localStorage.setItem(COLOURS_KEY, colours ? 'off' : 'on')
                            setColours(!colours)
                        }}
                    >
                        <Palette size={14} />
                    </button>
                    <button type="button" className="entropy-button entropy-button-secondary entropy-button-sm" onClick={download} disabled={!text} title="Download what is shown">
                        <Download size={14} /> Download
                    </button>
                    {buttons.map((input) => (
                        <button
                            key={input.name}
                            type="button"
                            className="entropy-button entropy-button-secondary entropy-button-sm"
                            disabled={!live || busy !== null}
                            title={input.description}
                            onClick={() => onRun(input)}
                        >
                            {busy === input.name && <LoaderCircle size={14} className="entropy-spin" />}
                            {input.label}
                        </button>
                    ))}
                </div>
            </header>
            {opened.notice && <p className="run-app-viewer-notice">{opened.notice}</p>}
            <div ref={body} className="run-app-viewer-body" role="document" aria-readonly="true">
                {lines.length === 0 ? (
                    <p className="run-app-muted">Nothing to show.</p>
                ) : (
                    lines.map((line, index) => (
                        <div key={index} className="run-app-viewer-line">
                            <span aria-hidden="true">{index + 1}</span>
                            <code>{highlight(line, index)}</code>
                        </div>
                    ))
                )}
            </div>
        </section>
    )
}
