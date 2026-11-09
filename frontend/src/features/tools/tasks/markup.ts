/**
 * What a task description can hold, read from its plain text (Markdown's common forms):
 * headings (# to #####), paragraphs, lists, checklists, tables, code blocks and attachments in
 * place, with bold, italic, underline (++text++, Markdown has none), strikethrough and `code`
 * inside. lib/tasks/markup.py reads it the same way for
 * the reports: change both together. Text only ever becomes React text, never HTML.
 */

export interface Run {
    text: string
    bold?: boolean
    italic?: boolean
    strike?: boolean
    underline?: boolean
    code?: boolean
}

export type HeadingLevel = 1 | 2 | 3 | 4 | 5

export interface ListItem {
    text: string
    /** Checklists: whether it is ticked; null for a plain item. */
    checked: boolean | null
    indent: number
    /** The item's line in the text, to tick it from the view. */
    line: number
}

export type Block =
    | { type: 'heading'; level: HeadingLevel; text: string }
    | { type: 'paragraph'; text: string }
    | { type: 'list'; ordered: boolean; start: number; items: ListItem[] }
    | { type: 'table'; header: string[]; rows: string[][] }
    | { type: 'code'; text: string }
    | { type: 'attachment'; id: number; caption: string }

const FENCE = /^\s*```/
const HEADING = /^(#{1,5})\s+(.+?)\s*$/
const LIST_ITEM = /^(\s*)([-*+]|\d+\.)\s+(?:\[([ xX])\](?:\s+|$))?(.*)$/
const TABLE_RULE = /^\s*\|?\s*:?-+:?\s*(?:\|\s*:?-+:?\s*)*\|?\s*$/
const ATTACHMENT = /!\[([^\]\n]*)\]\(attachment:(\d+)\)/g
const INLINE =
    /\\([\\*~`|+#.-])|`([^`\n]+)`|\*\*\*(?=\S)(.+?)(?<=\S)\*\*\*|\*\*(?=\S)(.+?)(?<=\S)\*\*|~~(?=\S)(.+?)(?<=\S)~~|\+\+(?=\S)(.+?)(?<=\S)\+\+|\*(?=[^\s*])(.+?)(?<=[^\s*])\*/g

export function tableCells(line: string): string[] {
    const inner = line.trim().replace(/^\|/, '').replace(/(?<!\\)\|$/, '')
    return inner.split(/(?<!\\)\|/).map((cell) => cell.trim().replaceAll('\\|', '|'))
}

function isTableStart(line: string, next: string | undefined): boolean {
    return line.includes('|') && next !== undefined && next.includes('|') && next.includes('-') && TABLE_RULE.test(next)
}

export function parseBlocks(source: string): Block[] {
    const lines = source.replaceAll('\r\n', '\n').split('\n')
    const blocks: Block[] = []
    let paragraph: string[] = []
    const flush = () => {
        const text = paragraph.join('\n').trim()
        if (text) blocks.push({ type: 'paragraph', text })
        paragraph = []
    }

    let index = 0
    while (index < lines.length) {
        const line = lines[index]

        if (FENCE.test(line)) {
            flush()
            const code: string[] = []
            index += 1
            while (index < lines.length && !FENCE.test(lines[index])) {
                code.push(lines[index])
                index += 1
            }
            blocks.push({ type: 'code', text: code.join('\n') })
            index += 1
            continue
        }

        if (!line.trim()) {
            flush()
            index += 1
            continue
        }

        const references = [...line.matchAll(ATTACHMENT)]
        if (references.length) {
            flush()
            let position = 0
            for (const match of references) {
                const start = match.index ?? 0
                const before = line.slice(position, start).trim()
                if (before) blocks.push({ type: 'paragraph', text: before })
                blocks.push({ type: 'attachment', id: Number(match[2]), caption: match[1] })
                position = start + match[0].length
            }
            const after = line.slice(position).trim()
            if (after) blocks.push({ type: 'paragraph', text: after })
            index += 1
            continue
        }

        const heading = HEADING.exec(line)
        if (heading) {
            flush()
            blocks.push({ type: 'heading', level: heading[1].length as HeadingLevel, text: heading[2] })
            index += 1
            continue
        }

        if (isTableStart(line, lines[index + 1])) {
            flush()
            const header = tableCells(line)
            const rows: string[][] = []
            index += 2
            while (index < lines.length && lines[index].trim() && lines[index].includes('|')) {
                const cells = tableCells(lines[index])
                rows.push(header.map((_, column) => cells[column] ?? ''))
                index += 1
            }
            blocks.push({ type: 'table', header, rows })
            continue
        }

        const item = LIST_ITEM.exec(line)
        if (item) {
            flush()
            const ordered = item[2].endsWith('.')
            const items: ListItem[] = []
            const start = ordered ? Number.parseInt(item[2], 10) : 1
            while (index < lines.length) {
                const current = LIST_ITEM.exec(lines[index])
                if (!current || current[2].endsWith('.') !== ordered) break
                items.push({
                    text: current[4].trim(),
                    checked: current[3] === undefined ? null : current[3] !== ' ',
                    indent: Math.floor(current[1].replaceAll('\t', '  ').length / 2),
                    line: index,
                })
                index += 1
            }
            blocks.push({ type: 'list', ordered, start, items })
            continue
        }

        paragraph.push(line)
        index += 1
    }
    flush()
    return blocks
}

export function parseInline(text: string, style: Omit<Run, 'text'> = {}): Run[] {
    const runs: Run[] = []
    let position = 0
    for (const match of text.matchAll(INLINE)) {
        const start = match.index ?? 0
        if (start > position) runs.push({ ...style, text: text.slice(position, start) })
        const [, escaped, code, both, bold, strike, underline, italic] = match
        if (escaped !== undefined) runs.push({ ...style, text: escaped })
        else if (code !== undefined) runs.push({ ...style, text: code, code: true })
        else if (both !== undefined) runs.push(...parseInline(both, { ...style, bold: true, italic: true }))
        else if (bold !== undefined) runs.push(...parseInline(bold, { ...style, bold: true }))
        else if (strike !== undefined) runs.push(...parseInline(strike, { ...style, strike: true }))
        else if (underline !== undefined) runs.push(...parseInline(underline, { ...style, underline: true }))
        else if (italic !== undefined) runs.push(...parseInline(italic, { ...style, italic: true }))
        position = start + match[0].length
    }
    if (position < text.length) runs.push({ ...style, text: text.slice(position) })
    return runs
}

const inlineText = (text: string) => parseInline(text).map((run) => run.text).join('')

/** The description without its formatting, for previews on task cards. */
export function plainText(source: string): string {
    const parts: string[] = []
    for (const block of parseBlocks(source)) {
        if (block.type === 'heading' || block.type === 'paragraph') parts.push(inlineText(block.text))
        else if (block.type === 'code') parts.push(block.text)
        else if (block.type === 'list') {
            for (const item of block.items) {
                const mark = item.checked === null ? '' : item.checked ? '[x] ' : '[ ] '
                parts.push(`${mark}${inlineText(item.text)}`)
            }
        } else if (block.type === 'table') {
            for (const row of [block.header, ...block.rows]) parts.push(row.map(inlineText).join(' | '))
        }
    }
    return parts.join('\n')
}
