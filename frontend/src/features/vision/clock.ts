import { useEffect, useState } from 'react'

import { visionLook, VISION_LOOK_EVENT, type VisionLook } from './bus'
import { dateTimeFormat, localeDateString, localeTimeString, zonedClock } from '../../services/timezone'

/** The chosen look, following changes made in Preferences (in this or another tab). */
export function useVisionLook(): VisionLook {
    const [look, setLook] = useState<VisionLook>(visionLook)
    useEffect(() => {
        const update = () => setLook(visionLook())
        const onStorage = (event: StorageEvent) => {
            if (event.key === null || event.key === 'entropy.vision.look') update()
        }
        window.addEventListener(VISION_LOOK_EVENT, update)
        window.addEventListener('storage', onStorage)
        return () => {
            window.removeEventListener(VISION_LOOK_EVENT, update)
            window.removeEventListener('storage', onStorage)
        }
    }, [])
    return look
}

/** The time now, ticking once a second while `active`; paused otherwise. */
export function useNow(active: boolean): Date {
    const [now, setNow] = useState(() => new Date())
    useEffect(() => {
        if (!active) return
        let timer: number | undefined
        // Tick on the second, so the digits change with the second hand.
        const tick = () => {
            setNow(new Date())
            timer = window.setTimeout(tick, 1000 - (Date.now() % 1000) + 5)
        }
        tick()
        return () => window.clearTimeout(timer)
    }, [active])
    return now
}

function clockFormat(look: VisionLook): Intl.DateTimeFormatOptions {
    return {
        hour: look.hour12 ? 'numeric' : '2-digit',
        minute: '2-digit',
        second: look.seconds ? '2-digit' : undefined,
        hour12: look.hour12,
    }
}

export function formatClock(now: Date, look: VisionLook): string {
    return localeTimeString(now, clockFormat(look))
}

/**
 * The time in pieces, so one separator can blink: `separator` marks the one before
 * the seconds (the second ":" of 20:31:05), in the user's own format.
 */
export function clockParts(now: Date, look: VisionLook): { text: string; separator: boolean }[] {
    return dateTimeFormat(clockFormat(look))
        .formatToParts(now)
        .map((part, index, parts) => ({
            text: part.value,
            separator: part.type === 'literal' && parts[index + 1]?.type === 'second',
        }))
}

export function formatDay(now: Date): string {
    return localeDateString(now, { weekday: 'short', day: 'numeric', month: 'short' })
}

export function greeting(now: Date): string {
    const hour = zonedClock(now).hours
    return hour < 5 ? 'Good night' : hour < 12 ? 'Good morning' : hour < 18 ? 'Good afternoon' : 'Good evening'
}
