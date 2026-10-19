import { useEffect, useRef, type ReactNode } from 'react'
import { X } from 'lucide-react'

import AppPortal from './AppPortal'

/**
 * Shared modal dialog: dims the page by the user's modal backdrop preference,
 * closes on Escape or a backdrop press, and returns focus when it closes.
 */
export default function Dialog({
    title,
    subtitle,
    icon,
    onClose,
    footer,
    className,
    children,
}: {
    title: string
    subtitle?: string
    icon?: ReactNode
    onClose: () => void
    footer?: ReactNode
    className?: string
    children: ReactNode
}) {
    const panelRef = useRef<HTMLDivElement>(null)
    const closeRef = useRef(onClose)

    useEffect(() => {
        closeRef.current = onClose
    })

    useEffect(() => {
        const previous = document.activeElement as HTMLElement | null
        const panel = panelRef.current
        const first = panel?.querySelector<HTMLElement>(
            'input:not([disabled]), select, textarea, [data-autofocus]',
        )

        ;(first ?? panel)?.focus()

        function handleKeyDown(event: KeyboardEvent) {
            if (event.key === 'Escape') {
                event.stopPropagation()
                closeRef.current()
            }
        }

        document.addEventListener('keydown', handleKeyDown)

        return () => {
            document.removeEventListener('keydown', handleKeyDown)
            previous?.focus?.()
        }
    }, [])

    return (
        <AppPortal>
            <div
                className="entropy-dialog-backdrop"
                onPointerDown={(event) => {
                    if (event.target === event.currentTarget) closeRef.current()
                }}
            >
                <div
                    ref={panelRef}
                    className={['entropy-dialog', className].filter(Boolean).join(' ')}
                    role="dialog"
                    aria-modal="true"
                    aria-label={title}
                    tabIndex={-1}
                >
                    <header className="entropy-dialog-header">
                        {icon && <span className="entropy-dialog-icon">{icon}</span>}
                        <div>
                            <h2>{title}</h2>
                            {subtitle && <p>{subtitle}</p>}
                        </div>
                        <button
                            type="button"
                            className="entropy-button entropy-button-ghost entropy-button-icon entropy-button-sm"
                            aria-label="Close"
                            onClick={onClose}
                        >
                            <X size={16} />
                        </button>
                    </header>

                    <div className="entropy-dialog-body">{children}</div>

                    {footer && <footer className="entropy-dialog-footer">{footer}</footer>}
                </div>
            </div>
        </AppPortal>
    )
}
