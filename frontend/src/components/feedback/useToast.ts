import { useEffect } from 'react'

import { useFeedback } from './FeedbackProvider'

/**
 * Show an error in the side toaster whenever `message` gets a new value,
 * instead of an on-screen banner. Pages keep their error state as before.
 */
export function useErrorToast(message: string | null | undefined | false, title?: string): void {
    const { notify } = useFeedback()
    useEffect(() => {
        if (message) notify.error(message, title ? { title } : undefined)
    }, [message, notify, title])
}

/** The same for a success message. */
export function useSuccessToast(message: string | null | undefined | false, title?: string): void {
    const { notify } = useFeedback()
    useEffect(() => {
        if (message) notify.success(message, title ? { title } : undefined)
    }, [message, notify, title])
}
