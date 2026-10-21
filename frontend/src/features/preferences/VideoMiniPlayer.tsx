import {
    useCallback,
    useEffect,
    useRef,
    useState,
    type KeyboardEvent as ReactKeyboardEvent,
    type PointerEvent as ReactPointerEvent,
} from 'react'
import {
    Film,
    Maximize2,
    Minimize2,
    EyeOff,
    Pause,
    Play,
    SkipBack,
    SkipForward,
    Volume2,
    VolumeX,
} from 'lucide-react'

import type { BackgroundImage } from '../../api/backgrounds.api'
import AppPortal from '../../components/layout/AppPortal'
import '../../styles/video-mini-player.css'

/** Where the player sits, remembered per browser. */
const SPOT_KEY = 'entropy.videoPlayer.spot'
/** Left by the old Close button (the player could not be brought back). */
const OLD_CLOSED_KEY = 'entropy.videoPlayer.closed'
/** Gap kept between the player and the viewport edges. */
const EDGE = 16
const EDGE_PHONE = 12
/** Pointer travel before a press on the player counts as a drag. */
const DRAG_THRESHOLD = 4
/** Length of the player's longer side: default, and the range it can be resized in. */
const DEFAULT_LONG_SIDE = 320
const MIN_LONG_SIDE = 160
const MAX_LONG_SIDE = 1100
/** Narrowest player that still fits its controls (tall videos get taller instead). */
const MIN_WIDTH = 150
/** Until the video reports its size. */
const DEFAULT_RATIO = 16 / 9

type Corner = 'nw' | 'ne' | 'sw' | 'se'
const CORNERS: Corner[] = ['nw', 'ne', 'sw', 'se']

type Mode = 'mini' | 'max' | 'pill'

/**
 * Position as fractions of the free space on each axis: 0 is the left/top
 * edge, 1 the right/bottom. Fractions keep the player inside the viewport
 * and in the same corner when the window is resized.
 */
interface Spot {
    x: number
    y: number
    minimized: boolean
    /** Corner the hidden player's tab sits in: 0 left/top, 1 right/bottom. */
    tabX: number
    tabY: number
    /** Longer side in pixels, so a size suits portrait and landscape videos alike. */
    size: number
}

const DEFAULT_SPOT: Spot = { x: 1, y: 1, minimized: false, tabX: 1, tabY: 1, size: DEFAULT_LONG_SIDE }

function clamp01(value: number): number {
    return Math.min(1, Math.max(0, Number.isFinite(value) ? value : 1))
}

function readSpot(): Spot {
    try {
        const saved = JSON.parse(window.localStorage.getItem(SPOT_KEY) ?? 'null') as Partial<Spot> | null
        if (!saved || typeof saved !== 'object') return DEFAULT_SPOT
        return {
            x: clamp01(Number(saved.x)),
            y: clamp01(Number(saved.y)),
            minimized: saved.minimized === true,
            tabX: Number(saved.tabX) === 0 ? 0 : 1,
            tabY: Number(saved.tabY) === 0 ? 0 : 1,
            size: Number.isFinite(Number(saved.size)) ? Number(saved.size) : DEFAULT_LONG_SIDE,
        }
    } catch {
        return DEFAULT_SPOT
    }
}

function writeSpot(spot: Spot) {
    try {
        window.localStorage.setItem(SPOT_KEY, JSON.stringify(spot))
    } catch {
        // Storage unavailable (private mode, blocked site data): position is not kept.
    }
}

function forgetOldClose() {
    try {
        window.sessionStorage.removeItem(OLD_CLOSED_KEY)
    } catch {
        // Nothing to forget.
    }
}

function viewportSize() {
    const root = document.documentElement
    return { width: root.clientWidth || window.innerWidth, height: root.clientHeight || window.innerHeight }
}

function prefersReducedMotion(): boolean {
    return typeof window.matchMedia === 'function'
        && window.matchMedia('(prefers-reduced-motion: reduce)').matches
}

/**
 * The player's box for a long-side length and the video's aspect ratio,
 * kept inside the viewport (minus `edge` on every side).
 */
function frameSize(longSide: number, ratio: number, viewport: { width: number; height: number }, edge: number) {
    const maxWidth = viewport.width - edge * 2
    const maxHeight = viewport.height - edge * 2
    let long = Math.min(Math.max(longSide, MIN_LONG_SIDE), MAX_LONG_SIDE)
    let width = ratio >= 1 ? long : long * ratio
    let height = ratio >= 1 ? long / ratio : long
    if (width < MIN_WIDTH) {
        height *= MIN_WIDTH / width
        width = MIN_WIDTH
    }
    // Shrink to fit; on small screens this can go below the usual minimum.
    const fit = Math.min(1, maxWidth / width, maxHeight / height)
    width *= fit
    height *= fit
    long = Math.max(width, height)
    return { width: Math.round(width), height: Math.round(height), long }
}

/** The wallpaper video playing behind the page, if any. */
function backgroundVideo(url: string): HTMLVideoElement | null {
    const videos = document.querySelectorAll<HTMLVideoElement>(
        '.wallpaper-layer video.wallpaper-media:not(.wallpaper-media-blur)',
    )
    const target = new URL(url, window.location.href).href

    return Array.from(videos).find((video) => video.currentSrc === target || video.src === target) ?? null
}

/**
 * The video wallpaper, also playing in a small floating window that can be
 * dragged, resized, enlarged, or hidden to a tab in a corner of the screen.
 */
export default function VideoMiniPlayer({
    background,
    position = null,
    onStep,
}: {
    background: BackgroundImage
    /** "2 / 5" among the video wallpapers, when there are others to switch to. */
    position?: string | null
    /** Switch the wallpaper to the previous (-1) or next (1) video. */
    onStep?: (direction: 1 | -1) => void
}) {
    const [spot, setSpot] = useState(readSpot)
    const [maximized, setMaximized] = useState(false)
    const [viewport, setViewport] = useState(viewportSize)
    const [measured, setMeasured] = useState<{ mode: Mode; width: number; height: number } | null>(null)
    const [reducedMotion, setReducedMotion] = useState(prefersReducedMotion)
    // Keyed by URL so a new wallpaper (shuffle) starts from its own state.
    const [playingUrl, setPlayingUrl] = useState<string | null>(null)
    const playing = playingUrl === background.url
    const [muted, setMuted] = useState(true)
    // The video's own shape (width / height); the frame follows it, no letterboxing.
    const [ratios, setRatios] = useState<Record<string, number>>({})
    const ratio = ratios[background.url] ?? DEFAULT_RATIO

    const mode: Mode = maximized ? 'max' : spot.minimized ? 'pill' : 'mini'

    const videoRef = useRef<HTMLVideoElement | null>(null)
    const frameRef = useRef<HTMLDivElement | null>(null)
    const maximizeRef = useRef<HTMLButtonElement | null>(null)
    const restoreRef = useRef<HTMLButtonElement | null>(null)
    const pillRef = useRef<HTMLButtonElement | null>(null)
    const drag = useRef<{
        pointerId: number
        startX: number
        startY: number
        left: number
        top: number
        moved: boolean
    } | null>(null)
    const resize = useRef<{
        pointerId: number
        corner: Corner
        startX: number
        startY: number
        left: number
        top: number
        width: number
        height: number
    } | null>(null)
    const suppressClick = useRef(false)
    const focusAfterMode = useRef<'maximize' | 'restore' | 'pill' | null>(null)

    useEffect(() => {
        const onResize = () => setViewport(viewportSize())
        window.addEventListener('resize', onResize)
        return () => window.removeEventListener('resize', onResize)
    }, [])

    useEffect(() => {
        if (typeof window.matchMedia !== 'function') return
        const query = window.matchMedia('(prefers-reduced-motion: reduce)')
        const onChange = () => setReducedMotion(query.matches)
        query.addEventListener('change', onChange)
        return () => query.removeEventListener('change', onChange)
    }, [])

    // Measure the floating element so it can be kept fully on screen.
    const observe = useCallback((node: HTMLDivElement | HTMLButtonElement | null, nodeMode: Mode) => {
        if (!node || typeof ResizeObserver === 'undefined') return undefined
        const observer = new ResizeObserver(() => {
            setMeasured({ mode: nodeMode, width: node.offsetWidth, height: node.offsetHeight })
        })
        observer.observe(node)
        return () => observer.disconnect()
    }, [])

    useEffect(() => {
        if (mode === 'max') return undefined
        return observe(mode === 'pill' ? pillRef.current : frameRef.current, mode)
    }, [mode, observe])

    useEffect(forgetOldClose, [])

    useEffect(() => {
        const video = videoRef.current
        if (video) video.muted = muted
    }, [muted, mode, background.url])

    // Escape restores the enlarged view.
    useEffect(() => {
        if (mode !== 'max') return undefined
        const onKeyDown = (event: KeyboardEvent) => {
            if (event.key !== 'Escape' || event.defaultPrevented) return
            event.preventDefault()
            focusAfterMode.current = 'maximize'
            setMaximized(false)
        }
        window.addEventListener('keydown', onKeyDown)
        return () => window.removeEventListener('keydown', onKeyDown)
    }, [mode])

    // Move focus with the view so keyboard users are not left on a removed button.
    useEffect(() => {
        const target = focusAfterMode.current
        focusAfterMode.current = null
        if (target === 'restore') restoreRef.current?.focus()
        else if (target === 'maximize') maximizeRef.current?.focus()
        else if (target === 'pill') pillRef.current?.focus()
    }, [mode])

    const edge = viewport.width <= 520 ? EDGE_PHONE : EDGE
    const frame = frameSize(spot.size, ratio, viewport, edge)
    const size =
        mode === 'pill'
            ? measured?.mode === 'pill'
                ? measured
                : { width: 44, height: 44 }
            : frame
    const freeX = Math.max(0, viewport.width - size.width - edge * 2)
    const freeY = Math.max(0, viewport.height - size.height - edge * 2)
    // The hidden player's tab has its own place: a corner.
    const hidden = mode === 'pill'
    const posX = hidden ? spot.tabX : spot.x
    const posY = hidden ? spot.tabY : spot.y
    const left = edge + posX * freeX
    const top = edge + posY * freeY

    const updateSpot = (next: Spot, persist: boolean) => {
        setSpot(next)
        if (persist) writeSpot(next)
    }

    const startDrag = (event: ReactPointerEvent<HTMLElement>) => {
        if (mode === 'max' || event.button !== 0) return
        // Buttons inside the player keep their own clicks (the tab is itself a button).
        const button = (event.target as HTMLElement).closest('button')
        if (button && button !== event.currentTarget) return

        // A new press: a click after it is a click unless this press drags.
        suppressClick.current = false
        // Follow the pointer from the press on: a quick first move can
        // already be outside a small target such as the corner tab.
        event.currentTarget.setPointerCapture(event.pointerId)
        drag.current = {
            pointerId: event.pointerId,
            startX: event.clientX,
            startY: event.clientY,
            left,
            top,
            moved: false,
        }
    }

    const moveDrag = (event: ReactPointerEvent<HTMLElement>) => {
        const state = drag.current
        if (!state || state.pointerId !== event.pointerId) return

        const dx = event.clientX - state.startX
        const dy = event.clientY - state.startY

        if (!state.moved) {
            if (Math.hypot(dx, dy) < DRAG_THRESHOLD) return
            state.moved = true
        }

        event.preventDefault()
        const x = freeX > 0 ? clamp01((state.left + dx - edge) / freeX) : posX
        const y = freeY > 0 ? clamp01((state.top + dy - edge) / freeY) : posY
        updateSpot(hidden ? { ...spot, tabX: x, tabY: y } : { ...spot, x, y }, false)
    }

    const endDrag = (event: ReactPointerEvent<HTMLElement>) => {
        const state = drag.current
        if (!state || state.pointerId !== event.pointerId) return
        drag.current = null
        if (event.currentTarget.hasPointerCapture(event.pointerId)) {
            event.currentTarget.releasePointerCapture(event.pointerId)
        }

        if (state.moved) {
            suppressClick.current = true
            // A dropped tab snaps to the nearest corner.
            updateSpot(
                hidden ? { ...spot, tabX: Math.round(spot.tabX), tabY: Math.round(spot.tabY) } : spot,
                true,
            )
        }
    }

    // Arrow keys move the focused player; Shift moves it further.
    const moveWithKeys = (event: ReactKeyboardEvent<HTMLElement>) => {
        if (mode === 'max' || event.target !== event.currentTarget) return
        if (event.key === '+' || event.key === '=' || event.key === '-' || event.key === '_') {
            event.preventDefault()
            resizeBy(event.key === '-' || event.key === '_' ? 1 / 1.15 : 1.15)
            return
        }
        const step = event.shiftKey ? 0.25 : 0.05
        const delta: Record<string, [number, number]> = {
            ArrowLeft: [-step, 0],
            ArrowRight: [step, 0],
            ArrowUp: [0, -step],
            ArrowDown: [0, step],
        }
        const move = delta[event.key]
        if (!move) return
        event.preventDefault()
        updateSpot({ ...spot, x: clamp01(spot.x + move[0]), y: clamp01(spot.y + move[1]) }, true)
    }

    const startResize = (event: ReactPointerEvent<HTMLElement>, corner: Corner) => {
        if (event.button !== 0) return
        event.stopPropagation()
        event.preventDefault()
        event.currentTarget.setPointerCapture(event.pointerId)
        resize.current = {
            pointerId: event.pointerId,
            corner,
            startX: event.clientX,
            startY: event.clientY,
            left,
            top,
            width: frame.width,
            height: frame.height,
        }
    }

    /** The spot that puts a box of `width` x `height` at `boxLeft`, `boxTop`. */
    const spotFor = (boxLeft: number, boxTop: number, width: number, height: number, long: number): Spot => {
        const roomX = Math.max(0, viewport.width - width - edge * 2)
        const roomY = Math.max(0, viewport.height - height - edge * 2)
        return {
            ...spot,
            size: long,
            x: roomX > 0 ? clamp01((boxLeft - edge) / roomX) : spot.x,
            y: roomY > 0 ? clamp01((boxTop - edge) / roomY) : spot.y,
        }
    }

    const moveResize = (event: ReactPointerEvent<HTMLElement>) => {
        const state = resize.current
        if (!state || state.pointerId !== event.pointerId) return
        event.stopPropagation()
        const west = state.corner.includes('w')
        const north = state.corner.includes('n')
        const dx = (event.clientX - state.startX) * (west ? -1 : 1)
        const dy = (event.clientY - state.startY) * (north ? -1 : 1)
        // Follow whichever direction the pointer moved further; the shape stays.
        const grow = Math.abs(dx) >= Math.abs(dy * ratio) ? dx : dy * ratio
        const wanted = state.width + grow
        const longSide = ratio >= 1 ? wanted : wanted / ratio
        // Keep the opposite corner where it is, and the box on screen.
        const right = state.left + state.width
        const bottom = state.top + state.height
        const room = {
            width: (west ? right : viewport.width - state.left) + edge,
            height: (north ? bottom : viewport.height - state.top) + edge,
        }
        const next = frameSize(longSide, ratio, room, edge)
        const boxLeft = west ? right - next.width : state.left
        const boxTop = north ? bottom - next.height : state.top
        updateSpot(spotFor(boxLeft, boxTop, next.width, next.height, next.long), false)
    }

    const endResize = (event: ReactPointerEvent<HTMLElement>) => {
        const state = resize.current
        if (!state || state.pointerId !== event.pointerId) return
        event.stopPropagation()
        resize.current = null
        if (event.currentTarget.hasPointerCapture(event.pointerId)) {
            event.currentTarget.releasePointerCapture(event.pointerId)
        }
        writeSpot(spot)
    }

    /** Grow or shrink by keyboard (+ / -), keeping the player's centre. */
    const resizeBy = (factor: number) => {
        const next = frameSize(frame.long * factor, ratio, viewport, edge)
        const centreX = left + frame.width / 2
        const centreY = top + frame.height / 2
        const boxLeft = Math.min(Math.max(edge, centreX - next.width / 2), viewport.width - edge - next.width)
        const boxTop = Math.min(Math.max(edge, centreY - next.height / 2), viewport.height - edge - next.height)
        updateSpot(spotFor(boxLeft, boxTop, next.width, next.height, next.long), true)
    }

    const togglePlay = () => {
        const video = videoRef.current
        if (!video) return
        if (video.paused) void video.play().catch(() => undefined)
        else video.pause()
    }

    const syncWithBackground = (video: HTMLVideoElement) => {
        const source = backgroundVideo(background.url)
        if (source && Number.isFinite(source.currentTime) && source.currentTime > 0) {
            video.currentTime = source.currentTime
        }
    }

    /** Tuck the player away as a tab in the screen corner nearest to it. */
    const hide = () => {
        focusAfterMode.current = 'pill'
        setMaximized(false)
        const centreX = left + frame.width / 2
        const centreY = top + frame.height / 2
        updateSpot(
            {
                ...spot,
                minimized: true,
                tabX: maximized || centreX >= viewport.width / 2 ? 1 : 0,
                tabY: maximized || centreY >= viewport.height / 2 ? 1 : 0,
            },
            true,
        )
    }

    const reopen = () => {
        if (suppressClick.current) {
            suppressClick.current = false
            return
        }
        focusAfterMode.current = 'maximize'
        updateSpot({ ...spot, minimized: false }, true)
    }

    const placed = { left, top }

    if (mode === 'pill') {
        return (
            <AppPortal>
                <button
                    ref={pillRef}
                    type="button"
                    className="video-mini-pill"
                    style={placed}
                    aria-label="Show the wallpaper video player (drag to another corner)"
                    title="Show the wallpaper video (drag to another corner)"
                    onClick={reopen}
                    onPointerDown={startDrag}
                    onPointerMove={moveDrag}
                    onPointerUp={endDrag}
                    onPointerCancel={endDrag}
                >
                    <Film size={18} aria-hidden="true" />
                </button>
            </AppPortal>
        )
    }

    const isMax = mode === 'max'

    return (
        <AppPortal>
            {isMax && (
                <div
                    className="video-mini-backdrop"
                    aria-hidden="true"
                    onClick={() => {
                        focusAfterMode.current = 'maximize'
                        setMaximized(false)
                    }}
                />
            )}
            <div
                ref={frameRef}
                className={[
                    'video-mini-player',
                    isMax ? 'is-max' : '',
                    playing ? 'is-playing' : 'is-paused',
                ].filter(Boolean).join(' ')}
                style={
                    isMax
                        ? {
                              aspectRatio: String(ratio),
                              width: `min(1200px, calc(100vw - 32px), calc((100vh - 48px) * ${ratio}))`,
                          }
                        : { ...placed, width: frame.width, height: frame.height }
                }
                role={isMax ? 'dialog' : 'region'}
                aria-modal={isMax ? true : undefined}
                aria-label={
                    isMax
                        ? `Wallpaper video: ${background.name}`
                        : `Wallpaper video player: ${background.name}. Drag or use arrow keys to move, a corner or + and - to resize.`
                }
                tabIndex={isMax ? -1 : 0}
                onPointerDown={startDrag}
                onPointerMove={moveDrag}
                onPointerUp={endDrag}
                onPointerCancel={endDrag}
                onKeyDown={moveWithKeys}
            >
                <video
                    key={background.url}
                    ref={videoRef}
                    className="video-mini-media"
                    src={background.url}
                    autoPlay={!reducedMotion}
                    muted
                    loop
                    playsInline
                    preload="metadata"
                    onLoadedMetadata={(event) => {
                        const video = event.currentTarget
                        if (video.videoWidth > 0 && video.videoHeight > 0) {
                            const shape = video.videoWidth / video.videoHeight
                            setRatios((current) => ({ ...current, [background.url]: shape }))
                        }
                        syncWithBackground(video)
                    }}
                    onPlay={() => setPlayingUrl(background.url)}
                    onPause={() => setPlayingUrl(null)}
                    onDoubleClick={() => {
                        focusAfterMode.current = isMax ? 'maximize' : 'restore'
                        setMaximized(!isMax)
                    }}
                />

                {!playing && (
                    <button
                        type="button"
                        className="video-mini-center-play"
                        aria-label="Play wallpaper video"
                        onClick={togglePlay}
                    >
                        <Play size={isMax ? 30 : 22} aria-hidden="true" />
                    </button>
                )}

                <div className="video-mini-bar video-mini-bar-top">
                    <span className="video-mini-title" title={background.name}>
                        {background.name}
                    </span>
                    <div className="video-mini-actions">
                        <button
                            type="button"
                            className="video-mini-button"
                            aria-label="Hide to corner"
                            title="Hide to corner"
                            onClick={hide}
                        >
                            <EyeOff size={15} aria-hidden="true" />
                        </button>
                        {isMax ? (
                            <button
                                ref={restoreRef}
                                type="button"
                                className="video-mini-button"
                                aria-label="Restore small player"
                                title="Restore (Esc)"
                                onClick={() => {
                                    focusAfterMode.current = 'maximize'
                                    setMaximized(false)
                                }}
                            >
                                <Minimize2 size={15} aria-hidden="true" />
                            </button>
                        ) : (
                            <button
                                ref={maximizeRef}
                                type="button"
                                className="video-mini-button"
                                aria-label="Maximize player"
                                title="Maximize"
                                onClick={() => {
                                    focusAfterMode.current = 'restore'
                                    setMaximized(true)
                                }}
                            >
                                <Maximize2 size={15} aria-hidden="true" />
                            </button>
                        )}
                    </div>
                </div>

                <div className="video-mini-bar video-mini-bar-bottom">
                    <button
                        type="button"
                        className="video-mini-button"
                        aria-label={playing ? 'Pause' : 'Play'}
                        title={playing ? 'Pause' : 'Play'}
                        onClick={togglePlay}
                    >
                        {playing ? <Pause size={15} aria-hidden="true" /> : <Play size={15} aria-hidden="true" />}
                    </button>
                    <button
                        type="button"
                        className="video-mini-button"
                        aria-label={muted ? 'Unmute' : 'Mute'}
                        aria-pressed={!muted}
                        title={muted ? 'Unmute' : 'Mute'}
                        onClick={() => setMuted((value) => !value)}
                    >
                        {muted ? <VolumeX size={15} aria-hidden="true" /> : <Volume2 size={15} aria-hidden="true" />}
                    </button>
                    {onStep && (
                        <div className="video-mini-step">
                            <button
                                type="button"
                                className="video-mini-button"
                                aria-label="Previous wallpaper"
                                title="Previous wallpaper"
                                onClick={() => onStep(-1)}
                            >
                                <SkipBack size={15} aria-hidden="true" />
                            </button>
                            {position && <span className="video-mini-position">{position}</span>}
                            <button
                                type="button"
                                className="video-mini-button"
                                aria-label="Next wallpaper"
                                title="Next wallpaper"
                                onClick={() => onStep(1)}
                            >
                                <SkipForward size={15} aria-hidden="true" />
                            </button>
                        </div>
                    )}
                </div>

                {!isMax &&
                    CORNERS.map((corner) => (
                        <span
                            key={corner}
                            className={`video-mini-resize is-${corner}`}
                            aria-hidden="true"
                            title="Drag to resize"
                            onPointerDown={(event) => startResize(event, corner)}
                            onPointerMove={moveResize}
                            onPointerUp={endResize}
                            onPointerCancel={endResize}
                        />
                    ))}
            </div>
        </AppPortal>
    )
}
