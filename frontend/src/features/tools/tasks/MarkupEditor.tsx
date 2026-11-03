import { useRef, useState, type ClipboardEvent, type KeyboardEvent, type ReactNode, type RefObject } from 'react'
import {
    Bold,
    CheckSquare,
    Code,
    Columns2,
    Eye,
    Italic,
    List,
    ListOrdered,
    Pencil,
    Rows2,
    Strikethrough,
    Table,
    Trash2,
} from 'lucide-react'

import FloatingMenu from '../../../components/layout/FloatingMenu'
import MarkupView from './MarkupView'
import MentionInput from './MentionInput'
import {
    addTableColumn,
    addTableRow,
    continueBlock,
    indentList,
    insertTable,
    lineStyleAt,
    moveCell,
    removeTableColumn,
    removeTableRow,
    setLineStyle,
    tableAt,
    toggleInline,
    type Edit,
    type LineStyle,
} from './markupEdit'
import type { Member } from './model'

const STYLES: { value: LineStyle; label: string }[] = [
    { value: 'paragraph', label: 'Paragraph' },
    { value: 'h1', label: 'Heading' },
    { value: 'h2', label: 'Subheading' },
    { value: 'h3', label: 'Small heading' },
]
const MAX_ROWS = 6
const MAX_COLUMNS = 6

function ToolButton({ label, shortcut, onApply, active, children }: {
    label: string
    shortcut?: string
    onApply: () => void
    active?: boolean
    children: ReactNode
}) {
    return (
        <button
            type="button"
            className={`task-editor-tool${active ? ' is-active' : ''}`}
            aria-label={label}
            aria-pressed={active === undefined ? undefined : active}
            title={shortcut ? `${label} (${shortcut})` : label}
            // Keeps the selection in the text while the button is pressed.
            onMouseDown={(event) => event.preventDefault()}
            onClick={onApply}
        >
            {children}
        </button>
    )
}

/** Asks how large a table to insert, by pointing at a grid. */
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
                aria-haspopup="menu"
                aria-expanded={open}
                title="Insert a table"
                onMouseDown={(event) => event.preventDefault()}
                onClick={() => setOpen((value) => !value)}
            >
                <Table size={15} />
            </button>
            <FloatingMenu anchorRef={triggerRef} open={open} onClose={() => setOpen(false)} align="start" className="task-editor-table-menu">
                <div className="task-editor-table-grid" style={{ gridTemplateColumns: `repeat(${MAX_COLUMNS}, 1fr)` }}>
                    {Array.from({ length: MAX_ROWS * MAX_COLUMNS }, (_, index) => {
                        const rows = Math.floor(index / MAX_COLUMNS) + 1
                        const columns = (index % MAX_COLUMNS) + 1
                        return (
                            <button
                                key={index}
                                type="button"
                                role="menuitem"
                                aria-label={`${rows} rows, ${columns} columns`}
                                className={rows <= size.rows && columns <= size.columns ? 'is-active' : undefined}
                                onMouseEnter={() => setSize({ rows, columns })}
                                onFocus={() => setSize({ rows, columns })}
                                onMouseDown={(event) => event.preventDefault()}
                                onClick={() => {
                                    setOpen(false)
                                    onPick(rows, columns)
                                }}
                            />
                        )
                    })}
                </div>
                <small className="task-muted">{size.rows} rows × {size.columns} columns, plus headings</small>
            </FloatingMenu>
        </>
    )
}

/**
 * Writing a description: formatting from the toolbar or the keyboard, on plain text that
 * stays readable, with a preview of how it will read. Lists and tables carry on with Enter
 * and Tab. Changes go through the browser's own editing, so Ctrl+Z undoes them.
 */
export default function MarkupEditor({
    value,
    onChange,
    members,
    rows = 8,
    ariaLabel,
    placeholder,
    autoFocus,
    inputRef,
    tools,
    attachment,
    onPaste,
    onSubmitShortcut,
    onCancel,
}: {
    value: string
    onChange: (value: string) => void
    members: Member[]
    rows?: number
    ariaLabel: string
    placeholder?: string
    autoFocus?: boolean
    inputRef?: RefObject<HTMLTextAreaElement | null>
    /** More controls for the toolbar, such as inserting an attachment. */
    tools?: ReactNode
    /** How attachments in the text look in the preview. */
    attachment?: (id: number, caption: string) => ReactNode
    onPaste?: (event: ClipboardEvent<HTMLTextAreaElement>) => void
    onSubmitShortcut?: () => void
    /** Escape. */
    onCancel?: () => void
}) {
    const ownRef = useRef<HTMLTextAreaElement>(null)
    const area = inputRef ?? ownRef
    const [preview, setPreview] = useState(false)
    const [caret, setCaret] = useState(0)

    const track = () => setCaret(area.current?.selectionStart ?? 0)

    const apply = (edit: Edit | null) => {
        const element = area.current
        if (!edit || !element) return
        // Only what differs is replaced, so undo restores just that.
        const current = element.value
        let head = 0
        while (head < current.length && head < edit.text.length && current[head] === edit.text[head]) head += 1
        let tail = 0
        while (
            tail < current.length - head &&
            tail < edit.text.length - head &&
            current[current.length - 1 - tail] === edit.text[edit.text.length - 1 - tail]
        ) {
            tail += 1
        }
        element.focus()
        element.setSelectionRange(head, current.length - tail)
        const inserted = edit.text.slice(head, edit.text.length - tail)
        const done = inserted
            ? document.execCommand('insertText', false, inserted)
            : document.execCommand('delete')
        if (!done) onChange(edit.text)
        const select = () => {
            element.setSelectionRange(edit.start, edit.end)
            setCaret(edit.start)
        }
        select()
        // A fallback through React sets the value after this.
        if (!done) window.requestAnimationFrame(select)
    }

    const selection = (): [number, number] => {
        const element = area.current
        return element ? [element.selectionStart, element.selectionEnd] : [value.length, value.length]
    }

    const inline = (marker: string) => {
        const [start, end] = selection()
        apply(toggleInline(value, start, end, marker))
    }
    const line = (style: LineStyle) => {
        const [start, end] = selection()
        apply(setLineStyle(value, start, end, style))
    }

    const onKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
        const [start, end] = selection()
        const modifier = event.metaKey || event.ctrlKey
        if (event.key === 'Escape' && onCancel) {
            onCancel()
            return
        }
        if (modifier && !event.altKey) {
            const key = event.key.toLowerCase()
            const marker = key === 'b' ? '**' : key === 'i' ? '*' : key === 'x' && event.shiftKey ? '~~' : key === 'e' ? '`' : null
            if (marker) {
                event.preventDefault()
                inline(marker)
            }
            return
        }
        if (event.key === 'Enter' && !event.shiftKey && start === end) {
            const edit = continueBlock(value, start)
            if (edit) {
                event.preventDefault()
                apply(edit)
            }
            return
        }
        // Tab only stays here in tables and lists; elsewhere it leaves the field, as it should.
        if (event.key === 'Tab') {
            const edit = moveCell(value, start, event.shiftKey) ?? indentList(value, start, end, event.shiftKey)
            if (edit) {
                event.preventDefault()
                apply(edit)
            }
        }
    }

    const inTable = tableAt(value, caret) !== null
    const current = lineStyleAt(value, caret)
    const heading = STYLES.some((item) => item.value === current) ? current : 'paragraph'

    return (
        <div className="task-editor">
            <div className="task-editor-toolbar" role="toolbar" aria-label="Formatting">
                {!preview && (
                    <>
                        <select
                            className="entropy-select task-editor-style"
                            aria-label="Text style"
                            value={heading}
                            onChange={(event) => line(event.target.value as LineStyle)}
                        >
                            {STYLES.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}
                        </select>
                        <span className="task-editor-group">
                            <ToolButton label="Bold" shortcut="Ctrl+B" onApply={() => inline('**')}><Bold size={15} /></ToolButton>
                            <ToolButton label="Italic" shortcut="Ctrl+I" onApply={() => inline('*')}><Italic size={15} /></ToolButton>
                            <ToolButton label="Strikethrough" shortcut="Ctrl+Shift+X" onApply={() => inline('~~')}><Strikethrough size={15} /></ToolButton>
                            <ToolButton label="Code" shortcut="Ctrl+E" onApply={() => inline('`')}><Code size={15} /></ToolButton>
                        </span>
                        <span className="task-editor-group">
                            <ToolButton label="Bulleted list" active={current === 'bullet'} onApply={() => line('bullet')}><List size={15} /></ToolButton>
                            <ToolButton label="Numbered list" active={current === 'number'} onApply={() => line('number')}><ListOrdered size={15} /></ToolButton>
                            <ToolButton label="Checklist" active={current === 'check'} onApply={() => line('check')}><CheckSquare size={15} /></ToolButton>
                        </span>
                        <span className="task-editor-group">
                            <TablePicker onPick={(tableRows, columns) => {
                                const [start, end] = selection()
                                apply(insertTable(value, start, end, tableRows, columns))
                            }} />
                            {inTable && (
                                <>
                                    <ToolButton label="Add a row" onApply={() => apply(addTableRow(value, selection()[0]))}><Rows2 size={15} /></ToolButton>
                                    <ToolButton label="Add a column" onApply={() => apply(addTableColumn(value, selection()[0]))}><Columns2 size={15} /></ToolButton>
                                    <ToolButton label="Delete this row" onApply={() => apply(removeTableRow(value, selection()[0]))}><Trash2 size={15} /><small>Row</small></ToolButton>
                                    <ToolButton label="Delete this column" onApply={() => apply(removeTableColumn(value, selection()[0]))}><Trash2 size={15} /><small>Col</small></ToolButton>
                                </>
                            )}
                        </span>
                        {tools}
                    </>
                )}
                <div className="seg-control task-editor-mode" role="tablist" aria-label="Editor view">
                    <button type="button" role="tab" aria-selected={!preview} className={preview ? '' : 'is-active'} onClick={() => setPreview(false)}>
                        <Pencil size={13} /> Write
                    </button>
                    <button type="button" role="tab" aria-selected={preview} className={preview ? 'is-active' : ''} onClick={() => setPreview(true)}>
                        <Eye size={13} /> Preview
                    </button>
                </div>
            </div>
            {preview ? (
                <div className="task-editor-preview">
                    {value.trim() ? (
                        <MarkupView
                            text={value}
                            members={members}
                            attachment={attachment ?? ((id, caption) => <p key={id} className="task-muted">[{caption || 'attachment'}]</p>)}
                        />
                    ) : (
                        <p className="task-muted">Nothing to preview yet.</p>
                    )}
                </div>
            ) : (
                <MentionInput
                    value={value}
                    onChange={onChange}
                    members={members}
                    rows={rows}
                    ariaLabel={ariaLabel}
                    placeholder={placeholder}
                    autoFocus={autoFocus}
                    inputRef={area}
                    textareaClassName="task-input task-editor-input"
                    onSubmitShortcut={onSubmitShortcut}
                    onEditorKeyDown={onKeyDown}
                    onPaste={onPaste}
                    onSelect={track}
                />
            )}
        </div>
    )
}
