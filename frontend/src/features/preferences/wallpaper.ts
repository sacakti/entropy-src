import { createContext, useEffect, useState, type CSSProperties } from 'react'

import type { BackgroundImage } from '../../api/backgrounds.api'
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

    const pool = backgrounds
        .filter((item) => shuffle.source === 'all' || item.source === 'upload')
        .map((item) => item.id)
    const poolKey = pool.join(',')

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

    return selectedId
}
