/**
 * Plugin SDK language support for Python plugin sources.
 *
 * Completion and hover are driven by the SDK catalog the server builds by
 * introspecting the real SDK classes, so they track the SDK as it changes.
 */
import type { IDisposable, IRange, Position, editor, languages } from 'monaco-editor'

import type {
    PluginDiagnostic,
    PluginSdkCatalog,
    SdkMember,
    SdkType,
} from '../../../api/plugins.api'
import type { Monaco } from './monaco'

const CHAIN = /\bself((?:\.[A-Za-z_]\w*)*)\.([A-Za-z_]\w*)?$/

/** Resolve `self.a.b` to the SDK type of `b`, or null when it leaves the SDK. */
function resolveChain(
    catalog: PluginSdkCatalog,
    segments: string[],
): SdkType | null {
    let current: SdkType | undefined = catalog.types[catalog.root]

    for (const segment of segments) {
        const member: SdkMember | undefined = current?.members.find(
            (item) => item.name === segment,
        )

        if (!member?.type) return null

        current = catalog.types[member.type]
    }

    return current ?? null
}

function memberDetail(member: SdkMember): string {
    if (member.kind === 'method') {
        return `${member.name}${member.signature ?? '()'}`
    }

    return `${member.name}: ${member.annotation ?? member.type ?? 'Any'}`
}

function importInsertLine(model: editor.ITextModel): number {
    let line = 1

    for (let index = 1; index <= model.getLineCount(); index += 1) {
        if (/^(from\s+\S+\s+import|import)\s/.test(model.getLineContent(index))) {
            line = index + 1
        }
    }

    return line
}

export function registerSdkLanguage(
    monaco: Monaco,
    catalog: PluginSdkCatalog,
): IDisposable {
    const { CompletionItemKind, CompletionItemInsertTextRule } =
        monaco.languages

    const completion = monaco.languages.registerCompletionItemProvider(
        'python',
        {
            triggerCharacters: ['.'],

            provideCompletionItems(model, position) {
                const before = model
                    .getLineContent(position.lineNumber)
                    .slice(0, position.column - 1)
                const word = model.getWordUntilPosition(position)
                const range: IRange = {
                    startLineNumber: position.lineNumber,
                    endLineNumber: position.lineNumber,
                    startColumn: word.startColumn,
                    endColumn: word.endColumn,
                }

                const chain = CHAIN.exec(before)

                if (chain) {
                    const segments = chain[1].split('.').filter(Boolean)
                    const type = resolveChain(catalog, segments)

                    if (!type) return { suggestions: [] }

                    return {
                        suggestions: type.members.map((member) => ({
                            label: member.name,
                            kind:
                                member.kind === 'method'
                                    ? CompletionItemKind.Method
                                    : CompletionItemKind.Property,
                            detail: memberDetail(member),
                            documentation: member.doc
                                ? { value: member.doc }
                                : undefined,
                            insertText:
                                member.kind === 'method'
                                    ? `${member.name}($0)`
                                    : member.name,
                            insertTextRules:
                                member.kind === 'method'
                                    ? CompletionItemInsertTextRule.InsertAsSnippet
                                    : undefined,
                            sortText: `0${member.name}`,
                            range,
                        })),
                    }
                }

                // Bare identifiers: offer SDK symbols with an auto-import.
                if (/\.\w*$/.test(before)) return { suggestions: [] }

                const source = model.getValue()
                const importLine = importInsertLine(model)

                return {
                    suggestions: catalog.symbols.map((symbol) => {
                        const imported = new RegExp(
                            `import[^\\n]*\\b${symbol.name}\\b`,
                        ).test(source)

                        return {
                            label: symbol.name,
                            kind:
                                symbol.kind === 'class'
                                    ? CompletionItemKind.Class
                                    : CompletionItemKind.Function,
                            detail: imported
                                ? `${symbol.module}.${symbol.name}`
                                : `Auto-import from ${symbol.module}`,
                            documentation: symbol.doc
                                ? { value: symbol.doc }
                                : undefined,
                            insertText: symbol.name,
                            additionalTextEdits: imported
                                ? undefined
                                : [
                                      {
                                          range: {
                                              startLineNumber: importLine,
                                              endLineNumber: importLine,
                                              startColumn: 1,
                                              endColumn: 1,
                                          },
                                          text: `from ${symbol.module} import ${symbol.name}\n`,
                                      },
                                  ],
                            range,
                        }
                    }),
                }
            },
        },
    )

    const hover = monaco.languages.registerHoverProvider('python', {
        provideHover(model, position: Position): languages.Hover | null {
            const word = model.getWordAtPosition(position)

            if (!word) return null

            const line = model.getLineContent(position.lineNumber)
            const before = line.slice(0, word.endColumn - 1)
            const chain = CHAIN.exec(before)

            if (!chain) return null

            const segments = chain[1].split('.').filter(Boolean)
            const type = resolveChain(catalog, segments)
            const member = type?.members.find((item) => item.name === word.word)

            if (!type || !member) return null

            return {
                range: {
                    startLineNumber: position.lineNumber,
                    endLineNumber: position.lineNumber,
                    startColumn: word.startColumn,
                    endColumn: word.endColumn,
                },
                contents: [
                    {
                        value: `\`\`\`python\n(${member.kind}) ${type.name}.${memberDetail(member)}\n\`\`\``,
                    },
                    ...(member.doc ? [{ value: member.doc }] : []),
                ],
            }
        },
    })

    return {
        dispose() {
            completion.dispose()
            hover.dispose()
        },
    }
}

export function toMarkers(
    monaco: Monaco,
    diagnostics: PluginDiagnostic[],
): editor.IMarkerData[] {
    const severity = {
        error: monaco.MarkerSeverity.Error,
        warning: monaco.MarkerSeverity.Warning,
        info: monaco.MarkerSeverity.Info,
    }

    return diagnostics.map((item) => ({
        severity: severity[item.severity] ?? monaco.MarkerSeverity.Error,
        message: item.message,
        source: `entropy:${item.source}`,
        startLineNumber: item.line,
        startColumn: item.column,
        endLineNumber: item.end_line ?? item.line,
        endColumn:
            item.end_column && (item.end_line ?? item.line) >= item.line
                ? item.end_column
                : item.column + 1,
    }))
}
