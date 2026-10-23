import { createContext, useEffect, useState, type CSSProperties } from 'react'

import { isVideoBackground, type BackgroundImage } from '../../api/backgrounds.api'
import type {
    UserPreferences,
    WallpaperPlacement,
    WallpaperShuffle,
} from '../../api/preferences.api'

/** Width / height below which a wallpaper counts as phone-shaped. */
const PORTRAIT_ASPECT = 0.8

export interface WallpaperState {
    background: BackgroundImage | null
    fit: UserPreferences['background_fit']
    /** 0–1 */
    opacity: number
    placement?: WallpaperPlacement
}

export const WallpaperContext = createContext<WallpaperState | null>(null)

export function isPortrait(width: number, height: number): boolean {
    return width > 0 && height > 0 && width / height < PORTRAIT_ASPECT
}

/** CSS for a placed wallpaper: focal point plus zoom around that point. */
export function placementStyle(placement: WallpaperPlacement): CSSProperties {
    return {
        objectFit: 'cover',
        objectPosition: `${placement.x}% ${placement.y}%`,
        transform: placement.zoom === 100 ? undefined : `scale(${placement.zoom / 100})`,
        transformOrigin: `${placement.x}% ${placement.y}%`,
    }
}

/**
 * The wallpaper to display: the chosen one, or while shuffle is on, a
 * different one from the pool every interval. Shuffling is not saved.
 */
export function useShuffledWallpaper(
    backgrounds: BackgroundImage[],
    selectedId: number | null,
    shuffle: WallpaperShuffle,
): number | null {
    const [shuffledId, setShuffledId] = useState<number | null>(null)

    const customIds = new Set(shuffle.custom_ids ?? [])
    const pool = backgrounds
        .filter((item) => {
            if (shuffle.source === 'uploads' && item.source !== 'upload') return false
            if (shuffle.source === 'custom' && !customIds.has(item.id)) return false
            if (shuffle.kind === 'image' && isVideoBackground(item)) return false
            if (shuffle.kind === 'video' && !isVideoBackground(item)) return false
            return true
        })
        .map((item) => item.id)
    const poolKey = pool.join(',')

    // A wallpaper chosen by hand shows until the next shuffle.
    const [shownFor, setShownFor] = useState(selectedId)
    if (shownFor !== selectedId) {
        setShownFor(selectedId)
        setShuffledId(null)
    }

    useEffect(() => {
        if (!shuffle.enabled) return

        const ids = poolKey ? poolKey.split(',').map(Number) : []

        if (ids.length < 2) return

        const timer = window.setInterval(() => {
            setShuffledId((current) => {
                const showing = current ?? selectedId
                const choices = ids.filter((id) => id !== showing)
                return choices[Math.floor(Math.random() * choices.length)]
            })
        }, shuffle.interval_minutes * 60_000)

        return () => window.clearInterval(timer)
    }, [poolKey, selectedId, shuffle.enabled, shuffle.interval_minutes])

    if (shuffle.enabled && shuffledId !== null && pool.includes(shuffledId)) {
        return shuffledId
    }

    if (shuffle.enabled && pool.length === 1) return pool[0]
    if (shuffle.enabled && pool.length > 0 && !pool.includes(selectedId ?? -1)) return pool[0]

    return selectedId
}
