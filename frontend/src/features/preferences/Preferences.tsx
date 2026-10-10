import { useRef, useState } from 'react'
import type { ChangeEvent, DragEvent } from 'react'
import {
    CloudUpload,
    Moon,
    RotateCcw,
    Sun,
    Trash2,
} from 'lucide-react'

import type { BackgroundImage } from '../../api/backgrounds.api'
import type { UserPreferences } from '../../api/preferences.api'
import { useFeedback } from '../../components/feedback/FeedbackProvider'

import './Preferences.css'

export interface PreferencesProps {
    theme: UserPreferences['theme']
    setTheme: (theme: UserPreferences['theme']) => void
    accentColor: string
    setAccentColor: (color: string) => void
    backgroundImageId: number | null
    backgroundFit: UserPreferences['background_fit']
    setBackgroundFit: (fit: UserPreferences['background_fit']) => void
    backgroundOpacity: number
    setBackgroundOpacity: (opacity: number) => void
    backgrounds: BackgroundImage[]
    preferencesLoaded: boolean
    preferencesError: string
    preferencesSaving: boolean
    backgroundUploading: boolean
    backgroundDeletingId: number | null
    saveAppearance: (
        theme: UserPreferences['theme'],
        accentColor: string,
        backgroundImageId: number | null,
        backgroundFit?: UserPreferences['background_fit'],
        backgroundOpacity?: number,
    ) => Promise<void>
    uploadBackground: (file: File) => Promise<void>
    removeBackground: (background: BackgroundImage) => Promise<void>
    resetAppearance: () => Promise<void>
}

const MAX_FILES_PER_UPLOAD = 20

export default function Preferences({
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
}: PreferencesProps) {
    const [backgroundDragActive, setBackgroundDragActive] = useState(false)
    const backgroundUploadInputRef = useRef<HTMLInputElement>(null)
    const { notify, modal } = useFeedback()

    const isBusy =
        !preferencesLoaded ||
        preferencesSaving ||
        backgroundUploading

    const saveAppearanceWithFeedback = async (
        nextTheme: UserPreferences['theme'],
        nextAccentColor: string,
        nextBackgroundImageId: number | null,
        nextBackgroundFit: UserPreferences['background_fit'],
        nextBackgroundOpacity: number,
        successMessage: string,
        ): Promise<boolean> => {
        try {
            await saveAppearance(
            nextTheme,
            nextAccentColor,
            nextBackgroundImageId,
            nextBackgroundFit,
            nextBackgroundOpacity,
            )

            notify.success(successMessage)
            return true
        } catch {
            notify.error('Unable to save appearance preferences.')
            return false
        }
    }

    const handleBackgroundDelete = async (
        background: BackgroundImage,
        ) => {
        if (
            !preferencesLoaded ||
            preferencesSaving ||
            backgroundUploading ||
            backgroundDeletingId !== null
        ) {
            return
        }

        const isSelected = backgroundImageId === background.id

        if (isSelected) {
            const confirmed = await modal.confirm({
            title: 'Delete active background?',
            message:
                `"${background.name}" is currently used as your workspace background. ` +
                'Deleting it will remove it from your workspace. This action cannot be undone.',
            confirmText: 'Delete background',
            cancelText: 'Keep background',
            destructive: true,
            })

            if (!confirmed) return
        } else {
            const confirmed = await modal.confirm({
            title: 'Delete background image?',
            message: `Are you sure you want to delete "${background.name}"? This action cannot be undone.`,
            confirmText: 'Delete',
            cancelText: 'Cancel',
            destructive: true,
            })

            if (!confirmed) return
        }

        try {
            // Clear the active reference before deleting its image.
            if (isSelected) {
            await saveAppearance(
                theme,
                accentColor,
                null,
                backgroundFit,
                backgroundOpacity,
            )
            }

            await removeBackground(background)

            notify.success(
            isSelected
                ? 'Background removed from the workspace and deleted.'
                : 'Background image deleted successfully.',
            )
        } catch {
            notify.error(
            'Unable to delete the background image. Please try again.',
            )
        }
        }

    const uploadFiles = async (files: File[]) => {
        if (isBusy || files.length === 0) return

        if (files.length > MAX_FILES_PER_UPLOAD) {
            notify.warning(
            `Select no more than ${MAX_FILES_PER_UPLOAD} images per upload.`,
            { title: 'Upload limit exceeded' },
            )
            return
        }

        const invalidFiles = files.filter(
            (file) =>
            !['image/png', 'image/jpeg', 'image/webp'].includes(file.type),
        )

        if (invalidFiles.length > 0) {
            notify.warning(
            'Only PNG, JPG, and WebP images are supported.',
            { title: 'Unsupported image format' },
            )
            return
        }

        let uploaded = 0
        let failed = 0

        for (const file of files) {
            try {
            await uploadBackground(file)
            uploaded += 1
            } catch {
            failed += 1
            }
        }

        if (uploaded > 0 && failed === 0) {
            notify.success(
            uploaded === 1
                ? 'Background image uploaded successfully.'
                : `${uploaded} background images uploaded successfully.`,
            )
        } else if (uploaded > 0 && failed > 0) {
            notify.warning(
            `${uploaded} uploaded successfully; ${failed} failed.`,
            { title: 'Upload partially completed' },
            )
        } else if (failed > 0) {
            notify.error(
            'No images could be uploaded. Please try again.',
            { title: 'Upload failed' },
            )
        }
        }

    const handleBackgroundFilesChange = async (
        event: ChangeEvent<HTMLInputElement>,
    ) => {
        const files = Array.from(event.currentTarget.files ?? [])

        // Allow selecting the same files again later.
        event.currentTarget.value = ''

        await uploadFiles(files)
    }

    const handleBackgroundDrop = async (
        event: DragEvent<HTMLDivElement>,
    ) => {
        event.preventDefault()
        setBackgroundDragActive(false)

        await uploadFiles(Array.from(event.dataTransfer.files))
    }

    const handleOpacitySave = (value: number) => {
        void saveAppearanceWithFeedback(
            theme,
            accentColor,
            backgroundImageId,
            backgroundFit,
            value,
            'Background opacity updated.',
        )
    }

    return (
        <section className="content-panel preferences-panel">
            <header className="preferences-heading">
                <h2>Appearance</h2>
                <p>Choose how Entropy looks on this device.</p>
            </header>

            <div className="theme-options">
                <button
                    type="button"
                    className={`theme-option ${
                        theme === 'dark' ? 'selected' : ''
                    }`}
                    aria-pressed={theme === 'dark'}
                    disabled={!preferencesLoaded || preferencesSaving}
                    onClick={() => {
                        setTheme('dark')
                        void saveAppearanceWithFeedback(
                            'dark',
                            accentColor,
                            backgroundImageId,
                            backgroundFit,
                            backgroundOpacity,
                            'Dark theme enabled.',
                        )
                    }}
                >
                    <Moon size={18} />
                    <span>Dark</span>
                    <small>Dark workspace</small>
                </button>

                <button
                    type="button"
                    className={`theme-option ${
                        theme === 'light' ? 'selected' : ''
                    }`}
                    aria-pressed={theme === 'light'}
                    disabled={!preferencesLoaded || preferencesSaving}
                    onClick={() => {
                        setTheme('light')
                        void saveAppearanceWithFeedback(
                            'light',
                            accentColor,
                            backgroundImageId,
                            backgroundFit,
                            backgroundOpacity,
                            'Light theme enabled.',
                        )
                    }}
                >
                    <Sun size={18} />
                    <span>Light</span>
                    <small>Light workspace</small>
                </button>
            </div>

            <div className="appearance-controls">
                <section className="appearance-control background-control">
                    <div className="background-heading">
                        <label>Workspace background</label>
                        <span className="background-count">
                            {backgrounds.length} images
                        </span>
                    </div>

                    <div
                        className={`background-dropzone ${
                            backgroundDragActive ? 'drag-active' : ''
                        } ${backgroundUploading ? 'uploading' : ''}`}
                        role="button"
                        tabIndex={isBusy ? -1 : 0}
                        aria-label="Upload background images"
                        aria-disabled={isBusy}
                        onClick={(event) => {
                            if (isBusy) return

                            const target = event.target as HTMLElement

                            // The cloud label already opens the file picker.
                            if (target.closest('label')) return

                            backgroundUploadInputRef.current?.click()
                        }}
                        onKeyDown={(event) => {
                            if (isBusy) return

                            if (event.key === 'Enter' || event.key === ' ') {
                                event.preventDefault()
                                backgroundUploadInputRef.current?.click()
                            }
                        }}
                        onDragEnter={(event) => {
                            event.preventDefault()
                            if (!isBusy) setBackgroundDragActive(true)
                        }}
                        onDragOver={(event) => {
                            event.preventDefault()
                            event.dataTransfer.dropEffect = isBusy ? 'none' : 'copy'
                        }}
                        onDragLeave={(event) => {
                            event.preventDefault()

                            if (
                                !event.currentTarget.contains(
                                    event.relatedTarget as Node | null,
                                )
                            ) {
                                setBackgroundDragActive(false)
                            }
                        }}
                        onDrop={(event) => {
                            void handleBackgroundDrop(event)
                        }}
                    >
                        <input
                            ref={backgroundUploadInputRef}
                            id="background-upload-input"
                            className="background-upload-input"
                            type="file"
                            accept="image/png,image/jpeg,image/webp"
                            multiple
                            disabled={isBusy}
                            onChange={(event) => {
                                void handleBackgroundFilesChange(event)
                            }}
                        />

                        <label
                            htmlFor="background-upload-input"
                            className="background-upload-icon"
                            title="Upload up to 20 images"
                            aria-label="Browse background images"
                            onClick={(event) => {
                                if (isBusy) event.preventDefault()
                            }}
                        >
                            <CloudUpload size={22} />
                        </label>

                        <span className="background-upload-hint">
                            {backgroundUploading
                                ? 'Uploading…'
                                : backgroundDragActive
                                  ? 'Drop images here'
                                  : 'Drop images or click to upload'}
                        </span>
                        <span className="background-upload-formats">
                            PNG, JPG, WebP · Up to 20 per batch
                        </span>
                    </div>

                    <div className="background-options">
                        <button
                            type="button"
                            className={`background-none-option ${
                                backgroundImageId === null ? 'selected' : ''
                            }`}
                            aria-pressed={backgroundImageId === null}
                            disabled={!preferencesLoaded || preferencesSaving}
                            onClick={() => {
                                if (backgroundImageId === null) return

                                void saveAppearanceWithFeedback(
                                    theme,
                                    accentColor,
                                    null,
                                    backgroundFit,
                                    backgroundOpacity,
                                    'Workspace background removed.',
                                )
                            }}
                        >
                            <span>No background image</span>
                        </button>

                        {backgrounds.map((background) => (
                            <div
                                key={background.id}
                                className="background-option"
                            >
                                <button
                                    type="button"
                                    className={`background-thumbnail ${
                                        backgroundImageId === background.id
                                            ? 'selected'
                                            : ''
                                    }`}
                                    aria-pressed={
                                        backgroundImageId === background.id
                                    }
                                    disabled={
                                        !preferencesLoaded ||
                                        preferencesSaving
                                    }
                                    onClick={() => {
                                        if (backgroundImageId === background.id) return

                                        void saveAppearanceWithFeedback(
                                            theme,
                                            accentColor,
                                            background.id,
                                            backgroundFit,
                                            backgroundOpacity,
                                            'Workspace background updated.',
                                        )
                                    }}
                                >
                                    <img
                                        className="background-image"
                                        src={background.url}
                                        alt=""
                                        loading="lazy"
                                    />
                                    <span title={background.name}>
                                        {background.name}
                                    </span>
                                </button>

                                {background.source === 'upload' && (
                                    <button
                                        type="button"
                                        className="background-delete-icon"
                                        aria-label={`Delete ${background.name}`}
                                        title={`Delete ${background.name}`}
                                        disabled={
                                            !preferencesLoaded ||
                                            preferencesSaving ||
                                            backgroundUploading ||
                                            backgroundDeletingId !== null
                                        }
                                        onClick={() => {
                                            void handleBackgroundDelete(background)
                                        }}
                                    >
                                        <Trash2 size={15} />
                                    </button>
                                )}
                            </div>
                        ))}
                    </div>
                </section>

                <aside className="appearance-side-controls">
                    <div className="appearance-control">
                        <label htmlFor="background-fit">
                            Background image fit
                        </label>
                        <select
                            id="background-fit"
                            value={backgroundFit}
                            disabled={!preferencesLoaded || preferencesSaving}
                            onChange={(event) => {
                                const nextFit = event.target.value as
                                    UserPreferences['background_fit']

                                setBackgroundFit(nextFit)

                                void saveAppearanceWithFeedback(
                                    theme,
                                    accentColor,
                                    backgroundImageId,
                                    nextFit,
                                    backgroundOpacity,
                                    'Background image fit updated.',
                                )
                            }}
                        >
                            <option value="cover">
                                Cover — fill workspace
                            </option>
                            <option value="contain">
                                Contain — show full image
                            </option>
                            <option value="fill">
                                Stretch — fill workspace
                            </option>
                        </select>
                    </div>

                    <div className="appearance-control">
                        <label htmlFor="background-opacity">
                            <span>Background opacity</span>
                            <span className="opacity-value">
                                {backgroundOpacity}%
                            </span>
                        </label>

                        <input
                            id="background-opacity"
                            className="background-opacity-slider"
                            type="range"
                            min="0"
                            max="100"
                            step="5"
                            value={backgroundOpacity}
                            disabled={!preferencesLoaded || preferencesSaving}
                            onChange={(event) => {
                                setBackgroundOpacity(
                                    Number(event.target.value),
                                )
                            }}
                            onPointerUp={(event) => {
                                handleOpacitySave(
                                    Number(event.currentTarget.value),
                                )
                            }}
                            onKeyUp={(event) => {
                                if (event.key.startsWith('Arrow')) {
                                    handleOpacitySave(
                                        Number(event.currentTarget.value),
                                    )
                                }
                            }}
                        />

                        <small>
                            100% shows the image clearly; 0% hides it.
                        </small>
                    </div>

                    <div className="appearance-control">
                        <label htmlFor="accent-color">Accent color</label>
                        <div className="color-control">
                            <input
                                id="accent-color"
                                type="color"
                                value={accentColor}
                                disabled={!preferencesLoaded || preferencesSaving}
                                onChange={(event) => {
                                    setAccentColor(event.target.value)
                                }}
                                onBlur={() => {
                                    void saveAppearanceWithFeedback(
                                        theme,
                                        accentColor,
                                        backgroundImageId,
                                        backgroundFit,
                                        backgroundOpacity,
                                        'Accent color updated.',
                                    )
                                }}
                            />
                            <span>{accentColor.toUpperCase()}</span>
                        </div>
                    </div>
                </aside>
            </div>

            <footer className="appearance-actions">
                <button
                    type="button"
                    className="appearance-reset-button"
                    disabled={!preferencesLoaded || preferencesSaving}
                    onClick={async () => {
                        const confirmed = await modal.confirm({
                            title: 'Reset appearance?',
                            message:
                            'This will restore the default theme, background, opacity, and accent color.',
                            confirmText: 'Reset appearance',
                            cancelText: 'Cancel',
                            destructive: true,
                        })

                        if (!confirmed) return

                        try {
                            await resetAppearance()
                            notify.success('Appearance preferences reset successfully.')
                        } catch {
                            notify.error('Unable to reset appearance preferences.')
                        }
                    }}
                >
                    <RotateCcw size={15} />
                    <span>Reset to default</span>
                </button>
            </footer>

            {preferencesSaving && (
                <p role="status" className="preferences-status">
                    Saving preferences…
                </p>
            )}

            {preferencesError && (
                <p role="alert" className="preferences-error">
                    {preferencesError}
                </p>
            )}
        </section>
    )
}
