// Monaco ships no typings for its feature-complete core entry; it exposes the
// same API as the package root.
declare module 'monaco-editor/esm/vs/editor/edcore.main' {
    export * from 'monaco-editor'
}
