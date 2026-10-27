/** CSV text <-> rows of cells (RFC 4180, with the file's own delimiter and line ends). */

export interface CsvTable {
    rows: string[][]
    delimiter: string
    /** Line end written between rows: the file's first one, else LF. */
    eol: '\r\n' | '\n'
    /** The text ended with a line end (kept when written back). */
    trailingEol: boolean
}

export const DELIMITERS: Array<{ value: string; label: string }> = [
    { value: ',', label: 'Comma' },
    { value: ';', label: 'Semicolon' },
    { value: '\t', label: 'Tab' },
    { value: '|', label: 'Pipe' },
]

/** The delimiter used most often outside quotes in the first lines. */
export function detectDelimiter(text: string): string {
    const counts = new Map<string, number>(DELIMITERS.map((item) => [item.value, 0]))
    let quoted = false
    let lines = 0

    for (let index = 0; index < text.length && lines < 20; index += 1) {
        const char = text[index]
        if (char === '"') quoted = !quoted
        else if (!quoted && char === '\n') lines += 1
        else if (!quoted && counts.has(char)) counts.set(char, (counts.get(char) ?? 0) + 1)
    }

    let best = ','
    for (const [delimiter, count] of counts) if (count > (counts.get(best) ?? 0)) best = delimiter
    return best
}

export function parseCsv(text: string, delimiter = detectDelimiter(text)): CsvTable {
    const rows: string[][] = []
    let row: string[] = []
    let cell = ''
    let quoted = false
    let eol: CsvTable['eol'] | null = null
    let index = 0

    const endRow = () => {
        row.push(cell)
        rows.push(row)
        row = []
        cell = ''
    }

    while (index < text.length) {
        const char = text[index]

        if (quoted) {
            if (char === '"' && text[index + 1] === '"') {
                cell += '"'
                index += 2
                continue
            }
            if (char === '"') quoted = false
            else cell += char
            index += 1
            continue
        }

        if (char === '"' && cell === '') quoted = true
        else if (char === delimiter) {
            row.push(cell)
            cell = ''
        } else if (char === '\r' || char === '\n') {
            const crlf = char === '\r' && text[index + 1] === '\n'
            eol = eol ?? (crlf ? '\r\n' : '\n')
            endRow()
            if (crlf) index += 1
        } else cell += char
        index += 1
    }

    const trailingEol = text.length > 0 && (text.endsWith('\n') || text.endsWith('\r')) && !quoted
    if (!trailingEol && text.length > 0) endRow()

    return { rows, delimiter, eol: eol ?? '\n', trailingEol }
}

function quote(cell: string, delimiter: string): string {
    return cell.includes(delimiter) || /["\r\n]/.test(cell) ? `"${cell.replace(/"/g, '""')}"` : cell
}

export function writeCsv(table: CsvTable): string {
    const body = table.rows
        .map((row) => row.map((cell) => quote(cell, table.delimiter)).join(table.delimiter))
        .join(table.eol)
    return table.trailingEol && table.rows.length > 0 ? body + table.eol : body
}

/** Spreadsheet column name: 0 -> A, 25 -> Z, 26 -> AA. */
export function columnName(index: number): string {
    let name = ''
    let value = index + 1
    while (value > 0) {
        const rest = (value - 1) % 26
        name = String.fromCharCode(65 + rest) + name
        value = Math.floor((value - 1) / 26)
    }
    return name
}

export function columnCount(rows: string[][]): number {
    return rows.reduce((most, row) => Math.max(most, row.length), 0)
}
