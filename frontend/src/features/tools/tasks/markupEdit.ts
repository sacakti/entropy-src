/** Changes to a description's text for the editor's toolbar and keys; each returns the result. */

import { tableCells } from './markup'

export interface Edit {
    text: string
    /** The selection afterwards. */
    start: number
    end: number
}

export type LineStyle = 'paragraph' | 'h1' | 'h2' | 'h3' | 'bullet' | 'number' | 'check'

const PREFIX = /^(\s*)(#{1,3}\s+|(?:[-*+]|\d+\.)\s+(?:\[[ xX]\](?:\s+|$))?)/
const LIST = /^(\s*)([-*+]|\d+\.)(\s+)(\[[ xX]\](?:\s+|$))?(.*)$/
const RULE = /^\s*\|?\s*:?-+:?\s*(?:\|\s*:?-+:?\s*)*\|?\s*$/

function lineStart(text: string, position: number): number {
    return text.lastIndexOf('\n', position - 1) + 1
}

function lineEnd(text: string, position: number): number {
    const end = text.indexOf('\n', position)
    return end === -1 ? text.length : end
}

/** Bold, italic, strikethrough or code around the selection; again takes it away. */
export function toggleInline(text: string, start: number, end: number, marker: string): Edit {
    const size = marker.length
    const selected = text.slice(start, end)

    if (selected.length >= 2 * size && selected.startsWith(marker) && selected.endsWith(marker)) {
        const inner = selected.slice(size, -size)
        return { text: text.slice(0, start) + inner + text.slice(end), start, end: start + inner.length }
    }
    if (text.slice(start - size, start) === marker && text.slice(end, end + size) === marker) {
        // `*` also closes `**`: only take a marker that is really this one.
        const lone = marker !== '*' || (text[start - 2] !== '*' && text[end + 1] !== '*')
        if (lone) {
            return {
                text: text.slice(0, start - size) + selected + text.slice(end + size),
                start: start - size,
                end: end - size,
            }
        }
    }
    if (!selected) {
        return { text: text.slice(0, start) + marker + marker + text.slice(end), start: start + size, end: start + size }
    }
    // Markers cannot span lines, and sit tight against the words.
    const wrapped = selected
        .split('\n')
        .map((line) => {
            const body = line.trim()
            return body ? line.replace(body, `${marker}${body}${marker}`) : line
        })
        .join('\n')
    return { text: text.slice(0, start) + wrapped + text.slice(end), start, end: start + wrapped.length }
}

export function lineStyleAt(text: string, position: number): LineStyle {
    const line = text.slice(lineStart(text, position), lineEnd(text, position))
    const heading = /^(#{1,3})\s/.exec(line)
    if (heading) return `h${heading[1].length}` as LineStyle
    const item = LIST.exec(line)
    if (!item) return 'paragraph'
    if (item[4] !== undefined) return 'check'
    return item[2].endsWith('.') ? 'number' : 'bullet'
}

/** Makes the selected lines a heading, a list or plain text; the same list style again undoes it. */
export function setLineStyle(text: string, start: number, end: number, style: LineStyle): Edit {
    const from = lineStart(text, start)
    const to = lineEnd(text, end)
    const toggled = style !== 'paragraph' && lineStyleAt(text, start) === style ? 'paragraph' : style
    let number = 0
    const result = text
        .slice(from, to)
        .split('\n')
        .map((line) => {
            const match = PREFIX.exec(line)
            const indent = match?.[1] ?? ''
            const body = match ? line.slice(match[0].length) : line
            if (toggled === 'paragraph') return indent + body
            if (!line.trim() && from !== to) return line
            number += 1
            const prefix = { h1: '# ', h2: '## ', h3: '### ', bullet: '- ', number: `${number}. `, check: '- [ ] ' }[toggled]
            return (toggled.startsWith('h') ? '' : indent) + prefix + body
        })
        .join('\n')
    const position = from + result.length
    return { text: text.slice(0, from) + result + text.slice(to), start: position, end: position }
}

function separated(text: string, start: number, end: number, block: string): Edit {
    const before = text.slice(0, start)
    const after = text.slice(end)
    const lead = !before ? '' : before.endsWith('\n\n') ? '' : before.endsWith('\n') ? '\n' : '\n\n'
    const tail = !after ? '\n' : after.startsWith('\n\n') ? '' : after.startsWith('\n') ? '\n' : '\n\n'
    const at = before.length + lead.length
    return { text: before + lead + block + tail + after, start: at, end: at + block.length }
}

/** A new table where the cursor is, its first heading selected to type over. */
export function insertTable(text: string, start: number, end: number, rows: number, columns: number): Edit {
    const header = Array.from({ length: columns }, (_, index) => `Column ${index + 1}`)
    const row = (cells: string[]) => `| ${cells.join(' | ')} |`
    const block = [
        row(header),
        row(header.map(() => '---')),
        ...Array.from({ length: rows }, () => row(header.map(() => ' '))),
    ].join('\n')
    const edit = separated(text, start, end, block)
    const first = edit.start + 2
    return { text: edit.text, start: first, end: first + header[0].length }
}

interface TableSpot {
    /** Where its lines start in the text, and those lines. */
    from: number
    to: number
    lines: string[]
    /** The line and cell the position is in. */
    line: number
    cell: number
}

/** The table the position is in, if any. */
export function tableAt(text: string, position: number): TableSpot | null {
    const from = lineStart(text, position)
    const to = lineEnd(text, position)
    if (!text.slice(from, to).includes('|')) return null

    let top = from
    while (top > 0) {
        const above = lineStart(text, top - 1)
        const line = text.slice(above, top - 1)
        if (!line.trim() || !line.includes('|')) break
        top = above
    }
    let bottom = to
    while (bottom < text.length) {
        const next = lineEnd(text, bottom + 1)
        const line = text.slice(bottom + 1, next)
        if (!line.trim() || !line.includes('|')) break
        bottom = next
    }
    const lines = text.slice(top, bottom).split('\n')
    if (lines.length < 2 || !lines[1].includes('-') || !RULE.test(lines[1])) return null

    const line = text.slice(top, from).split('\n').length - 1
    const left = text.slice(from, position)
    const cell = Math.max(0, (left.trim().startsWith('|') ? -1 : 0) + (left.match(/(?<!\\)\|/g)?.length ?? 0))
    return { from: top, to: bottom, lines, line, cell }
}

/** Selects the contents of a cell on a line, given where that line starts. */
function cellRange(line: string, from: number, cell: number): [number, number] {
    let position = line.startsWith('|') ? 1 : 0
    for (let index = 0; index < cell; index += 1) {
        const next = line.slice(position).search(/(?<!\\)\|/)
        if (next === -1) break
        position += next + 1
    }
    const rest = line.slice(position)
    const stop = rest.search(/(?<!\\)\|/)
    const content = stop === -1 ? rest : rest.slice(0, stop)
    const lead = content.length - content.trimStart().length
    const body = content.trim()
    // An empty cell: the cursor one space in, ready to type.
    const at = from + position + (body ? lead : Math.min(1, content.length))
    return [at, at + body.length]
}

function rewrite(text: string, spot: TableSpot, lines: string[], line: number, cell: number): Edit {
    const start = spot.from + lines.slice(0, line).reduce((sum, item) => sum + item.length + 1, 0)
    const [from, to] = cellRange(lines[line], start, cell)
    return { text: text.slice(0, spot.from) + lines.join('\n') + text.slice(spot.to), start: from, end: to }
}

const tableRow = (count: number) => `|${'   |'.repeat(count)}`

/** Tab and Shift+Tab move between cells; past the last, a new row starts. */
export function moveCell(text: string, position: number, backwards: boolean): Edit | null {
    const spot = tableAt(text, position)
    if (!spot) return null
    const columns = tableCells(spot.lines[0]).length
    let { line, cell } = spot
    cell += backwards ? -1 : 1
    if (cell >= columns) {
        cell = 0
        line += 1
    } else if (cell < 0) {
        cell = columns - 1
        line -= 1
    }
    if (line === 1) line += backwards ? -1 : 1
    if (line < 0) return null
    const lines = [...spot.lines]
    if (line >= lines.length) lines.push(tableRow(columns))
    return rewrite(text, spot, lines, line, cell)
}

export function addTableRow(text: string, position: number): Edit | null {
    const spot = tableAt(text, position)
    if (!spot) return null
    const columns = tableCells(spot.lines[0]).length
    const at = Math.max(spot.line, 1) + 1
    const lines = [...spot.lines.slice(0, at), tableRow(columns), ...spot.lines.slice(at)]
    return rewrite(text, spot, lines, at, 0)
}

export function addTableColumn(text: string, position: number): Edit | null {
    const spot = tableAt(text, position)
    if (!spot) return null
    const at = spot.cell + 1
    const lines = spot.lines.map((line, index) => {
        const cells = tableCells(line)
        cells.splice(at, 0, index === 0 ? `Column ${cells.length + 1}` : index === 1 ? '---' : '')
        return `| ${cells.join(' | ')} |`
    })
    return rewrite(text, spot, lines, spot.line, Math.min(at, tableCells(lines[0]).length - 1))
}

/** Removes the row at the cursor; the headings stay, as a table needs them. */
export function removeTableRow(text: string, position: number): Edit | null {
    const spot = tableAt(text, position)
    if (!spot || spot.line < 2) return null
    const lines = spot.lines.filter((_, index) => index !== spot.line)
    return rewrite(text, spot, lines, Math.min(spot.line, lines.length - 1), 0)
}

export function removeTableColumn(text: string, position: number): Edit | null {
    const spot = tableAt(text, position)
    if (!spot || tableCells(spot.lines[0]).length < 2) return null
    const lines = spot.lines.map((line) => {
        const cells = tableCells(line)
        cells.splice(spot.cell, 1)
        return `| ${cells.join(' | ')} |`
    })
    return rewrite(text, spot, lines, spot.line, Math.max(0, spot.cell - 1))
}

/** Enter: the next list item or table row. An empty item ends the list. */
export function continueBlock(text: string, position: number): Edit | null {
    const spot = tableAt(text, position)
    if (spot) {
        const columns = tableCells(spot.lines[0]).length
        const at = Math.max(spot.line, 1) + 1
        return rewrite(text, spot, [...spot.lines.slice(0, at), tableRow(columns), ...spot.lines.slice(at)], at, 0)
    }
    const from = lineStart(text, position)
    const to = lineEnd(text, position)
    const line = text.slice(from, to)
    const item = LIST.exec(line)
    if (!item) return null
    const [, indent, marker, space, check, body] = item
    if (!body.trim()) {
        return { text: text.slice(0, from) + text.slice(to), start: from, end: from }
    }
    const nextMarker = marker.endsWith('.') ? `${Number.parseInt(marker, 10) + 1}.` : marker
    const prefix = `\n${indent}${nextMarker}${space}${check !== undefined ? '[ ] ' : ''}`
    const caret = position + prefix.length
    return { text: text.slice(0, position) + prefix + text.slice(position), start: caret, end: caret }
}

/** Tab and Shift+Tab nest list items. */
export function indentList(text: string, start: number, end: number, outdent: boolean): Edit | null {
    const from = lineStart(text, start)
    const to = lineEnd(text, end)
    const lines = text.slice(from, to).split('\n')
    if (!lines.every((line) => LIST.test(line) || !line.trim())) return null
    let first = 0
    let total = 0
    const changed = lines.map((line, index) => {
        if (!line.trim()) return line
        const next = outdent ? line.replace(/^ {1,2}/, '') : `  ${line}`
        if (index === 0) first = next.length - line.length
        total += next.length - line.length
        return next
    })
    return {
        text: text.slice(0, from) + changed.join('\n') + text.slice(to),
        start: Math.max(from, start + first),
        end: Math.max(from, end + total),
    }
}

/** Ticks or unticks the checklist item on a line. */
export function toggleCheckbox(text: string, line: number): string {
    const lines = text.split('\n')
    if (line < 0 || line >= lines.length) return text
    lines[line] = lines[line].replace(/^(\s*(?:[-*+]|\d+\.)\s+\[)([ xX])(\])/, (_, open: string, mark: string, close: string) =>
        `${open}${mark === ' ' ? 'x' : ' '}${close}`,
    )
    return lines.join('\n')
}
