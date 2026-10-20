import { useCallback, useEffect, useState } from 'react'

import {
    getBackgrounds,
    uploadBackground as uploadBackgroundApi,
    deleteAllBackgrounds,
    deleteBackground,
    type BackgroundImage,
} from '../../api/backgrounds.api'
import {
    DEFAULT_WALLPAPER_SETTINGS,
    getPreferences,
    getInterfaceSettings,
    getWallpaperSettings,
    updateInterfaceSettings,
    updatePreferences,
    updateWallpaperSettings,
    type UserPreferences,
    type WallpaperSettings,
} from '../../api/preferences.api'

const DEFAULT_PREFERENCES: UserPreferences = {
    theme: 'dark',
    accent_color: '#d7ff63',
    background_image_id: null,
    background_fit: 'cover',
    background_opacity: 35,
    modal_backdrop_opacity: 48,
}

export function useAppearance() {
    const [theme, setTheme] = useState<UserPreferences['theme']>(DEFAULT_PREFERENCES.theme)
    const [backgroundImageId, setBackgroundImageId] = useState<number | null>(null)
    const [backgrounds, setBackgrounds] = useState<BackgroundImage[]>([])
    const [accentColor, setAccentColor] = useState(DEFAULT_PREFERENCES.accent_color)
    const [preferencesLoaded, setPreferencesLoaded] = useState(false)
    const [preferencesError, setPreferencesError] = useState('')
    const [preferencesSaving, setPreferencesSaving] = useState(false)
    const [backgroundUploading, setBackgroundUploading] = useState(false)
    const [backgroundDeletingId, setBackgroundDeletingId] = useState<number | null>(null)
    const [backgroundFit, setBackgroundFit] = useState<UserPreferences['background_fit']>(
        DEFAULT_PREFERENCES.background_fit,
    )
    const [backgroundOpacity, setBackgroundOpacity] = useState(
        DEFAULT_PREFERENCES.background_opacity,
    )
    const [modalBackdropOpacity, setModalBackdropOpacity] = useState(
        DEFAULT_PREFERENCES.modal_backdrop_opacity,
    )
    const [glass, setGlassState] = useState(false)
    // Off until the server says otherwise, so wallpaper controls never flash.
    const [themeEnabled, setThemeEnabled] = useState(false)
    const [wallpaperSettings, setWallpaperSettings] = useState<WallpaperSettings>(
        DEFAULT_WALLPAPER_SETTINGS,
    )

    const applyPreferences = useCallback((saved: UserPreferences) => {
        setTheme(saved.theme)
        setThemeEnabled(saved.theme_enabled ?? true)
        setAccentColor(saved.accent_color)
        setBackgroundImageId(saved.background_image_id)
        setBackgroundFit(saved.background_fit ?? DEFAULT_PREFERENCES.background_fit)
        setBackgroundOpacity(saved.background_opacity ?? DEFAULT_PREFERENCES.background_opacity)
        setModalBackdropOpacity(
            saved.modal_backdrop_opacity ?? DEFAULT_PREFERENCES.modal_backdrop_opacity,
        )
    }, [])

    // Set the value on the document root because shared dialogs/toasts may render
    // through a portal outside .entropy-app.
    useEffect(() => {
        document.documentElement.style.setProperty(
            '--app-modal-backdrop-opacity',
            String(modalBackdropOpacity / 100),
        )
    }, [modalBackdropOpacity])

    const refreshBackgrounds = useCallback(async () => {
        setBackgrounds(await getBackgrounds())
    }, [])

    useEffect(() => {
        let cancelled = false

        async function loadAppearance() {
            try {
                const [saved, availableBackgrounds] = await Promise.all([
                    getPreferences(),
                    getBackgrounds(),
                ])
                if (cancelled) return

                applyPreferences(saved)
                setBackgrounds(availableBackgrounds)
                setPreferencesError('')

                // Optional: servers older than the wallpaper settings API lack it.
                getWallpaperSettings()
                    .then((settings) => {
                        if (!cancelled) setWallpaperSettings(settings)
                    })
                    .catch(() => undefined)
                getInterfaceSettings()
                    .then((settings) => {
                        if (!cancelled) setGlassState(settings.glass)
                    })
                    .catch(() => undefined)
            } catch (error) {
                if (!cancelled) {
                    setPreferencesError(
                        error instanceof Error
                            ? error.message
                            : 'Unable to load appearance preferences.',
                    )
                }
            } finally {
                if (!cancelled) setPreferencesLoaded(true)
            }
        }

        void loadAppearance()
        return () => {
            cancelled = true
        }
    }, [applyPreferences])

    const saveAppearance = useCallback(async (
        nextTheme: UserPreferences['theme'],
        nextAccentColor: string,
        nextBackgroundImageId: number | null,
        nextBackgroundFit: UserPreferences['background_fit'] = backgroundFit,
        nextBackgroundOpacity: number = backgroundOpacity,
        nextModalBackdropOpacity: number = modalBackdropOpacity,
    ) => {
        setPreferencesSaving(true)
        setPreferencesError('')

        try {
            const saved = await updatePreferences({
                theme: nextTheme,
                accent_color: nextAccentColor,
                background_image_id: nextBackgroundImageId,
                background_fit: nextBackgroundFit,
                background_opacity: nextBackgroundOpacity,
                modal_backdrop_opacity: nextModalBackdropOpacity,
            })
            applyPreferences(saved)
        } catch (error) {
            setPreferencesError(
                error instanceof Error
                    ? error.message
                    : 'Unable to save appearance preferences.',
            )
            throw error
        } finally {
            setPreferencesSaving(false)
        }
    }, [applyPreferences, backgroundFit, backgroundOpacity, modalBackdropOpacity])

    const uploadBackground = useCallback(async (file: File) => {
        setPreferencesError('')
        setBackgroundUploading(true)

        try {
            await uploadBackgroundApi(file)
            await refreshBackgrounds()
        } catch (error) {
            setPreferencesError(
                error instanceof Error
                    ? error.message
                    : 'Unable to upload background image.',
            )
            throw error
        } finally {
            setBackgroundUploading(false)
        }
    }, [refreshBackgrounds])

    const removeBackground = useCallback(async (background: BackgroundImage) => {
        if (background.source !== 'upload') return

        setPreferencesError('')
        setBackgroundDeletingId(background.id)

        try {
            if (backgroundImageId === background.id) {
                const saved = await updatePreferences({
                    theme,
                    accent_color: accentColor,
                    background_image_id: null,
                    background_fit: backgroundFit,
                    background_opacity: backgroundOpacity,
                    modal_backdrop_opacity: modalBackdropOpacity,
                })
                applyPreferences(saved)
            }

            await deleteBackground(background.id)
            await refreshBackgrounds()
        } catch (error) {
            setPreferencesError(
                error instanceof Error
                    ? error.message
                    : 'Unable to remove background image.',
            )
            throw error
        } finally {
            setBackgroundDeletingId(null)
        }
    }, [
        accentColor,
        applyPreferences,
        backgroundFit,
        backgroundImageId,
        backgroundOpacity,
        modalBackdropOpacity,
        refreshBackgrounds,
        theme,
    ])

    const saveWallpaperSettings = useCallback(async (next: WallpaperSettings) => {
        const previous = wallpaperSettings
        setWallpaperSettings(next)

        try {
            setWallpaperSettings(await updateWallpaperSettings(next))
        } catch (error) {
            setWallpaperSettings(previous)
            throw error
        }
    }, [wallpaperSettings])

    const setGlass = useCallback(async (enabled: boolean) => {
        setGlassState(enabled)

        try {
            setGlassState((await updateInterfaceSettings({ glass: enabled })).glass)
        } catch (error) {
            setGlassState(!enabled)
            throw error
        }
    }, [])

    const removeAllUploads = useCallback(async () => {
        setPreferencesError('')

        const result = await deleteAllBackgrounds()
        // The server clears a selection that pointed at a deleted upload.
        const [saved] = await Promise.all([getPreferences(), refreshBackgrounds()])
        applyPreferences(saved)

        return result
    }, [applyPreferences, refreshBackgrounds])

    const resetAppearance = useCallback(() => saveAppearance(
        DEFAULT_PREFERENCES.theme,
        DEFAULT_PREFERENCES.accent_color,
        DEFAULT_PREFERENCES.background_image_id,
        DEFAULT_PREFERENCES.background_fit,
        DEFAULT_PREFERENCES.background_opacity,
        DEFAULT_PREFERENCES.modal_backdrop_opacity,
    ), [saveAppearance])

    return {
        theme,
        setTheme,
        accentColor,
        setAccentColor,
        backgroundImageId,
        backgroundFit,
        setBackgroundFit,
        backgroundOpacity,
        setBackgroundOpacity,
        modalBackdropOpacity,
        setModalBackdropOpacity,
        backgrounds,
        preferencesLoaded,
        preferencesError,
        preferencesSaving,
        backgroundUploading,
        backgroundDeletingId,
        saveAppearance,
        uploadBackground,
        removeBackground,
        resetAppearance,
        wallpaperSettings,
        saveWallpaperSettings,
        removeAllUploads,
        glass,
        setGlass,
        themeEnabled,
    }
}

export type Appearance = ReturnType<typeof useAppearance>
