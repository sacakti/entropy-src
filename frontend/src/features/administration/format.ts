export function formatDate(value: string | null): string {
    if (!value) return '—'

    // Server timestamps are UTC without a zone suffix.
    const date = new Date(/[zZ]|[+-]\d\d:?\d\d$/.test(value) ? value : `${value}Z`)

    return Number.isNaN(date.getTime())
        ? '—'
        : new Intl.DateTimeFormat(undefined, { dateStyle: 'medium', timeStyle: 'short' }).format(date)
}

export function errorMessage(error: unknown, fallback: string): string {
    return error instanceof Error ? error.message : fallback
}

/** Same members regardless of order. */
export function sameSet(first: string[], second: string[]): boolean {
    if (first.length !== second.length) return false
    const values = new Set(first)
    return second.every((value) => values.has(value))
}
