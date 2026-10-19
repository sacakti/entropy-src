import { useMemo, useState, type ReactNode } from 'react'
import { AlertCircle, RefreshCw, Search, X } from 'lucide-react'

/** List page frame shared by Users, Groups, Roles and Permissions. */
export function AdminPanel({
    title,
    count,
    subtitle,
    actions,
    toolbar,
    error,
    refreshing,
    onRefresh,
    children,
}: {
    title: string
    count: number
    subtitle: string
    actions?: ReactNode
    toolbar?: ReactNode
    error?: string | null
    refreshing?: boolean
    onRefresh: () => void
    children: ReactNode
}) {
    return (
        <section className="admin-panel">
            <div className="admin-panel-heading">
                <div>
                    <h2>
                        {title}
                        <span className="entropy-count" aria-label={`${count} in total`}>
                            {count}
                        </span>
                    </h2>
                    <p>{subtitle}</p>
                </div>

                <div className="entropy-panel-actions">
                    <button
                        type="button"
                        className="entropy-button entropy-button-secondary entropy-button-icon"
                        aria-label={`Refresh ${title.toLowerCase()}`}
                        title="Refresh"
                        onClick={onRefresh}
                        disabled={refreshing}
                    >
                        <RefreshCw size={16} className={refreshing ? 'entropy-spin' : ''} />
                    </button>
                    {actions}
                </div>
            </div>

            {error && (
                <div className="entropy-alert entropy-alert-error" role="alert">
                    <AlertCircle size={16} />
                    <span>{error}</span>
                </div>
            )}

            {toolbar && <div className="admin-toolbar">{toolbar}</div>}

            {children}
        </section>
    )
}

export function SearchField({
    value,
    onChange,
    placeholder,
    inputRef,
}: {
    value: string
    onChange: (value: string) => void
    placeholder: string
    inputRef?: React.Ref<HTMLInputElement>
}) {
    return (
        <label className="entropy-search admin-search">
            <Search size={15} aria-hidden="true" />
            <input
                ref={inputRef}
                type="search"
                value={value}
                onChange={(event) => onChange(event.target.value)}
                placeholder={placeholder}
                aria-label={placeholder}
            />
            {value && (
                <button
                    type="button"
                    className="entropy-button entropy-button-ghost entropy-button-icon entropy-button-sm"
                    aria-label="Clear search"
                    onClick={() => onChange('')}
                >
                    <X size={14} />
                </button>
            )}
        </label>
    )
}

/** A few chips, then "+N more". */
export function ChipList({
    values,
    max = 3,
    empty = '—',
    tone,
}: {
    values: string[]
    max?: number
    empty?: string
    tone?: 'accent'
}) {
    if (values.length === 0) return <span className="admin-muted">{empty}</span>

    const shown = values.slice(0, max)

    return (
        <span className="admin-chips" title={values.join(', ')}>
            {shown.map((value) => (
                <span key={value} className={`admin-chip${tone ? ` is-${tone}` : ''}`}>
                    {value}
                </span>
            ))}
            {values.length > max && <span className="admin-chip is-more">+{values.length - max}</span>}
        </span>
    )
}

export interface ChecklistItem {
    value: string
    label?: string
    detail?: string | null
    /** Shown but not changeable, e.g. the built-in admin role. */
    locked?: boolean
}

/**
 * Searchable checkbox list for choosing many items (roles, groups, users).
 * Selected items sort first so they are easy to review.
 */
export function Checklist({
    items,
    selected,
    onChange,
    placeholder,
    disabled,
    emptyText = 'Nothing to choose from yet.',
}: {
    items: ChecklistItem[]
    selected: string[]
    onChange: (selected: string[]) => void
    placeholder: string
    disabled?: boolean
    emptyText?: string
}) {
    const [query, setQuery] = useState('')
    const chosen = useMemo(() => new Set(selected), [selected])

    const visible = useMemo(() => {
        const needle = query.trim().toLowerCase()

        return items
            .filter(
                (item) =>
                    !needle ||
                    `${item.value} ${item.label ?? ''} ${item.detail ?? ''}`.toLowerCase().includes(needle),
            )
            .sort((a, b) => Number(chosen.has(b.value)) - Number(chosen.has(a.value)))
    }, [chosen, items, query])

    const toggle = (value: string) => {
        if (chosen.has(value)) onChange(selected.filter((item) => item !== value))
        else onChange([...selected, value])
    }

    return (
        <div className="admin-checklist">
            <div className="admin-checklist-head">
                <SearchField value={query} onChange={setQuery} placeholder={placeholder} />
                <span className="admin-muted">
                    {selected.length} selected
                </span>
            </div>

            {items.length === 0 ? (
                <p className="admin-checklist-empty">{emptyText}</p>
            ) : visible.length === 0 ? (
                <p className="admin-checklist-empty">Nothing matches “{query}”.</p>
            ) : (
                <ul role="list">
                    {visible.map((item) => (
                        <li key={item.value}>
                            <label className={item.locked ? 'is-locked' : undefined}>
                                <input
                                    type="checkbox"
                                    checked={chosen.has(item.value)}
                                    disabled={disabled || item.locked}
                                    onChange={() => toggle(item.value)}
                                />
                                <span>
                                    <strong>{item.label ?? item.value}</strong>
                                    {item.detail && <small>{item.detail}</small>}
                                </span>
                            </label>
                        </li>
                    ))}
                </ul>
            )}
        </div>
    )
}

export function Tabs<T extends string>({
    tabs,
    active,
    onChange,
}: {
    tabs: { id: T; label: string; count?: number }[]
    active: T
    onChange: (tab: T) => void
}) {
    return (
        <div className="admin-tabs" role="tablist">
            {tabs.map((tab) => (
                <button
                    key={tab.id}
                    type="button"
                    role="tab"
                    aria-selected={active === tab.id}
                    className={active === tab.id ? 'is-active' : ''}
                    onClick={() => onChange(tab.id)}
                >
                    {tab.label}
                    {tab.count !== undefined && <span>{tab.count}</span>}
                </button>
            ))}
        </div>
    )
}

export function EmptyRow({ colSpan, title, text }: { colSpan: number; title: string; text: string }) {
    return (
        <tr>
            <td colSpan={colSpan}>
                <div className="admin-empty">
                    <strong>{title}</strong>
                    <span>{text}</span>
                </div>
            </td>
        </tr>
    )
}
