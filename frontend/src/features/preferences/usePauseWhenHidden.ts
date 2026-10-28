import { useEffect, type RefObject } from 'react'

/**
 * Pause a video while the browser tab is hidden (another tab, minimized) and
 * resume it when the tab is shown again, if it was playing. Saves decoding,
 * battery and, for videos still streaming, network.
 */
export function usePauseWhenHidden(video: RefObject<HTMLVideoElement | null>) {
    useEffect(() => {
        let resume = false
        const onVisibility = () => {
            const element = video.current
            if (!element) return
            if (document.hidden) {
                resume = !element.paused
                element.pause()
            } else if (resume) {
                resume = false
                void element.play().catch(() => undefined)
            }
        }
        document.addEventListener('visibilitychange', onVisibility)
        return () => document.removeEventListener('visibilitychange', onVisibility)
    }, [video])
}
