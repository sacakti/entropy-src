import { useEffect, useRef } from 'react'
import type { editor } from 'monaco-editor'

import { monaco, type MonacoTheme } from './monacoTools'
import '../../styles/diff-view.css'

export type DiffStats = {
    added: number
    removed: number
    /** Changed regions (hunks). */
    changes: number
}

function statsOf(changes: editor.ILineChange[]): DiffStats {
    let added = 0
    let removed = 0

    for (const change of changes) {
        // An end line of 0 means the side has no lines in this change.
        if (change.originalEndLineNumber > 0) {
            removed += change.originalEndLineNumber - change.originalStartLineNumber + 1
        }
        if (change.modifiedEndLineNumber > 0) {
            added += change.modifiedEndLineNumber - change.modifiedStartLineNumber + 1
        }
    }

    return { added, removed, changes: changes.length }
}

/**
 * Read-only Monaco diff for the compare tools.
 *
 * Same lifecycle as the plugin editor's DiffView (models are detached
 * before disposal; the view fills its positioned parent via .diff-view),
 * plus whitespace handling and line counts reported through `onStats`.
 */
export default function ToolDiff({
    original,
    modified,
    language,
    theme,
    sideBySide,
    ignoreWhitespace,
    onStats,
}: {
    original: string
    modified: string
    language: string
    theme: MonacoTheme
    sideBySide: boolean
    ignoreWhitespace: boolean
    onStats?: (stats: DiffStats | null) => void
}) {
    const containerRef = useRef<HTMLDivElement>(null)
    const diffRef = useRef<editor.IStandaloneDiffEditor | null>(null)
    const onStatsRef = useRef(onStats)

    useEffect(() => {
        onStatsRef.current = onStats
    }, [onStats])

    useEffect(() => {
        const container = containerRef.current
        if (!container) return

        const diff = monaco.editor.createDiffEditor(container, {
            readOnly: true,
            originalEditable: false,
            automaticLayout: true,
            fontSize: 13,
            scrollBeyondLastLine: false,
            renderOverviewRuler: true,
            // Large pasted files: keep computing instead of giving up after 5 s.
            maxComputationTime: 0,
            maxFileSize: 0,
        })

        const listener = diff.onDidUpdateDiff(() => {
            const changes = diff.getLineChanges()
            onStatsRef.current?.(changes ? statsOf(changes) : null)
        })

        diffRef.current = diff

        return () => {
            listener.dispose()
            const model = diff.getModel()
            diff.setModel(null)
            diff.dispose()
            model?.original.dispose()
            model?.modified.dispose()
            diffRef.current = null
        }
    }, [])

    useEffect(() => {
        monaco.editor.setTheme(theme)
    }, [theme])

    useEffect(() => {
        const diff = diffRef.current
        if (!diff) return

        const previous = diff.getModel()

        onStatsRef.current?.(null)
        diff.setModel({
            original: monaco.editor.createModel(original, language),
            modified: monaco.editor.createModel(modified, language),
        })

        previous?.original.dispose()
        previous?.modified.dispose()
    }, [original, modified, language])

    useEffect(() => {
        diffRef.current?.updateOptions({
            renderSideBySide: sideBySide,
            ignoreTrimWhitespace: ignoreWhitespace,
        })
    }, [sideBySide, ignoreWhitespace])

    return <div ref={containerRef} className="diff-view" />
}
