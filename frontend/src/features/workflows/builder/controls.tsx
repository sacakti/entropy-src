import { useEffect, useMemo, useRef, useState, type KeyboardEvent } from 'react'
import { Braces, Plus, Search, Tag, X } from 'lucide-react'

// ----------------------------------------------------------------------
// Switch
// ----------------------------------------------------------------------

export function Switch({
    checked,
    onChange,
    label,
    disabled,
}: {
    checked: boolean
    onChange: (checked: boolean) => void
    label: string
    disabled?: boolean
}) {
    return (
        <button
            type="button"
            role="switch"
            aria-checked={checked}
            aria-label={label}
            title={label}
            className={`wf-switch${checked ? ' is-on' : ''}`}
            onClick={() => onChange(!checked)}
            disabled={disabled}
        >
            <span className="wf-switch-thumb" />
        </button>
    )
}

// ----------------------------------------------------------------------
// Popover helper
// ----------------------------------------------------------------------

function useDismiss(open: boolean, close: () => void) {
    const ref = useRef<HTMLDivElement>(null)

    useEffect(() => {
        if (!open) return

        function onPointerDown(event: PointerEvent) {
            if (!ref.current?.contains(event.target as Node)) close()
        }

        function onKeyDown(event: globalThis.KeyboardEvent) {
            if (event.key === 'Escape') close()
        }

        document.addEventListener('pointerdown', onPointerDown)
        document.addEventListener('keydown', onKeyDown)

        return () => {
            document.removeEventListener('pointerdown', onPointerDown)
            document.removeEventListener('keydown', onKeyDown)
        }
    }, [open, close])

    return ref
}

// ----------------------------------------------------------------------
// Reference picker
// ----------------------------------------------------------------------

export interface ReferenceItem {
    label: string
    expression: string
    hint?: string
}

export interface ReferenceGroup {
    label: string
    items: ReferenceItem[]
    empty: string
}

export function ReferencePicker({
    groups,
    onPick,
    label = 'Insert reference',
}: {
    groups: ReferenceGroup[]
    onPick: (expression: string) => void
    label?: string
}) {
    const [open, setOpen] = useState(false)
    const [query, setQuery] = useState('')
    const ref = useDismiss(open, () => setOpen(false))

    const filtered = useMemo(() => {
        const needle = query.trim().toLowerCase()

        return groups.map((group) => ({
            ...group,
            items: needle
                ? group.items.filter(
                      (item) =>
                          item.label.toLowerCase().includes(needle) ||
                          item.expression.toLowerCase().includes(needle),
                  )
                : group.items,
        }))
    }, [groups, query])

    return (
        <div className="wf-popover-anchor" ref={ref}>
            <button
                type="button"
                className="entropy-button entropy-button-secondary entropy-button-icon entropy-button-sm"
                aria-label={label}
                title={label}
                aria-haspopup="menu"
                aria-expanded={open}
                onClick={() => setOpen((value) => !value)}
            >
                <Braces size={14} />
            </button>

            {open && (
                <div className="wf-popover wf-reference-popover" role="menu">
                    <label className="entropy-search wf-popover-search">
                        <Search size={14} aria-hidden="true" />
                        <input
                            autoFocus
                            value={query}
                            onChange={(event) => setQuery(event.target.value)}
                            placeholder="Search references…"
                            aria-label="Search references"
                        />
                    </label>

                    <div className="wf-popover-scroll">
                        {filtered.map((group) => (
                            <section key={group.label} className="wf-reference-group">
                                <h4>{group.label}</h4>
                                {group.items.length === 0 ? (
                                    <p className="wf-reference-empty">{group.empty}</p>
                                ) : (
                                    group.items.map((item) => (
                                        <button
                                            key={item.expression}
                                            type="button"
                                            role="menuitem"
                                            onClick={() => {
                                                onPick(item.expression)
                                                setOpen(false)
                                                setQuery('')
                                            }}
                                        >
                                            <span>{item.label}</span>
                                            <code>{item.expression}</code>
                                            {item.hint && <small>{item.hint}</small>}
                                        </button>
                                    ))
                                )}
                            </section>
                        ))}
                    </div>
                </div>
            )}
        </div>
    )
}

// ----------------------------------------------------------------------
// Tags
// ----------------------------------------------------------------------

export function TagEditor({
    tags,
    onChange,
}: {
    tags: string[]
    onChange: (tags: string[]) => void
}) {
    const [open, setOpen] = useState(false)
    const [draft, setDraft] = useState('')
    const ref = useDismiss(open, () => setOpen(false))

    const add = () => {
        const tag = draft.trim()

        if (tag && !tags.includes(tag)) onChange([...tags, tag])
        setDraft('')
    }

    const onKeyDown = (event: KeyboardEvent<HTMLInputElement>) => {
        if (event.key === 'Enter' || event.key === ',') {
            event.preventDefault()
            add()
        } else if (event.key === 'Backspace' && !draft && tags.length > 0) {
            onChange(tags.slice(0, -1))
        }
    }

    return (
        <div className="wf-popover-anchor" ref={ref}>
            <button
                type="button"
                className="entropy-button entropy-button-secondary entropy-button-sm"
                aria-haspopup="dialog"
                aria-expanded={open}
                onClick={() => setOpen((value) => !value)}
                title="Edit tags"
            >
                <Tag size={13} />
                Tags
                {tags.length > 0 && <span className="wf-tag-count">{tags.length}</span>}
            </button>

            {open && (
                <div className="wf-popover wf-tag-popover" role="dialog" aria-label="Step tags">
                    <div className="wf-tag-list">
                        {tags.length === 0 && <span className="wf-reference-empty">No tags yet.</span>}
                        {tags.map((tag) => (
                            <span key={tag} className="wf-tag">
                                {tag}
                                <button
                                    type="button"
                                    aria-label={`Remove tag ${tag}`}
                                    onClick={() => onChange(tags.filter((item) => item !== tag))}
                                >
                                    <X size={11} />
                                </button>
                            </span>
                        ))}
                    </div>
                    <div className="wf-tag-input">
                        <input
                            autoFocus
                            value={draft}
                            onChange={(event) => setDraft(event.target.value)}
                            onKeyDown={onKeyDown}
                            placeholder="Add a tag and press Enter"
                            aria-label="New tag"
                        />
                        <button
                            type="button"
                            className="entropy-button entropy-button-secondary entropy-button-icon entropy-button-sm"
                            aria-label="Add tag"
                            onClick={add}
                        >
                            <Plus size={14} />
                        </button>
                    </div>
                </div>
            )}
        </div>
    )
}
