
import { useEffect, useRef, useState } from 'react'
import type { ChangeEvent, DragEvent } from 'react'
import {
    Check,
    ChevronLeft,
    ChevronRight,
    ChevronsLeft,
    ChevronsRight,
    CloudUpload,
    Download,
    Film,
    Moon,
    Shuffle,
    Sun,
    Trash2,
} from 'lucide-react'
import {
    BACKGROUND_UPLOAD_TYPES,
    BACKGROUNDS_ARCHIVE_URL,
    isVideoBackground,
    type BackgroundImage,
} from '../../api/backgrounds.api'
import type {
    UserPreferences,
    WallpaperPlacement,
    WallpaperSettings,
} from '../../api/preferences.api'
import { useFeedback } from '../../components/feedback/FeedbackProvider'
import WallpaperViewer from './WallpaperViewer'
import '../../styles/Preferences.css'

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
    modalBackdropOpacity: number
    setModalBackdropOpacity: (opacity: number) => void
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
        modalBackdropOpacity?: number,
    ) => Promise<void>
    uploadBackground: (file: File) => Promise<void>
    removeBackground: (background: BackgroundImage) => Promise<void>
    resetAppearance: () => Promise<void>
    wallpaperSettings: WallpaperSettings
    saveWallpaperSettings: (settings: WallpaperSettings) => Promise<void>
    removeAllUploads: () => Promise<{ deleted: number; message: string }>
}

const SHUFFLE_INTERVALS = [1, 5, 15, 30, 60, 180, 720, 1440]

function intervalLabel(minutes: number): string {
    if (minutes < 60) return `${minutes} minute${minutes === 1 ? '' : 's'}`
    const hours = minutes / 60
    return `${hours} hour${hours === 1 ? '' : 's'}`
}

const IMAGES_PER_PAGE = 6

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
}: PreferencesProps) {
    const [backgroundDragActive, setBackgroundDragActive] = useState(false)
    const [galleryPage, setGalleryPage] = useState(0)
    const [viewerIndex, setViewerIndex] = useState<number | null>(null)
    const [bulkBusy, setBulkBusy] = useState(false)
    const uploadInputRef = useRef<HTMLInputElement>(null)
    const { notify, modal } = useFeedback()
    const previewClickTimer = useRef<number | null>(null)

    const isBusy =
        !preferencesLoaded || preferencesSaving || backgroundUploading

    const pageCount = Math.max(
        1,
        Math.ceil(backgrounds.length / IMAGES_PER_PAGE),
    )
    const visibleBackgrounds = backgrounds.slice(
        galleryPage * IMAGES_PER_PAGE,
        galleryPage * IMAGES_PER_PAGE + IMAGES_PER_PAGE,
    )
    const uploadCount = backgrounds.filter((item) => item.source === 'upload').length

    useEffect(() => {
        setGalleryPage((current) => Math.min(current, pageCount - 1))
    }, [pageCount])



    useEffect(() => {
        return () => {
            if (previewClickTimer.current !== null) {
                window.clearTimeout(previewClickTimer.current)
            }
        }
    }, [])


    const saveWithFeedback = async (
        nextTheme: UserPreferences['theme'] = theme,
        nextAccent = accentColor,
        nextBackgroundId: number | null = backgroundImageId,
        nextFit: UserPreferences['background_fit'] = backgroundFit,
        nextOpacity = backgroundOpacity,
        message = 'Appearance preferences updated.',
        nextModalOpacity = modalBackdropOpacity,
    ) => {
        try {
            await saveAppearance(
                nextTheme,
                nextAccent,
                nextBackgroundId,
                nextFit,
                nextOpacity,
                nextModalOpacity,
            )
            notify.success(message)
        } catch {
            notify.error('Unable to save appearance preferences.')
        }
    }

    const uploadFiles = async (files: File[]) => {
        if (isBusy || files.length === 0) return

        const validFiles = files.filter((file) =>
            BACKGROUND_UPLOAD_TYPES.includes(file.type),
        )
        const invalidCount = files.length - validFiles.length

        if (invalidCount > 0) {
            notify.warning(
                `${invalidCount} file(s) skipped. Only PNG, JPG, WebP, MP4 and WebM are supported.`,
            )
        }

        let uploaded = 0
        let failed = 0

        for (const file of validFiles) {
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
                    ? 'Wallpaper uploaded successfully.'
                    : `${uploaded} wallpapers uploaded successfully.`,
            )
        } else if (uploaded > 0) {
            notify.warning(`${uploaded} uploaded; ${failed} failed.`)
        } else if (failed > 0) {
            notify.error('Unable to upload the selected files.')
        }
    }

    const handleFilesChange = async (
        event: ChangeEvent<HTMLInputElement>,
    ) => {
        const files = Array.from(event.currentTarget.files ?? [])
        event.currentTarget.value = ''
        await uploadFiles(files)
    }

    const handleDrop = async (event: DragEvent<HTMLDivElement>) => {
        event.preventDefault()
        setBackgroundDragActive(false)
        await uploadFiles(Array.from(event.dataTransfer.files))
    }

    const handleDelete = async (background: BackgroundImage) => {
        if (isBusy || backgroundDeletingId !== null) return false

        const confirmed = await modal.confirm({
            title:
                backgroundImageId === background.id
                    ? 'Delete active background?'
                    : 'Delete background image?',
            message:
                backgroundImageId === background.id
                    ? `"${background.name}" is currently your workspace background. Deleting it will remove it from your workspace. This cannot be undone.`
                    : `Are you sure you want to delete "${background.name}"? This cannot be undone.`,
            confirmText: 'Delete',
            cancelText: 'Cancel',
            destructive: true,
        })

        if (!confirmed) return false

        try {
            if (backgroundImageId === background.id) {
                await saveAppearance(
                    theme,
                    accentColor,
                    null,
                    backgroundFit,
                    backgroundOpacity,
                    modalBackdropOpacity,
                )
            }

            await removeBackground(background)
            notify.success('Background image deleted successfully.')
            return true
        } catch {
            notify.error('Unable to delete the background image.')
            return false
        }
    }

    const downloadAll = () => {
        // A plain navigation keeps the browser's own download handling.
        const link = document.createElement('a')
        link.href = BACKGROUNDS_ARCHIVE_URL
        link.download = 'entropy-backgrounds.zip'
        document.body.appendChild(link)
        link.click()
        link.remove()
    }

    const deleteAll = async () => {
        const confirmed = await modal.confirm({
            title: 'Delete all uploaded wallpapers?',
            message: `All ${uploadCount} wallpaper${uploadCount === 1 ? '' : 's'} you uploaded will be permanently deleted. Built-in wallpapers are kept. This cannot be undone.`,
            confirmText: 'Delete all',
            cancelText: 'Cancel',
            destructive: true,
        })

        if (!confirmed) return

        setBulkBusy(true)

        try {
            const result = await removeAllUploads()
            notify.success(result.message)
        } catch (error) {
            notify.error(error instanceof Error ? error.message : 'Unable to delete the uploads.')
        } finally {
            setBulkBusy(false)
        }
    }

    const setWallpaper = async (
        background: BackgroundImage,
        placement: WallpaperPlacement | null,
    ) => {
        const placements = { ...wallpaperSettings.placements }
        const key = String(background.id)

        if (placement) placements[key] = placement
        else delete placements[key]

        try {
            await saveWallpaperSettings({ ...wallpaperSettings, placements })
            await saveAppearance(
                theme,
                accentColor,
                background.id,
                backgroundFit,
                backgroundOpacity,
                modalBackdropOpacity,
            )
            notify.success(
                placement
                    ? `"${background.name}" set as your wallpaper.`
                    : `"${background.name}" set as your wallpaper and fitted automatically.`,
            )
        } catch (error) {
            notify.error(error instanceof Error ? error.message : 'Unable to set the wallpaper.')
            throw error
        }
    }

    const saveShuffle = async (shuffle: WallpaperSettings['shuffle'], message: string) => {
        try {
            await saveWallpaperSettings({ ...wallpaperSettings, shuffle })
            notify.success(message)
        } catch {
            notify.error('Unable to save shuffle settings.')
        }
    }

    const selectBackground = (id: number | null) => {
        void saveWithFeedback(
            theme,
            accentColor,
            id,
            backgroundFit,
            backgroundOpacity,
            id === null
                ? 'Workspace background removed.'
                : 'Workspace background updated.',
        )
    }

    const saveOpacity = (value: number) => {
        void saveWithFeedback(
            theme,
            accentColor,
            backgroundImageId,
            backgroundFit,
            value,
            'Wallpaper opacity updated.',
        )
    }

    return (
        <section className="preferences-panel">
            <header className="page-heading">
                <div>
                    <p className="page-eyebrow">ACCOUNT</p>
                    <h1>Preferences</h1>
                    <p className="page-subtitle">Personalize your Entropy workspace.</p>
                </div>

                <button
                    type="button"
                    className="entropy-button entropy-button-danger"
                    onClick={async () => {
                        const confirmed = await modal.confirm({
                            title: 'Reset appearance?',
                            message:
                                'Restore the default theme, background, opacity, modal backdrop, and accent color?',
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
                    Reset to default
                </button>
            </header>

            {preferencesError && (
                <p className="preferences-error" role="alert">
                    {preferencesError}
                </p>
            )}
            {/* <div className="preferences-toolbar">
                <button
                    type="button"
                    className="entropy-button entropy-button-danger"
                    onClick={async () => {
                        const confirmed = await modal.confirm({
                            title: 'Reset appearance?',
                            message:
                                'Restore the default theme, background, opacity, modal backdrop, and accent color?',
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
                    Reset to default
                </button>
            </div> */}
            {/* Theme */}
            <div className="preferences-top-grid">
                <section className="settings-section theme-section">
                    <div className="settings-section-heading">
                        <h3>Theme</h3>
                        <p>Choose the overall workspace theme.</p>
                    </div>

                    <div className="theme-options">
                        <button
                            type="button"
                            className={`theme-option ${theme === 'dark' ? 'selected' : ''}`}
                            aria-pressed={theme === 'dark'}
                            disabled={isBusy}
                            onClick={() => {
                                setTheme('dark')
                                void saveWithFeedback(
                                    'dark',
                                    accentColor,
                                    backgroundImageId,
                                    backgroundFit,
                                    backgroundOpacity,
                                    'Dark theme enabled.',
                                )
                            }}
                        >
                            <Moon size={20} />
                            <span>Dark</span>
                            <small>Dark workspace</small>
                            {theme === 'dark' && <Check className="theme-check" size={16} />}
                        </button>

                        <button
                            type="button"
                            className={`theme-option ${theme === 'light' ? 'selected' : ''}`}
                            aria-pressed={theme === 'light'}
                            disabled={isBusy}
                            onClick={() => {
                                setTheme('light')
                                void saveWithFeedback(
                                    'light',
                                    accentColor,
                                    backgroundImageId,
                                    backgroundFit,
                                    backgroundOpacity,
                                    'Light theme enabled.',
                                )
                            }}
                        >
                            <Sun size={20} />
                            <span>Light</span>
                            <small>Light workspace</small>
                            {theme === 'light' && <Check className="theme-check" size={16} />}
                        </button>
                    </div>
                </section>

                {/* Appearance */}
                <section className="settings-section">
                    <div className="settings-section-heading">
                        <h3>Appearance</h3>
                        <p>Adjust wallpaper visibility, accent color, and modal backdrop.</p>
                    </div>

                    <div className="appearance-settings-grid">
                        <div className="appearance-setting">
                            <label htmlFor="background-opacity">
                                <span>Wallpaper opacity</span>
                                <strong>{backgroundOpacity}%</strong>
                            </label>
                            <input
                                id="background-opacity"
                                type="range"
                                min="0"
                                max="100"
                                step="5"
                                value={backgroundOpacity}
                                disabled={!preferencesLoaded || preferencesSaving}
                                onChange={(event) =>
                                    setBackgroundOpacity(Number(event.target.value))
                                }
                                onPointerUp={(event) =>
                                    saveOpacity(Number(event.currentTarget.value))
                                }
                                onKeyUp={(event) => {
                                    if (event.key.startsWith('Arrow')) {
                                        saveOpacity(Number(event.currentTarget.value))
                                    }
                                }}
                            />
                            <small>Controls how clearly the wallpaper appears.</small>
                        </div>

                        <div className="appearance-setting accent-setting">
                            <label htmlFor="accent-color">Accent color</label>
                            <div className="accent-color-control">
                                <input
                                    id="accent-color"
                                    type="color"
                                    value={accentColor}
                                    disabled={!preferencesLoaded || preferencesSaving}
                                    onChange={(event) =>
                                        setAccentColor(event.target.value)
                                    }
                                    onBlur={() =>
                                        void saveWithFeedback(
                                            theme,
                                            accentColor,
                                            backgroundImageId,
                                            backgroundFit,
                                            backgroundOpacity,
                                            'Accent color updated.',
                                        )
                                    }
                                />
                                <span>{accentColor.toUpperCase()}</span>
                            </div>
                            <small>Used for highlights, selections, and controls.</small>
                        </div>

                        <div className="appearance-setting">
                            <label htmlFor="modal-backdrop-opacity">
                                <span>Modal backdrop</span>
                                <strong>{modalBackdropOpacity}%</strong>
                            </label>
                            <input
                                id="modal-backdrop-opacity"
                                type="range"
                                min="0"
                                max="80"
                                step="5"
                                value={modalBackdropOpacity}
                                disabled={!preferencesLoaded || preferencesSaving}
                                onChange={(event) =>
                                    setModalBackdropOpacity(Number(event.target.value))
                                }
                                onPointerUp={(event) => {
                                    void saveWithFeedback(
                                        theme,
                                        accentColor,
                                        backgroundImageId,
                                        backgroundFit,
                                        backgroundOpacity,
                                        'Modal backdrop opacity updated.',
                                        Number(event.currentTarget.value),
                                    )
                                }}
                                onKeyUp={(event) => {
                                    if (event.key.startsWith('Arrow')) {
                                        void saveWithFeedback(
                                            theme,
                                            accentColor,
                                            backgroundImageId,
                                            backgroundFit,
                                            backgroundOpacity,
                                            'Modal backdrop opacity updated.',
                                            Number(event.currentTarget.value),
                                        )
                                    }
                                }}
                            />
                            <small>
                                How much of your wallpaper shows through dialogs and full-screen
                                editors on every page. Lower is more see-through.
                            </small>
                        </div>
                    </div>
                </section>
            </div>

            {/* Background library */}
            <section className="settings-section background-section">
                <div className="settings-section-heading">
                    <h3>Background</h3>
                    <p>Upload wallpapers and choose the one used in your workspace.</p>
                </div>

                <div
                    className={`background-dropzone ${backgroundDragActive ? 'drag-active' : ''} ${backgroundUploading ? 'uploading' : ''}`}
                    role="button"
                    tabIndex={isBusy ? -1 : 0}
                    aria-label="Upload background images"
                    aria-disabled={isBusy}
                    onClick={() => {
                        if (!isBusy) uploadInputRef.current?.click()
                    }}
                    onKeyDown={(event) => {
                        if (!isBusy && (event.key === 'Enter' || event.key === ' ')) {
                            event.preventDefault()
                            uploadInputRef.current?.click()
                        }
                    }}
                    onDragEnter={(event) => {
                        event.preventDefault()
                        if (!isBusy) setBackgroundDragActive(true)
                    }}
                    onDragOver={(event) => {
                        event.preventDefault()
                    }}
                    onDragLeave={(event) => {
                        event.preventDefault()
                        if (!event.currentTarget.contains(event.relatedTarget as Node | null)) {
                            setBackgroundDragActive(false)
                        }
                    }}
                    onDrop={(event) => void handleDrop(event)}
                >
                    <input
                        ref={uploadInputRef}
                        className="background-upload-input"
                        type="file"
                        accept={BACKGROUND_UPLOAD_TYPES.join(',')}
                        multiple
                        disabled={isBusy}
                        onChange={(event) => void handleFilesChange(event)}
                    />
                    <CloudUpload size={30} />
                    <strong>
                        {backgroundUploading
                            ? 'Uploading…'
                            : backgroundDragActive
                              ? 'Drop to upload'
                              : 'Drag and drop wallpapers here'}
                    </strong>
                    <span>Or click to choose files · PNG, JPG, WebP images or MP4, WebM videos</span>
                    <small>Images up to 20 MB, videos up to 100 MB.</small>
                </div>

                <div className="background-library-toolbar">
                    <div>
                        <h4>Wallpaper gallery</h4>
                        <p>
                            {backgrounds.length} available · {uploadCount} uploaded by you ·
                            double-click to open the gallery
                        </p>
                    </div>

                    <div className="background-library-actions">
                        <button
                            type="button"
                            className="entropy-button entropy-button-secondary entropy-button-sm"
                            disabled={uploadCount === 0 || bulkBusy}
                            onClick={downloadAll}
                            title="Download every wallpaper you uploaded as a zip file"
                        >
                            <Download size={14} />
                            Download all
                        </button>
                        <button
                            type="button"
                            className="entropy-button entropy-button-danger-quiet entropy-button-sm"
                            disabled={uploadCount === 0 || bulkBusy || isBusy}
                            onClick={() => void deleteAll()}
                            title="Delete every wallpaper you uploaded; built-in wallpapers are kept"
                        >
                            <Trash2 size={14} />
                            Delete all
                        </button>
                        <button
                            type="button"
                            className={`entropy-button entropy-button-secondary entropy-button-sm background-none-option ${
                                backgroundImageId === null ? 'selected' : ''
                            }`}
                            aria-pressed={backgroundImageId === null}
                            disabled={isBusy}
                            onClick={() => selectBackground(null)}
                        >
                            No background image
                        </button>

                        <div className="background-fit-control">
                            <label htmlFor="background-fit">Image fit</label>
                            <select
                                id="background-fit"
                                className="entropy-select"
                                value={backgroundFit}
                                disabled={!preferencesLoaded || preferencesSaving}
                                onChange={(event) => {
                                    const fit =
                                        event.target.value as UserPreferences['background_fit']
                                    setBackgroundFit(fit)
                                    void saveWithFeedback(
                                        theme,
                                        accentColor,
                                        backgroundImageId,
                                        fit,
                                        backgroundOpacity,
                                        'Background image fit updated.',
                                    )
                                }}
                            >
                                <option value="cover">Cover</option>
                                <option value="contain">Contain</option>
                                <option value="fill">Stretch</option>
                            </select>
                        </div>
                    </div>
                </div>

                {backgrounds.length === 0 ? (
                    <div className="background-empty">
                        <CloudUpload size={26} />
                        <strong>No wallpapers uploaded yet</strong>
                        <span>Your uploaded images will appear here.</span>
                    </div>
                ) : (
                    <>
                        <div className="background-gallery">
                            {visibleBackgrounds.map((background) => {
                                const index = backgrounds.findIndex(
                                    (item) => item.id === background.id,
                                )
                                const selected = backgroundImageId === background.id

                                return (
                                    <article className="background-card" key={background.id}>
                                        <button
                                            type="button"
                                            className={`background-thumbnail ${selected ? 'selected' : ''}`}
                                            aria-pressed={selected}
                                            title={`${background.name} — double-click to open the gallery`}
                                            disabled={!preferencesLoaded || preferencesSaving}
                                            onClick={() => {
                                                if (previewClickTimer.current !== null) {
                                                    window.clearTimeout(previewClickTimer.current)
                                                }

                                                previewClickTimer.current = window.setTimeout(() => {
                                                    selectBackground(background.id)
                                                    previewClickTimer.current = null
                                                }, 250)
                                            }}
                                            onDoubleClick={(event) => {
                                                event.preventDefault()

                                                if (previewClickTimer.current !== null) {
                                                    window.clearTimeout(previewClickTimer.current)
                                                    previewClickTimer.current = null
                                                }

                                                setViewerIndex(index)
                                            }}
                                        >
                                            {isVideoBackground(background) ? (
                                                <>
                                                    <video
                                                        src={background.url}
                                                        muted
                                                        preload="metadata"
                                                        aria-label={background.name}
                                                    />
                                                    <span className="background-video-badge">
                                                        <Film size={12} />
                                                        Video
                                                    </span>
                                                </>
                                            ) : (
                                                <img
                                                    src={background.url}
                                                    alt={background.name}
                                                    loading="lazy"
                                                />
                                            )}
                                            {selected && (
                                                <span className="background-selected-mark">
                                                    <Check size={16} />
                                                </span>
                                            )}
                                            <span className="background-card-name">
                                                {background.name}
                                            </span>
                                            <small>Double-click to open</small>
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
                                                onClick={() => void handleDelete(background)}
                                            >
                                                <Trash2 size={15} />
                                            </button>
                                        )}
                                    </article>
                                )
                            })}
                        </div>

                        {pageCount > 1 && (
                            <nav className="gallery-pagination" aria-label="Wallpaper pages">
                                <span>
                                    Showing {galleryPage * IMAGES_PER_PAGE + 1}–
                                    {Math.min(
                                        (galleryPage + 1) * IMAGES_PER_PAGE,
                                        backgrounds.length,
                                    )}{' '}
                                    of {backgrounds.length}
                                </span>
                                <div className="gallery-pagination-actions">
                                    <button
                                        type="button"
                                        className="entropy-button entropy-button-secondary entropy-button-icon entropy-button-sm"
                                        aria-label="First page"
                                        disabled={galleryPage === 0}
                                        onClick={() => setGalleryPage(0)}
                                    >
                                        <ChevronsLeft size={17} />
                                    </button>
                                    <button
                                        type="button"
                                        className="entropy-button entropy-button-secondary entropy-button-icon entropy-button-sm"
                                        aria-label="Previous page"
                                        disabled={galleryPage === 0}
                                        onClick={() => setGalleryPage((page) => page - 1)}
                                    >
                                        <ChevronLeft size={17} />
                                    </button>
                                    <span className="gallery-page-count">
                                        Page {galleryPage + 1} of {pageCount}
                                    </span>
                                    <button
                                        type="button"
                                        className="entropy-button entropy-button-secondary entropy-button-icon entropy-button-sm"
                                        aria-label="Next page"
                                        disabled={galleryPage >= pageCount - 1}
                                        onClick={() => setGalleryPage((page) => page + 1)}
                                    >
                                        <ChevronRight size={17} />
                                    </button>
                                    <button
                                        type="button"
                                        className="entropy-button entropy-button-secondary entropy-button-icon entropy-button-sm"
                                        aria-label="Last page"
                                        disabled={galleryPage >= pageCount - 1}
                                        onClick={() => setGalleryPage(pageCount - 1)}
                                    >
                                        <ChevronsRight size={17} />
                                    </button>
                                </div>
                            </nav>
                        )}
                    </>
                )}
                <div className="wallpaper-shuffle">
                    <div className="wallpaper-shuffle-copy">
                        <span className="wallpaper-shuffle-icon">
                            <Shuffle size={16} />
                        </span>
                        <div>
                            <strong>Shuffle wallpapers</strong>
                            <span>
                                Show a different wallpaper every so often. Your chosen wallpaper
                                returns when shuffle is off.
                            </span>
                        </div>
                    </div>

                    <div className="wallpaper-shuffle-controls">
                        <label className="wallpaper-shuffle-switch">
                            <input
                                type="checkbox"
                                role="switch"
                                checked={wallpaperSettings.shuffle.enabled}
                                disabled={!preferencesLoaded}
                                onChange={(event) =>
                                    void saveShuffle(
                                        { ...wallpaperSettings.shuffle, enabled: event.target.checked },
                                        event.target.checked ? 'Wallpaper shuffle on.' : 'Wallpaper shuffle off.',
                                    )
                                }
                            />
                            <span aria-hidden="true" />
                            {wallpaperSettings.shuffle.enabled ? 'On' : 'Off'}
                        </label>

                        <label className="background-fit-control">
                            <span>Every</span>
                            <select
                                className="entropy-select"
                                value={wallpaperSettings.shuffle.interval_minutes}
                                disabled={!preferencesLoaded}
                                onChange={(event) =>
                                    void saveShuffle(
                                        {
                                            ...wallpaperSettings.shuffle,
                                            interval_minutes: Number(event.target.value),
                                        },
                                        'Shuffle interval updated.',
                                    )
                                }
                            >
                                {!SHUFFLE_INTERVALS.includes(wallpaperSettings.shuffle.interval_minutes) && (
                                    <option value={wallpaperSettings.shuffle.interval_minutes}>
                                        {intervalLabel(wallpaperSettings.shuffle.interval_minutes)}
                                    </option>
                                )}
                                {SHUFFLE_INTERVALS.map((minutes) => (
                                    <option key={minutes} value={minutes}>
                                        {intervalLabel(minutes)}
                                    </option>
                                ))}
                            </select>
                        </label>

                        <label className="background-fit-control">
                            <span>From</span>
                            <select
                                className="entropy-select"
                                value={wallpaperSettings.shuffle.source}
                                disabled={!preferencesLoaded}
                                onChange={(event) =>
                                    void saveShuffle(
                                        {
                                            ...wallpaperSettings.shuffle,
                                            source: event.target.value as WallpaperSettings['shuffle']['source'],
                                        },
                                        'Shuffle source updated.',
                                    )
                                }
                            >
                                <option value="all">All wallpapers</option>
                                <option value="uploads">My uploads</option>
                            </select>
                        </label>
                    </div>
                </div>
            </section>

            <footer className="appearance-actions">
                {preferencesSaving && (
                    <span className="preferences-status" role="status">
                        Saving preferences…
                    </span>
                )}
            </footer>

            {viewerIndex !== null && backgrounds.length > 0 && (
                <WallpaperViewer
                    backgrounds={backgrounds}
                    initialIndex={Math.min(viewerIndex, backgrounds.length - 1)}
                    selectedId={backgroundImageId}
                    placements={wallpaperSettings.placements}
                    busy={isBusy || backgroundDeletingId !== null}
                    onClose={() => setViewerIndex(null)}
                    onSetWallpaper={setWallpaper}
                    onDelete={handleDelete}
                />
            )}
        </section>
    )
}
