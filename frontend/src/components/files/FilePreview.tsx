import { useEffect, useMemo, useState } from 'react'
import { Code2, Download, Eye, FileText, Folder, LoaderCircle, Search, ShieldAlert, Table2, WrapText } from 'lucide-react'

import { fileKind } from './fileKind'

// Text beyond this is not loaded; the file can be downloaded instead.
const TEXT_LIMIT = 2 * 1024 * 1024

export type ArchiveBrowse = {
    entriesUrl: string
    entryUrl: (path: string) => string
    entryPreviewUrl: (path: string) => string
}

type Sheet = { name: string; rows: string[][]; total_rows: number; truncated: boolean }
type OfficePreview = { kind: 'sheet'; sheets: Sheet[] } | { kind: 'document'; html: string }
// Rows drawn for CSV; the rest stay in the raw view.
const CSV_ROWS = 2000

type Entry = { name: string; size: number; directory: boolean; encrypted: boolean; modified: string }
type Listing = { entries: Entry[]; total: number; truncated: boolean }

const formatBytes = (bytes: number) => {
    if (bytes < 1024) return `${bytes} B`
    const units = ['KB', 'MB', 'GB', 'TB']
    let value = bytes / 1024
    let index = 0
    while (value >= 1024 && index < units.length - 1) {
        value /= 1024
        index += 1
    }
    return `${value.toFixed(value >= 10 ? 0 : 1)} ${units[index]}`
}

async function failure(response: Response) {
    try {
        const body = (await response.json()) as { detail?: unknown }
        if (typeof body.detail === 'string') return body.detail
    } catch {
        // Not JSON: fall back to the status.
    }
    return `Unable to load the file (${response.status}).`
}

type Loaded = { url: string; text?: string; truncated?: boolean; source?: string; error?: string }

function useContent(url: string, mode: 'text' | 'blob' | null, type?: string) {
    const [loaded, setLoaded] = useState<Loaded | null>(null)
    useEffect(() => {
        if (!mode) return
        const controller = new AbortController()
        let source: string | undefined
        void (async () => {
            try {
                const response = await fetch(url, {
                    credentials: 'same-origin',
                    cache: 'no-store',
                    signal: controller.signal,
                    // Only the start of a long text file is needed.
                    headers: mode === 'text' ? { Range: `bytes=0-${TEXT_LIMIT - 1}` } : undefined,
                })
                if (!response.ok) throw new Error(await failure(response))
                const blob = await response.blob()
                if (mode === 'text') {
                    const total = Number(response.headers.get('Content-Range')?.split('/')[1] ?? blob.size)
                    setLoaded({ url, text: await blob.slice(0, TEXT_LIMIT).text(), truncated: total > TEXT_LIMIT || blob.size > TEXT_LIMIT })
                } else {
                    source = URL.createObjectURL(type ? new Blob([blob], { type }) : blob)
                    setLoaded({ url, source })
                }
            } catch (cause) {
                if (!controller.signal.aborted) setLoaded({ url, error: cause instanceof Error ? cause.message : 'Unable to load the file.' })
            }
        })()
        return () => {
            controller.abort()
            if (source) URL.revokeObjectURL(source)
        }
    }, [url, mode, type])
    return loaded?.url === url ? loaded : null
}

function Loading() {
    return <div className="file-preview-center"><LoaderCircle size={22} className="entropy-spin" aria-label="Loading" /></div>
}

function Problem({ text }: { text: string }) {
    return <div className="file-preview-center"><p className="file-preview-muted">{text}</p></div>
}

function TextPreview({ url, html }: { url: string; html?: boolean }) {
    const loaded = useContent(url, 'text')
    const [wrap, setWrap] = useState(true)
    const [mode, setMode] = useState<'visual' | 'raw'>('visual')
    const [scripts, setScripts] = useState(false)
    if (!loaded) return <Loading />
    if (loaded.error) return <Problem text={loaded.error} />
    const visual = html && mode === 'visual'
    return (
        <div className="file-preview-text">
            <div className="file-preview-bar">
                {html && (
                    <span className="file-preview-switch" role="group" aria-label="HTML view">
                        <button type="button" className={mode === 'visual' ? 'is-active' : ''} onClick={() => setMode('visual')}><Eye size={14} /> Visual</button>
                        <button type="button" className={mode === 'raw' ? 'is-active' : ''} onClick={() => setMode('raw')}><Code2 size={14} /> Raw</button>
                    </span>
                )}
                {visual ? (
                    <label className="file-preview-check" title="Scripts run isolated from Entropy (no access to your session), but only enable them for files you trust.">
                        <input type="checkbox" checked={scripts} onChange={(event) => setScripts(event.target.checked)} />
                        <ShieldAlert size={14} /> Run scripts
                    </label>
                ) : (
                    <button type="button" className={`entropy-button entropy-button-ghost entropy-button-sm${wrap ? ' is-active' : ''}`} onClick={() => setWrap(!wrap)} aria-pressed={wrap}>
                        <WrapText size={14} /> Wrap lines
                    </button>
                )}
                {loaded.truncated && <span className="file-preview-muted">Showing the first {formatBytes(TEXT_LIMIT)}; download for the rest.</span>}
            </div>
            {visual ? (
                // No same-origin access: the page cannot reach Entropy's session or API.
                <iframe key={String(scripts)} className="file-preview-frame is-html" title="HTML preview" sandbox={scripts ? 'allow-scripts' : ''} srcDoc={loaded.text} />
            ) : (
                <pre className={wrap ? 'is-wrapped' : ''}>{loaded.text || '(empty file)'}</pre>
            )}
        </div>
    )
}

function useJson<T>(url: string) {
    const [loaded, setLoaded] = useState<{ url: string; value?: T; error?: string } | null>(null)
    useEffect(() => {
        const controller = new AbortController()
        void (async () => {
            try {
                const response = await fetch(url, { credentials: 'same-origin', cache: 'no-store', signal: controller.signal })
                if (!response.ok) throw new Error(await failure(response))
                setLoaded({ url, value: (await response.json()) as T })
            } catch (cause) {
                if (!controller.signal.aborted) setLoaded({ url, error: cause instanceof Error ? cause.message : 'Unable to load the preview.' })
            }
        })()
        return () => controller.abort()
    }, [url])
    return loaded?.url === url ? loaded : null
}

const columnName = (index: number) => {
    let name = ''
    for (let value = index + 1; value > 0; value = Math.floor((value - 1) / 26)) name = String.fromCharCode(65 + ((value - 1) % 26)) + name
    return name
}

function Grid({ rows, header }: { rows: string[][]; header?: boolean }) {
    const width = rows.reduce((most, row) => Math.max(most, row.length), 0)
    const body = header ? rows.slice(1) : rows
    return (
        <div className="file-grid-wrap">
            <table className="file-grid">
                <thead>
                    <tr>
                        <th />
                        {Array.from({ length: width }, (_, index) => (
                            <th key={index}>{header ? rows[0]?.[index] ?? '' : columnName(index)}</th>
                        ))}
                    </tr>
                </thead>
                <tbody>
                    {body.map((row, index) => (
                        <tr key={index}>
                            <th>{index + (header ? 2 : 1)}</th>
                            {Array.from({ length: width }, (_, column) => <td key={column}>{row[column] ?? ''}</td>)}
                        </tr>
                    ))}
                </tbody>
            </table>
        </div>
    )
}

function SheetPreview({ sheets }: { sheets: Sheet[] }) {
    const [active, setActive] = useState(0)
    const sheet = sheets[active]
    if (!sheet) return <Problem text="The workbook has no sheets." />
    return (
        <div className="file-preview-text">
            <div className="file-preview-bar">
                <span className="file-preview-switch" role="tablist" aria-label="Sheets">
                    {sheets.map((item, index) => (
                        <button key={`${item.name}-${index}`} type="button" role="tab" aria-selected={index === active} className={index === active ? 'is-active' : ''} onClick={() => setActive(index)}>
                            <Table2 size={14} /> {item.name}
                        </button>
                    ))}
                </span>
                <span className="file-preview-muted">
                    {sheet.truncated ? `Showing the first ${sheet.rows.length} of ${sheet.total_rows} rows; download for the rest.` : `${sheet.rows.length} rows`}
                </span>
            </div>
            {sheet.rows.length ? <Grid key={active} rows={sheet.rows} /> : <Problem text="This sheet is empty." />}
        </div>
    )
}

// Word documents arrive as escaped HTML; shown isolated, like a page.
const DOCUMENT_STYLE = `<style>
body{margin:0;padding:32px 40px;font:15px/1.6 Georgia,'Times New Roman',serif;color:#1f2328;background:#fff;max-width:860px}
h1,h2,h3,h4,h5,h6{font-family:system-ui,sans-serif;line-height:1.3;margin:1.2em 0 .4em}
p{margin:0 0 .7em}ul{margin:0 0 .8em 1.4em;padding:0}
table{border-collapse:collapse;margin:.6em 0 1em;font:13px/1.45 system-ui,sans-serif}
td{border:1px solid #d0d7de;padding:5px 8px;vertical-align:top}
</style>`

function OfficeDocument({ url }: { url: string }) {
    const loaded = useJson<OfficePreview>(url)
    if (!loaded) return <Loading />
    if (loaded.error || !loaded.value) return <Problem text={loaded.error ?? 'Unable to load the preview.'} />
    const preview = loaded.value
    if (preview.kind === 'sheet') return <SheetPreview sheets={preview.sheets} />
    return (
        <div className="file-preview-text">
            <div className="file-preview-bar"><span className="file-preview-muted">Text, headings, lists and tables only; images and page layout are left out.</span></div>
            <iframe className="file-preview-frame" title="Document preview" sandbox="" srcDoc={DOCUMENT_STYLE + (preview.html || '<p><em>The document is empty.</em></p>')} />
        </div>
    )
}

/** Quoted fields, doubled quotes and line breaks inside quotes (RFC 4180). */
function parseCsv(text: string, delimiter: string): string[][] {
    const rows: string[][] = []
    let row: string[] = []
    let field = ''
    let quoted = false
    for (let index = 0; index < text.length && rows.length < CSV_ROWS; index += 1) {
        const char = text[index]
        if (quoted) {
            if (char === '"' && text[index + 1] === '"') {
                field += '"'
                index += 1
            } else if (char === '"') quoted = false
            else field += char
        } else if (char === '"' && field === '') quoted = true
        else if (char === delimiter) {
            row.push(field)
            field = ''
        } else if (char === '\n' || char === '\r') {
            if (char === '\r' && text[index + 1] === '\n') index += 1
            row.push(field)
            rows.push(row)
            row = []
            field = ''
        } else field += char
    }
    if (field || row.length) rows.push([...row, field])
    return rows
}

function CsvPreview({ url, name }: { url: string; name: string }) {
    const loaded = useContent(url, 'text')
    const [mode, setMode] = useState<'table' | 'raw'>('table')
    const rows = useMemo(() => {
        if (!loaded?.text) return []
        const firstLine = loaded.text.split('\n', 1)[0]
        const delimiter = /\.tsv$/i.test(name) ? '\t' : !firstLine.includes(',') && firstLine.includes(';') ? ';' : ','
        return parseCsv(loaded.text, delimiter)
    }, [loaded, name])
    if (!loaded) return <Loading />
    if (loaded.error) return <Problem text={loaded.error} />
    return (
        <div className="file-preview-text">
            <div className="file-preview-bar">
                <span className="file-preview-switch" role="group" aria-label="CSV view">
                    <button type="button" className={mode === 'table' ? 'is-active' : ''} onClick={() => setMode('table')}><Table2 size={14} /> Table</button>
                    <button type="button" className={mode === 'raw' ? 'is-active' : ''} onClick={() => setMode('raw')}><Code2 size={14} /> Raw</button>
                </span>
                <span className="file-preview-muted">
                    {rows.length >= CSV_ROWS || loaded.truncated ? `Showing the first ${rows.length} rows; download for the rest.` : `${Math.max(0, rows.length - 1)} rows`}
                </span>
            </div>
            {mode === 'table' ? (rows.length ? <Grid rows={rows} header /> : <Problem text="The file is empty." />) : <pre>{loaded.text}</pre>}
        </div>
    )
}

function PdfPreview({ url }: { url: string }) {
    const loaded = useContent(url, 'blob', 'application/pdf')
    if (!loaded) return <Loading />
    if (loaded.error) return <Problem text={loaded.error} />
    return <iframe className="file-preview-frame" title="PDF preview" src={loaded.source} />
}

function ImagePreview({ url, name }: { url: string; name: string }) {
    // Fetched, so an SVG renders as an image and errors can be shown.
    const loaded = useContent(url, 'blob', /\.svg$/i.test(name) ? 'image/svg+xml' : undefined)
    if (!loaded) return <Loading />
    if (loaded.error) return <Problem text={loaded.error} />
    return <div className="file-preview-center is-media"><img src={loaded.source} alt={name} /></div>
}

function ArchivePreview({ browse }: { browse: ArchiveBrowse }) {
    const [listing, setListing] = useState<Listing | { error: string } | null>(null)
    const [filter, setFilter] = useState('')
    const [selected, setSelected] = useState<Entry | null>(null)

    useEffect(() => {
        const controller = new AbortController()
        void (async () => {
            try {
                const response = await fetch(browse.entriesUrl, { credentials: 'same-origin', cache: 'no-store', signal: controller.signal })
                if (!response.ok) throw new Error(await failure(response))
                setListing((await response.json()) as Listing)
            } catch (cause) {
                if (!controller.signal.aborted) setListing({ error: cause instanceof Error ? cause.message : 'Unable to list the archive.' })
            }
        })()
        return () => controller.abort()
    }, [browse.entriesUrl])

    const files = useMemo(() => {
        if (!listing || 'error' in listing) return []
        const needle = filter.trim().toLowerCase()
        return listing.entries.filter((entry) => !entry.directory && (!needle || entry.name.toLowerCase().includes(needle)))
    }, [listing, filter])

    if (!listing) return <Loading />
    if ('error' in listing) return <Problem text={listing.error} />
    const entryUrl = selected ? browse.entryUrl(selected.name) : ''

    return (
        <div className="file-archive">
            <aside className="file-archive-list">
                <label className="file-archive-search">
                    <Search size={14} />
                    <input value={filter} onChange={(event) => setFilter(event.target.value)} placeholder="Filter files…" aria-label="Filter files in the archive" />
                </label>
                <small className="file-preview-muted">
                    {files.length} of {listing.entries.filter((entry) => !entry.directory).length} files
                    {listing.truncated ? ` · first ${listing.entries.length} of ${listing.total} entries` : ''}
                </small>
                <ul>
                    {files.map((entry) => {
                        const slash = entry.name.lastIndexOf('/')
                        return (
                            <li key={entry.name}>
                                <button type="button" className={selected?.name === entry.name ? 'is-active' : ''} onClick={() => setSelected(entry)} disabled={entry.encrypted} title={entry.encrypted ? 'Encrypted' : entry.name}>
                                    <FileText size={14} />
                                    <span>
                                        <strong>{entry.name.slice(slash + 1)}</strong>
                                        {slash > 0 && <small><Folder size={11} /> {entry.name.slice(0, slash)}</small>}
                                    </span>
                                    <em>{formatBytes(entry.size)}</em>
                                </button>
                            </li>
                        )
                    })}
                </ul>
            </aside>
            <section className="file-archive-view">
                {selected ? (
                    <>
                        <header>
                            <strong title={selected.name}>{selected.name}</strong>
                            <small className="file-preview-muted">{formatBytes(selected.size)} · {selected.modified}</small>
                            <a className="entropy-button entropy-button-ghost entropy-button-icon entropy-button-sm" href={entryUrl} download={selected.name.split('/').pop()} aria-label={`Download ${selected.name}`} title="Download this file">
                                <Download size={15} />
                            </a>
                        </header>
                        <FilePreview key={selected.name} name={selected.name} url={entryUrl} previewUrl={browse.entryPreviewUrl(selected.name)} />
                    </>
                ) : (
                    <Problem text="Choose a file to view it." />
                )}
            </section>
        </div>
    )
}

/**
 * The best view of a file the browser can give: images, video, audio, PDF,
 * HTML (visual or raw), CSV, Excel and Word (via the server), text, and the
 * files inside ZIP-format archives.
 */
export default function FilePreview({ name, url, previewUrl, browse }: {
    name: string
    url: string
    // Where the server turns spreadsheets and Word documents into a preview.
    previewUrl?: string
    browse?: ArchiveBrowse
}) {
    const kind = fileKind(name)
    if (kind === 'image') return <ImagePreview url={url} name={name} />
    if (kind === 'video') return <div className="file-preview-center is-media"><video src={url} controls preload="metadata" /></div>
    if (kind === 'audio') return <div className="file-preview-center"><audio src={url} controls preload="metadata" /></div>
    if (kind === 'pdf') return <PdfPreview url={url} />
    if (kind === 'html') return <TextPreview url={url} html />
    if (kind === 'csv') return <CsvPreview url={url} name={name} />
    if ((kind === 'sheet' || kind === 'document') && previewUrl) return <OfficeDocument url={previewUrl} />
    if (kind === 'legacy') return <Problem text="Older binary Office files (.xls, .doc, .ppt) and presentations cannot be previewed. Download the file, or save it as .xlsx/.docx to preview it." />
    if (kind === 'text') return <TextPreview url={url} />
    if (kind === 'archive' && browse) return <ArchivePreview browse={browse} />
    return <Problem text={kind === 'archive' ? 'Archives inside archives cannot be opened here; download it to look inside.' : 'There is no preview for this type of file. Download it to open it.'} />
}
