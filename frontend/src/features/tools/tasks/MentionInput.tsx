import { Fragment, useMemo, useRef, useState, type KeyboardEvent, type ReactNode } from 'react'

import type { Member } from './model'

const QUERY = /(^|[\s(])@([\w.-]*)$/

/**
 * A textarea that suggests project members after "@" (Enter or Tab picks,
 * arrows move, Escape closes). Mentioned members are notified by the server.
 */
export default function MentionInput({
    value,
    onChange,
    members,
    placeholder,
    rows = 2,
    ariaLabel,
    onSubmitShortcut,
}: {
    value: string
    onChange: (value: string) => void
    members: Member[]
    placeholder?: string
    rows?: number
    ariaLabel?: string
    /** Ctrl/⌘ + Enter. */
    onSubmitShortcut?: () => void
}) {
    const area = useRef<HTMLTextAreaElement>(null)
    const [query, setQuery] = useState<string | null>(null)
    const [active, setActive] = useState(0)

    const matches = useMemo(() => {
        if (query === null) return []
        const needle = query.toLowerCase()
        return members
            .filter(
                (member) =>
                    member.username.toLowerCase().includes(needle) ||
                    (member.full_name ?? '').toLowerCase().includes(needle),
            )
            .slice(0, 6)
    }, [members, query])

    const track = (text: string, caret: number) => {
        const match = QUERY.exec(text.slice(0, caret))
        setQuery(match ? match[2] : null)
        setActive(0)
    }

    const pick = (member: Member) => {
        const element = area.current
        if (!element) return
        const caret = element.selectionStart
        const before = value.slice(0, caret).replace(QUERY, (_, lead: string) => `${lead}@${member.username} `)
        const next = before + value.slice(caret)
        onChange(next)
        setQuery(null)
        requestAnimationFrame(() => {
            element.focus()
            element.setSelectionRange(before.length, before.length)
        })
    }

    const onKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
        if (matches.length) {
            if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
                event.preventDefault()
                setActive((index) => (index + (event.key === 'ArrowDown' ? 1 : matches.length - 1)) % matches.length)
                return
            }
            if (event.key === 'Enter' || event.key === 'Tab') {
                event.preventDefault()
                pick(matches[active])
                return
            }
            if (event.key === 'Escape') {
                event.preventDefault()
                setQuery(null)
                return
            }
        }
        if (event.key === 'Enter' && (event.ctrlKey || event.metaKey) && onSubmitShortcut) {
            event.preventDefault()
            onSubmitShortcut()
        }
    }

    return (
        <div className="task-mention">
            <textarea
                ref={area}
                rows={rows}
                value={value}
                placeholder={placeholder}
                aria-label={ariaLabel}
                aria-autocomplete="list"
                aria-expanded={matches.length > 0}
                onChange={(event) => {
                    onChange(event.target.value)
                    track(event.target.value, event.target.selectionStart)
                }}
                onKeyDown={onKeyDown}
                onClick={(event) => track(value, event.currentTarget.selectionStart)}
                onBlur={() => window.setTimeout(() => setQuery(null), 150)}
            />
            {matches.length > 0 && (
                <ul className="task-mention-list" role="listbox" aria-label="Mention a member">
                    {matches.map((member, index) => (
                        <li key={member.username} role="option" aria-selected={index === active}>
                            <button
                                type="button"
                                className={index === active ? 'is-active' : undefined}
                                onMouseDown={(event) => {
                                    event.preventDefault()
                                    pick(member)
                                }}
                            >
                                <strong>@{member.username}</strong>
                                {member.full_name && <span>{member.full_name}</span>}
                            </button>
                        </li>
                    ))}
                </ul>
            )}
        </div>
    )
}

/** Comment text with @mentions of members highlighted. */
export function MentionText({ text, members }: { text: string; members: Member[] }): ReactNode {
    const names = new Set(members.map((member) => member.username.toLowerCase()))
    const parts = text.split(/(@[\w.-]+)/g)
    return parts.map((part, index) =>
        part.startsWith('@') && names.has(part.slice(1).replace(/\.$/, '').toLowerCase()) ? (
            <span key={index} className="task-mention-chip">
                {part}
            </span>
        ) : (
            <Fragment key={index}>{part}</Fragment>
        ),
    )
}
