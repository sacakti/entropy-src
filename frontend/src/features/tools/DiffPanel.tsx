import { useState, type ReactNode } from 'react'
import { ArrowLeftRight, CircleCheck, Columns2, LoaderCircle, Rows2 } from 'lucide-react'

import { LANGUAGES, type LanguageId } from './files'
import { useMonacoTheme } from './monacoTools'
import ToolDiff, { type DiffStats } from './ToolDiff'

/** Language picker shared by the compare tools. */
export function LanguageSelect({
    value,
    onChange,
}: {
    value: LanguageId
    onChange: (value: LanguageId) => void
}) {
    return (
        <label className="tools-field">
            <span>Language</span>
            <select
                className="entropy-select"
                value={value}
                onChange={(event) => onChange(event.target.value as LanguageId)}
            >
                {LANGUAGES.map((language) => (
                    <option key={language.id} value={language.id}>
                        {language.label}
                    </option>
                ))}
            </select>
        </label>
    )
}

/**
 * Diff view with the compare options (language, whitespace, layout, swap)
 * and the added/removed line counts. Fills the width of its parent.
 */
export default function DiffPanel({
    original,
    modified,
    originalLabel,
    modifiedLabel,
    language,
    onLanguageChange,
    onSwap,
    actions,
}: {
    original: string
    modified: string
    originalLabel: string
    modifiedLabel: string
    language: LanguageId
    onLanguageChange: (language: LanguageId) => void
    onSwap?: () => void
    /** Extra buttons at the start of the toolbar (e.g. "Edit texts"). */
    actions?: ReactNode
}) {
    const theme = useMonacoTheme()
    const [sideBySide, setSideBySide] = useState(true)
    const [ignoreWhitespace, setIgnoreWhitespace] = useState(false)
    const [stats, setStats] = useState<DiffStats | null>(null)

    return (
        <div className="tools-diff">
            <div className="tools-diff-toolbar">
                <div className="tools-diff-toolbar-start">
                    {actions}
                    <LanguageSelect value={language} onChange={onLanguageChange} />
                    <label className="tools-check" title="Ignore leading and trailing whitespace on each line">
                        <input
                            type="checkbox"
                            checked={ignoreWhitespace}
                            onChange={(event) => setIgnoreWhitespace(event.target.checked)}
                        />
                        Ignore whitespace
                    </label>
                </div>

                <div className="tools-diff-toolbar-end">
                    {onSwap && (
                        <button
                            type="button"
                            className="entropy-button entropy-button-secondary entropy-button-sm"
                            onClick={onSwap}
                        >
                            <ArrowLeftRight size={14} /> Swap sides
                        </button>
                    )}
                    <button
                        type="button"
                        className="entropy-button entropy-button-secondary entropy-button-sm"
                        onClick={() => setSideBySide((value) => !value)}
                    >
                        {sideBySide ? <Rows2 size={14} /> : <Columns2 size={14} />}
                        {sideBySide ? 'Inline' : 'Side by side'}
                    </button>
                </div>
            </div>

            <div className="tools-diff-summary" aria-live="polite">
                <span className="tools-diff-side" title={originalLabel}>
                    {originalLabel}
                </span>
                <span className="tools-diff-stats">
                    {stats === null ? (
                        <span className="tools-diff-computing">
                            <LoaderCircle size={13} className="entropy-spin" /> Comparing…
                        </span>
                    ) : stats.changes === 0 ? (
                        <span className="tools-diff-same">
                            <CircleCheck size={13} /> No differences
                        </span>
                    ) : (
                        <>
                            <span className="tools-diff-added" title="Lines added">
                                +{stats.added.toLocaleString()}
                            </span>
                            <span className="tools-diff-removed" title="Lines removed">
                                −{stats.removed.toLocaleString()}
                            </span>
                            <span className="tools-diff-hunks">
                                {stats.changes.toLocaleString()} change{stats.changes === 1 ? '' : 's'}
                            </span>
                        </>
                    )}
                </span>
                <span className="tools-diff-side" title={modifiedLabel}>
                    {modifiedLabel}
                </span>
            </div>

            <div className="tools-diff-frame">
                <ToolDiff
                    original={original}
                    modified={modified}
                    language={language}
                    theme={theme}
                    sideBySide={sideBySide}
                    ignoreWhitespace={ignoreWhitespace}
                    onStats={setStats}
                />
            </div>
        </div>
    )
}
