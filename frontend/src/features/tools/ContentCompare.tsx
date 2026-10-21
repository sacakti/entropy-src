import { useState } from 'react'
import Editor from '@monaco-editor/react'
import { ArrowLeftRight, Eraser, GitCompareArrows, Pencil } from 'lucide-react'

import DiffPanel, { LanguageSelect } from './DiffPanel'
import type { LanguageId } from './files'
import { useMonacoTheme } from './monacoTools'

const EDITOR_OPTIONS = {
    automaticLayout: true,
    fontSize: 13,
    minimap: { enabled: false },
    scrollBeyondLastLine: false,
    tabSize: 4,
    wordWrap: 'off',
    renderWhitespace: 'selection',
} as const

function TextInput({
    label,
    path,
    value,
    language,
    onChange,
}: {
    label: string
    path: string
    value: string
    language: LanguageId
    onChange: (value: string) => void
}) {
    const theme = useMonacoTheme()
    const lines = value ? value.split('\n').length : 0

    return (
        <div className="tools-input">
            <div className="tools-input-heading">
                <strong>{label}</strong>
                <span>
                    {lines.toLocaleString()} line{lines === 1 ? '' : 's'}
                </span>
            </div>
            <div className="tools-input-editor">
                <Editor
                    path={path}
                    value={value}
                    language={language}
                    theme={theme}
                    onChange={(next) => onChange(next ?? '')}
                    options={{ ...EDITOR_OPTIONS, ariaLabel: `${label} text` }}
                />
            </div>
        </div>
    )
}

/** Text compare: paste or type two texts, then review the diff. */
export default function ContentCompare() {
    const [left, setLeft] = useState('')
    const [right, setRight] = useState('')
    const [language, setLanguage] = useState<LanguageId>('plaintext')
    const [comparing, setComparing] = useState(false)

    const swap = () => {
        setLeft(right)
        setRight(left)
    }

    if (comparing) {
        return (
            <DiffPanel
                original={left}
                modified={right}
                originalLabel="Original"
                modifiedLabel="Changed"
                language={language}
                onLanguageChange={setLanguage}
                onSwap={swap}
                actions={
                    <button
                        type="button"
                        className="entropy-button entropy-button-secondary entropy-button-sm"
                        onClick={() => setComparing(false)}
                    >
                        <Pencil size={14} /> Edit texts
                    </button>
                }
            />
        )
    }

    const empty = !left && !right

    return (
        <div className="tools-content-compare">
            <div className="tools-diff-toolbar">
                <div className="tools-diff-toolbar-start">
                    <LanguageSelect value={language} onChange={setLanguage} />
                </div>
                <div className="tools-diff-toolbar-end">
                    <button
                        type="button"
                        className="entropy-button entropy-button-ghost entropy-button-sm"
                        onClick={() => {
                            setLeft('')
                            setRight('')
                        }}
                        disabled={empty}
                    >
                        <Eraser size={14} /> Clear
                    </button>
                    <button
                        type="button"
                        className="entropy-button entropy-button-secondary entropy-button-sm"
                        onClick={swap}
                        disabled={empty}
                    >
                        <ArrowLeftRight size={14} /> Swap sides
                    </button>
                    <button
                        type="button"
                        className="entropy-button entropy-button-primary entropy-button-sm"
                        onClick={() => setComparing(true)}
                        disabled={empty}
                        title={empty ? 'Paste or type text on at least one side' : undefined}
                    >
                        <GitCompareArrows size={14} /> Compare
                    </button>
                </div>
            </div>

            <div className="tools-input-pair">
                <TextInput
                    label="Original"
                    path="entropy-tools://content-compare/original"
                    value={left}
                    language={language}
                    onChange={setLeft}
                />
                <TextInput
                    label="Changed"
                    path="entropy-tools://content-compare/changed"
                    value={right}
                    language={language}
                    onChange={setRight}
                />
            </div>
        </div>
    )
}
