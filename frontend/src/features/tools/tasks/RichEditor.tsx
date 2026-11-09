import {
    useCallback,
    useEffect,
    useImperativeHandle,
    useMemo,
    useRef,
    useState,
    type ClipboardEvent as ReactClipboardEvent,
    type KeyboardEvent as ReactKeyboardEvent,
    type MouseEvent as ReactMouseEvent,
    type ReactNode,
    type Ref,
} from 'react'
import {
    BetweenHorizontalEnd,
    BetweenVerticalEnd,
    Bold,
    Columns2,
    IndentDecrease,
    IndentIncrease,
    Italic,
    List,
    ListChecks,
    ListOrdered,
    RemoveFormatting,
    Rows2,
    Strikethrough,
    Table,
    Underline,
} from 'lucide-react'

import FloatingMenu from '../../../components/layout/FloatingMenu'
import type { Member } from './model'
import {
    attachmentElement,
    cleanPastedHtml,
    emptyParagraph,
    renderMarkup,
    serializeEditor,
    tableElement,
    type PlacedAttachment,
} from './richText'

type BlockStyle = 'p' | 'h1' | 'h2' | 'h3' | 'h4' | 'h5' | 'pre'

const BLOCK_STYLES: { value: BlockStyle; label: string }[] = [
    { value: 'p', label: 'Body' },
    { value: 'h1', label: 'Title' },
    { value: 'h2', label: 'Heading' },
    { value: 'h3', label: 'Subheading' },
    { value: 'h4', label: 'Heading 4' },
    { value: 'h5', label: 'Heading 5' },
    { value: 'pre', label: 'Monospaced' },
]
const MENTION = /(^|[\s(])@([\w.-]*)$/
const MAX_TABLE = 6
const IS_MAC = typeof navigator !== 'undefined' && /Mac|iPhone|iPad/.test(navigator.platform)
const MOD = IS_MAC ? '⌘' : 'Ctrl+'

/** An attachment to place; `placed` says how it looks, for one the parent just added. */
export interface InsertedAttachment {
    id: number
    caption: string
    placed?: PlacedAttachment
}

export interface RichEditorHandle {
    /** Place attachments where the cursor was, each on its own line. */
    insertAttachments: (items: InsertedAttachment[]) => void
    focus: () => void
}

interface Formats {
    block: BlockStyle | null
    bold: boolean
    italic: boolean
    underline: boolean
    strike: boolean
    list: 'ul' | 'ol' | 'check' | null
    table: boolean
}

const NO_FORMATS: Formats = {
    block: 'p',
    bold: false,
    italic: false,
    underline: false,
    strike: false,
    list: null,
    table: false,
}

function command(name: string, value?: string): void {
    // execCommand is old but is still how every browser edits rich text with undo.
    document.execCommand(name, false, value)
}

function ToolButton({ label, shortcut, onApply, active, disabled, children }: {
    label: string
    shortcut?: string
    onApply: () => void
    active?: boolean
    disabled?: boolean
    children: ReactNode
}) {
    return (
        <button
            type="button"
            className={`task-editor-tool${active ? ' is-active' : ''}`}
            aria-label={label}
            aria-pressed={active === undefined ? undefined : active}
            title={shortcut ? `${label} (${shortcut})` : label}
            disabled={disabled}
            // Keeps the selection in the text while the button is pressed.
            onMouseDown={(event) => event.preventDefault()}
            onClick={onApply}
        >
            {children}
        </button>
    )
}

/** How large a table to insert, by pointing at a grid. */
function TablePicker({ onPick }: { onPick: (rows: number, columns: number) => void }) {
    const [open, setOpen] = useState(false)
    const [size, setSize] = useState({ rows: 2, columns: 3 })
    const triggerRef = useRef<HTMLButtonElement>(null)
    return (
        <>
            <button
                ref={triggerRef}
                type="button"
                className="task-editor-tool"
                aria-label="Insert a table"
                title="Insert a table"
                aria-haspopup="menu"
                aria-expanded={open}
                onMouseDown={(event) => event.preventDefault()}
                onClick={() => setOpen((value) => !value)}
            >
                <Table size={15} />
            </button>
            <FloatingMenu anchorRef={triggerRef} open={open} onClose={() => setOpen(false)} className="task-editor-table-menu">
                <div
                    className="task-editor-table-grid"
                    style={{ gridTemplateColumns: `repeat(${MAX_TABLE}, 20px)` }}
                    onMouseDown={(event) => event.preventDefault()}
                >
                    {Array.from({ length: MAX_TABLE * MAX_TABLE }, (_, index) => {
                        const rows = Math.floor(index / MAX_TABLE) + 1
                        const columns = (index % MAX_TABLE) + 1
                        return (
                            <button
                                key={index}
                                type="button"
                                aria-label={`${rows} by ${columns}`}
                                className={rows <= size.rows && columns <= size.columns ? 'is-active' : undefined}
                                onMouseEnter={() => setSize({ rows, columns })}
                                onFocus={() => setSize({ rows, columns })}
                                onClick={() => {
                                    setOpen(false)
                                    onPick(rows, columns)
                                }}
                            />
                        )
                    })}
                </div>
                <small>
                    {size.columns} × {size.rows}: a heading row and {size.rows} {size.rows === 1 ? 'row' : 'rows'}
                </small>
            </FloatingMenu>
        </>
    )
}

/**
 * Write a description like a note: format the text itself (bold, underline, headings,
 * lists, checklists, tables) with no markup to learn and no preview. It is still saved
 * as plain formatted text (richText.ts), which the reports read.
 *
 * Shortcuts: B / I / U, Shift+X for strikethrough, Tab between table cells and to
 * indent list items, Enter on an empty list item to end the list, "@" to mention.
 * Typing "# ", "- ", "1. " or "[] " at the start of a line starts that format.
 */
export default function RichEditor({
    value,
    onChange,
    members,
    attachment,
    ariaLabel,
    placeholder,
    autoFocus,
    minHeight = 180,
    onFiles,
    onSubmitShortcut,
    onCancel,
    tools,
    handleRef,
}: {
    /** The text it starts from; later changes from outside are not shown. */
    value: string
    onChange: (value: string) => void
    members: Member[]
    attachment: (id: number, caption: string) => PlacedAttachment
    ariaLabel: string
    placeholder?: string
    autoFocus?: boolean
    minHeight?: number
    /** Pasted or dropped files; resolves to the attachments to place. */
    onFiles?: (files: File[]) => Promise<InsertedAttachment[]>
    onSubmitShortcut?: () => void
    onCancel?: () => void
    tools?: ReactNode
    handleRef?: Ref<RichEditorHandle>
}) {
    const root = useRef<HTMLDivElement>(null)
    const saved = useRef<Range | null>(null)
    const [formats, setFormats] = useState<Formats>(NO_FORMATS)
    const [empty, setEmpty] = useState(!value.trim())
    const [mention, setMention] = useState<{ query: string; left: number; top: number } | null>(null)
    const [active, setActive] = useState(0)
    // Only the first value is drawn: the editor owns its content afterwards.
    const initial = useRef(value)
    // The latest way to show attachments: a file pasted now is uploaded first, and the
    // parent only knows the new attachment when the upload has answered.
    const attachmentOf = useRef(attachment)
    useEffect(() => {
        attachmentOf.current = attachment
    })

    const emit = useCallback(() => {
        const element = root.current
        if (!element) return
        const text = serializeEditor(element)
        setEmpty(!text.trim())
        onChange(text)
    }, [onChange])

    useEffect(() => {
        const element = root.current
        if (!element) return
        renderMarkup(element, initial.current, attachment)
        // Enter makes paragraphs, not <div>s, in every browser.
        command('defaultParagraphSeparator', 'p')
        command('styleWithCSS', 'false')
        if (autoFocus) {
            element.focus()
            const range = document.createRange()
            range.selectNodeContents(element)
            range.collapse(false)
            window.getSelection()?.removeAllRanges()
            window.getSelection()?.addRange(range)
        }
        // Drawn once; `attachment` only labels what is placed later.
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [])

    // ------------------------------------------------------------------
    // Where the cursor is
    // ------------------------------------------------------------------

    const selectionInside = useCallback((): Range | null => {
        const selection = window.getSelection()
        if (!selection || !selection.rangeCount || !root.current) return null
        const range = selection.getRangeAt(0)
        return root.current.contains(range.commonAncestorContainer) ? range : null
    }, [])

    const closest = useCallback(
        (selector: string): HTMLElement | null => {
            const range = selectionInside()
            if (!range || !root.current) return null
            let node: Node | null = range.startContainer
            if (node.nodeType === Node.TEXT_NODE) node = node.parentNode
            const found = node instanceof Element ? node.closest(selector) : null
            return found instanceof HTMLElement && root.current.contains(found) && found !== root.current ? found : null
        },
        [selectionInside],
    )

    /** The top-level block holding the cursor. */
    const topBlock = useCallback((): HTMLElement | null => {
        const range = selectionInside()
        if (!range || !root.current) return null
        let node: Node | null = range.startContainer
        while (node && node.parentNode !== root.current) node = node.parentNode
        return node instanceof HTMLElement ? node : null
    }, [selectionInside])

    const readFormats = useCallback(() => {
        const range = selectionInside()
        if (!range) return
        saved.current = range.cloneRange()
        const block = closest('h1, h2, h3, h4, h5, h6, pre, p, li, td, th')
        const tag = block?.tagName.toLowerCase()
        const list = closest('ul, ol')
        setFormats({
            block: tag && /^h[1-5]$|^pre$|^p$/.test(tag) ? (tag as BlockStyle) : tag === 'h6' ? 'h5' : null,
            bold: document.queryCommandState('bold'),
            italic: document.queryCommandState('italic'),
            underline: document.queryCommandState('underline'),
            strike: document.queryCommandState('strikeThrough'),
            list: list ? (list.closest('[data-checklist="true"]') ? 'check' : list.tagName === 'OL' ? 'ol' : 'ul') : null,
            table: Boolean(closest('td, th')),
        })
    }, [closest, selectionInside])

    useEffect(() => {
        const onSelection = () => readFormats()
        document.addEventListener('selectionchange', onSelection)
        return () => document.removeEventListener('selectionchange', onSelection)
    }, [readFormats])

    const restore = () => {
        const element = root.current
        if (!element) return
        if (document.activeElement !== element) element.focus()
        if (!selectionInside() && saved.current) {
            window.getSelection()?.removeAllRanges()
            window.getSelection()?.addRange(saved.current)
        }
    }

    const placeCaret = (node: Node, atEnd = false) => {
        const range = document.createRange()
        range.selectNodeContents(node)
        range.collapse(!atEnd)
        window.getSelection()?.removeAllRanges()
        window.getSelection()?.addRange(range)
    }

    /** Put a block after the one holding the cursor (in its place, if that is empty). */
    const insertBlock = (block: HTMLElement) => {
        const element = root.current
        if (!element) return
        const current = topBlock()
        if (current && !current.textContent?.trim() && current.tagName === 'P' && !current.querySelector('img')) {
            current.replaceWith(block)
        } else if (current) {
            current.after(block)
        } else {
            element.appendChild(block)
        }
        if (!block.nextSibling) block.after(emptyParagraph())
    }

    const apply = (change: () => void) => {
        restore()
        change()
        normalize()
        emit()
        readFormats()
    }

    /** Keep the content in shapes the text can hold after the browser edits it. */
    const normalize = () => {
        const element = root.current
        if (!element) return
        element.querySelectorAll('[data-checklist="true"] ul, [data-checklist="true"] ol').forEach((list) => {
            ;(list as HTMLElement).dataset.checklist = 'true'
        })
        element.querySelectorAll('[data-checklist="true"] > li').forEach((item) => {
            const li = item as HTMLElement
            if (li.dataset.checked === undefined) li.dataset.checked = 'false'
        })
        // Some browsers wrap typed text in a <div> or leave it bare at the top level.
        Array.from(element.childNodes).forEach((node) => {
            if (node instanceof HTMLElement && node.tagName === 'DIV' && !node.dataset.attachment) {
                const paragraph = document.createElement('p')
                while (node.firstChild) paragraph.appendChild(node.firstChild)
                node.replaceWith(paragraph)
            } else if (node.nodeType === Node.TEXT_NODE && node.textContent?.trim()) {
                const paragraph = document.createElement('p')
                node.replaceWith(paragraph)
                paragraph.appendChild(node)
            }
        })
        if (!element.firstChild) element.appendChild(emptyParagraph())
    }

    // ------------------------------------------------------------------
    // Formatting
    // ------------------------------------------------------------------

    const setBlock = (style: BlockStyle) =>
        apply(() => {
            if (formats.list) command(formats.list === 'ol' ? 'insertOrderedList' : 'insertUnorderedList')
            command('formatBlock', `<${style}>`)
        })

    const toggleList = (kind: 'ul' | 'ol' | 'check') =>
        apply(() => {
            const list = closest('ul, ol')
            const checklist = list?.closest('[data-checklist="true"]') as HTMLElement | null
            if (kind === 'check') {
                if (checklist) {
                    // Off again: a plain bullet list.
                    checklist.removeAttribute('data-checklist')
                    checklist.querySelectorAll('[data-checklist]').forEach((node) => node.removeAttribute('data-checklist'))
                    checklist.querySelectorAll('li').forEach((item) => item.removeAttribute('data-checked'))
                    return
                }
                if (!list || list.tagName !== 'UL') command('insertUnorderedList')
                const made = closest('ul')
                if (made) made.dataset.checklist = 'true'
                return
            }
            if (checklist && kind === 'ul') {
                checklist.removeAttribute('data-checklist')
                checklist.querySelectorAll('li').forEach((item) => item.removeAttribute('data-checked'))
                return
            }
            command(kind === 'ol' ? 'insertOrderedList' : 'insertUnorderedList')
        })

    const insertTable = (rows: number, columns: number) =>
        apply(() => {
            const table = tableElement(
                Array.from({ length: columns }, () => ''),
                Array.from({ length: rows }, () => Array.from({ length: columns }, () => '')),
            )
            insertBlock(table)
            placeCaret(table.rows[0].cells[0])
        })

    const tableEdit = (kind: 'row' | 'column' | 'delete-row' | 'delete-column') =>
        apply(() => {
            const cell = closest('td, th') as HTMLTableCellElement | null
            const table = cell?.closest('table') as HTMLTableElement | null
            if (!cell || !table) return
            const row = cell.parentElement as HTMLTableRowElement
            const index = cell.cellIndex
            if (kind === 'row') {
                const body = table.tBodies[0] ?? table.createTBody()
                const added = row.parentElement === body ? body.insertRow(row.sectionRowIndex + 1) : body.insertRow(0)
                for (let column = 0; column < row.cells.length; column += 1) {
                    added.insertCell().appendChild(document.createElement('br'))
                }
                placeCaret(added.cells[Math.min(index, added.cells.length - 1)])
            } else if (kind === 'column') {
                Array.from(table.rows).forEach((line) => {
                    const added = line.parentElement?.tagName === 'THEAD' ? document.createElement('th') : document.createElement('td')
                    added.appendChild(document.createElement('br'))
                    line.cells[index].after(added)
                })
                placeCaret(row.cells[index + 1])
            } else if (kind === 'delete-row') {
                if (table.rows.length <= 1) return table.remove()
                const next = table.rows[Math.min(row.rowIndex + 1, table.rows.length - 1)] === row
                    ? table.rows[row.rowIndex - 1]
                    : table.rows[row.rowIndex + 1]
                const promote = row.parentElement?.tagName === 'THEAD'
                row.remove()
                if (promote && table.tBodies[0]?.rows.length) {
                    // The first row is the heading row: the next one takes its place.
                    const first = table.tBodies[0].rows[0]
                    const head = table.tHead ?? table.createTHead()
                    const heading = head.insertRow()
                    Array.from(first.cells).forEach((source) => {
                        const th = document.createElement('th')
                        while (source.firstChild) th.appendChild(source.firstChild)
                        heading.appendChild(th)
                    })
                    first.remove()
                }
                if (next?.cells[0]) placeCaret(next.cells[Math.min(index, next.cells.length - 1)])
            } else {
                if (row.cells.length <= 1) return table.remove()
                Array.from(table.rows).forEach((line) => line.cells[index]?.remove())
                placeCaret(row.cells[Math.max(0, index - 1)])
            }
        })

    const moveCell = (back: boolean): boolean => {
        const cell = closest('td, th') as HTMLTableCellElement | null
        const table = cell?.closest('table') as HTMLTableElement | null
        if (!cell || !table) return false
        const cells = Array.from(table.querySelectorAll('th, td')) as HTMLElement[]
        const position = cells.indexOf(cell)
        if (!back && position === cells.length - 1) {
            tableEdit('row')
            return true
        }
        const target = cells[position + (back ? -1 : 1)]
        if (target) placeCaret(target, true)
        return true
    }

    const clearFormatting = () =>
        apply(() => {
            command('removeFormat')
            const block = closest('h1, h2, h3, h4, h5, h6, pre')
            if (block) command('formatBlock', '<p>')
        })

    // ------------------------------------------------------------------
    // Mentions
    // ------------------------------------------------------------------

    const matches = useMemo(() => {
        if (mention === null) return []
        const needle = mention.query.toLowerCase()
        return members
            .filter(
                (member) =>
                    member.username.toLowerCase().includes(needle) || (member.full_name ?? '').toLowerCase().includes(needle),
            )
            .slice(0, 6)
    }, [members, mention])

    const trackMention = () => {
        const range = selectionInside()
        if (!range || !range.collapsed || range.startContainer.nodeType !== Node.TEXT_NODE || !root.current) {
            setMention(null)
            return
        }
        const before = (range.startContainer.textContent ?? '').slice(0, range.startOffset)
        const found = MENTION.exec(before)
        if (!found) {
            setMention(null)
            return
        }
        const box = range.getBoundingClientRect()
        const frame = root.current.getBoundingClientRect()
        setMention({ query: found[2], left: box.left - frame.left, top: box.bottom - frame.top + 4 })
        setActive(0)
    }

    const pickMention = (member: Member) => {
        const range = selectionInside()
        if (!range || range.startContainer.nodeType !== Node.TEXT_NODE || mention === null) return
        const remove = mention.query.length + 1
        const start = Math.max(0, range.startOffset - remove)
        const word = document.createRange()
        word.setStart(range.startContainer, start)
        word.setEnd(range.startContainer, range.startOffset)
        window.getSelection()?.removeAllRanges()
        window.getSelection()?.addRange(word)
        command('insertText', `@${member.username} `)
        setMention(null)
        emit()
    }

    // ------------------------------------------------------------------
    // Typing
    // ------------------------------------------------------------------

    /** "# ", "- ", "1. " or "[] " typed at the start of a paragraph start that format. */
    const shortcutAtStart = (): boolean => {
        const range = selectionInside()
        const block = closest('p, h1, h2, h3, h4, h5, h6')
        if (!range || !range.collapsed || !block || block.closest('li, td, th')) return false
        const probe = document.createRange()
        probe.selectNodeContents(block)
        probe.setEnd(range.startContainer, range.startOffset)
        const typed = probe.toString()
        let change: (() => void) | null = null
        const heading = /^(#{1,5})$/.exec(typed)
        if (heading) change = () => command('formatBlock', `<h${heading[1].length}>`)
        else if (typed === '-' || typed === '*') change = () => command('insertUnorderedList')
        else if (typed === '1.') change = () => command('insertOrderedList')
        else if (typed === '[]' || typed === '[ ]') {
            change = () => {
                command('insertUnorderedList')
                const made = closest('ul')
                if (made) made.dataset.checklist = 'true'
            }
        }
        if (!change) return false
        // Remove what was typed, then format the line.
        window.getSelection()?.removeAllRanges()
        window.getSelection()?.addRange(probe)
        command('delete')
        change()
        normalize()
        emit()
        return true
    }

    const onKeyDown = (event: ReactKeyboardEvent<HTMLDivElement>) => {
        if (matches.length) {
            if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
                event.preventDefault()
                setActive((index) => (index + (event.key === 'ArrowDown' ? 1 : matches.length - 1)) % matches.length)
                return
            }
            if (event.key === 'Enter' || event.key === 'Tab') {
                event.preventDefault()
                pickMention(matches[active])
                return
            }
            if (event.key === 'Escape') {
                event.preventDefault()
                setMention(null)
                return
            }
        }
        const mod = event.metaKey || event.ctrlKey
        if (mod && event.key === 'Enter' && onSubmitShortcut) {
            event.preventDefault()
            emit()
            onSubmitShortcut()
            return
        }
        if (event.key === 'Escape' && onCancel) {
            event.preventDefault()
            onCancel()
            return
        }
        if (mod && !event.altKey) {
            const key = event.key.toLowerCase()
            if (key === 'b' || key === 'i' || key === 'u') {
                event.preventDefault()
                apply(() => command(key === 'b' ? 'bold' : key === 'i' ? 'italic' : 'underline'))
                return
            }
            if (key === 'x' && event.shiftKey) {
                event.preventDefault()
                apply(() => command('strikeThrough'))
                return
            }
        }
        if (event.key === 'Tab') {
            if (moveCell(event.shiftKey)) {
                event.preventDefault()
                return
            }
            if (closest('li')) {
                event.preventDefault()
                apply(() => command(event.shiftKey ? 'outdent' : 'indent'))
                return
            }
        }
        if (event.key === ' ' && !mod && shortcutAtStart()) {
            event.preventDefault()
            return
        }
        if (event.key === 'Enter' && !event.shiftKey && closest('[data-checklist="true"] li')) {
            // A new checklist item starts unticked, whatever the one before it was.
            window.setTimeout(() => {
                const item = closest('li')
                if (item) item.dataset.checked = 'false'
                emit()
            })
        }
    }

    /** Clicking the box of a checklist item ticks it. */
    const onMouseDown = (event: ReactMouseEvent<HTMLDivElement>) => {
        const target = event.target as HTMLElement
        const item = target.closest('li[data-checked]') as HTMLElement | null
        if (!item || target !== item) return
        const box = item.getBoundingClientRect()
        if (event.clientX > box.left + 24) return
        event.preventDefault()
        item.dataset.checked = item.dataset.checked === 'true' ? 'false' : 'true'
        emit()
    }

    const onPaste = (event: ReactClipboardEvent<HTMLDivElement>) => {
        const files = Array.from(event.clipboardData.files)
        if (files.length && onFiles) {
            event.preventDefault()
            event.stopPropagation()
            const range = selectionInside()?.cloneRange() ?? null
            void onFiles(files).then((items) => {
                if (range) {
                    window.getSelection()?.removeAllRanges()
                    window.getSelection()?.addRange(range)
                }
                insertAttachments(items)
            })
            return
        }
        const html = event.clipboardData.getData('text/html')
        event.preventDefault()
        if (html) {
            // Only what a description can hold is kept, as the editor's own elements.
            const fragment = cleanPastedHtml(html, attachmentOf.current)
            const range = selectionInside()
            if (!range) return
            range.deleteContents()
            const last = fragment.lastChild
            const single = fragment.childNodes.length === 1 && fragment.firstChild?.nodeName === 'P'
            if (single && fragment.firstChild) {
                // One paragraph: its text goes where the cursor is, not as a new block.
                const holder = fragment.firstChild
                const inline = document.createDocumentFragment()
                while (holder.firstChild) inline.appendChild(holder.firstChild)
                const end = inline.lastChild
                range.insertNode(inline)
                if (end) placeCaret(end, true)
            } else {
                const current = topBlock()
                if (current) current.after(fragment)
                else root.current?.appendChild(fragment)
                if (last) placeCaret(last, true)
            }
            normalize()
            emit()
            return
        }
        command('insertText', event.clipboardData.getData('text/plain'))
    }

    const insertAttachments = (items: InsertedAttachment[]) => {
        restore()
        let last: HTMLElement | null = null
        for (const item of items) {
            const figure = attachmentElement(
                item.id,
                item.caption,
                item.placed ?? attachmentOf.current(item.id, item.caption),
            )
            insertBlock(figure)
            last = figure
        }
        const after = last?.nextElementSibling
        if (after) placeCaret(after)
        normalize()
        emit()
    }

    useImperativeHandle(handleRef, () => ({
        insertAttachments,
        focus: () => restore(),
    }))

    return (
        <div className="task-editor task-rich">
            <div className="task-editor-toolbar" role="toolbar" aria-label={`${ariaLabel} formatting`}>
                <select
                    className="entropy-select task-editor-style"
                    value={formats.block ?? ''}
                    onMouseDown={() => {
                        saved.current = selectionInside()?.cloneRange() ?? saved.current
                    }}
                    onChange={(event) => setBlock(event.target.value as BlockStyle)}
                    aria-label="Text style"
                    title="Text style"
                >
                    {formats.block === null && <option value="">—</option>}
                    {BLOCK_STYLES.map((style) => (
                        <option key={style.value} value={style.value}>
                            {style.label}
                        </option>
                    ))}
                </select>
                <span className="task-editor-group">
                    <ToolButton label="Bold" shortcut={`${MOD}B`} active={formats.bold} onApply={() => apply(() => command('bold'))}>
                        <Bold size={15} />
                    </ToolButton>
                    <ToolButton label="Italic" shortcut={`${MOD}I`} active={formats.italic} onApply={() => apply(() => command('italic'))}>
                        <Italic size={15} />
                    </ToolButton>
                    <ToolButton label="Underline" shortcut={`${MOD}U`} active={formats.underline} onApply={() => apply(() => command('underline'))}>
                        <Underline size={15} />
                    </ToolButton>
                    <ToolButton
                        label="Strikethrough"
                        shortcut={`${MOD}${IS_MAC ? '⇧' : 'Shift+'}X`}
                        active={formats.strike}
                        onApply={() => apply(() => command('strikeThrough'))}
                    >
                        <Strikethrough size={15} />
                    </ToolButton>
                </span>
                <span className="task-editor-group">
                    <ToolButton label="Bulleted list" active={formats.list === 'ul'} onApply={() => toggleList('ul')}>
                        <List size={15} />
                    </ToolButton>
                    <ToolButton label="Numbered list" active={formats.list === 'ol'} onApply={() => toggleList('ol')}>
                        <ListOrdered size={15} />
                    </ToolButton>
                    <ToolButton label="Checklist" active={formats.list === 'check'} onApply={() => toggleList('check')}>
                        <ListChecks size={15} />
                    </ToolButton>
                    <ToolButton label="Indent" shortcut="Tab" disabled={!formats.list} onApply={() => apply(() => command('indent'))}>
                        <IndentIncrease size={15} />
                    </ToolButton>
                    <ToolButton label="Outdent" shortcut="Shift+Tab" disabled={!formats.list} onApply={() => apply(() => command('outdent'))}>
                        <IndentDecrease size={15} />
                    </ToolButton>
                </span>
                <span className="task-editor-group">
                    <TablePicker onPick={insertTable} />
                    {formats.table && (
                        <>
                            <ToolButton label="Add a row below" onApply={() => tableEdit('row')}>
                                <BetweenHorizontalEnd size={15} />
                            </ToolButton>
                            <ToolButton label="Add a column to the right" onApply={() => tableEdit('column')}>
                                <BetweenVerticalEnd size={15} />
                            </ToolButton>
                            <ToolButton label="Delete this row" onApply={() => tableEdit('delete-row')}>
                                <Rows2 size={15} />
                                <small>−</small>
                            </ToolButton>
                            <ToolButton label="Delete this column" onApply={() => tableEdit('delete-column')}>
                                <Columns2 size={15} />
                                <small>−</small>
                            </ToolButton>
                        </>
                    )}
                </span>
                <span className="task-editor-group">
                    <ToolButton label="Clear formatting" onApply={clearFormatting}>
                        <RemoveFormatting size={15} />
                    </ToolButton>
                </span>
                {tools}
            </div>
            <div className="task-rich-frame">
                <div
                    ref={root}
                    className={`task-description task-rich-body${empty ? ' is-empty' : ''}`}
                    contentEditable
                    suppressContentEditableWarning
                    role="textbox"
                    aria-multiline="true"
                    aria-label={ariaLabel}
                    data-placeholder={placeholder ?? 'Write here…'}
                    spellCheck
                    style={{ minHeight }}
                    onInput={() => {
                        normalize()
                        emit()
                        trackMention()
                    }}
                    onKeyDown={onKeyDown}
                    onKeyUp={(event) => {
                        if (!['ArrowDown', 'ArrowUp', 'Enter', 'Tab', 'Escape'].includes(event.key)) trackMention()
                    }}
                    onMouseDown={onMouseDown}
                    onPaste={onPaste}
                    onBlur={() => {
                        window.setTimeout(() => setMention(null), 150)
                    }}
                />
                {matches.length > 0 && mention && (
                    <ul
                        className="task-mention-list task-rich-mentions"
                        role="listbox"
                        aria-label="Mention a member"
                        style={{ left: mention.left, top: mention.top }}
                    >
                        {matches.map((member, index) => (
                            <li key={member.username} role="option" aria-selected={index === active}>
                                <button
                                    type="button"
                                    className={index === active ? 'is-active' : undefined}
                                    onMouseDown={(event) => {
                                        event.preventDefault()
                                        pickMention(member)
                                    }}
                                >
                                    <strong>@{member.username}</strong>
                                    {member.full_name && <span>{member.full_name}</span>}
                                </button>
                            </li>
                        ))}
                    </ul>
                )}
            </div>
        </div>
    )
}
