import { useEffect, useId, useState, type KeyboardEvent, type ReactNode } from 'react'
import { LoaderCircle, Search } from 'lucide-react'

import Dialog from './Dialog'

export interface PickerItem {
    id: string
    label: string
    detail?: string
}

/**
 * Ask the user to choose one item, e.g. which plugin a shortcut should act on.
 * `load` receives the search text and returns matching items.
 */
export default function PickerDialog({
    title,
    subtitle,
    icon,
    placeholder = 'Search…',
    empty = 'Nothing matches your search.',
    load,
    onPick,
    onClose,
}: {
    title: string
    subtitle?: string
    icon?: ReactNode
    placeholder?: string
    empty?: string
    load: (query: string) => Promise<PickerItem[]> | PickerItem[]
    onPick: (item: PickerItem) => void
    onClose: () => void
}) {
    const [query, setQuery] = useState('')
    const [items, setItems] = useState<PickerItem[] | null>(null)
    const [highlighted, setHighlighted] = useState(0)
    const listId = useId()

    useEffect(() => {
        let active = true
        const timer = window.setTimeout(() => {
            Promise.resolve(load(query.trim()))
                .then((result) => {
                    if (!active) return
                    setItems(result)
                    setHighlighted(0)
                })
                .catch(() => {
                    if (active) setItems([])
                })
        }, 150)

        return () => {
            active = false
            window.clearTimeout(timer)
        }
        // `load` is usually an inline closure; reload on query changes only.
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [query])

    const pick = (item: PickerItem | undefined) => {
        if (!item) return
        onClose()
        onPick(item)
    }

    const handleKeyDown = (event: KeyboardEvent<HTMLInputElement>) => {
        if (!items?.length) return

        if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
            event.preventDefault()
            const step = event.key === 'ArrowDown' ? 1 : -1
            setHighlighted((index) => (index + step + items.length) % items.length)
        } else if (event.key === 'Enter') {
            event.preventDefault()
            pick(items[highlighted])
        }
    }

    return (
        <Dialog title={title} subtitle={subtitle} icon={icon} onClose={onClose} className="picker-dialog">
            <label className="entropy-search">
                <Search size={15} aria-hidden="true" />
                <input
                    type="search"
                    value={query}
                    placeholder={placeholder}
                    aria-label={placeholder}
                    role="combobox"
                    aria-expanded
                    aria-controls={listId}
                    aria-activedescendant={items?.length ? `${listId}-${highlighted}` : undefined}
                    onChange={(event) => setQuery(event.target.value)}
                    onKeyDown={handleKeyDown}
                />
            </label>

            {items === null ? (
                <p className="picker-dialog-status">
                    <LoaderCircle size={15} className="entropy-spin" />
                    Loading…
                </p>
            ) : items.length === 0 ? (
                <p className="picker-dialog-status">{empty}</p>
            ) : (
                <ul className="picker-dialog-list" id={listId} role="listbox">
                    {items.map((item, index) => (
                        <li
                            key={item.id}
                            id={`${listId}-${index}`}
                            role="option"
                            aria-selected={index === highlighted}
                            className={index === highlighted ? 'is-highlighted' : undefined}
                            onPointerEnter={() => setHighlighted(index)}
                            onClick={() => pick(item)}
                        >
                            <strong>{item.label}</strong>
                            {item.detail && <span>{item.detail}</span>}
                        </li>
                    ))}
                </ul>
            )}
        </Dialog>
    )
}
