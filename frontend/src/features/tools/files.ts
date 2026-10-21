/**
 * Browser-side file helpers shared by the compare tools: reading text
 * files safely, guessing an editor language and comparing contents.
 * Nothing here talks to the server.
 */

export const MAX_TEXT_BYTES = 5 * 1024 * 1024

export const LANGUAGES = [
    { id: 'plaintext', label: 'Plain text' },
    { id: 'json', label: 'JSON' },
    { id: 'yaml', label: 'YAML' },
    { id: 'xml', label: 'XML' },
    { id: 'sql', label: 'SQL' },
    { id: 'python', label: 'Python' },
    { id: 'shell', label: 'Shell' },
] as const

export type LanguageId = (typeof LANGUAGES)[number]['id']

const EXTENSION_LANGUAGES: Record<string, LanguageId> = {
    json: 'json',
    jsonc: 'json',
    ipynb: 'json',
    yaml: 'yaml',
    yml: 'yaml',
    xml: 'xml',
    xsd: 'xml',
    xsl: 'xml',
    xslt: 'xml',
    svg: 'xml',
    pom: 'xml',
    wsdl: 'xml',
    config: 'xml',
    sql: 'sql',
    pls: 'sql',
    plsql: 'sql',
    pks: 'sql',
    pkb: 'sql',
    pck: 'sql',
    prc: 'sql',
    fnc: 'sql',
    trg: 'sql',
    vw: 'sql',
    ddl: 'sql',
    dml: 'sql',
    py: 'python',
    pyw: 'python',
    pyi: 'python',
    sh: 'shell',
    bash: 'shell',
    ksh: 'shell',
    zsh: 'shell',
    env: 'shell',
}

const NAME_LANGUAGES: Record<string, LanguageId> = {
    dockerfile: 'shell',
    makefile: 'shell',
    '.bashrc': 'shell',
    '.profile': 'shell',
    '.bash_profile': 'shell',
}

/** Editor language for a file name, plain text when unknown. */
export function languageFromName(name: string): LanguageId {
    const base = name.split('/').pop()?.toLowerCase() ?? ''
    if (NAME_LANGUAGES[base]) return NAME_LANGUAGES[base]

    const dot = base.lastIndexOf('.')
    if (dot < 0) return 'plaintext'

    return EXTENSION_LANGUAGES[base.slice(dot + 1)] ?? 'plaintext'
}

export function formatSize(bytes: number): string {
    if (bytes < 1024) return `${bytes} B`

    const units = ['KB', 'MB', 'GB', 'TB']
    let size = bytes / 1024
    let unit = 0

    while (size >= 1024 && unit < units.length - 1) {
        size /= 1024
        unit += 1
    }

    return `${size >= 10 ? Math.round(size) : size.toFixed(1)} ${units[unit]}`
}

export class TextFileError extends Error {}

/** A NUL byte in the first few kilobytes marks a file as binary, as git does. */
function looksBinary(bytes: Uint8Array): boolean {
    const end = Math.min(bytes.length, 8000)

    for (let index = 0; index < end; index += 1) {
        if (bytes[index] === 0) return true
    }

    return false
}

/**
 * Read a file as text for the diff editor.
 *
 * Rejects binary and oversized files with a message meant for the user.
 * UTF-8 is tried first; legacy single-byte files fall back to Windows-1252
 * so they still compare instead of failing.
 */
export async function readTextFile(file: File, maxBytes = MAX_TEXT_BYTES): Promise<string> {
    if (file.size > maxBytes) {
        throw new TextFileError(
            `${file.name} is ${formatSize(file.size)}; files up to ${formatSize(maxBytes)} can be compared as text.`,
        )
    }

    const bytes = new Uint8Array(await file.arrayBuffer())

    if (looksBinary(bytes)) {
        throw new TextFileError(`${file.name} looks like a binary file; only text files can be compared line by line.`)
    }

    let text: string

    try {
        text = new TextDecoder('utf-8', { fatal: true }).decode(bytes)
    } catch {
        text = new TextDecoder('windows-1252').decode(bytes)
    }

    return text.charCodeAt(0) === 0xfeff ? text.slice(1) : text
}

// ----------------------------------------------------------------------
// Content equality
// ----------------------------------------------------------------------

/** Files up to this size are hashed whole; larger ones are compared in slices. */
const HASH_LIMIT = 64 * 1024 * 1024
const SLICE_BYTES = 8 * 1024 * 1024

function hasSubtleCrypto(): boolean {
    // crypto.subtle only exists in secure contexts (HTTPS or localhost).
    return typeof crypto !== 'undefined' && typeof crypto.subtle?.digest === 'function'
}

async function sha256(file: File): Promise<string> {
    const digest = await crypto.subtle.digest('SHA-256', await file.arrayBuffer())

    return Array.from(new Uint8Array(digest), (byte) => byte.toString(16).padStart(2, '0')).join('')
}

function sameBytes(left: Uint8Array, right: Uint8Array): boolean {
    if (left.length !== right.length) return false

    for (let index = 0; index < left.length; index += 1) {
        if (left[index] !== right[index]) return false
    }

    return true
}

async function sameSlices(left: File, right: File): Promise<boolean> {
    for (let offset = 0; offset < left.size; offset += SLICE_BYTES) {
        const [a, b] = await Promise.all([
            left.slice(offset, offset + SLICE_BYTES).arrayBuffer(),
            right.slice(offset, offset + SLICE_BYTES).arrayBuffer(),
        ])

        if (!sameBytes(new Uint8Array(a), new Uint8Array(b))) return false
    }

    return true
}

/**
 * Whether two files have the same content: size first, then SHA-256.
 *
 * Without Web Crypto (plain HTTP) or for very large files, the bytes are
 * compared slice by slice instead, which is exact and stops at the first
 * difference.
 */
export async function sameContent(left: File, right: File): Promise<boolean> {
    if (left.size !== right.size) return false
    if (left.size === 0) return true

    if (hasSubtleCrypto() && left.size <= HASH_LIMIT) {
        const [a, b] = await Promise.all([sha256(left), sha256(right)])
        return a === b
    }

    return sameSlices(left, right)
}

// ----------------------------------------------------------------------
// Folder input
// ----------------------------------------------------------------------

export type FolderEntry = { path: string; file: File }

export type PickedFolder = {
    name: string
    files: FolderEntry[]
}

/** Files from an `<input webkitdirectory>`, with the root folder stripped from paths. */
export function folderFromInput(list: FileList): PickedFolder | null {
    const files = Array.from(list)
    if (files.length === 0) return null

    const name = (files[0].webkitRelativePath || files[0].name).split('/')[0]

    return {
        name,
        files: files.map((file) => {
            const relative = file.webkitRelativePath || file.name
            const slash = relative.indexOf('/')

            return { path: slash >= 0 ? relative.slice(slash + 1) : relative, file }
        }),
    }
}

function readEntries(reader: FileSystemDirectoryReader): Promise<FileSystemEntry[]> {
    return new Promise((resolve, reject) => reader.readEntries(resolve, reject))
}

function entryFile(entry: FileSystemFileEntry): Promise<File> {
    return new Promise((resolve, reject) => entry.file(resolve, reject))
}

/**
 * Walk a dropped directory. `readEntries` returns at most ~100 entries per
 * call, so each directory is read until it comes back empty.
 */
export async function folderFromEntry(
    root: FileSystemDirectoryEntry,
    onProgress?: (count: number) => void,
): Promise<PickedFolder> {
    const files: FolderEntry[] = []
    const pending: { entry: FileSystemDirectoryEntry; prefix: string }[] = [{ entry: root, prefix: '' }]

    while (pending.length > 0) {
        const { entry, prefix } = pending.pop() as { entry: FileSystemDirectoryEntry; prefix: string }
        const reader = entry.createReader()

        for (;;) {
            const batch = await readEntries(reader)
            if (batch.length === 0) break

            for (const child of batch) {
                const path = `${prefix}${child.name}`

                if (child.isDirectory) {
                    pending.push({ entry: child as FileSystemDirectoryEntry, prefix: `${path}/` })
                } else if (child.isFile) {
                    files.push({ path, file: await entryFile(child as FileSystemFileEntry) })
                }
            }

            onProgress?.(files.length)
        }
    }

    return { name: root.name, files }
}

/**
 * The dropped directory, if any. Must be called synchronously inside the
 * drop handler: the DataTransfer is emptied once the event returns.
 */
export function droppedDirectory(dataTransfer: DataTransfer): FileSystemDirectoryEntry | null | undefined {
    const item = Array.from(dataTransfer.items).find((candidate) => candidate.kind === 'file')

    if (!item) return null
    if (typeof item.webkitGetAsEntry !== 'function') return undefined

    const entry = item.webkitGetAsEntry()

    return entry?.isDirectory ? (entry as FileSystemDirectoryEntry) : null
}
