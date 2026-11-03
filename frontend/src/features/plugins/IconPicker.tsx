import { createElement, useMemo, useRef, useState } from 'react'
import { RotateCcw, Search, type LucideIcon } from 'lucide-react'

import { useFeedback } from '../../components/feedback/FeedbackProvider'
import FloatingMenu from '../../components/layout/FloatingMenu'
import { PLUGIN_ICON_GROUPS } from './pluginIcons'

/** An item's icon; for those who may edit the item, a button that opens the collection. */
export default function IconPicker({
    name,
    noun,
    icon,
    glyph: Glyph,
    canEdit,
    onChoose,
}: {
    /** What the icon belongs to, for screen readers. */
    name: string
    /** Its kind: "plugin", "workflow". */
    noun: string
    /** The chosen icon; empty while it shows its default. */
    icon?: string | null
    glyph: LucideIcon
    canEdit: boolean
    /** Saves the choice (null: the default); a rejection is reported here. */
    onChoose: (icon: string | null) => Promise<void>
}) {
    const { notify } = useFeedback()
    const [open, setOpen] = useState(false)
    const [query, setQuery] = useState('')
    const [saving, setSaving] = useState(false)
    const triggerRef = useRef<HTMLButtonElement>(null)
    const glyph = createElement(Glyph, { size: 17 })

    const needle = query.trim().toLowerCase()
    const groups = useMemo(
        () =>
            PLUGIN_ICON_GROUPS.map((group) => ({
                ...group,
                icons: group.icons.filter(
                    (item) =>
                        !needle ||
                        item.label.toLowerCase().includes(needle) ||
                        group.title.toLowerCase().includes(needle),
                ),
            })).filter((group) => group.icons.length > 0),
        [needle],
    )

    if (!canEdit) {
        return (
            <span className="list-name-icon" aria-hidden="true">
                {glyph}
            </span>
        )
    }

    const choose = async (next: string | null) => {
        setSaving(true)
        try {
            await onChoose(next)
            setOpen(false)
            setQuery('')
        } catch (cause) {
            notify.error(cause instanceof Error ? cause.message : 'The icon was not saved.', { title: 'Icon not changed' })
        } finally {
            setSaving(false)
        }
    }

    return (
        // The row has its own click; nothing in here should trigger it.
        <span onClick={(event) => event.stopPropagation()}>
            <button
                ref={triggerRef}
                type="button"
                className="list-name-icon list-name-icon-button"
                aria-label={`Change the icon of ${name}`}
                aria-haspopup="menu"
                aria-expanded={open}
                title="Change icon"
                onClick={() => setOpen((value) => !value)}
            >
                {glyph}
            </button>
            <FloatingMenu
                anchorRef={triggerRef}
                open={open}
                onClose={() => setOpen(false)}
                align="start"
                className="plugin-icon-menu"
            >
                <div className="plugin-icon-toolbar">
                    <label className="plugin-icon-search">
                        <Search size={14} aria-hidden="true" />
                        <input
                            autoFocus
                            value={query}
                            placeholder="Search icons…"
                            aria-label="Search icons"
                            onChange={(event) => setQuery(event.target.value)}
                        />
                    </label>
                    <button
                        type="button"
                        className="entropy-button entropy-button-ghost entropy-button-sm"
                        disabled={saving || !icon}
                        title={`Go back to this ${noun}'s default icon`}
                        onClick={() => void choose(null)}
                    >
                        <RotateCcw size={13} aria-hidden="true" /> Default
                    </button>
                </div>
                {groups.map((group) => (
                    <section key={group.title} className="plugin-icon-group">
                        <h4>{group.title}</h4>
                        <div className="plugin-icon-grid">
                            {group.icons.map((item) => (
                                <button
                                    key={item.id}
                                    type="button"
                                    className={icon === item.id ? 'is-chosen' : undefined}
                                    aria-label={item.label}
                                    aria-pressed={icon === item.id}
                                    title={item.label}
                                    disabled={saving}
                                    onClick={() => void choose(item.id)}
                                >
                                    <item.icon size={17} aria-hidden="true" />
                                </button>
                            ))}
                        </div>
                    </section>
                ))}
                {groups.length === 0 && <p className="plugin-icon-empty">No icon matches your search.</p>}
            </FloatingMenu>
        </span>
    )
}
