import { useEffect, useState } from 'react'
import { Shuffle, X } from 'lucide-react'

import { isVideoBackground, type BackgroundImage } from '../../api/backgrounds.api'
import type { WallpaperMemories as MemoriesSettings } from '../../api/preferences.api'
import AppPortal from '../../components/layout/AppPortal'

function randomIndex(length: number, current = -1): number {
    if (length < 2) return 0
    const choices = Array.from({ length }, (_, index) => index).filter((index) => index !== current)
    return choices[Math.floor(Math.random() * choices.length)]
}

export default function Memories({
    backgrounds,
    onClose,
    animation = 'fade',
}: {
    backgrounds: BackgroundImage[]
    onClose: () => void
    animation?: MemoriesSettings['animation']
}) {
    const [index, setIndex] = useState(() => randomIndex(backgrounds.length))
    const background = backgrounds[index]

    useEffect(() => {
        const onKeyDown = (event: KeyboardEvent) => {
            if (event.key === 'Escape') onClose()
        }
        window.addEventListener('keydown', onKeyDown)
        return () => window.removeEventListener('keydown', onKeyDown)
    }, [onClose])

    if (!background) return null

    return (
        <AppPortal>
            <section className="wallpaper-memories" role="dialog" aria-modal="true" aria-label="Wallpaper memories">
                <div className={`wallpaper-memories-media is-${animation}`} key={background.id}>
                    {isVideoBackground(background) ? (
                        <video src={background.url} autoPlay muted loop controls playsInline />
                    ) : (
                        <img src={background.url} alt={background.name} />
                    )}
                </div>
                <header className="wallpaper-memories-header">
                    <div>
                        <strong>Memories</strong>
                        <span>{background.name}</span>
                    </div>
                    <div>
                        <button
                            type="button"
                            className="entropy-button entropy-button-secondary"
                            onClick={() => setIndex((current) => randomIndex(backgrounds.length, current))}
                        >
                            <Shuffle size={15} />
                            Another memory
                        </button>
                        <button
                            type="button"
                            className="entropy-button entropy-button-secondary entropy-button-icon"
                            aria-label="Close memories"
                            title="Close"
                            onClick={onClose}
                        >
                            <X size={17} />
                        </button>
                    </div>
                </header>
            </section>
        </AppPortal>
    )
}
