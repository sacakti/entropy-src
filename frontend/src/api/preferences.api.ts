import { apiRequest } from '../services/api'

export type Theme = 'dark' | 'light'
export type BackgroundFit = 'cover' | 'contain' | 'fill'

export interface UserPreferences {
    theme: Theme
    accent_color: string
    background_image_id: number | null
    background_fit: BackgroundFit
    background_opacity: number
    modal_backdrop_opacity: number
}

export async function getPreferences(): Promise<UserPreferences> {
    return apiRequest<UserPreferences>('/api/preferences')
}

export async function updatePreferences(
    preferences: UserPreferences,
): Promise<UserPreferences> {
    return apiRequest<UserPreferences>('/api/preferences', {
        method: 'PUT',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify(preferences),
    })
}

/** Focal point (percent) and zoom (percent, 100 = cover) for one wallpaper. */
export interface WallpaperPlacement {
    x: number
    y: number
    zoom: number
}

export interface WallpaperShuffle {
    enabled: boolean
    interval_minutes: number
    source: 'all' | 'uploads'
}

export interface WallpaperSettings {
    /** Keyed by background id; wallpapers without one fit automatically. */
    placements: Record<string, WallpaperPlacement>
    shuffle: WallpaperShuffle
}

export const DEFAULT_WALLPAPER_SETTINGS: WallpaperSettings = {
    placements: {},
    shuffle: { enabled: false, interval_minutes: 15, source: 'all' },
}

export async function getWallpaperSettings(): Promise<WallpaperSettings> {
    return apiRequest<WallpaperSettings>('/api/preferences/wallpaper')
}

export async function updateWallpaperSettings(
    settings: WallpaperSettings,
): Promise<WallpaperSettings> {
    return apiRequest<WallpaperSettings>('/api/preferences/wallpaper', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(settings),
    })
}

export interface InterfaceSettings {
    /** Translucent "liquid glass" buttons, dialogs and menus. */
    glass: boolean
}

export async function getInterfaceSettings(): Promise<InterfaceSettings> {
    return apiRequest<InterfaceSettings>('/api/preferences/interface')
}

export async function updateInterfaceSettings(settings: InterfaceSettings): Promise<InterfaceSettings> {
    return apiRequest<InterfaceSettings>('/api/preferences/interface', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(settings),
    })
}
