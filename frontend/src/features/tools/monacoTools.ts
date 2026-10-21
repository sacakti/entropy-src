/**
 * Monaco for the compare tools: the shared bundled setup plus the extra
 * languages the tools offer (XML, SQL, shell). Imported only by the lazily
 * loaded tools, so none of this reaches the main bundle.
 */
import { useSyncExternalStore } from 'react'

import { monaco } from '../plugins/editor/monaco'
import 'monaco-editor/esm/vs/basic-languages/xml/xml.contribution'
import 'monaco-editor/esm/vs/basic-languages/sql/sql.contribution'
import 'monaco-editor/esm/vs/basic-languages/shell/shell.contribution'

export { monaco }

export type MonacoTheme = 'entropy-light' | 'entropy-dark'

function currentTheme(): MonacoTheme {
    const light =
        document.documentElement.dataset.theme === 'light' ||
        Boolean(document.querySelector('.entropy-app')?.classList.contains('theme-light'))

    return light ? 'entropy-light' : 'entropy-dark'
}

function subscribe(onChange: () => void): () => void {
    const observer = new MutationObserver(onChange)
    const app = document.querySelector('.entropy-app')

    // Only the two elements that carry the theme; Monaco changes classes
    // inside the page constantly.
    observer.observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] })
    if (app) observer.observe(app, { attributes: true, attributeFilter: ['class'] })

    return () => observer.disconnect()
}

/** Monaco theme that follows the app theme, also when it changes while open. */
export function useMonacoTheme(): MonacoTheme {
    return useSyncExternalStore(subscribe, currentTheme, currentTheme)
}
