import { useRef, useState } from 'react'
import { FilePlus2, Plus, Upload } from 'lucide-react'

import FloatingMenu from './FloatingMenu'

/** The page "+" button: create a new item or import existing ones. */
export default function AddMenu({
    label,
    onCreate,
    onImport,
    createLabel = 'Create new',
    importLabel = 'Import…',
    disabledReason,
}: {
    label: string
    onCreate: () => void
    onImport: () => void
    createLabel?: string
    importLabel?: string
    /** Why the user may not add items; shown on hover instead of opening the menu. */
    disabledReason?: string | null
}) {
    const triggerRef = useRef<HTMLButtonElement>(null)
    const [open, setOpen] = useState(false)

    return (
        <>
            <button
                ref={triggerRef}
                type="button"
                className="entropy-button entropy-button-primary entropy-button-icon"
                aria-label={label}
                aria-haspopup="menu"
                aria-expanded={open}
                // aria-disabled rather than disabled, so the reason shows on hover.
                aria-disabled={disabledReason ? true : undefined}
                title={disabledReason ?? `${label} (Ctrl+N)`}
                onClick={() => {
                    if (!disabledReason) setOpen((value) => !value)
                }}
            >
                <Plus size={20} />
            </button>
            <FloatingMenu
                anchorRef={triggerRef}
                open={open}
                onClose={() => setOpen(false)}
                className="plugins-operation-menu"
            >
                <button
                    type="button"
                    role="menuitem"
                    onClick={() => {
                        setOpen(false)
                        onCreate()
                    }}
                >
                    <FilePlus2 size={15} />
                    {createLabel}
                </button>
                <button
                    type="button"
                    role="menuitem"
                    onClick={() => {
                        setOpen(false)
                        onImport()
                    }}
                >
                    <Upload size={15} />
                    {importLabel}
                </button>
            </FloatingMenu>
        </>
    )
}
