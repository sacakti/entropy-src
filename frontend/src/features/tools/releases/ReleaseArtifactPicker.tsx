import { useEffect, useMemo, useState } from 'react'
import { ChevronLeft, ChevronRight, LoaderCircle, Package, Search, X } from 'lucide-react'

import { apiRequest } from '../../../services/api'
import { formatBytes, formatDateTime } from '../../runs/format'
import {
    ARTIFACTS_PER_PAGE,
    artifactOrigin,
    artifactPage,
    artifactTime,
    newestFirst,
    searchArtifacts,
    type PickableArtifact,
} from './artifactSearch'

/**
 * Choosing the artifacts of a release: the latest come first, five at a time, and a search
 * finds the rest. What is chosen stays listed above, whichever page or search is showing.
 */
export default function ReleaseArtifactPicker({ initial, selected, onChange }: {
    /** What the page already has, shown until the current list arrives. */
    initial: PickableArtifact[]
    selected: number[]
    onChange: (ids: number[]) => void
}) {
    const [artifacts, setArtifacts] = useState(initial)
    const [loading, setLoading] = useState(true)
    const [query, setQuery] = useState('')
    const [requested, setPage] = useState(1)

    // A file generated a moment ago should be here without reloading the page.
    useEffect(() => {
        let active = true
        apiRequest<{ items: PickableArtifact[] }>('/api/artifacts')
            .then(({ items }) => {
                if (active) setArtifacts(items)
            })
            // The list from when the page opened still works.
            .catch(() => undefined)
            .finally(() => {
                if (active) setLoading(false)
            })
        return () => {
            active = false
        }
    }, [])

    const ordered = useMemo(() => newestFirst(artifacts), [artifacts])
    const found = useMemo(() => searchArtifacts(ordered, query), [ordered, query])
    const { items, page, pages } = artifactPage(found, requested)
    const chosen = selected.map((id) => artifacts.find((item) => item.id === id)).filter((item) => item !== undefined)
    const searching = query.trim().length > 0
    const first = found.length ? (page - 1) * ARTIFACTS_PER_PAGE + 1 : 0
    const last = Math.min(page * ARTIFACTS_PER_PAGE, found.length)

    const toggle = (id: number) =>
        onChange(selected.includes(id) ? selected.filter((item) => item !== id) : [...selected, id])

    return (
        <fieldset className="release-artifacts">
            <legend>Link artifacts</legend>

            {chosen.length > 0 && (
                <ul className="release-artifacts-chosen" aria-label="Chosen artifacts">
                    {chosen.map((artifact) => (
                        <li key={artifact.id}>
                            <span title={artifact.name}>{artifact.name}</span>
                            <button type="button" aria-label={`Remove ${artifact.name}`} title="Remove" onClick={() => toggle(artifact.id)}>
                                <X size={12} />
                            </button>
                        </li>
                    ))}
                </ul>
            )}

            <div className="list-search release-artifacts-search">
                <Search size={15} aria-hidden="true" />
                <input
                    type="search"
                    value={query}
                    placeholder="Search by name, plugin, tag or who added it…"
                    aria-label="Search artifacts"
                    onChange={(event) => {
                        setQuery(event.target.value)
                        setPage(1)
                    }}
                    // Enter here looks for something; it must not create the release.
                    onKeyDown={(event) => {
                        if (event.key === 'Enter') event.preventDefault()
                    }}
                />
                {query && (
                    <button type="button" aria-label="Clear search" onClick={() => {
                        setQuery('')
                        setPage(1)
                    }}>
                        <X size={14} />
                    </button>
                )}
            </div>

            <div className="release-artifacts-heading">
                <strong>{searching ? 'Search results' : 'Recently uploaded or generated'}</strong>
                {loading && <LoaderCircle size={13} className="entropy-spin" aria-label="Loading artifacts" />}
            </div>

            {items.length > 0 ? (
                <ul className="release-artifacts-list">
                    {items.map((artifact) => (
                        <li key={artifact.id}>
                            <label className={selected.includes(artifact.id) ? 'is-chosen' : undefined}>
                                <input
                                    type="checkbox"
                                    className="list-check"
                                    checked={selected.includes(artifact.id)}
                                    onChange={() => toggle(artifact.id)}
                                />
                                <span className="release-artifacts-name">
                                    <strong title={artifact.name}>{artifact.name}</strong>
                                    <small>
                                        {artifactOrigin(artifact)}
                                        {artifact.origin ? ` · ${artifact.origin}` : ''}
                                        {artifact.created_at ? ` · ${formatDateTime(artifactTime(artifact.created_at))}` : ''}
                                    </small>
                                </span>
                                <small>{formatBytes(artifact.size_bytes)}</small>
                            </label>
                        </li>
                    ))}
                </ul>
            ) : (
                <div className="release-artifacts-empty">
                    <Package size={18} aria-hidden="true" />
                    <span>
                        {loading
                            ? 'Loading artifacts…'
                            : searching
                              ? 'No artifact matches your search.'
                              : 'No artifacts yet. Upload one in Artifacts, or generate one with a run.'}
                    </span>
                </div>
            )}

            {found.length > 0 && (
                <footer className="release-artifacts-pages">
                    <span>{first}–{last} of {found.length}</span>
                    <div>
                        <button
                            type="button"
                            className="entropy-button entropy-button-secondary entropy-button-icon entropy-button-sm"
                            aria-label="Previous artifacts"
                            title="Previous"
                            disabled={page <= 1}
                            onClick={() => setPage(page - 1)}
                        >
                            <ChevronLeft size={15} />
                        </button>
                        <span>Page {page} of {pages}</span>
                        <button
                            type="button"
                            className="entropy-button entropy-button-secondary entropy-button-icon entropy-button-sm"
                            aria-label="Next artifacts"
                            title="Next"
                            disabled={page >= pages}
                            onClick={() => setPage(page + 1)}
                        >
                            <ChevronRight size={15} />
                        </button>
                    </div>
                </footer>
            )}
        </fieldset>
    )
}
