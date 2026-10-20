import { useEffect, useRef } from 'react'
import type { editor } from 'monaco-editor'

import { monaco } from './monaco'
import '../../../styles/diff-view.css'

/**
 * Read-only side-by-side or inline diff, filling its positioned parent.
 *
 * Owns its Monaco lifecycle so models are always detached from the diff
 * widget before either is disposed, and every render shows current text.
 */
export default function DiffView({
    original,
    modified,
    language,
    theme,
    sideBySide,
}: {
    original: string
    modified: string
    language: string
    theme: string
    sideBySide: boolean
}) {
    const containerRef = useRef<HTMLDivElement>(null)
    const diffRef = useRef<editor.IStandaloneDiffEditor | null>(null)

    useEffect(() => {
        const container = containerRef.current
        if (!container) return

        const diff = monaco.editor.createDiffEditor(container, {
            readOnly: true,
            originalEditable: false,
            automaticLayout: true,
            fontSize: 13,
            scrollBeyondLastLine: false,
            theme,
        })

        diffRef.current = diff

        return () => {
            const model = diff.getModel()
            diff.setModel(null)
            diff.dispose()
            model?.original.dispose()
            model?.modified.dispose()
            diffRef.current = null
        }
    }, [theme])

    useEffect(() => {
        const diff = diffRef.current
        if (!diff) return

        const previous = diff.getModel()

        diff.setModel({
            original: monaco.editor.createModel(original, language),
            modified: monaco.editor.createModel(modified, language),
        })

        previous?.original.dispose()
        previous?.modified.dispose()
    }, [original, modified, language, theme])

    useEffect(() => {
        diffRef.current?.updateOptions({ renderSideBySide: sideBySide })
    }, [sideBySide, theme])

    return <div ref={containerRef} className="diff-view" />
}
