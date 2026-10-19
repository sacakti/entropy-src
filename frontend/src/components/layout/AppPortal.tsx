import type { ReactNode } from 'react'
import { createPortal } from 'react-dom'

/**
 * Render overlays at the application root so they stack above the sidebar
 * and top bar while still inheriting the `.entropy-app` theme tokens.
 */
export default function AppPortal({ children }: { children: ReactNode }) {
    return createPortal(
        children,
        document.querySelector('.entropy-app') ?? document.body,
    )
}
