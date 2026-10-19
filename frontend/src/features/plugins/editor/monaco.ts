/**
 * Bundled Monaco setup.
 *
 * Entropy is often deployed without Internet access, so Monaco is bundled
 * locally instead of being fetched from a CDN, and only the languages plugin
 * development needs (Python, JSON, YAML, Markdown) are included.
 */
import * as monaco from 'monaco-editor/esm/vs/editor/edcore.main'
import 'monaco-editor/esm/vs/basic-languages/python/python.contribution'
import 'monaco-editor/esm/vs/basic-languages/markdown/markdown.contribution'
import 'monaco-editor/esm/vs/basic-languages/yaml/yaml.contribution'
import 'monaco-editor/esm/vs/language/json/monaco.contribution'
import EditorWorker from 'monaco-editor/esm/vs/editor/editor.worker?worker'
import JsonWorker from 'monaco-editor/esm/vs/language/json/json.worker?worker'
import { loader } from '@monaco-editor/react'

self.MonacoEnvironment = {
    getWorker(_workerId: string, label: string) {
        return label === 'json' ? new JsonWorker() : new EditorWorker()
    },
}

monaco.editor.defineTheme('entropy-dark', {
    base: 'vs-dark',
    inherit: true,
    rules: [],
    colors: {
        'editor.background': '#0d1117',
        'editorGutter.background': '#0d1117',
        'diffEditor.insertedTextBackground': '#3fb95033',
        'diffEditor.removedTextBackground': '#f8514933',
    },
})

monaco.editor.defineTheme('entropy-light', {
    base: 'vs',
    inherit: true,
    rules: [],
    colors: {
        'editor.background': '#ffffff',
    },
})

loader.config({ monaco })

export { monaco }
export type Monaco = typeof monaco
