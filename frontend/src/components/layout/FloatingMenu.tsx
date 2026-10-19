import { useLayoutEffect, useRef, useState, type ReactNode, type RefObject } from 'react'

import AppPortal from './AppPortal'
import { useDismiss } from './useDismiss'

const GAP = 6
const MARGIN = 8

/**
 * A menu anchored to a trigger but rendered at the app root, so scrolling
 * containers (tables, panels) never clip it. Opens upward near the viewport
 * bottom and closes on outside press, Escape, scroll or resize.
 */
export default function FloatingMenu({
    anchorRef,
    open,
    onClose,
    className,
    align = 'end',
    children,
}: {
    anchorRef: RefObject<HTMLElement | null>
    open: boolean
    onClose: () => void
    className?: string
    align?: 'start' | 'end'
    children: ReactNode
}) {
    const menuRef = useRef<HTMLDivElement>(null)
    const [position, setPosition] = useState<{ top: number; left: number } | null>(null)

    useDismiss(open, [anchorRef, menuRef], onClose)

    useLayoutEffect(() => {
        if (!open) return

        const anchor = anchorRef.current?.getBoundingClientRect()
        const menu = menuRef.current?.getBoundingClientRect()

        if (!anchor || !menu) return

        const below = anchor.bottom + GAP
        const top =
            below + menu.height > window.innerHeight - MARGIN && anchor.top - GAP - menu.height > MARGIN
                ? anchor.top - GAP - menu.height
                : below
        const preferred = align === 'end' ? anchor.right - menu.width : anchor.left
        const left = Math.min(Math.max(MARGIN, preferred), window.innerWidth - menu.width - MARGIN)

        setPosition({ top, left })
    }, [open, align, anchorRef])

    useLayoutEffect(() => {
        if (!open) return

        // Close rather than chase the anchor; the row may scroll out of view.
        const close = () => onClose()
        window.addEventListener('resize', close)
        window.addEventListener('scroll', close, true)

        return () => {
            window.removeEventListener('resize', close)
            window.removeEventListener('scroll', close, true)
        }
    }, [open, onClose])

    if (!open) return null

    return (
        <AppPortal>
            <div
                ref={menuRef}
                className={['entropy-floating-menu', className].filter(Boolean).join(' ')}
                role="menu"
                style={{
                    top: position?.top ?? 0,
                    left: position?.left ?? 0,
                    visibility: position ? 'visible' : 'hidden',
                }}
            >
                {children}
            </div>
        </AppPortal>
    )
}
