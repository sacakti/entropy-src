import { useEffect, useRef, useState, type KeyboardEvent } from 'react'
import { createPortal } from 'react-dom'
import { Eraser, LoaderCircle, SquareTerminal, X } from 'lucide-react'

import { getShellInfo, runShellCommand } from '../../api/shell.api'
import { openRun } from '../runs/navigation'
import '../../styles/web-shell.css'

const HISTORY_KEY = 'entropy.shell.history'
const HISTORY_LIMIT = 100

// Actions offered after a command's first word.
const ACTIONS: Record<string, string[]> = {
    workflow: ['list', 'get', 'run', 'history', 'restore', 'delete'],
    job: ['list', 'get', 'logs', 'stop'],
    plugin: ['list', 'run'],
    node: ['list'],
    schedule: ['list'],
    user: ['list'],
    group: ['list'],
    role: ['list'],
    vault: ['namespaces', 'list'],
    notification: ['list'],
}
const ALIASES: Record<string, string> = {
    wf: 'workflow',
    workflows: 'workflow',
    jobs: 'job',
    run: 'job',
    runs: 'job',
    plugins: 'plugin',
    pl: 'plugin',
    nodes: 'node',
    schedules: 'schedule',
    users: 'user',
    groups: 'group',
    roles: 'role',
    notifications: 'notification',
}

interface Entry {
    id: number
    command: string
    stdout: string
    stderr: string
    exitCode: number | null
}

function loadHistory(): string[] {
    try {
        const value = JSON.parse(window.localStorage.getItem(HISTORY_KEY) ?? '[]')
        return Array.isArray(value) ? value.filter((item) => typeof item === 'string') : []
    } catch {
        return []
    }
}

function saveHistory(history: string[]): void {
    try {
        window.localStorage.setItem(HISTORY_KEY, JSON.stringify(history.slice(-HISTORY_LIMIT)))
    } catch {
        // Private windows may refuse storage; history then lasts for the session.
    }
}

/** Longest common start of several words. */
function commonPrefix(words: string[]): string {
    if (words.length === 0) return ''
    let prefix = words[0]
    for (const word of words.slice(1)) {
        while (!word.startsWith(prefix)) prefix = prefix.slice(0, -1)
    }
    return prefix
}

function runIds(text: string): number[] {
    return Array.from(new Set(Array.from(text.matchAll(/Run #(\d+)/g), (match) => Number(match[1]))))
}

/**
 * A terminal docked at the bottom of the window. Commands are `ent`
 * commands without the `ent`; they run on the server as the signed-in user.
 */
export default function ShellPanel({ username, onClose }: { username: string; onClose: () => void }) {
    const [entries, setEntries] = useState<Entry[]>([])
    const [input, setInput] = useState('')
    const [busy, setBusy] = useState(false)
    const [vocabulary, setVocabulary] = useState<string[]>([])
    const [hint, setHint] = useState<string | null>(null)
    const historyRef = useRef<string[]>(loadHistory())
    const cursorRef = useRef<number | null>(null)
    const nextId = useRef(1)
    const outputRef = useRef<HTMLDivElement>(null)
    const inputRef = useRef<HTMLInputElement>(null)

    useEffect(() => {
        getShellInfo()
            .then((info) => setVocabulary(info.vocabulary))
            .catch(() => setVocabulary([]))
        inputRef.current?.focus()
    }, [])

    useEffect(() => {
        outputRef.current?.scrollTo({ top: outputRef.current.scrollHeight })
    }, [entries, busy])

    // Ready for the next command as soon as one finishes.
    useEffect(() => {
        if (!busy) inputRef.current?.focus()
    }, [busy])

    const execute = async (raw: string) => {
        const command = raw.trim()
        if (!command) return
        const history = historyRef.current
        if (history[history.length - 1] !== command) {
            history.push(command)
            saveHistory(history)
        }
        cursorRef.current = null
        setInput('')
        setHint(null)

        if (command === 'clear' || command === 'cls') {
            setEntries([])
            return
        }

        const id = nextId.current++
        setEntries((current) => [...current, { id, command, stdout: '', stderr: '', exitCode: null }])
        setBusy(true)
        try {
            const result = await runShellCommand(command)
            setEntries((current) =>
                current.map((entry) =>
                    entry.id === id
                        ? { ...entry, stdout: result.stdout, stderr: result.stderr, exitCode: result.exit_code }
                        : entry,
                ),
            )
        } catch (error) {
            setEntries((current) =>
                current.map((entry) =>
                    entry.id === id
                        ? {
                              ...entry,
                              stderr: error instanceof Error ? error.message : 'The command could not run.',
                              exitCode: 1,
                          }
                        : entry,
                ),
            )
        } finally {
            setBusy(false)
        }
    }

    const complete = () => {
        const words = input.split(/\s+/)
        if (words.length === 1) {
            const matches = vocabulary.filter((word) => word.startsWith(words[0]))
            if (matches.length === 1) setInput(`${matches[0]} `)
            else if (matches.length > 1) {
                const prefix = commonPrefix(matches)
                if (prefix.length > words[0].length) setInput(prefix)
                setHint(matches.join('  '))
            }
            return
        }
        if (words.length === 2) {
            const group = ALIASES[words[0]] ?? words[0]
            const matches = (ACTIONS[group] ?? []).filter((action) => action.startsWith(words[1]))
            if (matches.length === 1) setInput(`${words[0]} ${matches[0]} `)
            else if (matches.length > 1) setHint(matches.join('  '))
        }
    }

    const onKeyDown = (event: KeyboardEvent<HTMLInputElement>) => {
        const history = historyRef.current
        if (event.key === 'Enter') {
            event.preventDefault()
            if (!busy) void execute(input)
        } else if (event.key === 'Tab') {
            event.preventDefault()
            complete()
        } else if (event.key === 'ArrowUp') {
            event.preventDefault()
            if (history.length === 0) return
            const cursor = cursorRef.current === null ? history.length - 1 : Math.max(0, cursorRef.current - 1)
            cursorRef.current = cursor
            setInput(history[cursor])
        } else if (event.key === 'ArrowDown') {
            event.preventDefault()
            if (cursorRef.current === null) return
            const cursor = cursorRef.current + 1
            if (cursor >= history.length) {
                cursorRef.current = null
                setInput('')
            } else {
                cursorRef.current = cursor
                setInput(history[cursor])
            }
        } else if (event.key === 'l' && (event.ctrlKey || event.metaKey)) {
            event.preventDefault()
            setEntries([])
        } else if (event.key === 'Escape') {
            event.preventDefault()
            onClose()
        } else {
            setHint(null)
        }
    }

    const prompt = `${username}@entropy $`

    return createPortal(
        <section className="entropy-shell" role="dialog" aria-label="Shell">
            <header className="entropy-shell-header">
                <span className="entropy-shell-title">
                    <SquareTerminal size={16} aria-hidden="true" />
                    Shell
                    <small>ent commands without “ent”, as {username} · Tab completes · ↑↓ history</small>
                </span>
                <span className="entropy-shell-actions">
                    <button
                        type="button"
                        className="entropy-shell-icon"
                        onClick={() => setEntries([])}
                        title="Clear (Ctrl+L)"
                        aria-label="Clear"
                    >
                        <Eraser size={15} />
                    </button>
                    <button
                        type="button"
                        className="entropy-shell-icon"
                        onClick={onClose}
                        title="Close (Esc)"
                        aria-label="Close shell"
                    >
                        <X size={16} />
                    </button>
                </span>
            </header>

            <div className="entropy-shell-output" ref={outputRef} onClick={() => inputRef.current?.focus()}>
                {entries.length === 0 && (
                    <p className="entropy-shell-welcome">
                        Type <code>help</code> for the commands, e.g. <code>workflow list</code>,{' '}
                        <code>job list --state failed</code>, <code>users list</code>.
                    </p>
                )}
                {entries.map((entry) => {
                    const ids = runIds(`${entry.stdout}\n${entry.stderr}`)
                    return (
                        <div key={entry.id} className="entropy-shell-entry">
                            <div className="entropy-shell-line">
                                <span className="entropy-shell-prompt">{prompt}</span> {entry.command}
                            </div>
                            {entry.exitCode === null ? (
                                <div className="entropy-shell-running">
                                    <LoaderCircle size={13} className="entropy-spin" /> running…
                                </div>
                            ) : (
                                <>
                                    {entry.stdout && <pre className="entropy-shell-stdout">{entry.stdout}</pre>}
                                    {entry.stderr && (
                                        <pre
                                            className={
                                                entry.exitCode === 0 ? 'entropy-shell-note' : 'entropy-shell-stderr'
                                            }
                                        >
                                            {entry.stderr}
                                        </pre>
                                    )}
                                    {ids.length > 0 && ids.length <= 3 && (
                                        <div className="entropy-shell-links">
                                            {ids.map((runId) => (
                                                <button key={runId} type="button" onClick={() => openRun(runId)}>
                                                    Open run #{runId}
                                                </button>
                                            ))}
                                        </div>
                                    )}
                                </>
                            )}
                        </div>
                    )
                })}
            </div>

            {hint && <div className="entropy-shell-hint">{hint}</div>}

            <label className="entropy-shell-input">
                <span className="entropy-shell-prompt">{prompt}</span>
                <input
                    ref={inputRef}
                    value={input}
                    onChange={(event) => setInput(event.target.value)}
                    onKeyDown={onKeyDown}
                    // Read-only, not disabled, while a command runs: a disabled
                    // field loses keyboard focus.
                    readOnly={busy}
                    aria-busy={busy}
                    spellCheck={false}
                    autoComplete="off"
                    autoCapitalize="off"
                    aria-label="Command"
                    placeholder={busy ? '' : 'workflow list'}
                />
            </label>
        </section>,
        document.querySelector('.entropy-app') ?? document.body,
    )
}
