import { useEffect, useRef } from 'react'
import Editor, { type OnMount } from '@monaco-editor/react'
import { AlertCircle, CheckCircle2 } from 'lucide-react'

import { monaco } from '../../plugins/editor/monaco'
import type { CodeFormat, ParseFailure } from './model'

export default function CodeView({
    text,
    format,
    failure,
    theme,
    onChange,
    onSaveShortcut,
    readOnly = false,
}: {
    text: string
    format: CodeFormat
    failure: ParseFailure | null
    theme: string
    onChange: (text: string) => void
    onSaveShortcut: () => void
    /** View only: the definition cannot be changed. */
    readOnly?: boolean
}) {
    const editorRef = useRef<Parameters<OnMount>[0] | null>(null)
    const saveRef = useRef(onSaveShortcut)

    useEffect(() => {
        saveRef.current = onSaveShortcut
    }, [onSaveShortcut])

    // Syntax errors as editor markers.
    useEffect(() => {
        const model = editorRef.current?.getModel()
        if (!model) return

        monaco.editor.setModelMarkers(
            model,
            'workflow-syntax',
            failure
                ? [
                      {
                          severity: monaco.MarkerSeverity.Error,
                          message: failure.message,
                          startLineNumber: failure.line,
                          startColumn: failure.column,
                          endLineNumber: failure.line,
                          endColumn: failure.column + 1,
                      },
                  ]
                : [],
        )
    }, [failure, text])

    return (
        <div className="wf-code">
            <div className="wf-code-editor">
                <Editor
                    path={`workflow-builder://definition.${format}`}
                    language={format}
                    value={text}
                    theme={theme}
                    onChange={(value) => onChange(value ?? '')}
                    onMount={(editor, instance) => {
                        editorRef.current = editor
                        editor.addCommand(instance.KeyMod.CtrlCmd | instance.KeyCode.KeyS, () =>
                            saveRef.current(),
                        )
                    }}
                    options={{
                        automaticLayout: true,
                        fontSize: 13,
                        minimap: { enabled: false },
                        scrollBeyondLastLine: false,
                        tabSize: format === 'json' ? 4 : 2,
                        insertSpaces: true,
                        readOnly,
                    }}
                />
            </div>

            <footer className={`wf-code-status${failure ? ' is-error' : ''}`} role="status">
                {failure ? (
                    <>
                        <AlertCircle size={14} />
                        {format.toUpperCase()} syntax error at line {failure.line}, column{' '}
                        {failure.column}: {failure.message}
                    </>
                ) : (
                    <>
                        <CheckCircle2 size={14} />
                        Valid {format.toUpperCase()} syntax
                    </>
                )}
            </footer>
        </div>
    )
}
