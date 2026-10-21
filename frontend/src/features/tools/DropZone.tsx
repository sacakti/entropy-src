import { useState, type DragEvent, type ReactNode } from 'react'
import { X } from 'lucide-react'

/**
 * Drop target with a pick button: one side of a file or folder compare.
 * Shows the picked item's name and details once something is loaded.
 */
export default function DropZone({
    label,
    icon,
    prompt,
    pickLabel,
    picked,
    busy,
    error,
    onPick,
    onDrop,
    onClear,
}: {
    label: string
    icon: ReactNode
    prompt: string
    pickLabel: string
    picked: { name: string; detail: string } | null
    busy?: ReactNode
    error?: string | null
    onPick: () => void
    onDrop: (event: DragEvent<HTMLDivElement>) => void
    onClear: () => void
}) {
    const [over, setOver] = useState(false)

    return (
        <div
            className={`tools-drop${over ? ' is-over' : ''}${picked ? ' is-picked' : ''}${error ? ' has-error' : ''}`}
            onDragEnter={(event) => {
                event.preventDefault()
                setOver(true)
            }}
            onDragOver={(event) => {
                event.preventDefault()
                event.dataTransfer.dropEffect = 'copy'
            }}
            onDragLeave={(event) => {
                // Ignore leaving into a child element.
                if (!event.currentTarget.contains(event.relatedTarget as Node | null)) setOver(false)
            }}
            onDrop={(event) => {
                event.preventDefault()
                setOver(false)
                onDrop(event)
            }}
        >
            <span className="tools-drop-label">{label}</span>
            <span className="tools-drop-icon" aria-hidden="true">
                {icon}
            </span>

            {busy ? (
                <div className="tools-drop-text" role="status">
                    {busy}
                </div>
            ) : picked ? (
                <div className="tools-drop-text">
                    <strong title={picked.name}>{picked.name}</strong>
                    <span>{picked.detail}</span>
                </div>
            ) : (
                <div className="tools-drop-text">
                    <strong>{prompt}</strong>
                    <span>or</span>
                </div>
            )}

            <div className="tools-drop-actions">
                <button
                    type="button"
                    className="entropy-button entropy-button-secondary entropy-button-sm"
                    onClick={onPick}
                    disabled={Boolean(busy)}
                >
                    {picked ? 'Replace…' : pickLabel}
                </button>
                {picked && !busy && (
                    <button
                        type="button"
                        className="entropy-button entropy-button-ghost entropy-button-icon entropy-button-sm"
                        aria-label={`Clear ${label.toLowerCase()}`}
                        title="Clear"
                        onClick={onClear}
                    >
                        <X size={14} />
                    </button>
                )}
            </div>

            {error && (
                <p className="tools-drop-error" role="alert">
                    {error}
                </p>
            )}
        </div>
    )
}
