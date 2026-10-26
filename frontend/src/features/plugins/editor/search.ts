export type FileMap = Record<string, string>

export interface SearchMatch {
    path: string
    line: number
    /** 1-based columns, end exclusive, as Monaco counts them. */
    column: number
    endColumn: number
    preview: string
    /** Where the match starts in the preview. */
    offset: number
    length: number
}

interface Options {
    query: string
    caseSensitive: boolean
    wholeWord: boolean
    regex: boolean
}

export const MAX_MATCHES = 2000

function escapeRegExp(text: string): string {
    return text.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
}

/** The search as a global regular expression, or an error for a bad pattern. */
export function searchPattern(options: Options): { pattern: RegExp | null; error: string | null } {
    if (!options.query) return { pattern: null, error: null }
    let source = options.regex ? options.query : escapeRegExp(options.query)
    if (options.wholeWord) source = `\\b(?:${source})\\b`
    try {
        return { pattern: new RegExp(source, options.caseSensitive ? 'g' : 'gi'), error: null }
    } catch (cause) {
        return { pattern: null, error: cause instanceof Error ? cause.message : 'Invalid expression' }
    }
}

export function findMatches(files: FileMap, pattern: RegExp): SearchMatch[] {
    const matches: SearchMatch[] = []
    for (const path of Object.keys(files).sort()) {
        const lines = files[path].split(/\r\n|\r|\n/)
        for (let index = 0; index < lines.length && matches.length < MAX_MATCHES; index += 1) {
            const text = lines[index]
            pattern.lastIndex = 0
            let found: RegExpExecArray | null
            while ((found = pattern.exec(text)) !== null) {
                if (found[0].length === 0) {
                    pattern.lastIndex += 1
                    continue
                }
                // Leading indentation is left out; long lines keep 40 characters before the match.
                const indent = Math.min(text.length - text.trimStart().length, found.index)
                const start = Math.max(indent, found.index - 40)
                matches.push({
                    path,
                    line: index + 1,
                    column: found.index + 1,
                    endColumn: found.index + found[0].length + 1,
                    preview: (start > indent ? '…' : '') + text.slice(start, start + 160),
                    offset: found.index - start + (start > indent ? 1 : 0),
                    length: found[0].length,
                })
                if (matches.length >= MAX_MATCHES) break
            }
        }
    }
    return matches
}

/** `content` with every match (or only the one at line/column) replaced. */
export function replaceIn(
    content: string,
    pattern: RegExp,
    replacement: string,
    regex: boolean,
    only?: { line: number; column: number },
): string {
    // Keep the file's own line endings: replace line by line.
    const parts = content.split(/(\r\n|\r|\n)/)
    const value = regex ? replacement : replacement.replace(/\$/g, '$$$$')
    for (let index = 0, line = 1; index < parts.length; index += 2, line += 1) {
        if (only && only.line !== line) continue
        if (!only) {
            parts[index] = parts[index].replace(pattern, value)
            continue
        }
        // The one match that starts at this column.
        const sticky = new RegExp(pattern.source, pattern.flags.replace('g', '') + 'y')
        sticky.lastIndex = only.column - 1
        const text = parts[index]
        if (sticky.exec(text)) {
            sticky.lastIndex = only.column - 1
            parts[index] = text.slice(0, only.column - 1) + text.slice(only.column - 1).replace(
                new RegExp(`^(?:${pattern.source})`, pattern.flags.replace('g', '')),
                value,
            )
        }
    }
    return parts.join('')
}
