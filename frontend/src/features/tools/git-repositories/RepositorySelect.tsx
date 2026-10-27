import { useEffect, useState } from 'react'

import { apiRequest } from '../../../services/api'

interface Choice {
    id: number
    name: string
    scope: 'user' | 'project'
}

let cached: Promise<Choice[]> | null = null

/** Repositories from Tools → Git repositories the current user may use. */
function loadChoices(): Promise<Choice[]> {
    cached ??= apiRequest<{ items: Choice[] }>('/api/git-repositories')
        .then((result) => result.items)
        .catch(() => {
            cached = null
            return []
        })
    return cached
}

/**
 * Pick a repository from Tools → Git repositories for an argument that
 * takes one (contract `"picker": "git_repository"`). References and names
 * not listed stay editable as text.
 */
export default function RepositorySelect({
    value,
    onChange,
    label,
    placeholder,
    className,
}: {
    value: string
    onChange: (value: string) => void
    label: string
    placeholder: string
    className?: string
}) {
    const [choices, setChoices] = useState<Choice[] | null>(null)

    useEffect(() => {
        let active = true
        void loadChoices().then((items) => {
            if (active) setChoices(items)
        })
        return () => {
            active = false
        }
    }, [])

    const names = (choices ?? []).map((item) => item.name)
    const custom = value !== '' && !names.includes(value)

    if (custom || (choices !== null && choices.length === 0)) {
        return (
            <input
                className={className}
                value={value}
                onChange={(event) => onChange(event.target.value)}
                placeholder={choices?.length === 0 ? 'No repositories in Tools → Git repositories' : placeholder}
                aria-label={label}
                spellCheck={false}
            />
        )
    }

    return (
        <select className={className} value={value} onChange={(event) => onChange(event.target.value)} aria-label={label}>
            <option value="">{choices === null ? 'Loading repositories…' : placeholder}</option>
            {(choices ?? []).map((item) => (
                <option key={item.id} value={item.name}>
                    {item.name}
                    {item.scope === 'project' ? ' (project)' : ' (mine)'}
                </option>
            ))}
        </select>
    )
}
