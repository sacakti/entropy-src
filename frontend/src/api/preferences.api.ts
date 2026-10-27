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
    /** Wallpapers enabled on this server (install with ENTROPY_THEME_ENABLE=1). */
    theme_enabled?: boolean
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
    source: 'all' | 'uploads' | 'custom'
    kind?: 'all' | 'image' | 'video'
    custom_ids?: number[]
}

export interface WallpaperMemories {
    enabled: boolean
    interval_seconds: number
    animation: 'fade' | 'from-left' | 'from-top' | 'pop'
}

export interface WallpaperSettings {
    /** Keyed by background id; wallpapers without one fit automatically. */
    placements: Record<string, WallpaperPlacement>
    shuffle: WallpaperShuffle
    /**
     * Also play a video wallpaper in a small floating player window.
     * Missing from older servers; treat anything but `false` as on.
     */
    floating_player?: boolean
    floating_player_auto?: boolean
    floating_player_advance_mode?: 'ended' | 'interval'
    floating_player_interval_seconds?: number
    memories?: WallpaperMemories
}

export const DEFAULT_WALLPAPER_SETTINGS: WallpaperSettings = {
    placements: {},
    shuffle: { enabled: false, interval_minutes: 15, source: 'all', kind: 'all', custom_ids: [] },
    floating_player: true,
    floating_player_auto: false,
    floating_player_advance_mode: 'ended',
    floating_player_interval_seconds: 30,
    memories: { enabled: false, interval_seconds: 60, animation: 'fade' },
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

export type WidgetSize = 'small' | 'medium' | 'large' | 'full'

/** One widget on the dashboard; several of one type may be added. */
export interface DashboardWidget {
    id: string
    type: string
    size: WidgetSize
    settings: Record<string, unknown>
}

export interface DashboardLayout {
    widgets: DashboardWidget[]
    /** Seconds between refreshes; 0 is off. */
    refresh_seconds: number
    /** False until the user changes the default widgets. */
    customized?: boolean
}

export function getDashboardLayout(): Promise<DashboardLayout> {
    return apiRequest<DashboardLayout>('/api/preferences/dashboard')
}

export function saveDashboardLayout(layout: DashboardLayout): Promise<DashboardLayout> {
    return apiRequest<DashboardLayout>('/api/preferences/dashboard', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ widgets: layout.widgets, refresh_seconds: layout.refresh_seconds }),
    })
}

export function resetDashboardLayout(): Promise<DashboardLayout> {
    return apiRequest<DashboardLayout>('/api/preferences/dashboard', { method: 'DELETE' })
}
