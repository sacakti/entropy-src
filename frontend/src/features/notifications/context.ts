import { createContext, useContext } from 'react'

import type { NotificationLevel } from '../../api/notifications.api'

export interface NotifyInput {
    title: string
    message?: string
    level?: NotificationLevel
    source?: string
}

/** Record an entry in the user's notification center (stored on the server). */
export const NotificationCenterContext = createContext<(input: NotifyInput) => void>(() => undefined)

export function useNotificationCenter() {
    return useContext(NotificationCenterContext)
}
