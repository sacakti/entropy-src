import { useEffect, useId, useRef, useState, type KeyboardEvent } from 'react'
import { UserRound } from 'lucide-react'

import { vaultApi, type VaultUserSuggestion } from '../../api/vault.api'
import { useDismiss } from '../../components/layout/useDismiss'

/**
 * Username field that suggests matching users by username, full name or id.
 */
export default function UserSuggestInput({
    id,
    value,
    onChange,
    disabled,
}: {
    id: string
    value: string
    onChange: (username: string) => void
    disabled?: boolean
}) {
    const [open, setOpen] = useState(false)
    const [suggestions, setSuggestions] = useState<VaultUserSuggestion[]>([])
    const [highlighted, setHighlighted] = useState(0)
    const wrapRef = useRef<HTMLDivElement>(null)
    const listId = useId()

    useDismiss(open, [wrapRef], () => setOpen(false))

    useEffect(() => {
        if (!open) return

        let active = true
        const timer = window.setTimeout(() => {
            vaultApi
                .suggestUsers(value.trim())
                .then((result) => {
                    if (!active) return
                    setSuggestions(result.items)
                    setHighlighted(0)
                })
                .catch(() => {
                    if (active) setSuggestions([])
                })
        }, 180)

        return () => {
            active = false
            window.clearTimeout(timer)
        }
    }, [open, value])

    const choose = (suggestion: VaultUserSuggestion) => {
        onChange(suggestion.username)
        setOpen(false)
    }

    const handleKeyDown = (event: KeyboardEvent<HTMLInputElement>) => {
        if (!open || suggestions.length === 0) {
            if (event.key === 'ArrowDown') setOpen(true)
            return
        }

        if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
            event.preventDefault()
            const step = event.key === 'ArrowDown' ? 1 : -1
            setHighlighted((index) => (index + step + suggestions.length) % suggestions.length)
        } else if (event.key === 'Enter') {
            event.preventDefault()
            choose(suggestions[highlighted])
        }
    }

    const showList = open && suggestions.length > 0

    return (
        <div className="vault-user-suggest" ref={wrapRef}>
            <input
                id={id}
                type="text"
                autoComplete="off"
                placeholder="Search by username, name or id"
                value={value}
                disabled={disabled}
                role="combobox"
                aria-expanded={showList}
                aria-controls={listId}
                aria-autocomplete="list"
                aria-activedescendant={showList ? `${listId}-${highlighted}` : undefined}
                onFocus={() => setOpen(true)}
                onChange={(event) => {
                    onChange(event.target.value)
                    setOpen(true)
                }}
                onKeyDown={handleKeyDown}
                required
            />

            {showList && (
                <ul className="vault-user-suggest-list" id={listId} role="listbox">
                    {suggestions.map((suggestion, index) => (
                        <li
                            key={suggestion.id}
                            id={`${listId}-${index}`}
                            role="option"
                            aria-selected={index === highlighted}
                            className={index === highlighted ? 'is-highlighted' : undefined}
                            onPointerDown={(event) => {
                                // Keep focus in the input; choose before blur.
                                event.preventDefault()
                                choose(suggestion)
                            }}
                            onPointerEnter={() => setHighlighted(index)}
                        >
                            <UserRound size={15} aria-hidden="true" />
                            <span>
                                <strong>{suggestion.username}</strong>
                                {suggestion.full_name && <small>{suggestion.full_name}</small>}
                            </span>
                            <code>#{suggestion.id}</code>
                        </li>
                    ))}
                </ul>
            )}
        </div>
    )
}
