import { useEffect, useRef, useState, type KeyboardEvent } from 'react'
import { createPortal } from 'react-dom'
import { Eraser, LoaderCircle, SquareTerminal, X } from 'lucide-react'

import { getShellInfo, runShellCommand, type ShellResource, type ShellResult } from '../../api/shell.api'
import { currentProject, PROJECT_CHANGED_EVENT, setCurrentProject } from '../../services/project'
import { openRun } from '../runs/navigation'
import '../../styles/web-shell.css'

const HISTORY_KEY = 'entropy.shell.history'
const HISTORY_LIMIT = 100
// The shell's `config set output` preference (the ent client keeps it in its config file).
const OUTPUT_KEY = 'entropy.shell.output'

function loadOutput(): string | null {
    try {
        return window.localStorage.getItem(OUTPUT_KEY)
    } catch {
        return null
    }
}

function saveOutput(mode: string | null): void {
    try {
        if (mode) window.localStorage.setItem(OUTPUT_KEY, mode)
        else window.localStorage.removeItem(OUTPUT_KEY)
    } catch {
        // Storage may be refused (private windows); the choice lasts this visit.
    }
}

/** Apply what a command changed: the page's project and the output preference. */
function applyEffects(result: ShellResult, outputRef: { current: string | null }): void {
    const effects = result.effects
    if (!effects) return
    if ('project' in effects) setCurrentProject(effects.project ?? null)
    if ('output' in effects) {
        outputRef.current = effects.output ?? null
        saveOutput(outputRef.current)
    }
}

/** The resource a first word names (its name or an alias), from the command contract. */
function findResource(resources: Record<string, ShellResource>, word: string): ShellResource | undefined {
    return Object.entries(resources).find(([name, item]) => name === word || item.aliases.includes(word))?.[1]
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
    const [resources, setResources] = useState<Record<string, ShellResource>>({})
    const [project, setProject] = useState<string | null>(currentProject())
    const [hint, setHint] = useState<string | null>(null)
    const outputModeRef = useRef<string | null>(loadOutput())
    const historyRef = useRef<string[]>(loadHistory())
    const cursorRef = useRef<number | null>(null)
    const nextId = useRef(1)
    const outputRef = useRef<HTMLDivElement>(null)
    const inputRef = useRef<HTMLInputElement>(null)

    useEffect(() => {
        getShellInfo()
            .then((info) => {
                setVocabulary(info.vocabulary)
                setResources(info.resources ?? {})
            })
            .catch(() => setVocabulary([]))
        inputRef.current?.focus()
    }, [])

    // The prompt shows the project commands work in, like oc shows its project.
    useEffect(() => {
        const update = () => setProject(currentProject())
        window.addEventListener(PROJECT_CHANGED_EVENT, update)
        return () => window.removeEventListener(PROJECT_CHANGED_EVENT, update)
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

        if (command === 'exit' || command === 'quit') {
            onClose()
            return
        }

        const id = nextId.current++
        setEntries((current) => [...current, { id, command, stdout: '', stderr: '', exitCode: null }])
        setBusy(true)
        try {
            const result = await runShellCommand(command, outputModeRef.current)
            applyEffects(result, outputModeRef)
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
            const verbs = Object.keys(findResource(resources, words[0])?.verbs ?? {})
            const matches = verbs.filter((action) => action.startsWith(words[1]))
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

    const prompt = project ? `${username}@entropy:${project} $` : `${username}@entropy $`

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
                        title="Close (Esc or exit)"
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
                        <code>project set &lt;key&gt;</code>, <code>job list -o table</code>. The same commands
                        work in <code>ent</code> on your computer or the server.
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
