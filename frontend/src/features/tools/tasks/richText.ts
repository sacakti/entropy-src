/**
 * The description editor works on formatted text, like Notes, yet descriptions are kept
 * in their plain-text form (markup.ts, read alike by lib/tasks/markup.py for the reports).
 * This turns one into the other:
 *
 * - `renderMarkup` fills the editor from the text. It builds elements and sets their
 *   text; nothing the user wrote is ever read as HTML.
 * - `serializeEditor` writes the editor (or pasted HTML) back as text, keeping only what
 *   the text can hold: headings 1-5, paragraphs, lists and checklists, tables, code
 *   blocks, attachments, and bold, italic, underline, strikethrough and code.
 */

import { parseBlocks, parseInline, type Block, type Run } from './markup'

export interface PlacedAttachment {
    /** An image to show, or null for a file shown by name. */
    src: string | null
    label: string
}

const LIST_INDENT = 2

// ----------------------------------------------------------------------
// Text -> editor
// ----------------------------------------------------------------------

function appendRuns(parent: HTMLElement, text: string): void {
    const runs = parseInline(text)
    for (const run of runs) {
        let node: Node = document.createTextNode(run.text)
        const wrap = (tag: string) => {
            const element = document.createElement(tag)
            element.appendChild(node)
            node = element
        }
        if (run.code) wrap('code')
        if (run.strike) wrap('s')
        if (run.underline) wrap('u')
        if (run.italic) wrap('em')
        if (run.bold) wrap('strong')
        parent.appendChild(node)
    }
}

/** Text whose lines were joined by newlines: each newline a line break. */
function appendLines(parent: HTMLElement, text: string): void {
    text.split('\n').forEach((line, index) => {
        if (index) parent.appendChild(document.createElement('br'))
        appendRuns(parent, line)
    })
    if (!text) parent.appendChild(document.createElement('br'))
}

export function attachmentElement(id: number, caption: string, placed: PlacedAttachment): HTMLElement {
    const figure = document.createElement('figure')
    figure.className = 'task-rich-attachment'
    figure.contentEditable = 'false'
    figure.dataset.attachment = String(id)
    figure.dataset.caption = caption
    if (placed.src) {
        const image = document.createElement('img')
        image.src = placed.src
        image.alt = placed.label
        figure.appendChild(image)
    }
    const label = document.createElement('figcaption')
    label.textContent = placed.label
    figure.appendChild(label)
    return figure
}

export function tableElement(header: string[], rows: string[][]): HTMLTableElement {
    const table = document.createElement('table')
    const add = (parent: HTMLElement, tag: string) => parent.appendChild(document.createElement(tag))
    const head = add(add(table, 'thead'), 'tr')
    for (const cell of header) appendLines(add(head, 'th'), cell)
    const body = add(table, 'tbody')
    for (const row of rows) {
        const line = add(body, 'tr')
        for (const cell of row) appendLines(add(line, 'td'), cell)
    }
    return table
}

function blockElement(block: Block, attachment: (id: number, caption: string) => PlacedAttachment): HTMLElement {
    switch (block.type) {
        case 'heading': {
            const element = document.createElement(`h${block.level}`)
            appendRuns(element, block.text)
            return element
        }
        case 'paragraph': {
            const element = document.createElement('p')
            appendLines(element, block.text)
            return element
        }
        case 'code': {
            const element = document.createElement('pre')
            element.textContent = block.text || '\n'
            return element
        }
        case 'attachment':
            return attachmentElement(block.id, block.caption, attachment(block.id, block.caption))
        case 'table':
            return tableElement(block.header, block.rows)
        case 'list': {
            const list = document.createElement(block.ordered ? 'ol' : 'ul')
            if (block.ordered && block.start !== 1) (list as HTMLOListElement).start = block.start
            const checklist = block.items.some((item) => item.checked !== null)
            if (checklist) list.dataset.checklist = 'true'
            for (const item of block.items) {
                const element = document.createElement('li')
                if (checklist) element.dataset.checked = item.checked ? 'true' : 'false'
                if (item.indent) element.dataset.indent = String(Math.min(item.indent, 6))
                appendRuns(element, item.text)
                if (!item.text) element.appendChild(document.createElement('br'))
                list.appendChild(element)
            }
            return list
        }
    }
}

/** Fill the editor from a description's text. */
export function renderMarkup(
    root: HTMLElement,
    source: string,
    attachment: (id: number, caption: string) => PlacedAttachment,
): void {
    root.replaceChildren()
    for (const block of parseBlocks(source)) root.appendChild(blockElement(block, attachment))
    if (!root.firstChild) root.appendChild(emptyParagraph())
}

export function emptyParagraph(): HTMLParagraphElement {
    const paragraph = document.createElement('p')
    paragraph.appendChild(document.createElement('br'))
    return paragraph
}

// ----------------------------------------------------------------------
// Editor -> text
// ----------------------------------------------------------------------

type Style = Omit<Run, 'text'>

/** An element, also from a document DOMParser made (where `instanceof` may not hold). */
function isElement(node: Node): node is HTMLElement {
    return node.nodeType === 1
}
const BLOCK_TAGS = new Set([
    'P', 'DIV', 'H1', 'H2', 'H3', 'H4', 'H5', 'H6', 'UL', 'OL', 'LI', 'TABLE', 'PRE',
    'FIGURE', 'BLOCKQUOTE', 'SECTION', 'ARTICLE', 'HEADER', 'FOOTER', 'HR',
])

function styleOf(element: HTMLElement, inherited: Style): Style {
    const style: Style = { ...inherited }
    const tag = element.tagName
    if (tag === 'B' || tag === 'STRONG') style.bold = true
    if (tag === 'I' || tag === 'EM') style.italic = true
    if (tag === 'U' || tag === 'INS') style.underline = true
    if (tag === 'S' || tag === 'STRIKE' || tag === 'DEL') style.strike = true
    if (tag === 'CODE' || tag === 'KBD' || tag === 'SAMP') style.code = true
    // Pasted text often carries its looks in style="" rather than tags.
    const css = element.style
    if (css) {
        const weight = css.fontWeight
        if (weight === 'bold' || weight === 'bolder' || Number(weight) >= 600) style.bold = true
        if (weight === 'normal' || (weight && Number(weight) < 600)) style.bold = false
        if (css.fontStyle === 'italic') style.italic = true
        const decoration = `${css.textDecoration} ${css.textDecorationLine}`
        if (decoration.includes('underline')) style.underline = true
        if (decoration.includes('line-through')) style.strike = true
    }
    return style
}

function sameStyle(left: Style, right: Style): boolean {
    return (
        Boolean(left.bold) === Boolean(right.bold) &&
        Boolean(left.italic) === Boolean(right.italic) &&
        Boolean(left.underline) === Boolean(right.underline) &&
        Boolean(left.strike) === Boolean(right.strike) &&
        Boolean(left.code) === Boolean(right.code)
    )
}

/** The runs of an inline part of the page; line breaks become "\n" runs. */
function collectRuns(node: Node, style: Style, runs: Run[]): void {
    if (node.nodeType === Node.TEXT_NODE) {
        // Whitespace from HTML source layout is not text the user typed.
        const text = (node.textContent ?? '').replace(/[\t\r\n]+/g, ' ').replace(/\u00a0/g, ' ')
        if (text) runs.push({ ...style, text })
        return
    }
    if (!isElement(node)) return
    if (node.tagName === 'BR') {
        runs.push({ text: '\n' })
        return
    }
    if (node.tagName === 'IMG' || node.tagName === 'SCRIPT' || node.tagName === 'STYLE') return
    const inner = styleOf(node, style)
    node.childNodes.forEach((child) => collectRuns(child, inner, runs))
}

/** Characters that would start formatting the text does not mean, escaped. */
function escapeInline(text: string, inTable: boolean): string {
    // Text the parser reads back unchanged needs no escapes (C++, a*b, 50% off...).
    const parsed = parseInline(text)
    const plain = parsed.length === 1 && Object.keys(parsed[0]).length === 1 && parsed[0].text === text
    let result = plain || !text ? text : text.replace(/[\\*~`+]/g, (char) => `\\${char}`)
    if (inTable) result = result.replace(/(?<!\\)\|/g, '\\|')
    return result
}

function mark(text: string, style: Style): string {
    if (!text.trim()) return text
    // Marks hug the text: spaces at either end stay outside them.
    const lead = text.match(/^\s*/)?.[0] ?? ''
    const tail = text.match(/\s*$/)?.[0] ?? ''
    let body = text.slice(lead.length, text.length - tail.length)
    if (style.code) body = `\`${body.replace(/`/g, "'")}\``
    if (style.strike) body = `~~${body}~~`
    if (style.underline) body = `++${body}++`
    if (style.italic) body = `*${body}*`
    if (style.bold) body = `**${body}**`
    return lead + body + tail
}

function writeRuns(runs: Run[], inTable = false): string {
    // Merge neighbours of one style, so "**ab**" is not written "**a****b**".
    const merged: Run[] = []
    for (const run of runs) {
        const last = merged[merged.length - 1]
        if (last && run.text !== '\n' && last.text !== '\n' && sameStyle(last, run)) last.text += run.text
        else merged.push({ ...run })
    }
    return merged
        .map((run) => {
            if (run.text === '\n') return '\n'
            const text = run.code ? run.text : escapeInline(run.text, inTable)
            return mark(text, run)
        })
        .join('')
}

function inlineText(element: Node, inTable = false): string {
    const runs: Run[] = []
    element.childNodes.forEach((child) => collectRuns(child, {}, runs))
    // A trailing line break is how editors keep an empty line open; it is not text.
    while (runs.length && runs[runs.length - 1].text === '\n') runs.pop()
    return writeRuns(runs, inTable)
        .split('\n')
        .map((line) => line.replace(/\s+$/, ''))
        .join('\n')
        .trim()
}

/** A line that would read as a heading, list item or code fence starts escaped. */
function escapeLineStart(line: string): string {
    return line
        .replace(/^(\s*)(#{1,6}\s)/, '$1\\$2')
        .replace(/^(\s*)([-*+]\s)/, '$1\\$2')
        .replace(/^(\s*)(\d+)\.(\s)/, '$1$2\\.$3')
        .replace(/^(\s*)```/, '$1\\`\\`\\`')
}

function headingLevel(tag: string): number {
    return Math.min(5, Number(tag.slice(1)))
}

function listLines(list: HTMLElement, indent: number, out: string[]): void {
    const ordered = list.tagName === 'OL'
    const checklist = list.dataset.checklist === 'true'
    let number = ordered ? Math.max(1, (list as HTMLOListElement).start || 1) : 1
    for (const child of Array.from(list.children)) {
        if (child.tagName === 'UL' || child.tagName === 'OL') {
            // execCommand('indent') may nest a list next to the items.
            listLines(child as HTMLElement, indent + 1, out)
            continue
        }
        if (child.tagName !== 'LI') continue
        const item = child as HTMLElement
        const nested = Array.from(item.children).filter((node) => node.tagName === 'UL' || node.tagName === 'OL')
        const copy = item.cloneNode(true) as HTMLElement
        copy.querySelectorAll('ul, ol').forEach((node) => node.remove())
        const own = Number(item.dataset.indent || 0)
        const depth = indent + own
        const marker = ordered ? `${number}.` : '-'
        const box = checklist || item.dataset.checked !== undefined ? (item.dataset.checked === 'true' ? '[x] ' : '[ ] ') : ''
        const text = inlineText(copy).replace(/\n+/g, ' ')
        out.push(`${' '.repeat(depth * LIST_INDENT)}${marker} ${box}${text}`.replace(/\s+$/, ''))
        number += 1
        nested.forEach((node) => listLines(node as HTMLElement, depth + 1, out))
    }
}

function tableText(table: HTMLElement): string {
    const rows = Array.from(table.querySelectorAll('tr')).map((row) =>
        Array.from(row.children)
            .filter((cell) => cell.tagName === 'TD' || cell.tagName === 'TH')
            .map((cell) => inlineText(cell, true).replace(/\n+/g, ' ') || ' '),
    )
    if (!rows.length) return ''
    const width = Math.max(...rows.map((row) => row.length))
    const padded = rows.map((row) => [...row, ...Array(width - row.length).fill(' ')])
    const line = (cells: string[]) => `| ${cells.join(' | ')} |`
    return [line(padded[0]), line(padded[0].map(() => '---')), ...padded.slice(1).map(line)].join('\n')
}

/** The editor (or pasted HTML) as description text. */
export function serializeEditor(root: Node): string {
    const blocks: string[] = []
    let loose: Node[] = []

    const paragraph = (nodes: Node[]) => {
        const holder = document.createElement('p')
        nodes.forEach((node) => holder.appendChild(node.cloneNode(true)))
        const text = inlineText(holder)
        if (text) blocks.push(text.split('\n').map(escapeLineStart).join('\n'))
    }
    const flush = () => {
        if (loose.length) paragraph(loose)
        loose = []
    }

    const visit = (node: Node) => {
        if (!isElement(node) || !BLOCK_TAGS.has(node.tagName)) {
            loose.push(node)
            return
        }
        flush()
        const tag = node.tagName
        if (/^H[1-6]$/.test(tag)) {
            const text = inlineText(node).replace(/\n+/g, ' ')
            if (text) blocks.push(`${'#'.repeat(headingLevel(tag))} ${text}`)
        } else if (tag === 'UL' || tag === 'OL') {
            const lines: string[] = []
            listLines(node, 0, lines)
            if (lines.length) blocks.push(lines.join('\n'))
        } else if (tag === 'TABLE') {
            const text = tableText(node)
            if (text) blocks.push(text)
        } else if (tag === 'PRE') {
            const text = (node.textContent ?? '').replace(/\n$/, '')
            blocks.push(`\`\`\`\n${text.replace(/^```/gm, '\\`\\`\\`')}\n\`\`\``)
        } else if (tag === 'FIGURE' && node.dataset.attachment) {
            const caption = (node.dataset.caption ?? '').replace(/[\]\n]/g, ' ')
            blocks.push(`![${caption}](attachment:${node.dataset.attachment})`)
        } else if (tag === 'HR') {
            return
        } else if (Array.from(node.childNodes).some((child) => isElement(child) && BLOCK_TAGS.has(child.tagName))) {
            // A wrapper (a pasted <div>, say): its blocks count, not the wrapper.
            node.childNodes.forEach(visit)
            flush()
        } else {
            paragraph(Array.from(node.childNodes))
        }
    }

    root.childNodes.forEach(visit)
    flush()
    return blocks.join('\n\n')
}

/** Pasted HTML, kept to what a description can hold, as editor content. */
export function cleanPastedHtml(
    html: string,
    attachment: (id: number, caption: string) => PlacedAttachment,
): DocumentFragment {
    const parsed = new DOMParser().parseFromString(html, 'text/html')
    const holder = document.createElement('div')
    renderMarkup(holder, serializeEditor(parsed.body), attachment)
    const fragment = document.createDocumentFragment()
    while (holder.firstChild) fragment.appendChild(holder.firstChild)
    return fragment
}
