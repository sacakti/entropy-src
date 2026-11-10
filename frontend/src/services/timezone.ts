/**
 * The time zone times are shown in: the user's own (Settings), else the
 * installation's (Administration -> Settings), else the server's. The profile
 * carries the resolved zone; until it loads, times show in the browser's zone.
 *
 * Use these helpers instead of `Date#toLocaleString` and friends so every
 * screen follows the setting. Calendar dates without a time (a due date such
 * as 2026-11-10) are not instants and keep using the browser's methods.
 */

let zone: string | undefined

function supported(name: string): boolean {
    try {
        new Intl.DateTimeFormat(undefined, { timeZone: name })
        return true
    } catch {
        return false
    }
}

/** Set by the shell from the profile; an unknown or empty zone means the browser's. */
export function setDisplayTimeZone(name: string | null | undefined): void {
    zone = name && supported(name) ? name : undefined
}

/** The zone times are shown in, as an IANA name. */
export function displayTimeZone(): string {
    if (zone) return zone
    try {
        return Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC'
    } catch {
        return 'UTC'
    }
}

const withZone = (options?: Intl.DateTimeFormatOptions): Intl.DateTimeFormatOptions => ({ ...options, timeZone: zone })

/** `new Intl.DateTimeFormat(locale, options)` in the display zone. */
export function dateTimeFormat(options?: Intl.DateTimeFormatOptions, locale?: Intl.LocalesArgument): Intl.DateTimeFormat {
    return new Intl.DateTimeFormat(locale as string | string[] | undefined, withZone(options))
}

/** `date.toLocaleString(locale, options)` in the display zone. */
export function localeString(date: Date | string | number, options?: Intl.DateTimeFormatOptions, locale?: Intl.LocalesArgument): string {
    return new Date(date).toLocaleString(locale, withZone(options))
}

/** `date.toLocaleDateString(locale, options)` in the display zone. */
export function localeDateString(date: Date | string | number, options?: Intl.DateTimeFormatOptions, locale?: Intl.LocalesArgument): string {
    return new Date(date).toLocaleDateString(locale, withZone(options))
}

/** `date.toLocaleTimeString(locale, options)` in the display zone. */
export function localeTimeString(date: Date | string | number, options?: Intl.DateTimeFormatOptions, locale?: Intl.LocalesArgument): string {
    return new Date(date).toLocaleTimeString(locale, withZone(options))
}

/** Every zone the browser knows, with `current` and UTC first, for a picker. */
export function timeZoneNames(current?: string): string[] {
    const intl = Intl as unknown as { supportedValuesOf?: (key: string) => string[] }
    const zones = intl.supportedValuesOf?.('timeZone') ?? []
    return Array.from(new Set(['UTC', ...(current ? [current] : []), ...zones]))
}

/** Hours (0-23), minutes and seconds of `date` on the clock in the display zone. */
export function zonedClock(date: Date): { hours: number; minutes: number; seconds: number } {
    const parts = dateTimeFormat({ hour: '2-digit', minute: '2-digit', second: '2-digit', hourCycle: 'h23' }, 'en-US').formatToParts(date)
    const part = (type: Intl.DateTimeFormatPartTypes) => Number(parts.find((item) => item.type === type)?.value ?? 0)
    return { hours: part('hour') % 24, minutes: part('minute'), seconds: part('second') }
}
