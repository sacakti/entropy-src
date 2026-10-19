import { useEffect, useRef, type RefObject } from 'react'

/**
 * Close a popover on a pointer press outside every given element, or on Escape.
 */
export function useDismiss(
    open: boolean,
    refs: RefObject<HTMLElement | null>[],
    onClose: () => void,
) {
    // Callers pass fresh arrays and closures each render; read the latest.
    const latest = useRef({ refs, onClose })

    useEffect(() => {
        latest.current = { refs, onClose }
    })

    useEffect(() => {
        if (!open) return

        function handlePointerDown(event: PointerEvent) {
            const target = event.target as Node
            const inside = latest.current.refs.some((ref) => ref.current?.contains(target))

            if (!inside) latest.current.onClose()
        }

        function handleKeyDown(event: KeyboardEvent) {
            if (event.key === 'Escape') latest.current.onClose()
        }

        document.addEventListener('pointerdown', handlePointerDown)
        document.addEventListener('keydown', handleKeyDown)

        return () => {
            document.removeEventListener('pointerdown', handlePointerDown)
            document.removeEventListener('keydown', handleKeyDown)
        }
    }, [open])
}
