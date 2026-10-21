import { useRef, useState } from 'react'
import { FileText, LoaderCircle } from 'lucide-react'

import DiffPanel from './DiffPanel'
import DropZone from './DropZone'
import { MAX_TEXT_BYTES, TextFileError, formatSize, languageFromName, readTextFile, type LanguageId } from './files'

type Side = 'left' | 'right'

type LoadedFile = { name: string; size: number; text: string }

type SlotState = {
    file: LoadedFile | null
    loading: boolean
    error: string | null
}

const EMPTY_SLOT: SlotState = { file: null, loading: false, error: null }

/** File compare: pick or drop two text files and review the diff. */
export default function FileCompare() {
    const [slots, setSlots] = useState<Record<Side, SlotState>>({ left: EMPTY_SLOT, right: EMPTY_SLOT })
    const [language, setLanguage] = useState<LanguageId | null>(null)
    const inputs = {
        left: useRef<HTMLInputElement>(null),
        right: useRef<HTMLInputElement>(null),
    }
    // Ignore a slow read that a newer pick for the same side replaced.
    const tokens = useRef<Record<Side, number>>({ left: 0, right: 0 })

    const update = (side: Side, next: SlotState) => setSlots((current) => ({ ...current, [side]: next }))

    const load = async (side: Side, files: FileList | File[] | null | undefined) => {
        const list = Array.from(files ?? [])
        if (list.length === 0) return

        const token = ++tokens.current[side]
        const file = list[0]

        if (list.length > 1) {
            update(side, { ...EMPTY_SLOT, error: 'Drop one file per side.' })
            return
        }

        update(side, { file: null, loading: true, error: null })

        try {
            const text = await readTextFile(file)
            if (token !== tokens.current[side]) return
            update(side, { file: { name: file.name, size: file.size, text }, loading: false, error: null })
            // A new file brings its own language guess.
            setLanguage(null)
        } catch (error) {
            if (token !== tokens.current[side]) return
            update(side, {
                file: null,
                loading: false,
                error:
                    error instanceof TextFileError
                        ? error.message
                        : `${file.name} could not be read. If it is a folder, use Folder compare.`,
            })
        }
    }

    const clear = (side: Side) => {
        tokens.current[side] += 1
        update(side, EMPTY_SLOT)
        if (inputs[side].current) inputs[side].current.value = ''
    }

    const left = slots.left.file
    const right = slots.right.file
    const guessed = languageFromName(left?.name ?? right?.name ?? '')
    const effectiveLanguage =
        language ?? (guessed === 'plaintext' && right ? languageFromName(right.name) : guessed)

    return (
        <div className="tools-file-compare">
            <div className="tools-drop-pair">
                {(['left', 'right'] as const).map((side) => {
                    const slot = slots[side]

                    return (
                        <div key={side} className="tools-drop-slot">
                            <DropZone
                                label={side === 'left' ? 'Original file' : 'Changed file'}
                                icon={<FileText size={22} />}
                                prompt="Drop a text file here"
                                pickLabel="Choose file…"
                                picked={slot.file ? { name: slot.file.name, detail: formatSize(slot.file.size) } : null}
                                busy={
                                    slot.loading ? (
                                        <>
                                            <LoaderCircle size={16} className="entropy-spin" />
                                            <span>Reading file…</span>
                                        </>
                                    ) : null
                                }
                                error={slot.error}
                                onPick={() => inputs[side].current?.click()}
                                onDrop={(event) => void load(side, event.dataTransfer.files)}
                                onClear={() => clear(side)}
                            />
                            <input
                                ref={inputs[side]}
                                type="file"
                                hidden
                                onChange={(event) => void load(side, event.target.files)}
                            />
                        </div>
                    )
                })}
            </div>

            {left && right ? (
                <DiffPanel
                    original={left.text}
                    modified={right.text}
                    originalLabel={left.name}
                    modifiedLabel={right.name}
                    language={effectiveLanguage}
                    onLanguageChange={setLanguage}
                    onSwap={() => setSlots((current) => ({ left: current.right, right: current.left }))}
                />
            ) : (
                <div className="tools-empty">
                    <FileText size={22} aria-hidden="true" />
                    <strong>Choose two files to compare</strong>
                    <p>
                        Any text file up to {formatSize(MAX_TEXT_BYTES)}. Files are read in your browser and never
                        uploaded.
                    </p>
                </div>
            )}
        </div>
    )
}
