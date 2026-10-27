import {
    useEffect,
    useMemo,
    useRef,
    useState,
    type ClipboardEvent,
    type KeyboardEvent,
    type PointerEvent as ReactPointerEvent,
    type ReactNode,
} from 'react'
import {
    ArrowDownAZ,
    ArrowUpAZ,
    BetweenHorizontalEnd,
    BetweenHorizontalStart,
    BetweenVerticalEnd,
    BetweenVerticalStart,
    Rows3,
    TableColumnsSplit,
    TableRowsSplit,
} from 'lucide-react'

import { DELIMITERS, columnCount, columnName, detectDelimiter, parseCsv, writeCsv, type CsvTable } from './csv'

const ROW_HEIGHT = 26
const HEADER_HEIGHT = 26
const NUMBER_WIDTH = 52
const DEFAULT_WIDTH = 140
const MIN_WIDTH = 48
const OVERSCAN = 8

interface Cell {
    row: number
    col: number
}

interface Editing extends Cell {
    value: string
}

/** Copy a range as Excel does: tab-separated, quoted only when needed. */
function toTsv(rows: string[][]): string {
    return rows
        .map((row) => row.map((cell) => (/[\t\r\n"]/.test(cell) ? `"${cell.replace(/"/g, '""')}"` : cell)).join('\t'))
        .join('\n')
}

function setCells(rows: string[][], at: Cell, block: string[][]): string[][] {
    const next = rows.map((row) => [...row])
    block.forEach((values, offset) => {
        const index = at.row + offset
        while (next.length <= index) next.push([])
        const row = next[index]
        values.forEach((value, column) => {
            const position = at.col + column
            while (row.length < position) row.push('')
            row[position] = value
        })
    })
    return next
}

export default function CsvGrid({
    text,
    readOnly,
    onChange,
    onUndo,
    onRedo,
}: {
    text: string
    readOnly: boolean
    onChange: (text: string) => void
    onUndo: () => void
    onRedo: () => void
}) {
    const [delimiter, setDelimiter] = useState(() => detectDelimiter(text))
    const table = useMemo(() => parseCsv(text, delimiter), [text, delimiter])
    const columns = Math.max(columnCount(table.rows), 1)
    // One empty row and column past the data: typing there extends the table.
    const shownRows = table.rows.length + (readOnly ? 0 : 1)
    const shownColumns = columns + (readOnly ? 0 : 1)

    const [header, setHeader] = useState(true)
    const [anchor, setAnchor] = useState<Cell>({ row: 0, col: 0 })
    const [focus, setFocus] = useState<Cell>({ row: 0, col: 0 })
    const [editing, setEditing] = useState<Editing | null>(null)
    const [widths, setWidths] = useState<Record<number, number>>({})
    const [scroll, setScroll] = useState({ top: 0, height: 600 })
    const scroller = useRef<HTMLDivElement>(null)
    const editor = useRef<HTMLTextAreaElement>(null)

    const range = {
        top: Math.min(anchor.row, focus.row),
        bottom: Math.max(anchor.row, focus.row),
        left: Math.min(anchor.col, focus.col),
        right: Math.max(anchor.col, focus.col),
    }

    const widthOf = (col: number) => widths[col] ?? DEFAULT_WIDTH
    const offsets = useMemo(() => {
        const list = [NUMBER_WIDTH]
        for (let col = 0; col < shownColumns; col += 1) list.push(list[col] + (widths[col] ?? DEFAULT_WIDTH))
        return list
    }, [shownColumns, widths])

    useEffect(() => {
        const element = scroller.current
        if (!element) return
        const observer = new ResizeObserver(() => setScroll({ top: element.scrollTop, height: element.clientHeight }))
        observer.observe(element)
        return () => observer.disconnect()
    }, [])

    // Focus the cell editor when it opens, with the caret at the end.
    const editingKey = editing ? `${editing.row}:${editing.col}` : null
    useEffect(() => {
        const element = editor.current
        if (!editingKey || !element) return
        element.focus()
        element.setSelectionRange(element.value.length, element.value.length)
    }, [editingKey])

    const commit = (rows: string[][], next?: Partial<CsvTable>) => {
        if (readOnly) return
        const written = writeCsv({ ...table, ...next, rows })
        if (written !== text) onChange(written)
    }

    const cellValue = (cell: Cell) => table.rows[cell.row]?.[cell.col] ?? ''

    const select = (cell: Cell, extend = false) => {
        const clamped = {
            row: Math.max(0, Math.min(shownRows - 1, cell.row)),
            col: Math.max(0, Math.min(shownColumns - 1, cell.col)),
        }
        setFocus(clamped)
        if (!extend) setAnchor(clamped)
        const element = scroller.current
        if (!element) return
        const top = clamped.row * ROW_HEIGHT
        if (top < element.scrollTop) element.scrollTop = top
        else if (top + ROW_HEIGHT > element.scrollTop + element.clientHeight - HEADER_HEIGHT)
            element.scrollTop = top + ROW_HEIGHT - element.clientHeight + HEADER_HEIGHT
        const left = offsets[clamped.col] - NUMBER_WIDTH
        const right = offsets[clamped.col + 1]
        if (left < element.scrollLeft) element.scrollLeft = left
        else if (right > element.scrollLeft + element.clientWidth) element.scrollLeft = right - element.clientWidth
    }

    const startEdit = (cell: Cell, value = cellValue(cell)) => {
        if (!readOnly) setEditing({ ...cell, value })
    }

    const finishing = useRef(false)
    const finishEdit = (move?: Cell) => {
        // Focusing the grid blurs the editor, which would finish it again.
        if (!editing || finishing.current) return
        finishing.current = true
        requestAnimationFrame(() => {
            finishing.current = false
        })
        const current = cellValue(editing)
        if (editing.value !== current) commit(setCells(table.rows, editing, [[editing.value]]))
        setEditing(null)
        if (move) select(move)
        scroller.current?.focus()
    }

    const selectedBlock = () =>
        Array.from({ length: range.bottom - range.top + 1 }, (_, row) =>
            Array.from({ length: range.right - range.left + 1 }, (_, col) =>
                cellValue({ row: range.top + row, col: range.left + col }),
            ),
        )

    const clearRange = () => {
        const block = selectedBlock().map((row) => row.map(() => ''))
        commit(setCells(table.rows, { row: range.top, col: range.left }, block))
    }

    // Rows and columns ----------------------------------------------------

    const insertRows = (at: number) => {
        const next = [...table.rows]
        const count = range.bottom - range.top + 1
        next.splice(at, 0, ...Array.from({ length: count }, () => Array<string>(columns).fill('')))
        commit(next)
    }

    const deleteRows = () => {
        commit(table.rows.filter((_, index) => index < range.top || index > range.bottom))
        select({ row: range.top, col: focus.col })
    }

    const insertColumns = (at: number) => {
        const count = range.right - range.left + 1
        commit(
            table.rows.map((row) => {
                const next = [...row]
                while (next.length < at) next.push('')
                next.splice(at, 0, ...Array<string>(count).fill(''))
                return next
            }),
        )
    }

    const deleteColumns = () => {
        commit(table.rows.map((row) => row.filter((_, index) => index < range.left || index > range.right)))
        select({ row: focus.row, col: range.left })
    }

    const sort = (descending: boolean) => {
        const col = focus.col
        const first = header ? table.rows.slice(0, 1) : []
        const body = table.rows.slice(first.length)
        const collator = new Intl.Collator(undefined, { numeric: true, sensitivity: 'base' })
        const sorted = [...body].sort((a, b) => {
            const left = a[col] ?? ''
            const right = b[col] ?? ''
            // Empty cells last, either way.
            if (!left || !right) return left ? -1 : right ? 1 : 0
            return descending ? collator.compare(right, left) : collator.compare(left, right)
        })
        commit([...first, ...sorted])
    }

    // Keyboard and clipboard ---------------------------------------------

    const onKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
        if (editing) return
        const mod = event.ctrlKey || event.metaKey
        const key = event.key
        const moves: Record<string, Cell> = {
            ArrowUp: { row: focus.row - 1, col: focus.col },
            ArrowDown: { row: focus.row + 1, col: focus.col },
            ArrowLeft: { row: focus.row, col: focus.col - 1 },
            ArrowRight: { row: focus.row, col: focus.col + 1 },
            PageUp: { row: focus.row - 20, col: focus.col },
            PageDown: { row: focus.row + 20, col: focus.col },
        }
        if (moves[key]) {
            const target = mod
                ? key === 'ArrowUp'
                    ? { row: 0, col: focus.col }
                    : key === 'ArrowDown'
                      ? { row: shownRows - 1, col: focus.col }
                      : key === 'ArrowLeft'
                        ? { row: focus.row, col: 0 }
                        : key === 'ArrowRight'
                          ? { row: focus.row, col: shownColumns - 1 }
                          : moves[key]
                : moves[key]
            select(target, event.shiftKey)
        } else if (key === 'Home') select(mod ? { row: 0, col: 0 } : { row: focus.row, col: 0 }, event.shiftKey)
        else if (key === 'End')
            select(mod ? { row: shownRows - 1, col: shownColumns - 1 } : { row: focus.row, col: shownColumns - 1 }, event.shiftKey)
        else if (key === 'Tab') select({ row: focus.row, col: focus.col + (event.shiftKey ? -1 : 1) })
        else if (key === 'Enter' || key === 'F2') startEdit(focus)
        else if (key === 'Delete' || key === 'Backspace') clearRange()
        else if (mod && key.toLowerCase() === 'a') {
            setAnchor({ row: 0, col: 0 })
            setFocus({ row: shownRows - 1, col: shownColumns - 1 })
        } else if (mod && key.toLowerCase() === 'z' && !event.shiftKey) onUndo()
        else if (mod && (key.toLowerCase() === 'y' || (key.toLowerCase() === 'z' && event.shiftKey))) onRedo()
        else if (!mod && !event.altKey && key.length === 1) {
            startEdit(focus, key)
        } else return
        event.preventDefault()
    }

    const onCopy = (event: ClipboardEvent, cut = false) => {
        if (editing) return
        event.preventDefault()
        event.clipboardData.setData('text/plain', toTsv(selectedBlock()))
        if (cut) clearRange()
    }

    const onPaste = (event: ClipboardEvent) => {
        if (editing || readOnly) return
        event.preventDefault()
        const pasted = parseCsv(event.clipboardData.getData('text/plain'), '\t').rows
        if (pasted.length === 0) return
        const at = { row: range.top, col: range.left }
        commit(setCells(table.rows, at, pasted))
        setAnchor(at)
        setFocus({ row: at.row + pasted.length - 1, col: at.col + columnCount(pasted) - 1 })
    }

    // Mouse ---------------------------------------------------------------

    const dragging = useRef(false)
    const cellAt = (event: ReactPointerEvent): Cell | null => {
        const element = (event.target as HTMLElement).closest<HTMLElement>('[data-cell]')
        if (!element) return null
        const [row, col] = element.dataset.cell!.split(':').map(Number)
        return { row, col }
    }

    const resize = (col: number, event: ReactPointerEvent) => {
        event.preventDefault()
        event.stopPropagation()
        const start = event.clientX
        const initial = widthOf(col)
        const move = (moved: PointerEvent) =>
            setWidths((existing) => ({ ...existing, [col]: Math.max(MIN_WIDTH, initial + moved.clientX - start) }))
        const up = () => {
            window.removeEventListener('pointermove', move)
            window.removeEventListener('pointerup', up)
        }
        window.addEventListener('pointermove', move)
        window.addEventListener('pointerup', up)
    }

    // Rendering -----------------------------------------------------------

    const first = Math.max(0, Math.floor(scroll.top / ROW_HEIGHT) - OVERSCAN)
    const last = Math.min(shownRows, Math.ceil((scroll.top + scroll.height) / ROW_HEIGHT) + OVERSCAN)
    const totalWidth = offsets[shownColumns]
    const inRange = (row: number, col: number) =>
        row >= range.top && row <= range.bottom && col >= range.left && col <= range.right
    const hasRange = range.top !== range.bottom || range.left !== range.right

    const button = (label: string, icon: ReactNode, action: () => void, disabled = false) => (
        <button
            type="button"
            className="plugin-ide-tool"
            aria-label={label}
            title={label}
            disabled={readOnly || disabled}
            onClick={() => {
                action()
                scroller.current?.focus()
            }}
        >
            {icon}
        </button>
    )

    return (
        <div className="csv-grid">
            <div className="csv-grid-toolbar" role="toolbar" aria-label="Table tools">
                <span className="csv-grid-ref" aria-live="polite">
                    {columnName(range.left)}
                    {range.top + 1}
                    {hasRange && `:${columnName(range.right)}${range.bottom + 1}`}
                </span>
                <input
                    className="csv-grid-formula"
                    aria-label="Cell value"
                    value={editing ? editing.value : cellValue(focus)}
                    readOnly={readOnly}
                    onFocus={() => !editing && startEdit(focus)}
                    onChange={(event) => setEditing({ ...focus, value: event.target.value })}
                    onKeyDown={(event) => {
                        if (event.key === 'Enter') finishEdit({ row: focus.row + 1, col: focus.col })
                        if (event.key === 'Escape') {
                            setEditing(null)
                            scroller.current?.focus()
                        }
                    }}
                    onBlur={() => editing && finishEdit()}
                />
                <span className="csv-grid-sep" />
                {button('Insert rows above', <BetweenHorizontalStart size={15} />, () => insertRows(range.top))}
                {button('Insert rows below', <BetweenHorizontalEnd size={15} />, () => insertRows(range.bottom + 1))}
                {button('Delete rows', <TableRowsSplit size={15} />, deleteRows, range.top >= table.rows.length)}
                {button('Insert columns left', <BetweenVerticalStart size={15} />, () => insertColumns(range.left))}
                {button('Insert columns right', <BetweenVerticalEnd size={15} />, () => insertColumns(range.right + 1))}
                {button('Delete columns', <TableColumnsSplit size={15} />, deleteColumns, range.left >= columns)}
                {button('Sort A to Z by this column', <ArrowDownAZ size={15} />, () => sort(false))}
                {button('Sort Z to A by this column', <ArrowUpAZ size={15} />, () => sort(true))}
                <span className="csv-grid-sep" />
                <button
                    type="button"
                    className={`plugin-ide-tool${header ? ' is-active' : ''}`}
                    aria-pressed={header}
                    aria-label="First row is a header"
                    title="First row is a header (kept on top when scrolling and sorting)"
                    onClick={() => setHeader((value) => !value)}
                >
                    <Rows3 size={15} />
                </button>
                <label className="csv-grid-delimiter" title="How the file separates its values">
                    <span>Delimiter</span>
                    <select
                        value={delimiter}
                        onChange={(event) => {
                            setDelimiter(event.target.value)
                            scroller.current?.focus()
                        }}
                    >
                        {DELIMITERS.map((item) => (
                            <option key={item.value} value={item.value}>
                                {item.label}
                            </option>
                        ))}
                    </select>
                </label>
                <span className="csv-grid-size">
                    {table.rows.length} × {columnCount(table.rows)}
                </span>
            </div>

            <div
                ref={scroller}
                className="csv-grid-scroll"
                tabIndex={0}
                role="grid"
                aria-label="CSV table"
                aria-rowcount={shownRows}
                aria-colcount={shownColumns}
                aria-readonly={readOnly}
                onScroll={(event) =>
                    setScroll({ top: event.currentTarget.scrollTop, height: event.currentTarget.clientHeight })
                }
                onKeyDown={onKeyDown}
                onCopy={(event) => onCopy(event)}
                onCut={(event) => !readOnly && onCopy(event, true)}
                onPaste={onPaste}
                onPointerDown={(event) => {
                    const cell = cellAt(event)
                    if (!cell || event.button !== 0) return
                    if (editing) finishEdit()
                    dragging.current = true
                    select(cell, event.shiftKey)
                }}
                onPointerMove={(event) => {
                    if (!dragging.current) return
                    const cell = cellAt(event)
                    if (cell) setFocus(cell)
                }}
                onPointerUp={() => {
                    dragging.current = false
                }}
                onDoubleClick={(event) => {
                    const element = (event.target as HTMLElement).closest<HTMLElement>('[data-cell]')
                    if (!element) return
                    const [row, col] = element.dataset.cell!.split(':').map(Number)
                    startEdit({ row, col })
                }}
            >
                <div className="csv-grid-canvas" style={{ width: totalWidth, height: HEADER_HEIGHT + shownRows * ROW_HEIGHT }}>
                    <div className="csv-grid-head" style={{ width: totalWidth }} role="row">
                        <div
                            className="csv-grid-corner"
                            style={{ width: NUMBER_WIDTH }}
                            title="Select all"
                            onPointerDown={(event) => {
                                event.stopPropagation()
                                setAnchor({ row: 0, col: 0 })
                                setFocus({ row: shownRows - 1, col: shownColumns - 1 })
                            }}
                        />
                        {Array.from({ length: shownColumns }, (_, col) => (
                            <div
                                key={col}
                                role="columnheader"
                                className={`csv-grid-colhead${col >= range.left && col <= range.right ? ' is-selected' : ''}${col >= columns ? ' is-extra' : ''}`}
                                style={{ width: widthOf(col) }}
                                onPointerDown={(event) => {
                                    event.stopPropagation()
                                    const from = event.shiftKey ? anchor.col : col
                                    setAnchor({ row: 0, col: from })
                                    setFocus({ row: shownRows - 1, col })
                                }}
                            >
                                {columnName(col)}
                                <span
                                    className="csv-grid-resize"
                                    onPointerDown={(event) => resize(col, event)}
                                    onDoubleClick={() =>
                                        setWidths((existing) => {
                                            const next = { ...existing }
                                            delete next[col]
                                            return next
                                        })
                                    }
                                />
                            </div>
                        ))}
                    </div>
                    {header && scroll.top > 0 && table.rows.length > 0 && (
                        <div className="csv-grid-pinned" style={{ width: totalWidth, top: HEADER_HEIGHT }} role="row">
                            <div className="csv-grid-rownum" style={{ width: NUMBER_WIDTH }}>
                                1
                            </div>
                            {Array.from({ length: shownColumns }, (_, col) => (
                                <div
                                    key={col}
                                    data-cell={`0:${col}`}
                                    className={`csv-grid-cell${inRange(0, col) ? ' is-selected' : ''}`}
                                    style={{ width: widthOf(col) }}
                                >
                                    {(table.rows[0][col] ?? '').replace(/\r?\n/g, ' ↵ ')}
                                </div>
                            ))}
                        </div>
                    )}

                    {Array.from({ length: last - first }, (_, offset) => {
                        const row = first + offset
                        const values = table.rows[row]
                        const isHeader = header && row === 0 && values !== undefined
                        return (
                            <div
                                key={row}
                                role="row"
                                className={`csv-grid-row${isHeader ? ' is-header' : ''}${values === undefined ? ' is-extra' : ''}`}
                                style={{ top: HEADER_HEIGHT + row * ROW_HEIGHT, width: totalWidth }}
                            >
                                <div
                                    className={`csv-grid-rownum${row >= range.top && row <= range.bottom ? ' is-selected' : ''}`}
                                    style={{ width: NUMBER_WIDTH }}
                                    onPointerDown={(event) => {
                                        event.stopPropagation()
                                        const from = event.shiftKey ? anchor.row : row
                                        setAnchor({ row: from, col: 0 })
                                        setFocus({ row, col: shownColumns - 1 })
                                    }}
                                >
                                    {row + 1}
                                </div>
                                {Array.from({ length: shownColumns }, (_, col) => {
                                    const value = values?.[col] ?? ''
                                    const active = focus.row === row && focus.col === col
                                    const isEditing = editing?.row === row && editing.col === col
                                    return (
                                        <div
                                            key={col}
                                            role="gridcell"
                                            data-cell={`${row}:${col}`}
                                            aria-selected={inRange(row, col)}
                                            className={`csv-grid-cell${inRange(row, col) ? ' is-selected' : ''}${active ? ' is-active' : ''}${
                                                /^-?\d+([.,]\d+)?$/.test(value.trim()) ? ' is-number' : ''
                                            }`}
                                            style={{ width: widthOf(col) }}
                                            title={value.length > 20 || value.includes('\n') ? value : undefined}
                                        >
                                            {isEditing ? (
                                                <textarea
                                                    ref={editor}
                                                    className="csv-grid-input"
                                                    value={editing.value}
                                                    rows={1}
                                                    aria-label={`Cell ${columnName(col)}${row + 1}`}
                                                    onChange={(event) => setEditing({ row, col, value: event.target.value })}
                                                    onBlur={() => finishEdit()}
                                                    onKeyDown={(event) => {
                                                        event.stopPropagation()
                                                        if (event.key === 'Escape') {
                                                            event.preventDefault()
                                                            setEditing(null)
                                                            scroller.current?.focus()
                                                        } else if (event.key === 'Enter' && !event.altKey && !event.shiftKey) {
                                                            event.preventDefault()
                                                            finishEdit({ row: row + 1, col })
                                                        } else if (event.key === 'Tab') {
                                                            event.preventDefault()
                                                            finishEdit({ row, col: col + (event.shiftKey ? -1 : 1) })
                                                        } else if (event.key === 'Enter') {
                                                            // Alt/Shift + Enter: a line break inside the cell.
                                                            event.preventDefault()
                                                            const target = event.currentTarget
                                                            const start = target.selectionStart
                                                            const value = `${editing.value.slice(0, start)}\n${editing.value.slice(target.selectionEnd)}`
                                                            setEditing({ row, col, value })
                                                            requestAnimationFrame(() => target.setSelectionRange(start + 1, start + 1))
                                                        }
                                                    }}
                                                />
                                            ) : (
                                                value.replace(/\r?\n/g, ' ↵ ')
                                            )}
                                        </div>
                                    )
                                })}
                            </div>
                        )
                    })}
                </div>
            </div>
        </div>
    )
}
