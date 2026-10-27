import { useCallback, useEffect, useRef, useState } from 'react'

import { ApiError } from '../../../services/api'

/** What every widget receives from the dashboard. */
export interface WidgetProps<S = Record<string, unknown>> {
    settings: S
    /** Changes on every automatic refresh. */
    tick: number
    /** Changes when the user asks for a refresh (always reloads). */
    force: number
}

/** Open a tool of the Tools menu, as its card in the gallery does. */
export function openTool(id: string): void {
    window.history.pushState(null, '', `#/tools/${id}`)
    window.dispatchEvent(new PopStateEvent('popstate'))
}

const shared = new Map<string, { at: number; promise: Promise<unknown> }>()

/**
 * One request for widgets that read the same data (the run widgets share
 * /api/dashboard): a call within `maxAge` ms gets the pending/last answer.
 */
export function sharedRequest<T>(key: string, load: () => Promise<T>, maxAge = 1500): Promise<T> {
    const hit = shared.get(key)
    if (hit && Date.now() - hit.at < maxAge) return hit.promise as Promise<T>
    const promise = load()
    shared.set(key, { at: Date.now(), promise })
    promise.catch(() => shared.delete(key))
    return promise
}

export type WidgetState<T> = {
    data: T | null
    error: string | null
    /** The user may not use this tool in the current project. */
    denied: boolean
    loading: boolean
    reload: () => void
}

/**
 * Load a widget's data, again on refresh ticks (at most every `minInterval`
 * ms, so tool data is not fetched every few seconds) and on manual refresh.
 */
export function useWidgetData<T>(
    load: () => Promise<T>,
    { tick, force }: { tick: number; force: number },
    minInterval = 0,
    deps: unknown[] = [],
): WidgetState<T> {
    const [data, setData] = useState<T | null>(null)
    const [error, setError] = useState<string | null>(null)
    const [denied, setDenied] = useState(false)
    const [loading, setLoading] = useState(true)
    const loaded = useRef(0)
    const loadRef = useRef(load)
    useEffect(() => {
        loadRef.current = load
    })

    const run = useCallback(() => {
        loaded.current = Date.now()
        loadRef
            .current()
            .then((result) => {
                setData(result)
                setError(null)
                setDenied(false)
            })
            .catch((cause: unknown) => {
                if (cause instanceof ApiError && cause.status === 403) setDenied(true)
                else setError(cause instanceof Error ? cause.message : 'Unable to load.')
            })
            .finally(() => setLoading(false))
    }, [])

    // First load, manual refresh and settings changes.
    useEffect(() => {
        run()
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [run, force, ...deps])

    useEffect(() => {
        if (tick === 0 || Date.now() - loaded.current < minInterval) return
        run()
    }, [tick, minInterval, run])

    return { data, error, denied, loading, reload: run }
}

export function formatWhen(value: string | null | undefined): string {
    if (!value) return '—'
    const date = new Date(value)
    if (Number.isNaN(date.getTime())) return '—'
    const diff = date.getTime() - Date.now()
    const minutes = Math.round(diff / 60000)
    const format = new Intl.RelativeTimeFormat(undefined, { numeric: 'auto' })
    if (Math.abs(minutes) < 60) return format.format(minutes, 'minute')
    const hours = Math.round(minutes / 60)
    if (Math.abs(hours) < 24) return format.format(hours, 'hour')
    const days = Math.round(hours / 24)
    if (Math.abs(days) < 7) return format.format(days, 'day')
    return new Intl.DateTimeFormat(undefined, { dateStyle: 'medium' }).format(date)
}

export function formatBytes(value: number): string {
    if (value < 1024) return `${value} B`
    const units = ['KB', 'MB', 'GB', 'TB']
    let size = value / 1024
    let unit = 0
    while (size >= 1024 && unit < units.length - 1) {
        size /= 1024
        unit += 1
    }
    return `${size.toFixed(size < 10 ? 1 : 0)} ${units[unit]}`
}

export function limitOf(settings: Record<string, unknown>, fallback = 6): number {
    const value = Number(settings.limit)
    return Number.isInteger(value) && value > 0 ? Math.min(value, 50) : fallback
}
