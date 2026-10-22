import { useEffect, useRef } from 'react'
import type { editor } from 'monaco-editor'

import { monaco, useMonacoTheme } from '../monacoTools'

/**
 * A small Monaco editor (the request's JSON/raw body, the response body).
 * The editor fills its `.eagle-code` frame; `value` changes from outside
 * replace the text, typing reports through `onChange`.
 */
export default function CodeEditor({
    value,
    language,
    onChange,
    readOnly = false,
    label,
}: {
    value: string
    language: string
    onChange?: (value: string) => void
    readOnly?: boolean
    label: string
}) {
    const containerRef = useRef<HTMLDivElement>(null)
    const editorRef = useRef<editor.IStandaloneCodeEditor | null>(null)
    const onChangeRef = useRef(onChange)
    const theme = useMonacoTheme()

    useEffect(() => {
        onChangeRef.current = onChange
    }, [onChange])

    useEffect(() => {
        const container = containerRef.current
        if (!container) return

        const instance = monaco.editor.create(container, {
            model: monaco.editor.createModel('', 'plaintext'),
            automaticLayout: true,
            fontSize: 13,
            minimap: { enabled: false },
            scrollBeyondLastLine: false,
            wordWrap: 'on',
            tabSize: 2,
            lineNumbersMinChars: 3,
            ariaLabel: label,
            fixedOverflowWidgets: true,
        })
        const listener = instance.onDidChangeModelContent(() => {
            onChangeRef.current?.(instance.getValue())
        })
        editorRef.current = instance

        return () => {
            listener.dispose()
            const model = instance.getModel()
            instance.dispose()
            model?.dispose()
            editorRef.current = null
        }
    }, [label])

    useEffect(() => {
        monaco.editor.setTheme(theme)
    }, [theme])

    useEffect(() => {
        editorRef.current?.updateOptions({ readOnly })
    }, [readOnly])

    useEffect(() => {
        const model = editorRef.current?.getModel()
        if (!model) return
        monaco.editor.setModelLanguage(model, language)
    }, [language])

    useEffect(() => {
        const instance = editorRef.current
        if (!instance || instance.getValue() === value) return
        instance.getModel()?.setValue(value)
    }, [value])

    return <div ref={containerRef} className="eagle-code-editor" />
}
