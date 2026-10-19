import { useContext, useState, type CSSProperties } from 'react'

import { isVideoBackground, type BackgroundImage } from '../../api/backgrounds.api'
import { WallpaperContext, isPortrait, placementStyle } from './wallpaper'

function WallpaperMedia({
    background,
    className,
    style,
    onMeasure,
}: {
    background: BackgroundImage
    className: string
    style?: CSSProperties
    onMeasure?: (width: number, height: number) => void
}) {
    if (isVideoBackground(background)) {
        return (
            <video
                className={className}
                style={style}
                src={background.url}
                autoPlay
                muted
                loop
                playsInline
                aria-hidden="true"
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
            alt=""
            aria-hidden="true"
            onLoad={(event) =>
                onMeasure?.(event.currentTarget.naturalWidth, event.currentTarget.naturalHeight)
            }
        />
    )
}

/**
 * The user's wallpaper as a decorative layer. Place it first inside a
 * positioned, isolated container; it sits behind the container's content.
 *
 * Phone-shaped wallpapers without a custom placement fit automatically:
 * shown whole, over a blurred copy that fills the space.
 */
export default function WallpaperLayer({
    className,
    veil,
}: {
    className?: string
    /**
     * Tint drawn over the wallpaper at the overlay solidity, so full-screen
     * views stay readable while following the modal backdrop preference.
     */
    veil?: string
}) {
    const state = useContext(WallpaperContext)
    const [measured, setMeasured] = useState<{ url: string; portrait: boolean } | null>(null)

    if (!state?.background) return null

    const { background, fit, opacity, placement } = state
    const portrait = measured?.url === background.url && measured.portrait
    const autoFit = !placement && portrait

    const mediaStyle: CSSProperties = placement
        ? placementStyle(placement)
        : { objectFit: autoFit ? 'contain' : fit === 'fill' ? 'fill' : fit }

    return (
        <div
            className={['wallpaper-layer', className].filter(Boolean).join(' ')}
            aria-hidden="true"
        >
            <div className="wallpaper-layer-media" style={{ opacity }}>
                {autoFit && (
                    <WallpaperMedia
                        key={`blur-${background.id}`}
                        background={background}
                        className="wallpaper-media wallpaper-media-blur"
                    />
                )}
                <WallpaperMedia
                    key={background.id}
                    background={background}
                    className="wallpaper-media"
                    style={mediaStyle}
                    onMeasure={(width, height) =>
                        setMeasured({ url: background.url, portrait: isPortrait(width, height) })
                    }
                />
            </div>
            {veil && (
                <span
                    className="wallpaper-veil"
                    style={{ '--wallpaper-veil': veil } as CSSProperties}
                />
            )}
        </div>
    )
}
