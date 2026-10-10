import { useCallback, useEffect, useState } from 'react'

import {
    getBackgrounds,
    uploadBackground as uploadBackgroundApi,
    deleteBackground,
    type BackgroundImage,
} from '../../api/backgrounds.api'
import {
    getPreferences,
    updatePreferences,
    type UserPreferences,
} from '../../api/preferences.api'

const DEFAULT_PREFERENCES: UserPreferences = {
    theme: 'dark',
    accent_color: '#d7ff63',
    background_image_id: null,
    background_fit: 'cover',
    background_opacity: 35,
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

    const applyPreferences = useCallback((saved: UserPreferences) => {
        setTheme(saved.theme)
        setAccentColor(saved.accent_color)
        setBackgroundImageId(saved.background_image_id)
        setBackgroundFit(saved.background_fit ?? DEFAULT_PREFERENCES.background_fit)
        setBackgroundOpacity(saved.background_opacity ?? DEFAULT_PREFERENCES.background_opacity)
    }, [])

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
            })
            applyPreferences(saved)
        } catch (error) {
            setPreferencesError(
                error instanceof Error
                    ? error.message
                    : 'Unable to save appearance preferences.',
            )
        } finally {
            setPreferencesSaving(false)
        }
    }, [applyPreferences, backgroundFit, backgroundOpacity])

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
        } finally {
            setBackgroundUploading(false)
        }
    }, [refreshBackgrounds])

    const removeBackground = useCallback(async (background: BackgroundImage) => {
        if (background.source !== 'upload') return

        // const confirmed = window.confirm(`Remove the background image "${background.name}"?`)
        // if (!confirmed) return

        setPreferencesError('')
        setBackgroundDeletingId(background.id)

        try {
            // Clear the preference before deleting the image currently in use.
            if (backgroundImageId === background.id) {
                const saved = await updatePreferences({
                    theme,
                    accent_color: accentColor,
                    background_image_id: null,
                    background_fit: backgroundFit,
                    background_opacity: backgroundOpacity,
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
        } finally {
            setBackgroundDeletingId(null)
        }
    }, [accentColor, applyPreferences, backgroundFit, backgroundImageId, backgroundOpacity, refreshBackgrounds, theme])

    const resetAppearance = useCallback(() => saveAppearance(
        DEFAULT_PREFERENCES.theme,
        DEFAULT_PREFERENCES.accent_color,
        DEFAULT_PREFERENCES.background_image_id,
        DEFAULT_PREFERENCES.background_fit,
        DEFAULT_PREFERENCES.background_opacity,
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
    }
}
