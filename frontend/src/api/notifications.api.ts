import { apiRequest } from '../services/api'

export type NotificationLevel = 'info' | 'success' | 'warning' | 'error'

export interface AppNotification {
    id: number
    title: string
    message: string
    level: NotificationLevel
    source: string | null
    read: boolean
    /** ISO time in UTC. */
    created_at: string
}

const BASE = '/api/notifications'

export const notificationsApi = {
    list: () => apiRequest<{ items: AppNotification[]; unread: number }>(BASE),
    create: (notification: {
        title: string
        message?: string
        level?: NotificationLevel
        source?: string
    }) =>
        apiRequest<AppNotification>(BASE, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(notification),
        }),
    markRead: (id: number) => apiRequest<unknown>(`${BASE}/${id}/read`, { method: 'POST' }),
    markAllRead: () => apiRequest<unknown>(`${BASE}/read`, { method: 'POST' }),
    remove: (id: number) => apiRequest<unknown>(`${BASE}/${id}`, { method: 'DELETE' }),
    clear: () => apiRequest<unknown>(BASE, { method: 'DELETE' }),
}
