import { dateTimeFormat } from '../../services/timezone'

/** "just now", "5 min ago", "3 h ago", then a date. */
export function relativeTime(value: string): string {
    const time = new Date(value).getTime()

    if (Number.isNaN(time)) return ''

    const minutes = Math.round((Date.now() - time) / 60_000)

    if (minutes < 1) return 'just now'
    if (minutes < 60) return `${minutes} min ago`
    if (minutes < 24 * 60) return `${Math.round(minutes / 60)} h ago`

    return dateTimeFormat({ dateStyle: 'medium', timeStyle: 'short' }).format(time)
}
