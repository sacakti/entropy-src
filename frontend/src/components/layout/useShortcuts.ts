import { useEffect, useRef } from 'react'

/**
 * A key combination such as `mod+n`, `mod+shift+d` or `alt+n`, where `mod`
 * is Ctrl (Cmd on macOS).
 */
export type ShortcutKey = string

interface Parsed {
    key: string
    mod: boolean
    shift: boolean
    alt: boolean
}

function parse(combo: ShortcutKey): Parsed {
    const parts = combo.toLowerCase().split('+')

    return {
        key: parts[parts.length - 1],
        mod: parts.includes('mod'),
        shift: parts.includes('shift'),
        alt: parts.includes('alt'),
    }
}

/**
 * The physical key for a letter or digit (`KeyS`, `Digit1`). Windows and
 * non-US layouts (or Alt held down) can report another character in
 * `event.key`, so the physical key is matched too.
 */
function codeOf(key: string): string | null {
    if (/^[a-z]$/.test(key)) return `Key${key.toUpperCase()}`
    if (/^[0-9]$/.test(key)) return `Digit${key}`
    return null
}

export function keyMatches(event: KeyboardEvent, key: string): boolean {
    const wanted = key.toLowerCase()
    return event.key.toLowerCase() === wanted || (codeOf(wanted) !== null && event.code === codeOf(wanted))
}

function matches(event: KeyboardEvent, combo: Parsed): boolean {
    const mod = event.ctrlKey || event.metaKey

    return (
        keyMatches(event, combo.key) &&
        mod === combo.mod &&
        event.shiftKey === combo.shift &&
        event.altKey === combo.alt
    )
}

/**
 * Bind page-level keyboard shortcuts while `enabled`. Matching keys have the
 * browser default (bookmark, save page, …) suppressed unless the handler
 * returns `false` to decline the key.
 */
export function useShortcuts(
    bindings: Record<ShortcutKey, (event: KeyboardEvent) => boolean | void>,
    enabled = true,
) {
    const latest = useRef(bindings)

    useEffect(() => {
        latest.current = bindings
    })

    useEffect(() => {
        if (!enabled) return

        function handleKeyDown(event: KeyboardEvent) {
            if (event.defaultPrevented || event.repeat) return

            for (const [combo, handler] of Object.entries(latest.current)) {
                if (matches(event, parse(combo))) {
                    if (handler(event) !== false) event.preventDefault()
                    return
                }
            }
        }

        window.addEventListener('keydown', handleKeyDown)
        return () => window.removeEventListener('keydown', handleKeyDown)
    }, [enabled])
}

/** True when the event comes from a text field, where bare keys type text. */
export function isTyping(event: KeyboardEvent): boolean {
    const target = event.target as HTMLElement | null

    return Boolean(
        target &&
            (target.isContentEditable ||
                ['INPUT', 'TEXTAREA', 'SELECT'].includes(target.tagName)),
    )
}
