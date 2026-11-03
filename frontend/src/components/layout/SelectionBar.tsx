import { useEffect, useRef, useState } from 'react'
import { LoaderCircle, X } from 'lucide-react'

import { isTyping, useShortcuts } from './useShortcuts'

/** Several bars can be on a page (run app tables): the latest one takes the shortcuts. */
const mounted: object[] = []

/**
 * How much of a paginated list to select: this page, or everything that matches
 * the current search and filters. Clicking the active choice again cancels it, and
 * so does Clear. The list's header checkbox adds or removes this page's rows.
 *
 * Mod+A and Mod+Shift+A do the same as the buttons, unless someone is typing or a
 * dialog is open: then the browser keeps those keys.
 *
 * `onSelectAll` may be async (lists paged on the server fetch the rest); leave it
 * out when the rows of other pages cannot be selected.
 */
export default function SelectionBar({
    noun,
    pageCount,
    total,
    pageSelected,
    selectedCount,
    onSelectPage,
    onSelectAll,
    onClear,
    disabled = false,
}: {
    /** Plural, for example "plugins". */
    noun: string
    pageCount: number
    total: number
    /** Selected rows on this page. */
    pageSelected: number
    /** Selected rows in all. */
    selectedCount: number
    onSelectPage: () => void
    onSelectAll?: () => void | Promise<void>
    onClear: () => void
    disabled?: boolean
}) {
    const [loadingAll, setLoadingAll] = useState(false)
    const token = useRef({})

    useEffect(() => {
        const self = token.current
        mounted.push(self)
        return () => {
            mounted.splice(mounted.indexOf(self), 1)
        }
    }, [])

    const busy = disabled || loadingAll
    const severalPages = total > pageCount
    const pageIsSelection = pageCount > 0 && pageSelected === pageCount && selectedCount === pageCount
    const allIsSelection = total > 0 && selectedCount === total

    const choosePage = () => (pageIsSelection ? onClear() : onSelectPage())

    const chooseAll = async () => {
        if (allIsSelection) {
            onClear()
            return
        }
        setLoadingAll(true)
        try {
            await onSelectAll?.()
        } finally {
            setLoadingAll(false)
        }
    }

    const mayUseShortcut = (event: KeyboardEvent) =>
        !busy &&
        total > 0 &&
        !isTyping(event) &&
        mounted[mounted.length - 1] === token.current &&
        !document.querySelector('[role="dialog"]')

    useShortcuts({
        // Returning false leaves the key to the browser (select the text, ...).
        'mod+a': (event) => {
            if (!mayUseShortcut(event) || pageCount === 0) return false
            choosePage()
        },
        'mod+shift+a': (event) => {
            if (!mayUseShortcut(event) || !onSelectAll) return false
            void chooseAll()
        },
    })

    if (total === 0) return null

    return (
        <div className="selection-bar" role="group" aria-label={`Select ${noun}`}>
            <span>Select</span>
            {severalPages && (
                <button
                    type="button"
                    aria-pressed={pageIsSelection}
                    disabled={busy || pageCount === 0}
                    title={pageIsSelection ? 'Cancel this selection (Ctrl/Cmd+A)' : `Select only the ${pageCount} ${noun} on this page (Ctrl/Cmd+A)`}
                    onClick={choosePage}
                >
                    Current page ({pageCount.toLocaleString()})
                </button>
            )}
            {onSelectAll && (
                <button
                    type="button"
                    aria-pressed={allIsSelection}
                    disabled={busy}
                    title={allIsSelection ? 'Cancel this selection (Ctrl/Cmd+Shift+A)' : `Select all ${total} ${noun} matching the current search and filters, on every page (Ctrl/Cmd+Shift+A)`}
                    onClick={() => void chooseAll()}
                >
                    {loadingAll && <LoaderCircle size={12} className="entropy-spin" aria-hidden="true" />}
                    All {total.toLocaleString()} {noun}
                </button>
            )}
            {selectedCount > 0 && (
                <button type="button" className="selection-bar-clear" disabled={busy} title="Cancel the selection" onClick={onClear}>
                    <X size={12} aria-hidden="true" /> Clear ({selectedCount.toLocaleString()})
                </button>
            )}
        </div>
    )
}
