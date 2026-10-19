import { useCallback, useEffect, useRef, useState } from 'react'

import { notificationsApi, type AppNotification } from '../../api/notifications.api'
import type { NotifyInput } from './context'

const POLL_MS = 20_000

/** Server-backed notification center state, refreshed by polling and on focus. */
export function useNotifications() {
    const [items, setItems] = useState<AppNotification[]>([])
    const inFlight = useRef(false)

    const refresh = useCallback(async () => {
        if (inFlight.current) return
        inFlight.current = true

        try {
            setItems((await notificationsApi.list()).items)
        } catch {
            // Older servers lack the API; the center simply stays empty.
        } finally {
            inFlight.current = false
        }
    }, [])

    useEffect(() => {
        const first = window.setTimeout(() => void refresh(), 0)
        const timer = window.setInterval(() => void refresh(), POLL_MS)
        const onFocus = () => void refresh()
        window.addEventListener('focus', onFocus)

        return () => {
            window.clearTimeout(first)
            window.clearInterval(timer)
            window.removeEventListener('focus', onFocus)
        }
    }, [refresh])

    const push = useCallback(
        (input: NotifyInput) => {
            notificationsApi
                .create(input)
                .then((created) => setItems((current) => [created, ...current]))
                .catch(() => undefined)
        },
        [],
    )

    const markRead = useCallback((id: number) => {
        setItems((current) => current.map((item) => (item.id === id ? { ...item, read: true } : item)))
        void notificationsApi.markRead(id).catch(() => refresh())
    }, [refresh])

    const markAllRead = useCallback(() => {
        setItems((current) => current.map((item) => ({ ...item, read: true })))
        void notificationsApi.markAllRead().catch(() => refresh())
    }, [refresh])

    const remove = useCallback((id: number) => {
        setItems((current) => current.filter((item) => item.id !== id))
        void notificationsApi.remove(id).catch(() => refresh())
    }, [refresh])

    const clear = useCallback(() => {
        setItems([])
        void notificationsApi.clear().catch(() => refresh())
    }, [refresh])

    return { items, push, markRead, markAllRead, remove, clear, refresh }
}
