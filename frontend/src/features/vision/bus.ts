import type { NotificationLevel } from '../../api/notifications.api'

/** What a module just reported; every toast passes through here. */
export interface VisionEvent {
    level: NotificationLevel
    title: string
    message: string
}

/** Ask Vision to read its status now, instead of at its next poll. */
export const VISION_REFRESH_EVENT = 'entropy:vision-refresh'

type Listener = (event: VisionEvent) => void

const listeners = new Set<Listener>()

/** Tell Vision; nothing happens while it is off or not on the page. */
export function publishVision(event: VisionEvent): void {
    listeners.forEach((listener) => listener(event))
}

export function subscribeVision(listener: Listener): () => void {
    listeners.add(listener)
    return () => {
        listeners.delete(listener)
    }
}
