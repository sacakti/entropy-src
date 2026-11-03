/** Dates and repeats for the due date and reminder pickers. Dates are `YYYY-MM-DD`, local. */

export type Schedule = { date: string; time: string; repeat: string }

export const REPEATS: { id: string; label: string }[] = [
    { id: '', label: 'Does not repeat' },
    { id: 'daily', label: 'Every day' },
    { id: 'weekdays', label: 'Every weekday (Mon–Fri)' },
    { id: 'weekly', label: 'Every week' },
    { id: 'monthly', label: 'Every month' },
    { id: 'yearly', label: 'Every year' },
]

const pad = (value: number) => String(value).padStart(2, '0')

export const toIso = (date: Date) => `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`

/** Noon, so a daylight-saving change can never move it to another day. */
export function parseIso(value: string): Date {
    const [year, month, day] = value.split('-').map(Number)
    return new Date(year, month - 1, day, 12)
}

export function addDays(value: string, days: number): string {
    const date = parseIso(value)
    date.setDate(date.getDate() + days)
    return toIso(date)
}

/** The same day in another month, or that month's last day if it is shorter. */
export function addMonths(value: string, months: number): string {
    const date = parseIso(value)
    const day = date.getDate()
    date.setDate(1)
    date.setMonth(date.getMonth() + months)
    const last = new Date(date.getFullYear(), date.getMonth() + 1, 0).getDate()
    date.setDate(Math.min(day, last))
    return toIso(date)
}

/** The first day of the week here: 0 is Sunday. Monday where the browser cannot say. */
export function firstDayOfWeek(locale: string): number {
    try {
        const info = new Intl.Locale(locale) as Intl.Locale & {
            getWeekInfo?: () => { firstDay: number }
            weekInfo?: { firstDay: number }
        }
        const firstDay = (info.getWeekInfo?.() ?? info.weekInfo)?.firstDay
        return firstDay === undefined ? 1 : firstDay % 7
    } catch {
        return 1
    }
}

/** Six weeks around the month of `value`, so the grid never changes height between months. */
export function monthGrid(value: string, firstDay: number): string[] {
    const start = parseIso(`${value.slice(0, 7)}-01`)
    const back = (start.getDay() - firstDay + 7) % 7
    const first = addDays(toIso(start), -back)
    return Array.from({ length: 42 }, (_, index) => addDays(first, index))
}

/** The start of the week `value` is in. */
export function weekStart(value: string, firstDay: number): string {
    return addDays(value, -((parseIso(value).getDay() - firstDay + 7) % 7))
}

/** The next `weekday` (0 is Sunday) strictly after `value`. */
export function nextWeekday(value: string, weekday: number): string {
    const gap = (weekday - parseIso(value).getDay() + 7) % 7
    return addDays(value, gap === 0 ? 7 : gap)
}

export function isPastDue(date: string | null | undefined, time: string | null | undefined, now = new Date()): boolean {
    if (!date) return false
    const today = toIso(now)
    if (date !== today) return date < today
    return Boolean(time) && (time as string) < `${pad(now.getHours())}:${pad(now.getMinutes())}`
}

export function dateLabel(value: string, today: string, locale?: string): string {
    const date = parseIso(value)
    const text = date.toLocaleDateString(locale, {
        weekday: 'short',
        day: 'numeric',
        month: 'short',
        ...(value.slice(0, 4) === today.slice(0, 4) ? {} : { year: 'numeric' }),
    })
    if (value === today) return `Today · ${text}`
    if (value === addDays(today, 1)) return `Tomorrow · ${text}`
    if (value === addDays(today, -1)) return `Yesterday · ${text}`
    return text
}

/** In words, for the reader: "Every week on Monday". */
export function repeatLabel(repeat: string, date: string, locale?: string): string {
    if (!repeat) return ''
    if (!date) return REPEATS.find((item) => item.id === repeat)?.label ?? repeat
    const day = parseIso(date)
    if (repeat === 'weekly') return `Every week on ${day.toLocaleDateString(locale, { weekday: 'long' })}`
    if (repeat === 'monthly') return `Every month on day ${day.getDate()}`
    if (repeat === 'yearly') return `Every year on ${day.toLocaleDateString(locale, { day: 'numeric', month: 'long' })}`
    return REPEATS.find((item) => item.id === repeat)?.label ?? repeat
}

/** A reminder is one local date and time in the task: split it for the picker. */
export function fromLocal(value: string, repeat: string): Schedule {
    return { date: value.slice(0, 10), time: value.slice(11, 16), repeat }
}

export function toLocal(schedule: Schedule): string {
    return schedule.date ? `${schedule.date}T${schedule.time || '09:00'}` : ''
}
