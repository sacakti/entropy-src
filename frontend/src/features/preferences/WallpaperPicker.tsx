import { useEffect, useMemo, useState } from 'react'
import { Check, ChevronLeft, ChevronRight, ChevronsLeft, ChevronsRight, Film, Search, X } from 'lucide-react'

import { isVideoBackground, type BackgroundImage } from '../../api/backgrounds.api'
import AppPortal from '../../components/layout/AppPortal'

const WALLPAPERS_PER_PAGE = 6

export default function WallpaperPicker({
    backgrounds,
    selectedIds,
    onApply,
    onClose,
}: {
    backgrounds: BackgroundImage[]
    selectedIds: number[]
    onApply: (ids: number[]) => void
    onClose: () => void
}) {
    const [draftIds, setDraftIds] = useState(() => new Set(selectedIds))
    const [query, setQuery] = useState('')
    const [page, setPage] = useState(0)
    const matching = useMemo(() => {
        const normalized = query.trim().toLowerCase()
        return normalized
            ? backgrounds.filter((item) => item.name.toLowerCase().includes(normalized))
            : backgrounds
    }, [backgrounds, query])
    const pageCount = Math.max(1, Math.ceil(matching.length / WALLPAPERS_PER_PAGE))
    const visible = matching.slice(page * WALLPAPERS_PER_PAGE, (page + 1) * WALLPAPERS_PER_PAGE)
    const matchingIds = useMemo(() => matching.map((item) => item.id), [matching])

    useEffect(() => {
        setPage((current) => Math.min(current, pageCount - 1))
    }, [pageCount])

    useEffect(() => {
        const onKeyDown = (event: KeyboardEvent) => {
            const modifier = event.ctrlKey || event.metaKey
            const target = event.target
            const editingSearch = target instanceof HTMLInputElement || target instanceof HTMLTextAreaElement

            if (event.key === 'Escape') {
                event.preventDefault()
                onClose()
                return
            }
            if (!modifier) return

            if (event.key.toLowerCase() === 'a' && !editingSearch) {
                event.preventDefault()
                setDraftIds((current) => new Set([...current, ...matchingIds]))
            } else if (event.key.toLowerCase() === 'd') {
                event.preventDefault()
                setDraftIds(new Set<number>())
            } else if (event.key.toLowerCase() === 'i') {
                event.preventDefault()
                setDraftIds((current) => {
                    const next = new Set(current)
                    for (const id of matchingIds) {
                        if (next.has(id)) next.delete(id)
                        else next.add(id)
                    }
                    return next
                })
            }
        }

        window.addEventListener('keydown', onKeyDown)
        return () => window.removeEventListener('keydown', onKeyDown)
    }, [matchingIds, onClose])

    const toggle = (id: number) => {
        setDraftIds((current) => {
            const next = new Set(current)
            if (next.has(id)) next.delete(id)
            else next.add(id)
            return next
        })
    }

    return (
        <AppPortal>
            <div className="wallpaper-picker-backdrop" onClick={onClose}>
            <section
                className="wallpaper-picker"
                role="dialog"
                aria-modal="true"
                aria-label="Choose wallpapers for shuffle"
                onClick={(event) => event.stopPropagation()}
            >
                <header className="wallpaper-picker-header">
                    <div className="wallpaper-picker-heading">
                        <div>
                            <strong>Choose wallpapers</strong>
                            <span>{draftIds.size} selected · {matching.length} wallpapers</span>
                        </div>
                        <label className="wallpaper-picker-search">
                            <Search size={16} aria-hidden="true" />
                            <input
                                type="search"
                                value={query}
                                onChange={(event) => {
                                    setQuery(event.target.value)
                                    setPage(0)
                                }}
                                placeholder="Search wallpapers"
                                aria-label="Search wallpapers"
                            />
                        </label>
                    </div>
                    <div className="wallpaper-picker-actions">
                        <button type="button" className="entropy-button entropy-button-secondary entropy-button-sm" onClick={() => setDraftIds((current) => new Set([...current, ...matchingIds]))}>
                            Select all
                        </button>
                        <button type="button" className="entropy-button entropy-button-secondary entropy-button-sm" onClick={() => setDraftIds(new Set<number>())}>
                            Clear
                        </button>
                        <button
                            type="button"
                            className="entropy-button entropy-button-secondary entropy-button-sm"
                            onClick={() => setDraftIds((current) => {
                                const next = new Set(current)
                                for (const id of matchingIds) {
                                    if (next.has(id)) next.delete(id)
                                    else next.add(id)
                                }
                                return next
                            })}
                        >
                            Invert
                        </button>
                        <button type="button" className="entropy-button entropy-button-secondary entropy-button-icon entropy-button-sm" aria-label="Close wallpaper picker" title="Close" onClick={onClose}>
                            <X size={17} />
                        </button>
                    </div>
                </header>

                <div className="wallpaper-picker-grid">
                    {visible.map((item) => {
                        const selected = draftIds.has(item.id)
                        const video = isVideoBackground(item)
                        return (
                            <button
                                key={item.id}
                                type="button"
                                className={`wallpaper-picker-card${selected ? ' is-selected' : ''}`}
                                aria-pressed={selected}
                                onClick={() => toggle(item.id)}
                            >
                                {video ? (
                                    <video src={item.url} muted loop autoPlay playsInline preload="metadata" aria-hidden="true" />
                                ) : (
                                    <img src={item.url} alt="" loading="lazy" />
                                )}
                                <span className="wallpaper-picker-card-check" aria-hidden="true">
                                    {selected && <Check size={15} />}
                                </span>
                                <span className="wallpaper-picker-card-caption">
                                    <strong title={item.name}>{item.name}</strong>
                                    <small>{video ? <><Film size={12} /> Video</> : 'Image'} · {item.source === 'upload' ? 'Uploaded' : 'System'}</small>
                                </span>
                            </button>
                        )
                    })}
                    {visible.length === 0 && <p className="wallpaper-picker-empty">No wallpapers match that search.</p>}
                </div>

                {matching.length > 0 && (
                    <nav className="wallpaper-picker-pagination" aria-label="Wallpaper picker pages">
                        <span>
                            Showing {page * WALLPAPERS_PER_PAGE + 1}–
                            {Math.min((page + 1) * WALLPAPERS_PER_PAGE, matching.length)} of {matching.length}
                        </span>
                        <div>
                            <button type="button" className="entropy-button entropy-button-secondary entropy-button-icon entropy-button-sm" aria-label="First page" disabled={page === 0} onClick={() => setPage(0)}><ChevronsLeft size={16} /></button>
                            <button type="button" className="entropy-button entropy-button-secondary entropy-button-icon entropy-button-sm" aria-label="Previous page" disabled={page === 0} onClick={() => setPage((current) => current - 1)}><ChevronLeft size={16} /></button>
                            <span>Page {page + 1} of {pageCount}</span>
                            <button type="button" className="entropy-button entropy-button-secondary entropy-button-icon entropy-button-sm" aria-label="Next page" disabled={page >= pageCount - 1} onClick={() => setPage((current) => current + 1)}><ChevronRight size={16} /></button>
                            <button type="button" className="entropy-button entropy-button-secondary entropy-button-icon entropy-button-sm" aria-label="Last page" disabled={page >= pageCount - 1} onClick={() => setPage(pageCount - 1)}><ChevronsRight size={16} /></button>
                        </div>
                    </nav>
                )}

                <footer className="wallpaper-picker-footer">
                    <span>Shortcuts: Ctrl/Cmd+A select matching · Ctrl/Cmd+D clear · Ctrl/Cmd+I invert matching · Esc close</span>
                    <div>
                        <button type="button" className="entropy-button entropy-button-secondary" onClick={onClose}>Cancel</button>
                        <button type="button" className="entropy-button entropy-button-primary" onClick={() => onApply([...draftIds])}>Apply selection</button>
                    </div>
                </footer>
            </section>
            </div>
        </AppPortal>
    )
}
