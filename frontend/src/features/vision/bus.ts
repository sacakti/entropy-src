import type { NotificationLevel } from '../../api/notifications.api'

/**
 * How Entropy tells you things:
 * - The result of your own action (saved, failed, copied) is a short message: Vision
 *   flashes it, or a toast shows it when Vision is off, hidden by a dialog, or the user
 *   chose classic toasts. It is not stored.
 * - What matters later, or happened without you (run finished, task assigned, upload
 *   done), is a server notification: the bell keeps it, Vision flashes it once.
 * - What everyone must know right now (broadcasts, database switch, active runs) is
 *   Vision's alone.
 */

/** What a module just reported; every short message passes through here. */
export interface VisionEvent {
    level: NotificationLevel
    title: string
    message: string
}

/** The event as Vision receives it: `flash` says whether Vision is the one showing it. */
export interface PublishedVisionEvent extends VisionEvent {
    flash: boolean
}

/** Ask Vision to read its status now, instead of at its next poll. */
export const VISION_REFRESH_EVENT = 'entropy:vision-refresh'

/** Where short messages appear: Vision's island, or the classic toasts. */
export type MessageStyle = 'vision' | 'toasts'

const STYLE_KEY = 'entropy.messages'

/** Dispatched on `window` after the message style changes. */
export const MESSAGE_STYLE_EVENT = 'entropy:message-style'

export function messageStyle(): MessageStyle {
    try {
        return window.localStorage.getItem(STYLE_KEY) === 'toasts' ? 'toasts' : 'vision'
    } catch {
        return 'vision'
    }
}

export function setMessageStyle(style: MessageStyle): void {
    try {
        window.localStorage.setItem(STYLE_KEY, style)
    } catch {
        // Storage may be refused (private windows); Vision stays the default.
    }
    window.dispatchEvent(new Event(MESSAGE_STYLE_EVENT))
}

type Listener = (event: PublishedVisionEvent) => void

const listeners = new Set<Listener>()

/**
 * Tell Vision. Returns true when Vision shows the message itself, so no toast is
 * needed: Vision is on the page, the user keeps the Vision style, and no dialog
 * covers the topbar.
 */
export function publishVision(event: VisionEvent): boolean {
    const flash =
        listeners.size > 0 &&
        messageStyle() === 'vision' &&
        document.querySelector('[aria-modal="true"]') === null
    listeners.forEach((listener) => listener({ ...event, flash }))
    return flash
}

/** Vision on the page listens here; while nobody does, toasts show every message. */
export function subscribeVision(listener: Listener): () => void {
    listeners.add(listener)
    return () => {
        listeners.delete(listener)
    }
}

/**
 * What the island shows while nothing is happening; cosmetic and per browser.
 * Anything to tell (a message, a run, a broadcast) still takes its place.
 */
export type VisionIdle = 'clock' | 'clock-date' | 'greeting' | 'mark'

export interface VisionLook {
    idle: VisionIdle
    /** 12-hour time (3:05 PM) instead of 24-hour (15:05). */
    hour12: boolean
    seconds: boolean
}

const LOOK_KEY = 'entropy.vision.look'
const IDLE_CHOICES: VisionIdle[] = ['clock', 'clock-date', 'greeting', 'mark']
export const DEFAULT_VISION_LOOK: VisionLook = { idle: 'clock-date', hour12: false, seconds: true }

/** Dispatched on `window` after the look changes. */
export const VISION_LOOK_EVENT = 'entropy:vision-look'

export function visionLook(): VisionLook {
    try {
        const stored: unknown = JSON.parse(window.localStorage.getItem(LOOK_KEY) ?? 'null')
        if (!stored || typeof stored !== 'object') return DEFAULT_VISION_LOOK
        const value = stored as Partial<VisionLook>
        return {
            idle: IDLE_CHOICES.includes(value.idle as VisionIdle) ? (value.idle as VisionIdle) : DEFAULT_VISION_LOOK.idle,
            hour12: value.hour12 === true,
            seconds: typeof value.seconds === 'boolean' ? value.seconds : DEFAULT_VISION_LOOK.seconds,
        }
    } catch {
        return DEFAULT_VISION_LOOK
    }
}

export function setVisionLook(look: VisionLook): void {
    try {
        window.localStorage.setItem(LOOK_KEY, JSON.stringify(look))
    } catch {
        // Storage may be refused (private windows); the look lasts until reload.
    }
    window.dispatchEvent(new Event(VISION_LOOK_EVENT))
}
