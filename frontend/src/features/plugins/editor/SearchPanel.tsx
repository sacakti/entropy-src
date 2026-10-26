import { useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { CaseSensitive, ChevronDown, ChevronRight, Regex, Replace, ReplaceAll, WholeWord } from 'lucide-react'

import { MAX_MATCHES, findMatches, replaceIn, searchPattern, type FileMap, type SearchMatch } from './search'

/**
 * Find (and replace) across every file of the plugin, unsaved edits
 * included.
 */
export default function SearchPanel({
    files,
    readOnly,
    focusReplace,
    onOpen,
    onReplace,
}: {
    files: FileMap
    readOnly: boolean
    /** Bumped to focus the replace field (Ctrl+Shift+H). */
    focusReplace: number
    onOpen: (match: SearchMatch) => void
    onReplace: (changes: FileMap) => void
}) {
    const [query, setQuery] = useState('')
    const [replacement, setReplacement] = useState('')
    const [caseSensitive, setCaseSensitive] = useState(false)
    const [wholeWord, setWholeWord] = useState(false)
    const [regex, setRegex] = useState(false)
    const [showReplace, setShowReplace] = useState(focusReplace > 0)
    const [collapsed, setCollapsed] = useState<Record<string, boolean>>({})
    const queryRef = useRef<HTMLInputElement>(null)
    const replaceRef = useRef<HTMLInputElement>(null)

    // Ctrl+Shift+H opens the replace field (adjusted while rendering, not in an effect).
    const [seenFocus, setSeenFocus] = useState(focusReplace)
    if (seenFocus !== focusReplace) {
        setSeenFocus(focusReplace)
        if (focusReplace > 0) setShowReplace(true)
    }

    useEffect(() => {
        if (focusReplace > 0) window.setTimeout(() => replaceRef.current?.focus(), 0)
        else queryRef.current?.focus()
    }, [focusReplace])

    const options = { query, caseSensitive, wholeWord, regex }
    const { pattern, error } = searchPattern(options)
    const source = pattern?.source
    const flags = pattern?.flags
    const matches = useMemo(
        () => (source !== undefined && flags !== undefined ? findMatches(files, new RegExp(source, flags)) : []),
        [files, source, flags],
    )
    const byFile = useMemo(() => {
        const groups = new Map<string, SearchMatch[]>()
        for (const match of matches) groups.set(match.path, [...(groups.get(match.path) ?? []), match])
        return [...groups.entries()]
    }, [matches])

    const replaceFiles = (paths: string[], only?: SearchMatch) => {
        if (!pattern) return
        const changes: FileMap = {}
        for (const path of paths) {
            const next = replaceIn(files[path], new RegExp(pattern.source, pattern.flags), replacement, regex, only)
            if (next !== files[path]) changes[path] = next
        }
        if (Object.keys(changes).length) onReplace(changes)
    }

    const toggle = (active: boolean, set: (value: boolean) => void, label: string, icon: ReactNode) => (
        <button
            type="button"
            className={`plugin-ide-search-toggle${active ? ' is-active' : ''}`}
            aria-pressed={active}
            title={label}
            aria-label={label}
            onClick={() => set(!active)}
        >
            {icon}
        </button>
    )

    return (
        <div className="plugin-ide-search">
            <div className="plugin-ide-search-fields">
                {!readOnly && (
                    <button
                        type="button"
                        className="plugin-ide-search-expand"
                        aria-label={showReplace ? 'Hide replace' : 'Show replace'}
                        aria-expanded={showReplace}
                        onClick={() => setShowReplace((value) => !value)}
                    >
                        {showReplace ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
                    </button>
                )}
                <div className="plugin-ide-search-inputs">
                    <div className="plugin-ide-search-input">
                        <input
                            ref={queryRef}
                            value={query}
                            onChange={(event) => setQuery(event.target.value)}
                            placeholder="Search"
                            aria-label="Search in all files"
                            spellCheck={false}
                        />
                        {toggle(caseSensitive, setCaseSensitive, 'Match case', <CaseSensitive size={14} />)}
                        {toggle(wholeWord, setWholeWord, 'Match whole word', <WholeWord size={14} />)}
                        {toggle(regex, setRegex, 'Use regular expression', <Regex size={14} />)}
                    </div>
                    {showReplace && !readOnly && (
                        <div className="plugin-ide-search-input">
                            <input
                                ref={replaceRef}
                                value={replacement}
                                onChange={(event) => setReplacement(event.target.value)}
                                placeholder={regex ? 'Replace ($1 for groups)' : 'Replace'}
                                aria-label="Replace with"
                                spellCheck={false}
                            />
                            <button
                                type="button"
                                className="plugin-ide-search-toggle"
                                title="Replace all"
                                aria-label="Replace all"
                                disabled={!matches.length}
                                onClick={() => replaceFiles(byFile.map(([path]) => path))}
                            >
                                <ReplaceAll size={14} />
                            </button>
                        </div>
                    )}
                </div>
            </div>

            <p className={`plugin-ide-search-summary${error ? ' plugin-ide-error' : ''}`} role="status">
                {error
                    ? error
                    : !query
                      ? 'Searches every file, unsaved edits included.'
                      : matches.length === 0
                        ? 'No results.'
                        : `${matches.length >= MAX_MATCHES ? `${MAX_MATCHES}+` : matches.length} result${
                              matches.length === 1 ? '' : 's'
                          } in ${byFile.length} file${byFile.length === 1 ? '' : 's'}`}
            </p>

            <ul className="plugin-ide-search-results">
                {byFile.map(([path, items]) => (
                    <li key={path}>
                        <div className="plugin-ide-search-file">
                            <button
                                type="button"
                                onClick={() => setCollapsed((current) => ({ ...current, [path]: !current[path] }))}
                                aria-expanded={!collapsed[path]}
                            >
                                {collapsed[path] ? <ChevronRight size={13} /> : <ChevronDown size={13} />}
                                <span className="plugin-ide-tree-label">{path}</span>
                                <span className="plugin-ide-badge">{items.length}</span>
                            </button>
                            {showReplace && !readOnly && (
                                <button
                                    type="button"
                                    className="plugin-ide-search-toggle"
                                    title={`Replace all in ${path}`}
                                    aria-label={`Replace all in ${path}`}
                                    onClick={() => replaceFiles([path])}
                                >
                                    <ReplaceAll size={13} />
                                </button>
                            )}
                        </div>
                        {!collapsed[path] && (
                            <ul>
                                {items.map((match) => (
                                    <li key={`${match.line}:${match.column}`} className="plugin-ide-search-match">
                                        <button type="button" onClick={() => onOpen(match)} title={`Line ${match.line}`}>
                                            <span className="plugin-ide-search-line">{match.line}</span>
                                            <span className="plugin-ide-search-preview">
                                                {match.preview.slice(0, match.offset)}
                                                <mark>{match.preview.slice(match.offset, match.offset + match.length)}</mark>
                                                {match.preview.slice(match.offset + match.length)}
                                            </span>
                                        </button>
                                        {showReplace && !readOnly && (
                                            <button
                                                type="button"
                                                className="plugin-ide-search-toggle"
                                                title="Replace"
                                                aria-label={`Replace on line ${match.line}`}
                                                onClick={() => replaceFiles([path], match)}
                                            >
                                                <Replace size={13} />
                                            </button>
                                        )}
                                    </li>
                                ))}
                            </ul>
                        )}
                    </li>
                ))}
            </ul>
        </div>
    )
}
