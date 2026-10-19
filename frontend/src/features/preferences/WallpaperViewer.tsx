import {
    useCallback,
    useEffect,
    useRef,
    useState,
    type CSSProperties,
    type PointerEvent as ReactPointerEvent,
} from 'react'
import {
    Check,
    ChevronLeft,
    ChevronRight,
    Film,
    LoaderCircle,
    Maximize2,
    Minimize2,
    Move,
    RotateCcw,
    Scan,
    Smartphone,
    Trash2,
    Wallpaper,
    X,
    ZoomIn,
    ZoomOut,
} from 'lucide-react'

import { isVideoBackground, type BackgroundImage } from '../../api/backgrounds.api'
import type { WallpaperPlacement } from '../../api/preferences.api'
import AppPortal from '../../components/layout/AppPortal'
import WallpaperLayer from './WallpaperLayer'
import { isPortrait, placementStyle } from './wallpaper'

const MIN_ZOOM = 0.25
const MAX_ZOOM = 6
const DEFAULT_PLACEMENT: WallpaperPlacement = { x: 50, y: 50, zoom: 100 }

function clampZoom(value: number): number {
    return Math.min(MAX_ZOOM, Math.max(MIN_ZOOM, Math.round(value * 100) / 100))
}

function Media({
    background,
    className,
    style,
    controls,
    onMeasure,
}: {
    background: BackgroundImage
    className?: string
    style?: CSSProperties
    controls?: boolean
    onMeasure?: (width: number, height: number) => void
}) {
    if (isVideoBackground(background)) {
        return (
            <video
                className={className}
                style={style}
                src={background.url}
                autoPlay={controls}
                muted
                loop
                playsInline
                controls={controls}
                preload="metadata"
                draggable={false}
                onLoadedMetadata={(event) =>
                    onMeasure?.(event.currentTarget.videoWidth, event.currentTarget.videoHeight)
                }
            />
        )
    }

    return (
        <img
            className={className}
            style={style}
            src={background.url}
            alt={background.name}
            draggable={false}
            onLoad={(event) =>
                onMeasure?.(event.currentTarget.naturalWidth, event.currentTarget.naturalHeight)
            }
        />
    )
}

/**
 * Full-screen wallpaper gallery: thumbnails on the left, the selected
 * wallpaper with zoom and pan, and "set as wallpaper" with placement.
 */
export default function WallpaperViewer({
    backgrounds,
    initialIndex,
    selectedId,
    placements,
    busy,
    onClose,
    onSetWallpaper,
    onDelete,
}: {
    backgrounds: BackgroundImage[]
    initialIndex: number
    selectedId: number | null
    placements: Record<string, WallpaperPlacement>
    busy: boolean
    onClose: () => void
    /** `placement` null means fit automatically. */
    onSetWallpaper: (background: BackgroundImage, placement: WallpaperPlacement | null) => Promise<void>
    onDelete: (background: BackgroundImage) => Promise<boolean>
}) {
    const rootRef = useRef<HTMLDivElement>(null)
    const stripRef = useRef<HTMLDivElement>(null)
    const frameRef = useRef<HTMLDivElement>(null)
    const dragRef = useRef<{ x: number; y: number; panX: number; panY: number } | null>(null)

    const [index, setIndex] = useState(initialIndex)
    const [zoom, setZoom] = useState(1)
    const [pan, setPan] = useState({ x: 0, y: 0 })
    const [maximized, setMaximized] = useState(false)
    const [sizes, setSizes] = useState<Record<number, { width: number; height: number }>>({})
    const [placing, setPlacing] = useState<WallpaperPlacement | null>(null)
    const [saving, setSaving] = useState(false)

    const count = backgrounds.length
    const current = backgrounds[Math.min(index, count - 1)] ?? null
    const size = current ? sizes[current.id] : undefined
    const portrait = size ? isPortrait(size.width, size.height) : false

    const go = useCallback(
        (next: number) => {
            if (next < 0 || next >= count) return
            setIndex(next)
            setZoom(1)
            setPan({ x: 0, y: 0 })
            setPlacing(null)
        },
        [count],
    )

    const fit = () => {
        setZoom(1)
        setPan({ x: 0, y: 0 })
    }

    const toggleMaximized = useCallback(() => {
        const next = !maximized
        setMaximized(next)

        // Use the browser's full screen too, where allowed.
        try {
            if (next && !document.fullscreenElement) {
                void rootRef.current?.requestFullscreen?.().catch(() => undefined)
            } else if (!next && document.fullscreenElement) {
                void document.exitFullscreen().catch(() => undefined)
            }
        } catch {
            // Full screen unavailable: the in-page maximized view still applies.
        }
    }, [maximized])

    // Leaving browser full screen (Esc) also restores the view.
    useEffect(() => {
        const handleChange = () => {
            if (!document.fullscreenElement) setMaximized(false)
        }

        document.addEventListener('fullscreenchange', handleChange)
        return () => {
            document.removeEventListener('fullscreenchange', handleChange)
            if (document.fullscreenElement) void document.exitFullscreen().catch(() => undefined)
        }
    }, [])

    // Keep the current thumbnail in view.
    useEffect(() => {
        stripRef.current
            ?.querySelector<HTMLElement>(`[data-index="${index}"]`)
            ?.scrollIntoView({ block: 'nearest' })
    }, [index])

    useEffect(() => {
        function handleKeyDown(event: KeyboardEvent) {
            const target = event.target as HTMLElement | null

            if (target && ['INPUT', 'TEXTAREA', 'SELECT'].includes(target.tagName)) return

            if (event.key === 'Escape') {
                event.preventDefault()
                if (placing) setPlacing(null)
                else if (maximized) toggleMaximized()
                else onClose()
            } else if (event.key === 'ArrowLeft') {
                event.preventDefault()
                go(index - 1)
            } else if (event.key === 'ArrowRight') {
                event.preventDefault()
                go(index + 1)
            } else if (event.key === '+' || event.key === '=') {
                setZoom((value) => clampZoom(value + 0.25))
            } else if (event.key === '-' || event.key === '_') {
                setZoom((value) => clampZoom(value - 0.25))
            } else if (event.key === '0') {
                setZoom(1)
                setPan({ x: 0, y: 0 })
            } else if (event.key.toLowerCase() === 'f') {
                toggleMaximized()
            }
        }

        window.addEventListener('keydown', handleKeyDown)
        return () => window.removeEventListener('keydown', handleKeyDown)
    }, [go, index, maximized, onClose, placing, toggleMaximized])

    if (!current) return null

    const measure = (id: number) => (width: number, height: number) =>
        setSizes((value) =>
            value[id]?.width === width && value[id]?.height === height
                ? value
                : { ...value, [id]: { width, height } },
        )

    const startPan = (event: ReactPointerEvent<HTMLDivElement>) => {
        if (zoom <= 1 || event.button !== 0) return
        event.currentTarget.setPointerCapture(event.pointerId)
        dragRef.current = { x: event.clientX, y: event.clientY, panX: pan.x, panY: pan.y }
    }

    const movePan = (event: ReactPointerEvent<HTMLDivElement>) => {
        const drag = dragRef.current
        if (!drag) return
        setPan({ x: drag.panX + event.clientX - drag.x, y: drag.panY + event.clientY - drag.y })
    }

    const setAsWallpaper = async (placement: WallpaperPlacement | null) => {
        setSaving(true)
        try {
            await onSetWallpaper(current, placement)
            setPlacing(null)
        } finally {
            setSaving(false)
        }
    }

    const beginSetWallpaper = () => {
        // Phone-shaped wallpapers fit themselves; others get placement controls.
        if (portrait) {
            void setAsWallpaper(null)
        } else {
            setPlacing(placements[String(current.id)] ?? DEFAULT_PLACEMENT)
        }
    }

    // Drag inside the placement preview to move the focal point.
    const movePlacement = (event: ReactPointerEvent<HTMLDivElement>) => {
        if (!placing || !(event.buttons & 1)) return
        const rect = frameRef.current?.getBoundingClientRect()
        if (!rect) return
        const x = Math.round(Math.min(100, Math.max(0, ((event.clientX - rect.left) / rect.width) * 100)))
        const y = Math.round(Math.min(100, Math.max(0, ((event.clientY - rect.top) / rect.height) * 100)))
        setPlacing({ ...placing, x, y })
    }

    const isSelected = selectedId === current.id
    const video = isVideoBackground(current)

    return (
        <AppPortal>
            <div
                ref={rootRef}
                className={`wallpaper-viewer${maximized ? ' is-maximized' : ''}`}
                role="dialog"
                aria-modal="true"
                aria-label={`Wallpaper gallery: ${current.name}`}
            >
                <WallpaperLayer veil="var(--app-bg)" />

                {!maximized && (
                    <header className="wallpaper-viewer-topbar">
                        <button
                            type="button"
                            className="entropy-button entropy-button-secondary"
                            onClick={onClose}
                        >
                            <X size={16} />
                            Close
                        </button>

                        <div className="wallpaper-viewer-title">
                            <strong title={current.name}>{current.name}</strong>
                            <span>
                                {index + 1} of {count}
                            </span>
                            <span className="wallpaper-viewer-chip">
                                {video ? <Film size={12} /> : null}
                                {video ? 'Video' : 'Image'}
                                {size ? ` · ${size.width}×${size.height}` : ''}
                            </span>
                            {portrait && (
                                <span className="wallpaper-viewer-chip" title="Fits automatically as a wallpaper">
                                    <Smartphone size={12} />
                                    Phone aspect
                                </span>
                            )}
                            {isSelected && (
                                <span className="wallpaper-viewer-chip is-accent">
                                    <Check size={12} />
                                    Current wallpaper
                                </span>
                            )}
                        </div>

                        <div className="wallpaper-viewer-tools">
                            <ZoomControls zoom={zoom} setZoom={setZoom} onFit={fit} />
                            <button
                                type="button"
                                className="entropy-button entropy-button-ghost entropy-button-icon"
                                aria-label="Maximize"
                                title="Maximize (F)"
                                onClick={toggleMaximized}
                            >
                                <Maximize2 size={17} />
                            </button>

                            {current.source === 'upload' && (
                                <button
                                    type="button"
                                    className="entropy-button entropy-button-danger-quiet entropy-button-icon"
                                    aria-label={`Delete ${current.name}`}
                                    title="Delete"
                                    disabled={busy || saving}
                                    onClick={async () => {
                                        const deleted = await onDelete(current)
                                        if (deleted && count <= 1) onClose()
                                        else if (deleted) go(Math.max(0, Math.min(index, count - 2)))
                                    }}
                                >
                                    <Trash2 size={16} />
                                </button>
                            )}

                            <button
                                type="button"
                                className="entropy-button entropy-button-primary"
                                disabled={busy || saving || placing !== null}
                                onClick={beginSetWallpaper}
                            >
                                {saving ? <LoaderCircle size={15} className="entropy-spin" /> : <Wallpaper size={15} />}
                                Set as wallpaper
                            </button>
                        </div>
                    </header>
                )}

                <div className="wallpaper-viewer-body">
                    {!maximized && (
                        <nav className="wallpaper-viewer-strip" ref={stripRef} aria-label="Wallpapers">
                            {backgrounds.map((background, position) => (
                                <button
                                    key={background.id}
                                    type="button"
                                    data-index={position}
                                    className={`wallpaper-viewer-thumb${position === index ? ' is-active' : ''}`}
                                    aria-current={position === index ? 'true' : undefined}
                                    aria-label={background.name}
                                    title={background.name}
                                    onClick={() => go(position)}
                                >
                                    <Media background={background} onMeasure={measure(background.id)} />
                                    {isVideoBackground(background) && (
                                        <span className="wallpaper-viewer-thumb-badge">
                                            <Film size={11} />
                                        </span>
                                    )}
                                    {background.id === selectedId && (
                                        <span className="wallpaper-viewer-thumb-check">
                                            <Check size={11} />
                                        </span>
                                    )}
                                    <span className="wallpaper-viewer-thumb-name">{background.name}</span>
                                </button>
                            ))}
                        </nav>
                    )}

                    <main
                        className={`wallpaper-viewer-stage${zoom > 1 ? ' is-pannable' : ''}`}
                        onWheel={(event) => {
                            setZoom((value) => clampZoom(value * (event.deltaY < 0 ? 1.12 : 1 / 1.12)))
                        }}
                        onPointerDown={startPan}
                        onPointerMove={movePan}
                        onPointerUp={() => {
                            dragRef.current = null
                        }}
                        onDoubleClick={() => (zoom === 1 ? setZoom(2) : fit())}
                    >
                        <button
                            type="button"
                            className="wallpaper-viewer-nav is-previous"
                            aria-label="Previous wallpaper"
                            title="Previous (←)"
                            disabled={index === 0}
                            onPointerDown={(event) => event.stopPropagation()}
                            onClick={() => go(index - 1)}
                        >
                            <ChevronLeft size={24} />
                        </button>

                        <Media
                            key={current.id}
                            background={current}
                            className="wallpaper-viewer-media"
                            controls={video}
                            onMeasure={measure(current.id)}
                            style={{ transform: `translate(${pan.x}px, ${pan.y}px) scale(${zoom})` }}
                        />

                        <button
                            type="button"
                            className="wallpaper-viewer-nav is-next"
                            aria-label="Next wallpaper"
                            title="Next (→)"
                            disabled={index >= count - 1}
                            onPointerDown={(event) => event.stopPropagation()}
                            onClick={() => go(index + 1)}
                        >
                            <ChevronRight size={24} />
                        </button>

                        {maximized && (
                            <div
                                className="wallpaper-viewer-floating"
                                onPointerDown={(event) => event.stopPropagation()}
                                onDoubleClick={(event) => event.stopPropagation()}
                            >
                                <ZoomControls zoom={zoom} setZoom={setZoom} onFit={fit} />
                                <button
                                    type="button"
                                    className="entropy-button entropy-button-ghost entropy-button-icon"
                                    aria-label="Minimize"
                                    title="Minimize (F or Esc)"
                                    onClick={toggleMaximized}
                                >
                                    <Minimize2 size={17} />
                                </button>
                            </div>
                        )}
                    </main>

                    {placing && !maximized && (
                        <aside className="wallpaper-viewer-placement" aria-label="Wallpaper placement">
                            <header>
                                <strong>Wallpaper placement</strong>
                                <span>Drag in the preview to choose the focus, then size it.</span>
                            </header>

                            <div
                                ref={frameRef}
                                className="wallpaper-placement-frame"
                                style={{ aspectRatio: `${window.innerWidth} / ${window.innerHeight}` }}
                                onPointerDown={(event) => {
                                    event.currentTarget.setPointerCapture(event.pointerId)
                                    movePlacement(event)
                                }}
                                onPointerMove={movePlacement}
                            >
                                <Media background={current} style={placementStyle(placing)} />
                                <span
                                    className="wallpaper-placement-focus"
                                    style={{ left: `${placing.x}%`, top: `${placing.y}%` }}
                                >
                                    <Move size={12} />
                                </span>
                            </div>

                            <label className="wallpaper-placement-field">
                                <span>
                                    Size <strong>{placing.zoom}%</strong>
                                </span>
                                <input
                                    type="range"
                                    min="100"
                                    max="400"
                                    step="5"
                                    value={placing.zoom}
                                    onChange={(event) => setPlacing({ ...placing, zoom: Number(event.target.value) })}
                                />
                            </label>
                            <label className="wallpaper-placement-field">
                                <span>
                                    Horizontal <strong>{placing.x}%</strong>
                                </span>
                                <input
                                    type="range"
                                    min="0"
                                    max="100"
                                    value={placing.x}
                                    onChange={(event) => setPlacing({ ...placing, x: Number(event.target.value) })}
                                />
                            </label>
                            <label className="wallpaper-placement-field">
                                <span>
                                    Vertical <strong>{placing.y}%</strong>
                                </span>
                                <input
                                    type="range"
                                    min="0"
                                    max="100"
                                    value={placing.y}
                                    onChange={(event) => setPlacing({ ...placing, y: Number(event.target.value) })}
                                />
                            </label>

                            <footer>
                                <button
                                    type="button"
                                    className="entropy-button entropy-button-ghost entropy-button-sm"
                                    onClick={() => setPlacing(DEFAULT_PLACEMENT)}
                                >
                                    <RotateCcw size={14} />
                                    Reset
                                </button>
                                <button
                                    type="button"
                                    className="entropy-button entropy-button-secondary entropy-button-sm"
                                    onClick={() => setPlacing(null)}
                                    disabled={saving}
                                >
                                    Cancel
                                </button>
                                <button
                                    type="button"
                                    className="entropy-button entropy-button-primary entropy-button-sm"
                                    onClick={() => void setAsWallpaper(placing)}
                                    disabled={saving || busy}
                                >
                                    {saving ? <LoaderCircle size={14} className="entropy-spin" /> : <Check size={14} />}
                                    Apply
                                </button>
                            </footer>
                        </aside>
                    )}
                </div>
            </div>
        </AppPortal>
    )
}

function ZoomControls({
    zoom,
    setZoom,
    onFit,
}: {
    zoom: number
    setZoom: (update: (value: number) => number) => void
    onFit: () => void
}) {
    return (
        <div className="wallpaper-viewer-zoom">
            <button
                type="button"
                className="entropy-button entropy-button-ghost entropy-button-icon entropy-button-sm"
                aria-label="Zoom out"
                title="Zoom out (−)"
                disabled={zoom <= MIN_ZOOM}
                onClick={() => setZoom((value) => clampZoom(value - 0.25))}
            >
                <ZoomOut size={16} />
            </button>
            <span>{Math.round(zoom * 100)}%</span>
            <button
                type="button"
                className="entropy-button entropy-button-ghost entropy-button-icon entropy-button-sm"
                aria-label="Zoom in"
                title="Zoom in (+)"
                disabled={zoom >= MAX_ZOOM}
                onClick={() => setZoom((value) => clampZoom(value + 0.25))}
            >
                <ZoomIn size={16} />
            </button>
            <button
                type="button"
                className="entropy-button entropy-button-ghost entropy-button-icon entropy-button-sm"
                aria-label="Fit to screen"
                title="Fit to screen (0)"
                onClick={onFit}
            >
                <Scan size={16} />
            </button>
        </div>
    )
}
